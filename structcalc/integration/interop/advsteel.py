# -*- coding: utf-8 -*-
"""
integration/interop/advsteel.py — Connecteur Advance Steel (héberge AutoCAD).

Vérité (sonde interop, spec §19) — établie par `tools/probe_advsteel.py` +
`tools/probe_advsteel_activate.py` sur Advance Steel 2027 :

  - L'instance AutoCAD ACTIVE est « Autodesk Advance Steel 2027 » (hôte
    `acad.exe` partagé, Version 26.0s LMS Tech). Tout dessin Advance Steel est
    donc accessible au niveau DESSIN (DWG) via le COM AutoCAD VÉRIFIÉ.
  - La bibliothèque de types `AutoCAD 2027\\ADVS\\AstorMain5.tlb` (325 Ko,
    986 symboles) expose le VRAI modèle objet ACIER : AdvanceSteelApplication,
    Beam, Bolt, Anchor, BentBeam, BeamNotchStd, AstUI, DwgFiler,
    DesignEffortsStandard... MAIS ses coclasses ont un CLSID NON ENREGISTRÉ
    pour l'activation COM (« Classe non enregistrée », REGDB_E_CLASSNOTREG) :
    le modèle objet avancé n'est PAS pilotable depuis un processus externe
    (composant en-processus ObjectARX/.NET chargé dans Advance Steel).
  - Conséquence HONNÊTE : la SEMANTIQUE acier (profilés, matières, connexions,
    boulons, plates, features AstorMain5) n'est PAS accessible en COM externe
    -> refus EXPLICITE (§19, aucune API inventée). Seul le DWG de niveau
    dessin l'est (via l'hôte AutoCAD commun).

Ce connecteur rend donc Advance Steel PRÉSENT et DÉTECTÉ comme nœud du maillage
(accessible au DWG via l'hôte commun), tout en refusant sans complaisance la
lecture/écriture de ses objets intelligents.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ..interop.base import (
    Capability, CapabilityReport, CapabilityStatus, Detection, OpReport,
)
from .autocad import AutoCADConnector

# Chemin type de la TLB modèle objet Advance Steel (preuve d'installation)
ADVS_TLB = r"C:\Program Files\Autodesk\AutoCAD 2027\ADVS\AstorMain5.tlb"

# Coclasses du modèle objet acier VUES dans la TLB mais NON enregistrées pour
# l'activation COM externe (probe_advsteel_activate : « Classe non enregistrée »).
ASTOR_COCLASSES = ("AdvanceSteelApplication", "AstUI", "AstObjectsArr")
ASTOR_ACTIVATION_ERROR = "REGDB_E_CLASSNOTREG (coclass non enregistré en COM)"


class AdvanceSteelConnector(AutoCADConnector):
    """
    Pont Advance Steel <-> pivot SC-* (protocole en étoile, voir interop/hub.py).

    Hérite des opérations DWG VÉRIFIÉES d'AutoCAD (même hôte COM), et ajoute :
      - détection spécifique Advance Steel (TLB AstorMain5 présente) ;
      - refus explicite de la sémantique AstorMain5 (modèle objet non COM).
    """

    name = "advsteel"
    label = "Autodesk Advance Steel"

    def __init__(self, attach_only: bool = False, saveas_code: int = 24):
        super().__init__(attach_only=attach_only, saveas_code=saveas_code)

    # ------------------------------------------------------------------
    # Détection : installation Advance Steel + hôte COM AutoCAD
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        installed = os.path.isfile(ADVS_TLB)
        version = ""
        try:
            import winreg
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
                    if isinstance(disp, str) and "Advance Steel" in disp:
                        installed = True
                        for w in disp.split():
                            if w.isdigit() and len(w) == 4:
                                version = w
                uk.Close()
        except ImportError:  # pragma: no cover
            pass

        host = super().detect()
        return Detection(
            name=self.name, installed=installed or host.installed,
            version=version or host.version,
            progs=list(host.progs),          # ProgIDs = AutoCAD (même hôte)
            transport="com" if host.progs else "none",
            automatable=bool(host.progs),    # dessin seulement, pas AstorMain5
            detail=("Hôte COM AutoCAD partagé (acad.exe) : accès DWG de "
                    "niveau dessin OK ; modèle objet AstorMain5 (acier) non "
                    "activable en COM externe (§19)."
                    if host.progs else
                    "Hôte COM AutoCAD introuvable"),
        )

    # ------------------------------------------------------------------
    # Capacités : dessin OK (hérité) / sémantique acier refusée
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        caps = super().capabilities()
        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "TLB AstorMain5 présente + hôte COM AutoCAD"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.SUPPORTED,
                "Session COM via AutoCAD.Application (acad.exe partagé)"),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.PARTIAL,
                "Entités DWG/calques seulement ; sémantique acier AstorMain5 "
                "(profilés, matières, connexions, boulons) REFUSÉE : coclasses "
                "non enregistrées en COM externe (§19)"),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.PARTIAL,
                "Écriture DWG de niveau dessin seulement ; objets acier "
                "AstorMain5 non créés (§19)"),
            Capability.READ_RESULTS: caps[Capability.READ_RESULTS],
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.NOT_SUPPORTED,
                "Charges Advance Steel = AstorMain5 non exposé en COM (§19)"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.PARTIAL,
                "Calques/entités DWG lus (hérité AutoCAD) ; styles/détails "
                "AstorMain5 non garantis (§19)"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.PARTIAL,
                "Géométrie + calques + SaveAs DWG (hérité AutoCAD vérifié) ; "
                "styles/détails AstorMain5 non supportés"),
        }

    # ------------------------------------------------------------------
    # Ponts : le dessin marche (hérité), la SÉMANTIQUE acier est refusée
    # ------------------------------------------------------------------
    def read_model(self, project: Any) -> OpReport:
        rep = super().read_model(project)
        extra = (" | sémantique acier AstorMain5 (profilés, matières, "
                 "connexions, boulons) NON lue — modèle objet non activable "
                 "en COM externe (§19)")
        rep.message = (rep.message or "") + extra
        rep.objects.setdefault("advsteel_semantic_skipped", -1)  # inconnu
        return rep

    def write_model(self, project: Any) -> OpReport:
        rep = super().write_model(project)
        extra = (" | écriture DWG de niveau dessin uniquement : aucun objet "
                 "acier AstorMain5 créé (§19)")
        rep.message = (rep.message or "") + extra
        return rep

    # Refus explicite des opérations AstorMain5 (pas d'API inventée, §19)
    def read_steel_objects(self) -> OpReport:
        """Profilés/connexions/boulons AstorMain5 : REFUS motivé."""
        return OpReport(
            "read_steel_objects", "NOT_IMPLEMENTED", source=self.name,
            message=("[advsteel] objets acier AstorMain5 REFUSÉS : coclasses "
                     f"({', '.join(ASTOR_COCLASSES)}) non enregistrées en COM "
                     f"externe ({ASTOR_ACTIVATION_ERROR}). Modèle objet "
                     "chargé en-processus dans Advance Steel. Aucun objet lu "
                     "— §19."))

    def write_steel_objects(self) -> OpReport:
        return OpReport(
            "write_steel_objects", "NOT_IMPLEMENTED", source=self.name,
            message=("[advsteel] création d'objets acier AstorMain5 REFUSÉE : "
                     "modèle objet non activable en COM externe (§19). "
                     "Aucun objet écrit."))
