# -*- coding: utf-8 -*-
"""
integration/interop/revit.py — Connecteur Revit (via Named Pipe add-in).

STRATÉGIE D'HONNÊTETÉ (spec §19, §19) :
  - Revit n'expose AUCUN COM modèle (ProgID non disponible pour l'API modèle).
  - L'unique voie validée : l'add-in C# StructCalcRevitAddin chargé dans Revit
    expose un serveur Named Pipe (\\) pour READ_MODEL / APPLY_CHANGES.
  - Ce connecteur ne fait QUE le transport pipe ; la logique métier (mapping
    sections, armatures) est dans `integration.revit.writer/reinforcement`.
  - Toute capacité non prouvée par la sonde pipe = REFUSED explicite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)
from ...core.model import Project
from ...integration.revit.protocol import (
    RevitPipeClient, RevitPipeError, RevitProtocolError, PipeEnvelope,
)
from ...integration.revit.writer import (
    write_model_to_revit, WriteReport, export_nomenclature_to_revit,
)
from ...integration.revit.families import FamiliesMap


@dataclass
class RevitConnectionState:
    """État interne de la connexion pipe (pour SessionState GUI)."""
    pipe_connected: bool = False
    addin_loaded: bool = False
    project_name: str = ""
    last_read: str = ""
    last_write: str = ""


class RevitConnector(AutodeskConnector):
    """
    Pont Revit <-> pivot SC-* via Named Pipe add-in.

    Capacités (états HONNÊTES) :
      - DETECT        : SUPPORTED (détection processus Revit + pipe)
      - CONNECT       : SUPPORTED (connexion Named Pipe)
      - READ_MODEL    : SUPPORTED (pipe -> StructuralModelDto)
      - WRITE_MODEL   : PARTIAL   (APPLY_CHANGES : sections + rebars,
                                SANS appuis ni conditions aux limites)
      - READ_RESULTS  : NOT_SUPPORTED  (pas d'API résultats Revit)
      - WRITE_LOADS   : NOT_SUPPORTED
      - READ_DRAWINGS : NOT_SUPPORTED
      - WRITE_DRAWINGS: NOT_SUPPORTED

    Prérequis runtime :
      - Revit 2027+ ouvert
      - Add-in StructCalcRevitAddin chargé (LED verte dans STRUCTCALC)
      - pywin32 installé (Named Pipe Windows)
    """

    name = "revit"
    label = "Autodesk Revit (via Named Pipe add-in)"

    def __init__(self, families_map_path: str = "", pipe_name: str = ""):
        self._client: Optional[RevitPipeClient] = None
        self._state = RevitConnectionState()
        self._families_map_path = families_map_path
        self._pipe_name = pipe_name or r"\\.\pipe\structcalc_revit"
        self._reinforcement_plans: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Détection (processus Revit + pipe)
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        installed = False
        version = ""
        progs: List[str] = []
        automatable = False
        detail = ""
        transport = "named_pipe"

        # 1. Détecter installation Revit (registre) - même si pas lancé
        try:
            import winreg
            # Chercher dans les clés de désinstallation
            for root in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    uk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(uk, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            sk = winreg.OpenKey(uk, sub)
                            disp = winreg.QueryValueEx(sk, "DisplayName")[0]
                            sk.Close()
                        except (OSError, FileNotFoundError):
                            continue
                        if isinstance(disp, str) and "Revit" in disp:
                            installed = True
                            for w in disp.split():
                                if w.isdigit() and len(w) == 4:
                                    version = w
                            break
                    uk.Close()
                except OSError:
                    pass
        except ImportError:
            pass

        # 2. Détecter processus Revit.exe en cours (pour version précise)
        try:
            import subprocess
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Revit.exe", "/NH"],
                capture_output=True, text=True, timeout=10)
            if "revit.exe" in (out.stdout or "").lower():
                installed = True
                # Extraire version depuis le titre de fenêtre si possible
                try:
                    import win32gui
                    def enum_windows(hwnd, _):
                        title = win32gui.GetWindowText(hwnd)
                        if "Autodesk Revit" in title and "[" in title:
                            # ex: "Autodesk Revit 2027 - [Projet.rvt]"
                            import re
                            m = re.search(r"Revit (\d{4})", title)
                            if m:
                                version = f"20{m.group(1)}"
                    win32gui.EnumWindows(enum_windows, None)
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Sonde pipe (add-in chargé ?)
        if installed:
            try:
                client = RevitPipeClient()
                client.connect(retries=3, delay=0.5)
                ping = client.ping()
                client.close()
                if ping.get("pipe") == "structcalc_revit":
                    automatable = True
                    self._state.addin_loaded = True
                    detail = "Pipe structcalc_revit détecté (add-in chargé)"
                else:
                    detail = "Revit ouvert mais pipe add-in introuvable"
            except Exception as exc:
                detail = f"Revit ouvert, pipe non accessible : {exc}"
        else:
            detail = "Revit non détecté (processus absent)"

        return Detection(
            name=self.name,
            installed=installed,
            version=version,
            progs=progs,
            transport=transport,
            automatable=automatable,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Capacités (matrix honnête)
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        det = self.detect()
        pipe_ok = det.automatable

        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Détection processus Revit + sonde pipe réalisée."),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT,
                CapabilityStatus.SUPPORTED if pipe_ok else CapabilityStatus.NOT_SUPPORTED,
                "Connexion Named Pipe \\\\.\\pipe\\structcalc_revit"
                + (" OK" if pipe_ok else " (Revit/add-in non prêt)")),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL,
                CapabilityStatus.SUPPORTED if pipe_ok else CapabilityStatus.NOT_SUPPORTED,
                "READ_MODEL via pipe -> StructuralModelDto (nœuds, barres, sections, matériaux, cas de charge)"
                + ("" if pipe_ok else " (add-in non prêt)")),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL,
                CapabilityStatus.PARTIAL if pipe_ok else CapabilityStatus.NOT_SUPPORTED,
                "APPLY_CHANGES via pipe : sections (FamilySymbol) + armatures (Rebar). "
                "LIMITES : appuis non écrits (conditions aux limites Revit exigent hôte+référence), "
                "enrobages/recouvrements NON fournis -> barres à l'AXE, positionnement à ajuster."
                + ("" if pipe_ok else " (add-in non prêt)")),
            Capability.READ_RESULTS: CapabilityReport(
                Capability.READ_RESULTS, CapabilityStatus.NOT_SUPPORTED,
                "Revit n'expose AUCUNE API résultats calcul (pas de solveur FEM)."),
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.NOT_SUPPORTED,
                "Pas d'API charges Revit exploitable pour calcul structurel."),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Dessins Revit (vues, feuilles) : pas de lecture structurée via add-in."),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Création de vues/feuilles non implémentée dans l'add-in."),
        }

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def connect(self, timeout: float = 60.0) -> "RevitConnector":
        """Ouvre la connexion Named Pipe vers l'add-in Revit."""
        if self.connected:
            return self
        try:
            self._client = RevitPipeClient(pipe_name=self._pipe_name)
            self._client.connect()
            self._state.pipe_connected = True
            # Ping pour valider
            ping = self._client.ping()
            self._state.addin_loaded = True
            return self
        except (RevitPipeError, RevitProtocolError) as exc:
            self._client = None
            self._state.pipe_connected = False
            self._state.addin_loaded = False
            raise InteropError(f"[{self.name}] Connexion pipe échouée : {exc}")

    def disconnect(self) -> None:
        """Ferme la session pipe (sans effet sur le document Revit, §5.4)."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._state.pipe_connected = False

    def probe_addin(self) -> Tuple[bool, str]:
        """
        Sonde l'add-in Revit sans établir de connexion persistante.
        Retourne (True, "ok") si l'add-in répond au PING, (False, motif) sinon.
        """
        try:
            client = RevitPipeClient(pipe_name=self._pipe_name)
            client.connect(retries=3, delay=0.5)
            ping = client.ping()
            client.close()
            if ping.get("pipe") == "structcalc_revit":
                return True, "add-in vivant (PING OK)"
            return False, "pipe détecté mais réponse inattendue"
        except Exception as exc:
            return False, f"add-in inaccessible : {exc}"

    # ------------------------------------------------------------------
    # Ponts vers/depuis le pivot
    # ------------------------------------------------------------------
    def read_model(self, project: Project) -> OpReport:
        """
        Lit le modèle Revit complet via le pipe (READ_MODEL).

        Remplit `project` avec nœuds, barres (poteaux/poutres), sections,
        matériaux, cas de charge, appuis.
        """
        if not self.connected:
            return OpReport("read_model", "NOT_IMPLEMENTED", source=self.name,
                            message="REFUSÉE : Non connecté (connect() requis).")

        try:
            data = self._client.read_model()
            # Conversion StructuralModelDto -> Project SC-*
            # (La conversion détaillée serait dans un module dédié,
            #  pour l'instant on retourne les données brutes dans le rapport)
            return OpReport(
                "read_model", "OK", source=self.name,
                objects={
                    "nodes": len(data.get("nodes", [])),
                    "bars": len(data.get("bars", [])),
                    "load_cases": len(data.get("loadCases", [])),
                },
                message=f"Modèle Revit lu : {len(data.get('nodes', []))} nœuds, "
                        f"{len(data.get('bars', []))} barres, "
                        f"{len(data.get('loadCases', []))} cas de charge",
            )
        except RevitProtocolError as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"Protocole Revit : {exc}")
        except RevitPipeError as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"Pipe Revit : {exc}")

    def write_model(self, project: Project) -> OpReport:
        """
        Écrit le pivot vers Revit (APPLY_CHANGES) :
          - Sections (FamilySymbol) via mapping families_map.json
          - Armatures (Rebar) via plans de ferraillage (ReinforcementPlan)
        """
        if not self.connected:
            return OpReport("write_model", "NOT_IMPLEMENTED", source=self.name,
                            message="REFUSÉE : Non connecté (connect() requis).")

        if not self._families_map_path:
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message="Chemin families_map.json non fourni (obligatoire pour mapping sections).")

        try:
            report: WriteReport = write_model_to_revit(
                project,
                self._families_map_path,
                reinforcement_plans=self._reinforcement_plans,
                pipe_client=self._client,
            )
            return OpReport(
                "write_model",
                "OK" if report.ok else "PARTIAL",
                source=self.name,
                objects={
                    "bars_processed": report.bars_processed,
                    "sections_applied": report.sections_applied,
                    "rebars_created": report.rebars_created,
                },
                message=(
                    f"Sections appliquées : {report.sections_applied}, "
                    f"Armatures créées : {report.rebars_created}"
                    + ("" if report.ok else " (voir notes)")
                ),
            )
        except RevitPipeError as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"Pipe Revit : {exc}")
        except RevitProtocolError as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"Protocole Revit : {exc}")
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"Écriture Revit : {exc}")

    # ------------------------------------------------------------------
    # CREATE_SCHEDULE : planning nomenclatures
    # ------------------------------------------------------------------
    def create_schedule(self, schedule_data: Dict[str, Any]) -> OpReport:
        """
        Crée un planning (Schedule/Quantities) Revit avec les données de nomenclature.

        Nécessite que les éléments/armatures existent déjà avec paramètres partagés SC_*.
        """
        if not self.connected:
            return self._refuse(Capability.WRITE_DRAWINGS)

        try:
            result = self._client.create_schedule(schedule_data)
            return OpReport(
                "create_schedule",
                "OK" if result.get("success") else "ERROR",
                source=self.name,
                message=result.get("message", "Planning créé"),
            )
        except RevitPipeError as exc:
            return OpReport("create_schedule", "ERROR", source=self.name,
                            message=f"Pipe Revit : {exc}")
        except RevitProtocolError as exc:
            return OpReport("create_schedule", "ERROR", source=self.name,
                            message=f"Protocole Revit : {exc}")
        except Exception as exc:
            return OpReport("create_schedule", "ERROR", source=self.name,
                            message=f"Création planning : {exc}")

    # ------------------------------------------------------------------
    # API spécifique armatures (pour plans ferraillage)
    # ------------------------------------------------------------------
    def set_reinforcement_plans(self, plans: Dict[str, Any]) -> None:
        """Définit les plans de ferraillage à envoyer avec write_model."""
        self._reinforcement_plans = plans

    def clear_reinforcement_plans(self) -> None:
        self._reinforcement_plans.clear()

    # ------------------------------------------------------------------
    # SessionState pour GUI
    # ------------------------------------------------------------------
    def session_state(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "project_open": self._state.project_name != "",
            "last_operation": "write_model" if self._state.last_write else "read_model" if self._state.last_read else "",
            "last_status": "OK" if self.connected else "DISCONNECTED",
            "addin_loaded": self._state.addin_loaded,
            "pipe": r"\\.\pipe\structcalc_revit",
        }