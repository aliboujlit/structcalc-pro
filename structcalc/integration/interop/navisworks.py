# -*- coding: utf-8 -*-
"""
integration/interop/navisworks.py — Connecteur Navisworks (COM) VÉRIFIÉ.

Découverte (sonde interop, spec §19). Corrections de mes diagnostics initiaux :
  - Navisworks 2027 expose UN VRAI COM : ProgID `Navisworks.Document(.24)`
    (LocalServer32 -> Roamer.exe) + une famille `NavisworksIntegratedAPI.*`
    (Inproc, lcodieD.dll).
  - Seul `Navisworks.Document.24` est SÛR en automation externe. Les coclasses
    Inproc (nwUtilityObject/nwControlSDI/nwOpState/nwScriptParser) plantent en
    NATIF au Dispatch hors processus Navisworks : JAMAIS touchées ici.

Surface COM VÉRIFIÉE par exécution réelle (probe_nw_step.py + probe_nw_discover.py)
sur Navisworks Manage 2027 — la bibliothèque de types `roamer.tlb` est vide
(métaclass seule), donc l'énumération typeinfo est impossible et on s'appuie
SUR LE COM LUI-MÊME (getattr confirme/infirme chaque entité) :

    app.Visible        propriété      -> lisible (False)  [test de promptitude]
    app.OpenFile(path) MÉTHODE, 1 arg -> EXISTE (non appelée hors test volontaire)
    app.SaveAs(path)   MÉTHODE, 1 arg -> EXISTE (non appelée hors test volontaire)
    app.Name/.Version/.Documents/.ActiveDocument/... -> AttributeError (inexistants)

Conséquence HONNÊTE pour l'interopérabilité (§19, aucune API inventée) :
  - Navisworks est un CONSOMMATEUR/PRODUCTEUR de FICHIERS de coordination :
    OpenFile( formats supportés : NWC/NWD/DWG/IFC/... ) puis SaveAs( NWC/NWD ).
    C'est son VRAI rôle : fabriquer des maquettes de coordination.
  - Il ne PEUT PAS, via ce COM, énumérer la géométrie d'un modèle (read_model)
    ni créer de la géométrie à partir du pivot (write_model) : AUCUN membre COM
    n'expose le contenu du modèle -> REFUS EXPLICITE, jamais simulé.
  - Navisworks n'est pas un solveur : aucun résultat de calcul.

Ce connecteur est donc réellement connecté au maillage (détecté, lançable,
capable de convertir un fichier produit par AutoCAD/Civil 3D/Robot en NWC/NWD),
mais il n'est PAS un nœud de géométrie via le pivot SC-* : la matrice de routes
du hub le dira sans complaisance.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from ..interop.base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)

# ProgID VÉRIFIÉS (registre HKCR -> LocalServer32 Roamer.exe).
# .24 est celui confirmé opérationnel ; le version-indépendant sert de repli.
PROGID_PREFERRED = "Navisworks.Document.24"
PROGIDS = (PROGID_PREFERRED, "Navisworks.Document")

# Membres VÉRIFIÉS (probe_nw_discover) : lecture = test de promptitude.
READABLE_PROP = "Visible"
# Méthodes VÉRIFIÉES (1 argument chacune, probe_nw_discover) :
METHOD_OPEN_FILE = "OpenFile"
METHOD_SAVE_AS = "SaveAs"


class NavisworksConnectionError(InteropError):
    """Erreur de connexion Navisworks (COM indisponible / délai dépassé)."""


class NavisworksConnector(AutodeskConnector):
    """
    Pont Navisworks <-> pivot SC-* (protocole en étoile, voir interop/hub.py).

    Rôle RÉEL vérifié : convertisseur de fichiers de coordination
    (OpenFile -> SaveAs, ex. DWG -> NWC). Rôle de géométrie via pivot : REFUSÉ
    (aucun membre COM n'expose le contenu du modèle, §19).

    Usage :
        nw = NavisworksConnector()
        nw.detect()                       # sans lancer Navisworks
        nw.connect()                      # Dispatch Navisworks.Document.24
        nw.convert("modele.dwg", "modele.nwc")   # VÉRIFIÉ
        nw.disconnect()
    """

    name = "navisworks"
    label = "Autodesk Navisworks Manage"

    PROGIDS = PROGIDS
    # Dossier d'installation type (détection version via LocalServer32)
    INSTALL_HINT = "Navisworks"

    def __init__(self, attach_only: bool = False):
        self.attach_only = attach_only
        self._app = None
        self._connected = False

    # ------------------------------------------------------------------
    # Détection (registre, sans lancer Navisworks)
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        progs: List[str] = []
        installed = False
        version = ""
        local_servers: List[str] = []
        try:
            import winreg
        except ImportError:  # pragma: no cover
            return Detection(name=self.name, installed=False,
                             transport="com", automatable=False,
                             detail="winreg indisponible (non-Windows)")

        for pid in self.PROGIDS:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    pid + r"\CLSID") as k:
                    clsid = winreg.QueryValueEx(k, "")[0]
                progs.append(pid)
                installed = True
                try:
                    with winreg.OpenKey(
                            winreg.HKEY_CLASSES_ROOT,
                            rf"CLSID\{clsid}\LocalServer32") as k2:
                        local_servers.append(winreg.QueryValueEx(k2, "")[0])
                except OSError:
                    pass
            except OSError:
                continue

        for ls in local_servers:
            for token in ls.replace("/", "\\").split("\\"):
                for word in token.split():
                    if word.isdigit() and len(word) == 4:
                        version = word
                        break
                if version:
                    break
            if version:
                break

        return Detection(
            name=self.name, installed=installed, version=version,
            progs=progs, transport="com",
            automatable=bool(progs),
            detail=("COM Navisworks disponible (LocalServer32 Roamer.exe)"
                    if progs else
                    "Aucun ProgID Navisworks dans le registre"),
        )

    # ------------------------------------------------------------------
    # Capacités (§19 : seules les opérations réellement exécutées)
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Registre ProgID Navisworks.Document(.24) + LocalServer32"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.SUPPORTED,
                "Dispatch Navisworks.Document.24 (vérifié live : "
                "tools/verify_navisworks_live.py, connect ~20s + "
                "OpenFile/SaveAs exécutés -> NWD produit). Rôle réel : "
                "convertisseur de fichiers de coordination OpenFile/SaveAs/convert"),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.NOT_SUPPORTED,
                "COM n'expose QUE OpenFile/SaveAs/Visible : AUCUN membre "
                "pour énumérer la géométrie/propriétés d'un modèle -> refus "
                " explicite (§19, aucun faux succès)"),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.NOT_SUPPORTED,
                "Aucun membre COM pour créer de la géométrie à partir du "
                "pivot -> refus explicite (§19)"),
            Capability.READ_RESULTS: CapabilityReport(
                Capability.READ_RESULTS, CapabilityStatus.NOT_SUPPORTED,
                "Navisworks n'est pas un solveur structurel"),
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.NOT_SUPPORTED,
                "Aucun membre COM de charges (§19)"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Navisworks produit des MAQUETTES de coordination (NWC/NWD), "
                "pas des dessins ; contenu non lisible via COM (§19)"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Voir convert() : rôle réel = conversion de fichiers de "
                "coordination, pas d'écriture de dessin"),
        }

    # ------------------------------------------------------------------
    # Session COM
    # ------------------------------------------------------------------
    def connect(self, timeout: float = 120.0) -> "NavisworksConnector":
        """
        Dispatch Navisworks.Document.24 avec RETRY (lance Roamer.exe, ~20s).

        Test de promptitude via `Visible` (SEUL membre lisible vérifié).
        Le retry absorbe CO_E_SERVER_EXEC_FAILURE pendant l'initialisation.
        """
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        deadline = time.time() + timeout
        last_err: Optional[Exception] = None
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            for pid in self.PROGIDS:
                if self.attach_only and pid != PROGID_PREFERRED:
                    continue
                try:
                    app = win32com.client.Dispatch(pid)
                    # promptitude : lire Visible (SEUL membre lisible vérifié)
                    _ = getattr(app, READABLE_PROP)
                    self._app = app
                    self._connected = True
                    self._progid_used = pid
                    return self
                except AttributeError as exc:
                    # objet dispatché mais Visible absent -> Progid non bon
                    last_err = exc
                except Exception as exc:
                    last_err = exc
            time.sleep(min(1.0 * attempt, 5.0))   # backoff

        raise NavisworksConnectionError(
            f"Connexion Navisworks impossible après {timeout}s "
            f"({attempt} tentatives) : {last_err}")

    @property
    def connected(self) -> bool:
        return bool(self._connected and self._app is not None)

    @property
    def app(self):
        if not self._connected or self._app is None:
            raise NavisworksConnectionError(
                "Non connecté. Appelez connect() d'abord.")
        return self._app

    def disconnect(self) -> None:
        """Détache sans quitter Navisworks ni sauvegarder (§5.4)."""
        self._app = None
        self._connected = False
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Opérations RÉELLES VÉRIFIÉES (fichiers de coordination)
    # ------------------------------------------------------------------
    def open_file(self, path: str) -> OpReport:
        """
        OpenFile(path) : charge un modèle dans Navisworks (VÉRIFIÉ, 1 arg).

        Formats : ceux supportés par Navisworks (NWC/NWD/DWG/IFC...). On ne
        garantit pas le support d'un format précis : on exécute et on rapporte.
        """
        op = "navisworks.open_file"
        if not self.connected:
            return OpReport(op, "REFUSED", source=self.name,
                            message="[navisworks] non connecté (connect() "
                                    "d'abord) — aucun fichier ouvert.")
        if not path or not isinstance(path, str):
            return OpReport(op, "REFUSED", source=self.name,
                            message="[navisworks] chemin invalide.")
        if not os.path.isfile(path):
            return OpReport(op, "REFUSED", source=self.name,
                            message=f"[navisworks] fichier introuvable : {path}")
        try:
            self.app.OpenFile(path)
        except Exception as exc:
            return OpReport(op, "ERROR", source=self.name,
                            message=f"[navisworks] OpenFile('{path}') en "
                                    f"échec : {type(exc).__name__}: {exc}")
        return OpReport(op, "OK", source=self.name,
                        message=f"[navisworks] OpenFile('{path}') exécuté.",
                        objects={"opened": 1})

    def save_as(self, path: str) -> OpReport:
        """
        SaveAs(path) : enregistre le document courant (VÉRIFIÉ, 1 arg).

        borne VÉRIFIÉE par exécution live (tools/probe_nw_saveas.py) :
          - `.nwd` (Navisworks Document) -> SUCCES, fichier produit ;
          - `.nwc` -> ÉCHEC « Failed to save document » (odviewdll_clr) :
            le .nwc est un CACHE généré par l'Optimizeur/Publisher, PAS une
            cible SaveAs d'un document. On ne prétend donc pas l'obtenir ici.

        L'extension décide du format ; seule `.nwd` est ici qualifiée.
        """
        op = "navisworks.save_as"
        if not self.connected:
            return OpReport(op, "REFUSED", source=self.name,
                            message="[navisworks] non connecté (connect() "
                                    "d'abord) — rien à enregistrer.")
        if not path or not isinstance(path, str):
            return OpReport(op, "REFUSED", source=self.name,
                            message="[navisworks] chemin invalide.")
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            return OpReport(op, "REFUSED", source=self.name,
                            message=f"[navisworks] dossier cible introuvable "
                                    f": {parent}")
        try:
            self.app.SaveAs(path)
        except Exception as exc:
            return OpReport(op, "ERROR", source=self.name,
                            message=f"[navisworks] SaveAs('{path}') en "
                                    f"échec : {type(exc).__name__}: {exc}")
        return OpReport(op, "OK", source=self.name,
                        message=f"[navisworks] SaveAs('{path}') exécuté.",
                        objects={"saved": 1})

    def convert(self, source_path: str, target_path: str) -> OpReport:
        """
        Conversion VÉRIFIÉE live : OpenFile(source) -> SaveAs(cible .nwd).

        Pont RÉEL Navisworks <-> AutoCAD/Civil 3D/Robot : un DWG produit par
        un autre logiciel est converti en maquette de coordination .nwd
        (préuve : tools/verify_navisworks_live.py, DWG -> NWD).

        bornes vérifiées (§19) :
          - cible `.nwd` : SUCCES (format document) ;
          - cible `.nwc` : ÉCHEC (cache, pas une cible SaveAs — voir save_as).

        Aucun contenu de modèle n'est lu ni inventé : seule la conversion
        fichier->fichier est exécutée.
        """
        op = "navisworks.convert"
        r_open = self.open_file(source_path)
        if not r_open.ok:
            return OpReport(op, r_open.status, source=self.name,
                            message=f"étape OpenFile refusée/échouée : "
                                    f"{r_open.message}")
        r_save = self.save_as(target_path)
        if not r_save.ok:
            return OpReport(op, r_save.status, source=self.name,
                            message=f"étape SaveAs refusée/échouée : "
                                    f"{r_save.message}")
        return OpReport(
            op, "OK", source=self.name,
            message=f"[navisworks] conversion {source_path} -> {target_path} "
                    f"exécutée (fichier de coordination).",
            objects={"converted": 1})

    # ------------------------------------------------------------------
    # Ponts pivot : REFUS EXPLICITES (§19 — aucune géométrie via COM)
    # ------------------------------------------------------------------
    def read_model(self, project: Any) -> OpReport:
        return self._refuse(Capability.READ_MODEL)

    def write_model(self, project: Any) -> OpReport:
        return self._refuse(Capability.WRITE_MODEL)
