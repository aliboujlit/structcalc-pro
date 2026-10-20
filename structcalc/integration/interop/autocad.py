# -*- coding: utf-8 -*-
"""
integration/interop/autocad.py — Connecteur AutoCAD (COM) VÉRIFIÉ.

Toutes les opérations ci-dessous ont été CONFIRMÉES par exécution réelle
sur AutoCAD 2027 (hôte acad.exe, ProgID AutoCAD.Application) via :

    tools/probe_autocad_members.py    (attach, membres exposés)
    tools/probe_autocad_doc.py        (round-trip document)
    tools/probe_autocad_cycle.py      (SaveAs -> Open -> lecture)
    tools/probe_autocad_identify.py   (codes AcSaveAsType -> DWG réel)
    tools/probe_autocad_props.py      (Layer/Handle/Delete/calques)

API VÉRILIÉE (seule utilisée ci-dessous) :
  app       : Name, Version, Caption, Visible, Documents, Quit
  docs      : Count, Add(), Open(path)   [Open exige un RETRY : CALL_REJECTED
              tant que le document n'est pas chargé]
  doc       : Name, FullName, ModelSpace, Layers, Regen(1),
              SaveAs(path, code), Close(False)
  modelspace: Count, Item(i), AddLine(VARIANT p1, VARIANT p2),
              AddLightWeightPolyline(VARIANT 8 doubles)
  entité    : ObjectName, StartPoint, EndPoint, Layer (get/set), Handle,
              Color, Delete()
  layers    : Count, Add(name), Item(name); layer.Color = int
  codes DWG : 12 -> AC1015, 24 -> AC1018 (les autres ont échoué)

NON VÉRIFIÉ -> JAMAIS appelé (spec §19) :
  AddText / AddMText      : signature inutilisable (échec toutes formes)
  ItemByRef(Handle)       : inexistant -> lookup en parcours de ModelSpace

Pièges rencontrés et gérés :
  - Dispatch -> CO_E_SERVER_EXEC_FAILURE (jusqu'à ~2 min de blocage puis
    échec quand acad.exe tarde à s'enregistrer au SCM) : on LANCE
    acad.exe directement (chemin registre LocalServer32) puis on poll
    GetActiveObject ; Dispatch ne reste qu'un repli à UN essai ;
  - GetActiveObject sur instance non prête -> AttributeError transitoire ;
  - Documents.Open -> CALL_REJECTED (0x80010001) tant que non chargé ;
  - plusieurs documents ouverts -> read_model rapporte TOUJOURS l'identité
    (Name/FullName) du document lu (et accepte un document ciblé).

Fermeture : SANS sauvegarde par défaut (spec §5.4).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from ..interop.base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)

# Codes AcSaveAsType confirmés -> DWG réel (probe_autocad_identify.py)
SAVEAS_DWG_AC1018 = 24   # DWG AC1018 (recommandé)
SAVEAS_DWG_AC1015 = 12   # DWG AC1015 (repli)

# Couches STRUCTCALC écrites/attendues dans le DWG
LAYER_COLUMN = "SC_COLUMN"
LAYER_BEAM = "SC_BEAM"
LAYER_SLAB = "SC_SLAB"
LAYER_NODE = "SC_NODE"
SC_PREFIX = "SC_"


def _v6(vals: List[float]):
    """VARIANT VT_ARRAY|VT_R8 — FORME VÉRIFIÉE pour les points AutoCAD."""
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                   list(vals))


def find_doc_by_path(app, path: str):
    """
    Document DÉJÀ ouvert correspondant à `path` (FullName), sinon None.

    Usage : réutiliser en LECTURE SEULE un document déjà ouvert (par
    l'utilisateur ou une session antérieure) au lieu de le réouvrir —
    jamais fermé ni modifié puisque nous ne l'avons pas ouvert (§5.4).
    Comparaison insensible à la casse sur le chemin absolu (normcase).
    """
    import os
    try:
        target = os.path.normcase(os.path.abspath(str(path)))
    except Exception:
        target = str(path).lower()
    try:
        docs = app.Documents
        for i in range(docs.Count):
            try:
                d = docs.Item(i)
            except Exception:
                # Document fantôme/inaccessible (com_error Item constaté
                # live 20/10 sur AutoCAD après boucle) : ne JAMAIS laisser
                # casser la recherche du document réellement ouvert —
                # sinon le chargeur croit « non ouvert » et tente une
                # réouverture (dialogue modal -> blocage).
                continue
            try:
                full = str(d.FullName or "")
            except Exception:
                continue
            if not full:
                continue
            try:
                if os.path.normcase(os.path.abspath(full)) == target:
                    return d
            except Exception:
                if full.lower() == str(path).lower():
                    return d
    except Exception:
        pass
    return None


def _acad_process_running() -> bool:
    """
    True si un acad.exe tourne déjà (tasklist, sans COM ni dépendance).

    Sert de garde au repli `Dispatch` de `_active()` : avec un processus
    existant, Dispatch se RATTACHE à l'objet mono-instance ; sans processus,
    il en LANCERAIT un — ce que `_active()` ne doit jamais faire.
    """
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq acad.exe", "/NH"],
            capture_output=True, text=True, timeout=10)
        return "acad.exe" in (out.stdout or "").lower()
    except Exception:
        return False


class AutoCADConnectionError(InteropError):
    """Erreur de connexion AutoCAD (COM indisponible / délai dépassé)."""


class AutoCADConnector(AutodeskConnector):
    """
    Pont AutoCAD <-> pivot SC-* (protocole en étoile, voir interop/hub.py).

    Usage :
        ac = AutoCADConnector()
        ac.detect()          # sans lancer AutoCAD
        ac.connect()         # attach ou lancement avec backoff
        ac.write_model(project)
        ac.disconnect()
    """

    name = "autocad"
    label = "Autodesk AutoCAD"

    PROGIDS = ("AutoCAD.Application", "AutoCAD.Application.27",
               "AutoCAD.Application.26", "AutoCAD.Application.24")
    REG_PATHS = (
        (r"SOFTWARE\Autodesk\AutoCAD", ""),
    )

    def __init__(self, attach_only: bool = False,
                 saveas_code: int = SAVEAS_DWG_AC1018):
        self.attach_only = attach_only
        self.saveas_code = saveas_code
        self._app = None
        self._connected = False
        self._exe_path: Optional[str] = None   # acad.exe (registre, mémorisé)
        self._exe_cached = False

    # ------------------------------------------------------------------
    # Détection (registre, sans lancer l'application)
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        progs: List[str] = []
        installed = False
        local_servers: List[str] = []
        try:
            import winreg
        except ImportError:  # pragma: no cover
            return Detection(name=self.name, installed=False,
                             transport="com", automatable=False,
                             detail="winreg indisponible (non-Windows)")
        # ProgID présents ?
        for pid in self.PROGIDS:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    pid + r"\CLSID") as k:
                    clsid = winreg.QueryValueEx(k, "")[0]
                progs.append(pid)
                installed = True
                # LocalServer32 -> chemin acad.exe
                try:
                    with winreg.OpenKey(
                            winreg.HKEY_CLASSES_ROOT,
                            rf"CLSID\{clsid}\LocalServer32") as k2:
                        local_servers.append(winreg.QueryValueEx(k2, "")[0])
                except OSError:
                    pass
            except OSError:
                continue

        version = ""
        for ls in local_servers:
            if "AutoCAD" in ls:
                # "..\\AutoCAD 2027\\acad.exe" -> 2027
                # (jeton mixte « AutoCAD 2027 », pas un nombre pur)
                for token in ls.replace("/", "\\").split("\\"):
                    for word in token.split():
                        if word.isdigit() and len(word) == 4:
                            version = word
                            break
                    if version:
                        break

        return Detection(
            name=self.name, installed=installed, version=version,
            progs=progs, transport="com",
            automatable=bool(progs),
            detail=("COM AutoCAD disponible" if progs else
                    "Aucun ProgID AutoCAD dans le registre"),
        )

    # ------------------------------------------------------------------
    # Capacités (§19 : seules les opérations exécutées sont SUPPORTED)
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Registre ProgID + LocalServer32 (probe_autocad_members)"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.SUPPORTED,
                "GetActiveObject -> lancement direct acad.exe (registre "
                "LocalServer32) -> repli Dispatch (vérifié ; "
                "CO_E_SERVER_EXEC_FAILURE géré sans faux succès)"),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.SUPPORTED,
                "Parcours ModelSpace: ObjectName/StartPoint/EndPoint/Layer"),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.SUPPORTED,
                "AddLine + AddLightWeightPolyline (VARIANT) + calques SC_*"),
            Capability.READ_RESULTS: CapabilityReport(
                Capability.READ_RESULTS, CapabilityStatus.NOT_SUPPORTED,
                "AutoCAD n'est pas un solveur : aucun résultat de calcul"),
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.UNVERIFIED,
                "Écriture de charges non sondée — jamais présentée "
                "comme disponible"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.PARTIAL,
                "Entités + calques lus ; TEXTES NON lisibles (AddText/MText "
                "non vérifiés)"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.PARTIAL,
                "Géométrie + calques + SaveAs DWG vérifiés ; "
                "TEXTES NON supportés (AddText échoue en toutes formes)"),
        }

    # ------------------------------------------------------------------
    # Session COM
    # ------------------------------------------------------------------
    @staticmethod
    def _server_path(raw: str) -> Optional[str]:
        """'« C:\\...\\acad.exe »' ou 'C:\\...\\acad.exe' -> chemin exécutable."""
        s = (raw or "").strip()
        if not s:
            return None
        if s.startswith('"'):
            end = s.find('"', 1)
            return s[1:end] if end > 1 else None
        idx = s.lower().find(".exe")
        if idx > 0:
            return s[:idx + 4]
        return s

    def acad_exe(self) -> Optional[str]:
        """
        Chemin de acad.exe via le registre (ProgID -> CLSID -> LocalServer32).

        Sert à LANCER AutoCAD directement : le `Dispatch` COM peut bloquer
        ~2 minutes puis rendre CO_E_SERVER_EXEC_FAILURE quand acad.exe met
        plus de temps à s'enregistrer que le délai d'activation SCM (constaté
        en live sur cette machine). Mémorisé (positif ou négatif).
        """
        if self._exe_cached:
            return self._exe_path
        self._exe_cached = True
        self._exe_path = None
        try:
            import winreg
        except ImportError:          # pragma: no cover — non-Windows
            return None
        for pid in self.PROGIDS:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    pid + r"\CLSID") as k:
                    clsid = winreg.QueryValueEx(k, "")[0]
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    rf"CLSID\{clsid}\LocalServer32") as k2:
                    raw = winreg.QueryValueEx(k2, "")[0]
            except OSError:
                continue
            path = self._server_path(str(raw))
            if path:
                self._exe_path = path
                break
        return self._exe_path

    def _active(self):
        """
        Instance AutoCAD active -> (app, dernière_erreur).

        Validation EXIGE `app.Name` ET `app.Documents.Count` — deux pièges
        constatés en live :
          - instance non prête -> AttributeError/COM transitoire (sur `Name`) ;
          - instance DÉGRADÉE (après des dizaines de milliers d'appels COM
            sans respiration) -> `Documents` ne résout plus
            (`AttributeError <unknown>.Count`) et les lectures d'entités
            partent alors en chaîne de `com_error`. Une instance qui ne
            résout pas `Documents.Count` n'est PAS prête : on n'accepte
            jamais une telle connexion.
        Repli `Dispatch(ProgID)` UNIQUEMENT si un acad.exe tourne déjà
        (`_acad_process_running`) : il se rattache alors à l'objet
        mono-instance, sans lancer d'AutoCAD (cf. helper).
        """
        import win32com.client
        last: Optional[Exception] = None
        for pid in self.PROGIDS:
            try:
                app = win32com.client.GetActiveObject(pid)
                _ = app.Name
                _ = app.Documents.Count      # membrane de prêt réel
                self._show_app(app)
                return app, None
            except Exception as exc:
                last = exc
        # ROT sans entrée valide (instance purgée/fermée) mais un acad.exe
        # tourne -> Dispatch se rattache à l'instance existante.
        if _acad_process_running():
            for pid in self.PROGIDS:
                try:
                    app = win32com.client.Dispatch(pid)
                    _ = app.Name
                    _ = app.Documents.Count
                    self._show_app(app)
                    return app, None
                except Exception as exc:
                    last = exc
        return None, last

    @staticmethod
    def _show_app(app) -> None:
        """
        Rend l'instance AutoCAD VISIBLE.

        Une instance lancée par COM (Dispatch/serveur LocalServer32) démarre
        avec `Visible=False` (constaté live : les transferts avaient lieu
        « dans le dos » de l'utilisateur, aucun plan visible à l'écran).
        L'utilisateur doit VOIR chaque opération — meilleure preuve + aucun
        travail caché. Échec silencieux : la visibilité n'est jamais un
        prétexte à refuser une opération.
        """
        try:
            app.Visible = True
        except Exception:
            pass

    def connect(self, timeout: float = 180.0) -> "AutoCADConnector":
        """
        Attach à une instance active, sinon lancement avec RETRY.

        Ordre (défaut) :
          1. GetActiveObject (rapide) sur les ProgIDs connus ;
          2. lancement DIRECT de acad.exe (registre LocalServer32) puis
             polling GetActiveObject — contourne le délai d'activation SCM ;
          3. repli `Dispatch` (UN essai : chaque tentative peut bloquer
             ~2 min puis rendre CO_E_SERVER_EXEC_FAILURE, constaté en live).

        Refus final TOUJOURS motivé (aucun faux succès) : le message indique
        les tentatives, la dernière erreur, et si acad.exe a été lancé.
        """
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        deadline = time.time() + timeout
        last_err: Optional[Exception] = None
        attempt = 0
        launch_tried = False     # Popen tenté (succès ou échec)
        launched = False         # acad.exe démarré par nous
        dispatch_tried = False   # repli Dispatch consommé

        while time.time() < deadline:
            attempt += 1
            # 1) instance déjà active (rapide)
            app, err = self._active()
            if app is not None:
                self._app = app
                self._connected = True
                return self
            last_err = err

            if not self.attach_only:
                if not launch_tried:
                    # 2) lancement direct acad.exe (une seule tentative)
                    launch_tried = True
                    exe = self.acad_exe()
                    if exe:
                        try:
                            import subprocess
                            subprocess.Popen([exe])
                            launched = True
                        except Exception as exc:
                            last_err = exc
                elif launched:
                    pass        # attendre l'enregistrement dans le ROT
                elif not dispatch_tried:
                    # 3) pas de chemin exploitable -> repli Dispatch (1 essai)
                    dispatch_tried = True
                    try:
                        app = win32com.client.Dispatch("AutoCAD.Application")
                        _ = app.Name
                        self._show_app(app)   # l'utilisateur doit voir
                        self._app = app
                        self._connected = True
                        return self
                    except Exception as exc:
                        last_err = exc
            time.sleep(min(1.0 * attempt, 3.0))   # backoff

        hint = ""
        if launched:
            hint = (" ; acad.exe a été lancé mais AutoCAD ne s'est pas "
                    "enregistré dans le délai (fenêtre de licence ou de "
                    "démarrage bloquante ?) : fermez-la puis réessayez")
        raise AutoCADConnectionError(
            f"Connexion AutoCAD impossible après {timeout}s "
            f"({attempt} tentatives) : {last_err}{hint}")

    @property
    def connected(self) -> bool:
        return bool(self._connected and self._app is not None)

    @property
    def app(self):
        if not self._connected or self._app is None:
            raise AutoCADConnectionError(
                "Non connecté. Appelez connect() d'abord.")
        return self._app

    def disconnect(self) -> None:
        """Détache sans quitter l'application utilisateur (§5.4)."""
        self._app = None
        self._connected = False
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Document helpers (retry obligatoire)
    # ------------------------------------------------------------------
    def new_document(self, tries: int = 12, delay: float = 1.5):
        """Documents.Add() + attente que ModelSpace soit utilisable."""
        doc = self.app.Documents.Add()
        self._wait_ready(doc, tries, delay)
        return doc

    def open_document(self, path: str, tries: int = 12,
                      delay: float = 1.5):
        """
        Documents.Open(path) avec RETRY : AutoCAD lève CALL_REJECTED
        (0x80010001) tant que le document n'est pas terminé (vérifié).
        """
        last: Optional[Exception] = None
        for _ in range(tries):
            try:
                doc = self.app.Documents.Open(path)
            except Exception as exc:
                last = exc
                time.sleep(delay)
                continue
            try:
                self._wait_ready(doc, tries, delay)
                return doc
            except Exception as exc:
                last = exc
                time.sleep(delay)
        raise AutoCADConnectionError(
            f"Open('{path}') non exploitable après {tries} essais : {last}")

    def _wait_ready(self, doc, tries: int, delay: float) -> None:
        last: Optional[Exception] = None
        for _ in range(tries):
            try:
                _ = doc.ModelSpace.Count
                return
            except Exception as exc:
                last = exc
                time.sleep(delay)
        raise AutoCADConnectionError(f"Document non prêt : {last}")

    def save_document(self, doc, path: str, code: Optional[int] = None) -> str:
        """
        SaveAs avec un code AcSaveAsType VÉRIFIÉ (24=AC1018, 12=AC1015).

        Un code inconnu provoque « Argument incorrect » : on ne tente que
        les codes confirmés, avec repli sur le second.
        """
        codes = [code if code is not None else self.saveas_code]
        if SAVEAS_DWG_AC1018 not in codes:
            codes.append(SAVEAS_DWG_AC1018)
        if SAVEAS_DWG_AC1015 not in codes:
            codes.append(SAVEAS_DWG_AC1015)
        last: Optional[Exception] = None
        for c in codes:
            try:
                doc.SaveAs(path, c)
                return path
            except Exception as exc:
                last = exc
                continue
        raise AutoCADConnectionError(
            f"SaveAs('{path}') a échoué pour {codes} : {last}")

    def close_document(self, doc, save: bool = False) -> None:
        """Fermeture ; SANS sauvegarde par défaut (§5.4)."""
        doc.Close(bool(save))

    # ------------------------------------------------------------------
    # ÉCRITURE : pivot -> AutoCAD (VÉRIFIÉ)
    # ------------------------------------------------------------------
    def write_model(self, project: Any) -> OpReport:
        """
        Dessine le modèle SC-* dans un nouveau document AutoCAD.

        Projection plan (x, y) des nœuds/barres, calques SC_* :
          - nœuds    -> SC_NODE    (petits traits en croix)
          - poteaux  -> SC_COLUMN  (losange/point au pied)
          - poutres  -> SC_BEAM    (AddLine)
          - dalles   -> SC_SLAB    (contour AddLightWeightPolyline)
        Les identifiants SC-* sont conservés via le mapping handle (dict
        local) pour le retour, faute d'ItemByRef (non vérifié).
        """
        if not self._connected:
            return OpReport("write_model", "REFUSED", source=self.name,
                            message="Non connecté (connect() requis).")
        # Pivot vide -> REFUS (jamais un « succès » à 0 objet, jamais de
        # document AutoCAD créé pour rien).
        _cnt = {c: getattr(project, c, None)
                for c in ("nodes", "beams", "columns", "slabs")}
        if not any(isinstance(v, dict) and v for v in _cnt.values()):
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[autocad] écriture REFUSÉE : pivot vide (0 nœud, "
                         "0 poutre, 0 poteau, 0 dalle) — rien à dessiner, "
                         "aucun document créé."))
        try:
            doc = self.new_document()
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=str(exc))

        self._handles: Dict[str, str] = {}   # SC-* -> AutoCAD Handle
        counts = {"nodes": 0, "columns": 0, "beams": 0, "slabs": 0,
                  "entities": 0}
        errors: List[str] = []

        try:
            ms = doc.ModelSpace
            layers = doc.Layers
            for lname in (LAYER_NODE, LAYER_COLUMN, LAYER_BEAM, LAYER_SLAB):
                self._ensure_layer(layers, lname)

            nodes = getattr(project, "nodes", {}) or {}

            def nxy(nid):
                n = nodes.get(nid)
                if n is None:
                    return None
                try:
                    x = 0.0 if n.x.is_missing else float(n.x.value)
                    y = 0.0 if n.y.is_missing else float(n.y.value)
                    return (x, y)
                except Exception:
                    return None

            # -- Poutres (AddLine) --
            for bid, beam in (getattr(project, "beams", {}) or {}).items():
                p1, p2 = nxy(beam.start_node), nxy(beam.end_node)
                if not p1 or not p2:
                    errors.append(f"{bid}: nœuds manquants")
                    continue
                try:
                    e = ms.AddLine(_v6([p1[0], p1[1], 0.0]),
                                   _v6([p2[0], p2[1], 0.0]))
                    e.Layer = LAYER_BEAM
                    self._handles[bid] = str(e.Handle)
                    counts["beams"] += 1
                    counts["entities"] += 1
                except Exception as exc:
                    errors.append(f"{bid}: {type(exc).__name__}")

            # -- Poteaux (nœud haut/bas) : trait vertical projeté au pied --
            for cid, col in (getattr(project, "columns", {}) or {}).items():
                p1, p2 = nxy(col.start_node), nxy(col.end_node)
                if not p1 or not p2:
                    errors.append(f"{cid}: nœuds manquants")
                    continue
                try:
                    # losange de 0.3 m autour du pied (repère plan)
                    x, y = p1
                    s = 0.15
                    pts = [x, y + s, x + s, y, x, y - s, x - s, y]
                    e = ms.AddLightWeightPolyline(_v6(pts))
                    e.Layer = LAYER_COLUMN
                    self._handles[cid] = str(e.Handle)
                    counts["columns"] += 1
                    counts["entities"] += 1
                except Exception as exc:
                    errors.append(f"{cid}: {type(exc).__name__}")

            # -- Dalles (contour 4 coins) --
            for sid, slab in (getattr(project, "slabs", {}) or {}).items():
                pts: List[float] = []
                ok = True
                for nid in (getattr(slab, "node_ids", []) or []):
                    p = nxy(nid)
                    if p is None:
                        ok = False
                        break
                    pts.extend([p[0], p[1]])
                if not ok or len(pts) < 6:
                    errors.append(f"{sid}: contour incomplet")
                    continue
                try:
                    e = ms.AddLightWeightPolyline(_v6(pts))
                    e.Layer = LAYER_SLAB
                    self._handles[sid] = str(e.Handle)
                    counts["slabs"] += 1
                    counts["entities"] += 1
                except Exception as exc:
                    errors.append(f"{sid}: {type(exc).__name__}")

            # -- Nœuds (croix 0.2 m) --
            for nid in nodes:
                p = nxy(nid)
                if p is None:
                    continue
                x, y = p
                try:
                    e1 = ms.AddLine(_v6([x - 0.1, y, 0.0]),
                                    _v6([x + 0.1, y, 0.0]))
                    e2 = ms.AddLine(_v6([x, y - 0.1, 0.0]),
                                    _v6([x, y + 0.1, 0.0]))
                    e1.Layer = LAYER_NODE
                    e2.Layer = LAYER_NODE
                    self._handles[nid] = str(e1.Handle)
                    counts["nodes"] += 1
                    counts["entities"] += 2
                except Exception as exc:
                    errors.append(f"{nid}: {type(exc).__name__}")

            doc.Regen(1)
            self._last_doc = doc
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            objects=counts, message=str(exc))

        status = "OK" if not errors else "PARTIAL"
        return OpReport(
            "write_model", status, source=self.name, objects=counts,
            message=("géométrie écrite (textes non supportés, §19)"
                     if not errors else
                     f"{len(errors)} élément(s) non écrit(s) : "
                     + "; ".join(errors[:5])))

    # ------------------------------------------------------------------
    # ÉCRITURE : plans de coffrage -> AutoCAD (v1.4)
    # ------------------------------------------------------------------
    def write_coffrage(self, project: Any, out_path: str = "") -> OpReport:
        """
        Dessine les plans de coffrage (un niveau = un décalage en Y) dans
        un NOUVEAU document AutoCAD, calques SC_COFFRAGE_*.

        Rectangles de poteaux à leurs dimensions DÉDUITES (R<b>x<h> cm) et
        doubles lignes de poutres. Le document est laissé ouvert ; s'il
        `out_path` est fourni, il est SaveAs DWG (code vérifié). Le texte
        n'est PAS écrit (AddText inutilisable — spec §19) : le plan PDF
        porte cotes et légendes, le DWG la géométrie éditable.
        """
        if not self._connected:
            return OpReport("write_coffrage", "REFUSED", source=self.name,
                            message="Non connecté (connect() requis).")
        from ...reporting.plan_coffrage import build_level_plans
        plans = [lp for lp in build_level_plans(project) if lp.columns]
        if not plans:
            return OpReport(
                "write_coffrage", "REFUSED", source=self.name,
                message=("Aucun poteau exploitable : 0 plan de coffrage "
                         "(0 objet = 0 écrit, rien n'est inventé)."))
        try:
            doc = self.new_document()
        except Exception as exc:
            return OpReport("write_coffrage", "ERROR", source=self.name,
                            message=str(exc))
        self._handles = {}
        counts = {"levels": 0, "columns": 0, "beams": 0, "entities": 0}
        errors: List[str] = []
        try:
            ms = doc.ModelSpace
            layers = doc.Layers
            for lname in ("SC_COFFRAGE_COL", "SC_COFFRAGE_POUTRE"):
                self._ensure_layer(layers, lname)
            y_off = 0.0
            for lp in plans:
                for col in lp.columns:
                    try:
                        if col.dims_cm:
                            b = col.dims_cm[0] / 100.0 / 2.0
                            h = col.dims_cm[1] / 100.0 / 2.0
                        else:
                            b = h = 0.05     # croix d'axe (section inconnue)
                        x, y = col.x, col.y + y_off
                        if col.dims_cm:
                            pts = [x - b, y - h, x + b, y - h,
                                   x + b, y + h, x - b, y + h]
                        else:
                            pts = [x - b, y, x + b, y]
                        e = ms.AddLightWeightPolyline(_v6(pts))
                        e.Layer = "SC_COFFRAGE_COL"
                        self._handles[col.sc_id] = str(e.Handle)
                        counts["columns"] += 1
                        counts["entities"] += 1
                    except Exception as exc:
                        errors.append(f"{col.sc_id}: "
                                      f"{type(exc).__name__}")
                for bm in lp.beams:
                    try:
                        y1, y2 = bm.p1[1] + y_off, bm.p2[1] + y_off
                        if bm.width_cm:
                            w = bm.width_cm / 100.0 / 2.0
                            dx, dy = (bm.p2[0] - bm.p1[0]), (y2 - y1)
                            L = (dx * dx + dy * dy) ** 0.5 or 1.0
                            nx, ny = -dy / L * w, dx / L * w
                            e1 = ms.AddLine(
                                _v6([bm.p1[0] + nx, y1 + ny, 0.0]),
                                _v6([bm.p2[0] + nx, y2 + ny, 0.0]))
                            e2 = ms.AddLine(
                                _v6([bm.p1[0] - nx, y1 - ny, 0.0]),
                                _v6([bm.p2[0] - nx, y2 - ny, 0.0]))
                            e1.Layer = e2.Layer = "SC_COFFRAGE_POUTRE"
                        else:
                            e1 = ms.AddLine(_v6([bm.p1[0], y1, 0.0]),
                                            _v6([bm.p2[0], y2, 0.0]))
                            e1.Layer = "SC_COFFRAGE_POUTRE"
                        counts["beams"] += 1
                        counts["entities"] += 1
                    except Exception as exc:
                        errors.append(f"{bm.sc_id}: "
                                      f"{type(exc).__name__}")
                counts["levels"] += 1
                y_off += 10.0      # décalage inter-niveaux (m)
            doc.Regen(1)
            self._last_doc = doc
            if out_path:
                self.save_document(doc, out_path)
        except Exception as exc:
            return OpReport("write_coffrage", "ERROR", source=self.name,
                            objects=counts, message=str(exc))
        status = "OK" if not errors else "PARTIAL"
        msg = (f"{counts['levels']} niveau(x), {counts['columns']} "
               f"poteau(x), {counts['beams']} poutre(s) — géométrie seule "
               f"(textes non supportés, §19)"
               if not errors else
               f"{len(errors)} élément(s) non écrit(s) : "
               + "; ".join(errors[:5]))
        return OpReport("write_coffrage", status, source=self.name,
                        objects=counts, message=msg)

    # ------------------------------------------------------------------
    # LECTURE : AutoCAD -> pivot (VÉRIFIÉ)
    # ------------------------------------------------------------------
    def read_model(self, project: Any, document: Any = None) -> OpReport:
        """
        Lit les entités SC_* de ModelSpace vers le pivot.

        document : objet COM doc à lire (défaut : Documents.Item(0)).
        L'identité du document lu (Name/FullName) est TOUJOURS rapportée :
        avec plusieurs documents ouverts, jamais de lecture silencieuse du
        mauvais fichier.

        Interprétation honnête par calque (aucune géométrie inventée) :
          - SC_BEAM (AcDbLine)      -> poutres (nœuds créés si absents)
          - SC_COLUMN (AcDbPolyline)-> poteaux au centroïde
          - SC_SLAB (AcDbPolyline)  -> dalles (sommets)
          - autres calques          -> IGNORÉS et COMPTE rapportés
        Un Handle non résolvable n'est jamais transformé en succès.
        """
        if not self._connected:
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Non connecté (connect() requis).")
        doc = document
        if doc is None:
            try:
                doc = self.app.Documents.Item(0) if self.app.Documents.Count \
                    else None
            except Exception as exc:
                return OpReport("read_model", "ERROR", source=self.name,
                                message=f"Accès document : {exc}")
        if doc is None:
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Aucun document ouvert.")
        try:
            _dname = str(getattr(doc, "Name", "") or "")
        except Exception:
            _dname = ""
        try:
            _dfull = str(getattr(doc, "FullName", "") or "")
        except Exception:
            _dfull = ""
        doc_id = _dfull or _dname or "<document sans nom>"

        counts = {"nodes": 0, "columns": 0, "beams": 0, "slabs": 0,
                  "ignored": 0}
        errors: List[str] = []
        try:
            ms = doc.ModelSpace
            n = ms.Count
        except Exception as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"ModelSpace : {exc}")

        # index des SC-* déja présents -> réutilisation
        # déduplication contre le VRAI dict (un dict vide est falsy ->
        # `or {}` détacherait le conteneur et casserait la dédup)
        existing_nodes = getattr(project, "nodes", None)
        if not isinstance(existing_nodes, dict):
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Pivot sans conteneur `nodes` (dict).")

        def ensure_node(x: float, y: float) -> str:
            """Nœud par coordonnée (dédupliqué) -> SC-NODE-*."""
            for nid, nd in existing_nodes.items():
                try:
                    if (not nd.x.is_missing and not nd.y.is_missing
                            and abs(float(nd.x.value) - x) < 1e-6
                            and abs(float(nd.y.value) - y) < 1e-6):
                        return nid
                except Exception:
                    continue
            node = project.new_node(x, y, 0.0)
            existing_nodes[node.sc_id] = node
            counts["nodes"] += 1
            return node.sc_id

        for i in range(n):
            try:
                ent = ms.Item(i)
                oname = str(ent.ObjectName)
                layer = str(ent.Layer)
            except Exception as exc:
                errors.append(f"ent#{i}: {type(exc).__name__}")
                continue

            if not layer.startswith(SC_PREFIX):
                counts["ignored"] += 1
                continue

            if oname == "AcDbLine" and layer == LAYER_BEAM:
                try:
                    sp, ep = tuple(ent.StartPoint), tuple(ent.EndPoint)
                    n1 = ensure_node(float(sp[0]), float(sp[1]))
                    n2 = ensure_node(float(ep[0]), float(ep[1]))
                    bid = project.allocator.new("BEAM")
                    from ...core.model import Beam
                    b = Beam(sc_id=bid, start_node=n1, end_node=n2)
                    project.beams[bid] = b
                    counts["beams"] += 1
                except Exception as exc:
                    errors.append(f"line#{i}: {type(exc).__name__}")

            elif oname in ("AcDbPolyline", "AcDb2dPolyline"):
                try:
                    # Points d'insertion : propriété non sondée pour poly ->
                    # on tente puis on signale sans inventer.
                    pts = self._poly_points(ent)
                    if pts is None:
                        errors.append(f"poly#{i}: géométrie non lisible "
                                      f"(propriété non vérifiée)")
                        continue
                    if layer == LAYER_SLAB:
                        sid = project.allocator.new("SLAB")
                        from ...core.model import Slab
                        node_ids = [ensure_node(px, py) for px, py in pts]
                        s = Slab(sc_id=sid, node_ids=node_ids)
                        project.slabs[sid] = s
                        counts["slabs"] += 1
                    elif layer == LAYER_COLUMN:
                        cx = sum(p[0] for p in pts) / len(pts)
                        cy = sum(p[1] for p in pts) / len(pts)
                        ensure_node(cx, cy)
                        counts["columns"] += 1
                    else:
                        counts["ignored"] += 1
                except Exception as exc:
                    errors.append(f"poly#{i}: {type(exc).__name__}")
            else:
                counts["ignored"] += 1

        status = "OK" if not errors else "PARTIAL"
        total_sc = counts["beams"] + counts["columns"] + counts["slabs"]
        if errors:
            body = (f"{len(errors)} entité(s) non traitée(s) : "
                    + "; ".join(errors[:5]))
        elif total_sc == 0:
            body = ("aucune entité SC_* : 0 objet structurel importé "
                    "(hors calques STRUCTCALC, rien n'est inventé)")
        else:
            body = "entités SC_* importées"
        return OpReport(
            "read_model", status, source=self.name, objects=counts,
            message=f"document lu : {doc_id} ; {body}")

    @staticmethod
    def _poly_points(ent) -> Optional[Tuple[Tuple[float, float], ...]]:
        """
        Sommets d'une polyligne. Le getter exact (Coordinates /
        GetExtensionDictionary...) N'EST PAS VÉRIFIÉ : on essaie les deux
        formes documentées et on renvoie None si aucune ne marche — jamais
        de géométrie inventée.
        """
        for attr in ("Coordinates", "coordinates"):
            try:
                raw = getattr(ent, attr)
                vals = list(raw)
                if len(vals) >= 4:
                    # forme plate [x1,y1,x2,y2,...]
                    if len(vals) % 2 == 0 and not isinstance(vals[0], tuple):
                        return tuple((float(vals[k]), float(vals[k + 1]))
                                     for k in range(0, len(vals), 2))
                    # forme [(x,y), ...]
                    return tuple((float(p[0]), float(p[1])) for p in vals)
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    def _ensure_layer(self, layers, lname: str) -> None:
        """Calque idempotent (Add déjà existant lève une erreur gérée)."""
        try:
            layers.Item(lname)
        except Exception:
            try:
                layers.Add(lname)
            except Exception:
                pass
