# -*- coding: utf-8 -*-
"""
integration/revit/connection.py — Connexion Revit (spec §6, §7.3).

ANALYSE Phase 0 (audité) :
  - Revit 2027 installé ; API .NET (RevitAPI.dll, RevitAPIUI.dll) présente.
  - AUCUN ProgID COM complet comme Robot. Revit n'est pas pilotable en COM
    pour l'accès au modèle (règle §6.3 : ne pas tenter de piloter l'API Revit
    comme une bibliothèque Python sans respecter son environnement .NET).

Voies d'intégration (spec §6.2, dans l'ordre de préférence) :
  1. Intégration native Revit–Robot (à privilégier si elle couvre le besoin).
  2. Fichiers intermédiaires (SMXX) si versions compatibles.
  3. Extension Revit .NET (add-in) — seule voie pour un accès programmatique
     profond au modèle BIM.
  4. Échange structuré interne documenté.

Ce module fournit un connecteur qui :
  - détecte l'installation et la version ;
  - ouvre Revit avec un fichier si demandé (processus, pas COM modèle) ;
  - signale EXPLICITEMENT que l'accès au modèle exige un add-in .NET.

Il ne prétend JAMAIS lire/écrire des éléments BIM sans add-in (spec §19).
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional


class RevitConnectionError(Exception):
    """Erreur / limitation du connecteur Revit."""


class RevitConnection:
    """
    Connecteur Revit — honnête sur ses limites (spec §6, §19).

    Usage :
        rc = RevitConnection()
        print(rc.compatibility())          # fiche de compatibilité
        rc.launch_with_file("projet.rvt")  # ouvre Revit (processus)
    """

    # Chemins candidats Revit 2027 (audité Phase 0)
    EXE_CANDIDATES = [
        r"C:\Program Files\Autodesk\Revit 2027\Revit.exe",
    ]

    def __init__(self, exe_path: Optional[str] = None):
        self.exe_path = exe_path or self._find_exe()
        self._process: Optional[subprocess.Popen] = None

    @classmethod
    def _find_exe(cls) -> Optional[str]:
        for p in cls.EXE_CANDIDATES:
            if os.path.isfile(p):
                return p
        return None

    @property
    def is_installed(self) -> bool:
        return self.exe_path is not None

    def version(self) -> str:
        """Extrait la version depuis le chemin d'installation."""
        if not self.exe_path:
            return ""
        m = os.path.basename(os.path.dirname(self.exe_path))
        digits = "".join(c for c in m if c.isdigit())
        return digits or m

    # ------------------------------------------------------------------
    # Fiche de compatibilité (spec §6.2, §7.3)
    # ------------------------------------------------------------------
    def compatibility(self) -> dict:
        """
        Fiche de compatibilité Revit (livrable Phase 0/4).

        Indique les objets échangés, la direction, l'API/format, les
        dépendances, la version, les pertes d'information possibles.
        """
        return {
            "logiciel": "Autodesk Revit",
            "version": self.version() or "2027 (non localisé)",
            "installe": self.is_installed,
            "exe": self.exe_path,
            "api": ".NET (RevitAPI.dll / RevitAPIUI.dll)",
            "com_available": False,     # vérifié Phase 0 : pas de COM modèle
            "pilotage_python_direct": False,
            "voies_integration": [
                "1. Intégration native Revit->Robot (à privilégier, §6.2)",
                "2. Fichiers intermédiaires SMXX (si compatibles)",
                "3. Extension Revit .NET (add-in) pour accès profond (§6.3)",
                "4. Échange structuré interne documenté",
            ],
            "objets_echanges_si_addin": [
                "niveaux, axes, poteaux, poutres, dalles, voiles, fondations",
                "matériaux, sections, propriétés",
            ],
            "direction": "import BIM + export modèle analytique (via native/SMXX)",
            "pertes_info_possibles": [
                "conversion analytique vs géométrie architecturale",
                "propriétés non mappées",
                "conventions de coordonnées/axes",
            ],
            "statut": "NON OPÉRATIONNEL pour accès profond sans add-in .NET",
            "verification_requise": (
                "Confirmer la disponibilité de l'intégration native "
                "Revit<->Robot sur 2027 et la compatibilité SMXX (spec §6.2)."
            ),
        }

    # ------------------------------------------------------------------
    # Ouverture (processus, pas COM modèle)
    # ------------------------------------------------------------------
    def launch_with_file(self, rvt_path: str) -> int:
        """
        Ouvre Revit avec un fichier (processus). NE LIT PAS le modèle.

        L'accès programmatique aux éléments exige un add-in .NET (spec §6.3).
        """
        if not self.is_installed:
            raise RevitConnectionError(
                "Revit introuvable. Installez Revit ou spécifiez exe_path.")
        rvt_path = os.path.abspath(rvt_path)
        if not os.path.isfile(rvt_path):
            raise RevitConnectionError(f"Fichier RVT introuvable : {rvt_path}")
        self._process = subprocess.Popen([self.exe_path, rvt_path])
        return self._process.pid

    def model_access_status(self) -> dict:
        """
        Statut d'accès au modèle — EXPLICITEMENT limité sans add-in (§19).
        """
        return {
            "model_readable": False,
            "reason": (
                "Revit n'expose pas d'API COM pour le modèle. La lecture/"
                "écriture des éléments BIM nécessite un add-in .NET "
                "(IRobotCommand / IExternalCommand) — spec §6.3. Aucun add-in "
                "STRUCTCALC n'est actuellement installé."
            ),
            "recommended_path": (
                "Utiliser l'intégration native Revit->Robot pour le transfert "
                "du modèle structurel, ou développer un add-in .NET pont."
            ),
        }

    def close(self):
        """Ferme le processus Revit si on l'a lancé (bas niveau)."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None
