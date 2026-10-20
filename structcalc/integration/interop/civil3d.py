# -*- coding: utf-8 -*-
"""
integration/interop/civil3d.py — Connecteur Civil 3D (héberge AutoCAD).

Vérité (sonde Phase interop, spec §19) — CORRIGÉE d'après l'inventaire COM
complet (tools/probe_civil3d_nw_com.py + tools/probe_autodesk_all_com.py) :
  - Civil 3D 2027 INSTALLÉ (clé désinstallation + HKLM\\SOFTWARE\\Autodesk).
  - DES ProgIDs `AeccX*` EXISTENT bel et bien dans le registre (contre un
    diagnostic initial erroné qui les déclarait absents — le premier scan
    exigeait le préfixe exact « Aecc. » et ratait « AeccX... ») :
        AeccXUiLand.AeccApplication.13.9   CLSID {E933000F-...}
        AeccXUiLand.AeccDocument.13.9      CLSID {E9330011-...}
        AeccXUiPipe.AeccPipeApplication.13.9
      -> serveur InprocServer32 (AeccXUiLand.dll, .NET, Apartment) dans
         AutoCAD 2027\\C3D\\.
  - MAIS ces serveurs Inproc N'ARRIVENT PAS à s'activer depuis un processus
    externe : échec 0x8007007E « module spécifié introuvable », y compris en
    ajoutant C3D\\ et la racine AutoCAD à la recherche de DLL (os.add_dll_directory).
    Ils exigent le CONTEXTE en-processus Civil 3D (add-in .NET) — hors portée
    d'une automation COM externe. HONNÊTEMENT : inactivables ici.
  - Civil 3D est un VERTICAL AutoCAD : il tourne sur le MÊME hôte `acad.exe`
    et le même ProgID `AutoCAD.Application`. Tout dessin Civil 3D est donc
    accessible au niveau DESSIN (DWG) via le COM AutoCAD VÉRIFIÉ.
  - Les OBJETS INTELLIGENTS Civil 3D (alignements, surfaces, corridors,
    réseaux, profilés...) sont des objets propriétaires stockés dans le DWG
    mais lisibles/seuls modifiables via l'API .NET (AeccDb / ObjectARX) :
    NON activable ici (cf. ci-dessus) -> refus EXPLICITE.

Conséquence pour l'interopérabilité :
  - DWG de niveau dessin (entités, calques, blocs)  -> AUTOCAD (VÉRIFIÉ)
  - objets Civil 3D intelligents                    -> REFUS motivé (.NET)

Ce connecteur expose les capacités de dessin (héritées d'AutoCAD) en marquant
très clairement que la SEMANTIQUE Civil 3D n'est pas portée sans add-in .NET.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ..interop.base import (
    Capability, CapabilityReport, CapabilityStatus, Detection, OpReport,
)
from .autocad import AutoCADConnector

# ProgIDs Civil 3D RÉELLEMENT présents (probe_civil3d_nw_com.py) : serveurs
# Inproc (AeccXUiLand.dll, .NET) MAIS inactivables depuis un processus externe
# (0x8007007E même avec os.add_dll_directory sur C3D\\ + racine AutoCAD).
# On les documente pour traçabilité : leur existence est CONFIRMÉE au registre,
# leur activation EXTERNE est IMPOSSIBLE (contexte en-processus Civil 3D requis).
AECX_PROGIDS = (
    "AeccXUiLand.AeccApplication.13.9",
    "AeccXUiLand.AeccDocument.13.9",
    "AeccXUiPipe.AeccPipeApplication.13.9",
)
# Motif d'échec d'activation externe observé (module non résolvable hors C3D)
AECX_ACTIVATION_ERROR = "0x8007007E (module introuvable hors processus Civil 3D)"


class Civil3DConnector(AutoCADConnector):
    """
    Pont Civil 3D <-> pivot SC-*.

    Hérite des opérations DWG VÉRIFIÉES d'AutoCAD (même hôte COM), et ajoute :
      - détection spécifique Civil 3D (installée, pas de ProgID Aecc) ;
      - refus explicite des objets intelligents Civil 3D (.NET requis).
    """

    name = "civil3d"
    label = "Autodesk Civil 3D"

    # Les ProgIDs de l'hôte sont ceux d'AutoCAD (même acad.exe)
    CIVIL_REG_HINTS = ("Autodesk Civil 3D", "Aecc")

    def __init__(self, attach_only: bool = False, saveas_code: int = 24):
        super().__init__(attach_only=attach_only, saveas_code=saveas_code)

    # ------------------------------------------------------------------
    # Détection : installation Civil 3D + hôte COM AutoCAD
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        installed = False
        version = ""
        families: List[str] = []
        try:
            import winreg
            # 1) FAMILLES Autodesk présentes
            try:
                k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                   r"SOFTWARE\Autodesk")
                i = 0
                while True:
                    try:
                        families.append(winreg.EnumKey(k, i))
                    except OSError:
                        break
                    i += 1
                k.Close()
            except OSError:
                pass
            # 2) Produits désinstallés (plus fiable pour la version)
            for root in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                         r"SOFTWARE\WOW6432Node\Microsoft\Windows"
                         r"\CurrentVersion\Uninstall"):
                try:
                    uk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
                except OSError:
                    continue
                j = 0
                while True:
                    try:
                        sub = winreg.EnumKey(uk, j)
                    except OSError:
                        break
                    j += 1
                    try:
                        sk = winreg.OpenKey(uk, sub)
                        disp = winreg.QueryValueEx(sk, "DisplayName")[0]
                        sk.Close()
                    except (OSError, FileNotFoundError):
                        continue
                    if isinstance(disp, str) and "Civil 3D" in disp:
                        installed = True
                        for w in disp.split():
                            if w.isdigit() and len(w) == 4:
                                version = w
                uk.Close()
        except ImportError:  # pragma: no cover
            return Detection(name=self.name, installed=False, transport="com",
                             automatable=False,
                             detail="winreg indisponible (non-Windows)")

        # Hôte COM : celui d'AutoCAD (vérifié : acad.exe commun)
        host = super().detect()

        return Detection(
            name=self.name, installed=installed or host.installed,
            version=version or host.version,
            progs=list(host.progs),        # ProgIDs = AutoCAD (même hôte)
            transport="com" if host.progs else "none",
            automatable=bool(host.progs),  # dessin seulement, pas .NET
            detail=("Hôte COM AutoCAD partagé (acad.exe) : accès DWG de "
                    "niveau dessin OK ; objets intelligents Civil 3D = "
                    ".NET non disponible (§19)."
                    if host.progs else
                    "Hôte COM AutoCAD introuvable"),
        )

    # ------------------------------------------------------------------
    # Capacités : dessin OK (hérité) / objets Civil 3D refusés
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        caps = super().capabilities()   # base AutoCAD VÉRIFIÉE
        note_dwg = " (via hôte AutoCAD, DWG de niveau dessin)"
        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Registre produit Civil 3D + hôte COM AutoCAD"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.SUPPORTED,
                "Session COM via AutoCAD.Application (acad.exe partagé)"),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.PARTIAL,
                "Lecture des entités DWG/calques seulement ; OBJETS "
                "INTELLIGENTS Civil 3D (alignements, surfaces, corridors, "
                "réseaux) REFUSÉS : API .NET requise (§19)"),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.PARTIAL,
                "Écriture DWG de niveau dessin seulement ; objets Civil 3D "
                "intelligents REFUSÉS : API .NET requise (§19)"),
            Capability.READ_RESULTS: caps[Capability.READ_RESULTS],
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.NOT_SUPPORTED,
                "Charges Civil 3D (charges de trafic, sols) = .NET "
                "non exposé en COM ici (§19)"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.PARTIAL,
                "Calques/entités DWG lus ; annotations/textes et styles "
                "Civil 3D non garantis (§19)"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.PARTIAL,
                "Géométrie + calques + SaveAs DWG (hérité AutoCAD vérifié) ; "
                "textes et styles Civil 3D non supportés"),
        }

    # ------------------------------------------------------------------
    # Ponts : le dessin marche (hérité), la SEMANTIQUE est refusée
    # ------------------------------------------------------------------
    def read_model(self, project: Any) -> OpReport:
        """
        Lit le DWG au niveau dessin, puis signale ce qui est hors périmètre.

        Les objets intelligents Civil 3D ne sont PAS lus (impossible sans
        .NET) : ils sont COMPTE rapportés comme ignorés, jamais inventés.
        """
        rep = super().read_model(project)
        # Enrichit le rapport : la sémantique Civil 3D n'est pas portée
        extra = (" | objets intelligents Civil 3D (alignements, surfaces, "
                 "corridors, réseaux) NON lus — API .NET requise (§19)")
        rep.message = (rep.message or "") + extra
        rep.objects.setdefault("civil3d_intelligent_skipped", -1)  # inconnu
        return rep

    def write_model(self, project: Any) -> OpReport:
        """
        Écrit la géométrie SC-* en DWG (hérité AutoCAD vérifié).

        Aucun objet intelligent Civil 3D n'est créé (impossible sans .NET) :
        le rapport le dit explicitement.
        """
        rep = super().write_model(project)
        extra = (" | écriture DWG de niveau dessin uniquement : aucun objet "
                 "intelligent Civil 3D créé (API .NET requise, §19)")
        rep.message = (rep.message or "") + extra
        return rep

    # Refus explicite des opérations .NET (pas d'API inventée, §19)
    def read_civil_objects(self) -> OpReport:
        """Alignements/surfaces/corridors/réseaux : REFUS motivé."""
        return OpReport(
            "read_civil_objects", "NOT_IMPLEMENTED", source=self.name,
            message=("[civil3d] objets intelligents Civil 3D REFUSÉS : "
                     "nécessitent l'API .NET (AeccDb/ObjectARX). Les ProgIDs "
                     f"Civil 3D ({', '.join(AECX_PROGIDS)}) EXISTENT au "
                     "registre mais échouent à l'activation externe "
                     f"({AECX_ACTIVATION_ERROR}) : add-in .NET en-processus "
                     "requis. Aucun objet lu — §19."))

    def write_civil_objects(self) -> OpReport:
        return OpReport(
            "write_civil_objects", "NOT_IMPLEMENTED", source=self.name,
            message=("[civil3d] création d'objets intelligents Civil 3D "
                     "REFUSÉE : API .NET requise (§19). Aucun objet écrit."))
