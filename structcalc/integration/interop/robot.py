# -*- coding: utf-8 -*-
"""
integration/interop/robot.py — Adaptateur Robot dans l'architecture en étoile.

Ce module est la COUCHE PIVOT de l'interconnexion réciproque : il traduit le
modèle interne SC-* (Project) vers/depuis le format dictionnaire neutre que
`integration/robot/model.py` sait déjà écrire/lire dans Robot (voies VÉRIFIÉES
Phase 0/2).

Vérité des opérations (spec §19) — repris de integration/robot/ :
  - connection.py : connect/new_project/close (VERIFIE Phase 0)
  - model.py      : import_nodes/import_bars, export_nodes/export_bars,
                    count_nodes/count_bars, verify_transfer (VERIFIE)
  - results.py    : import_reactions/import_displacements/import_bar_forces
                    (VERIFIE, arbre sondé)
  - loads.py      : export_dead_load_case/list_cases/apply_uniform_bar_load/
                    calculate (VERIFIE) ; create_combination -> LEVE
                    (NON VERIFIE en Phase 2)

Mapping (règle §4.1 : IDs stables, aucune perte) :
    SC-NODE-000001  <->  numéro Robot dense 1..N (table _node_numbers)
    SC-BEAM-000001  <->  barre Robot dense 1..M (table _bar_numbers)

Le pivot garde la vérité : on n'écrit dans Robot QUE ce qui existe dans le
Project, et on ne crée dans le Project QUE ce qui existe dans Robot.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..interop.base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)
from ...core.model import Beam, Column, Node
from ...core.status import DataStatus
from ...core.tracked import Provenance


class RobotConnector(AutodeskConnector):
    """
    Pont Robot Structural Analysis <-> pivot SC-*.

    Usage :
        rc = RobotConnector()
        rc.detect()          # registre, sans lancer Robot
        rc.connect()         # ouvre Robot (COM vérifié)
        rc.write_model(project)
        rc.disconnect()
    """

    name = "robot"
    label = "Autodesk Robot Structural Analysis"

    PROGIDS = ("Robot.Application", "Robot.Application.1")
    REG_LOCALSERVER = r"CLSID\{CLSID}\LocalServer32"

    def __init__(self, visible: bool = True, attach_only: bool = False,
                 new_project_type: int = 4):
        # 4 = I_PT_FRAME_3D (vérifie Phase 0) ; 1 = FRAME_2D
        self.visible = visible
        self.attach_only = attach_only
        self.new_project_type = new_project_type
        self._rc = None
        # Tables de correspondance SC-* <-> numéros Robot (§4.1)
        self._node_numbers: Dict[str, int] = {}
        self._bar_numbers: Dict[str, int] = {}
        self._numbers_node: Dict[int, str] = {}
        self._numbers_bar: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Détection (registre, sans lancer Robot)
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        progs: List[str] = []
        local_servers: List[str] = []
        try:
            import winreg
        except ImportError:  # pragma: no cover
            return Detection(name=self.name, installed=False, transport="com",
                             automatable=False,
                             detail="winreg indisponible (non-Windows)")
        for pid in self.PROGIDS:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    pid + r"\CLSID") as k:
                    clsid = winreg.QueryValueEx(k, "")[0]
                progs.append(pid)
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
            # chemin type "...\Robot\Exe\RobotStructure.exe" (pas de version)
            for token in ls.replace("/", "\\").split("\\"):
                for word in token.split():
                    if word.isdigit() and len(word) >= 3:
                        version = word
                        break
                if version:
                    break

        return Detection(
            name=self.name, installed=bool(progs), version=version,
            progs=progs, transport="com", automatable=bool(progs),
            detail=("COM Robot disponible (Phase 0 vérifié)" if progs else
                    "Aucun ProgID Robot dans le registre"),
        )

    # ------------------------------------------------------------------
    # Capacités (§19)
    # ------------------------------------------------------------------
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Registre ProgID Robot.Application (Phase 0)"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.SUPPORTED,
                "RobotConnection.connect + new_project (Phase 0 vérifié)"),
            Capability.READ_MODEL: CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.SUPPORTED,
                "model.import_nodes/import_bars (GetAll/Get, Phase 0)"),
            Capability.WRITE_MODEL: CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.SUPPORTED,
                "model.export_nodes/export_bars (Create, Phase 0)"),
            Capability.READ_RESULTS: CapabilityReport(
                Capability.READ_RESULTS, CapabilityStatus.SUPPORTED,
                "results.import_reactions/displacements/bar_forces (sondé)"),
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.PARTIAL,
                "loads: cas mort/uni/calculate OK ; "
                "create_combination NON VERIFIE -> leve (§19)"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Robot n'est pas un outil de dessin bidirectionnel ici"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Même raison : pas de pont plan Robot vérifié"),
        }

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    def connect(self, timeout: float = 180.0) -> "RobotConnector":
        from ..robot.connection import RobotConnection
        rc = RobotConnection(visible=self.visible,
                             attach_only=self.attach_only)
        rc.connect(timeout=timeout)
        self._rc = rc
        return self

    @property
    def connected(self) -> bool:
        return self._rc is not None

    @property
    def rc(self):
        if self._rc is None:
            raise InteropError(
                "[robot] Non connecté : connect() d'abord (§19, "
                "aucun accès silencieux).")
        return self._rc

    def disconnect(self) -> None:
        if self._rc is not None:
            try:
                self._rc.disconnect()   # fermeture sans sauvegarde (§5.4)
            except Exception:
                pass
            self._rc = None

    def ensure_project(self) -> None:
        """
        Ouvre un projet Robot si aucun n'est ouvert (nécessaire I/O).

        Un projet live ouvert par une AUTRE session (votre travail dans
        Robot) est ADOPTÉ pour la LECTURE seule : `opened_by_us` reste faux,
        donc toute écriture reste refusée avec son motif (§5.4). Avant ce
        correctif, la lecture levait « Aucun projet ouvert » alors qu'un
        projet était bel et bien ouvert (incohérence constatée live : le
        projet vivait dans l'application mais pas dans CETTE session).
        """
        rc = self.rc
        if rc.is_project_open:
            if not rc.opened_by_us:
                rc.adopt_live_project()
            return
        rc.new_project(self.new_project_type)

    # ------------------------------------------------------------------
    # ECRITURE : pivot -> Robot
    # ------------------------------------------------------------------
    def write_model(self, project: Any) -> OpReport:
        """
        Pousse le Project SC-* dans Robot (nœuds puis barres).

        Ordre imposé par Robot : les barres référencent des nœuds déjà créés.
        Les colonnes et dalles du pivot sont traduits en barres/nœuds ?
        NON : seules les BARRES (poutres) et NŒUDS sont transférés — c'est ce
        que model.export_* sait faire de façon vérifiée. Poteaux/dalles sont
        signalés comme hors périmètre plutôt que perdus silencieusement.
        """
        if not self.connected:
            return OpReport("write_model", "REFUSED", source=self.name,
                            message="Non connecté (connect() requis).")
        # §5.4 : JAMAIS écrire dans un projet ouvert hors de cette session
        # (fermé ici, ou ouvert par l'utilisateur dans Robot) — refus motivé,
        # aucun objet écrit, aucune contamination silencieuse.
        if self.rc.is_project_open and not self.rc.opened_by_us:
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[robot] écriture REFUSÉE : un projet est ouvert "
                         "dans Robot hors de cette session (peut-être votre "
                         "travail) — fermez-le dans Robot avant d'écrire "
                         "(§5.4, aucune modification silencieuse). "
                         "Aucun objet écrit."))
        # Pivot vide -> REFUS (jamais un « succès » à 0 objet, jamais de
        # projet Robot créé pour rien).
        _nd = getattr(project, "nodes", None)
        _bd = getattr(project, "beams", None)
        if not (isinstance(_nd, dict) and _nd) and \
                not (isinstance(_bd, dict) and _bd):
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[robot] écriture REFUSÉE : pivot vide (0 nœud et "
                         "0 barre) — rien à pousser, aucun projet créé."))
        from ..robot import model as rmodel
        try:
            self.ensure_project()
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"Ouverture projet Robot : {exc}")

        nodes = getattr(project, "nodes", {}) or {}
        beams = getattr(project, "beams", {}) or {}

        # -- Table SC-* -> numéro dense Robot (1..N) --
        self._node_numbers.clear()
        self._numbers_node.clear()
        num = 1
        for nid in nodes:
            self._node_numbers[nid] = num
            self._numbers_node[num] = nid
            num += 1

        r_nodes = []
        for nid, nd in nodes.items():
            try:
                if nd.x.is_missing or nd.y.is_missing:
                    return OpReport(
                        "write_model", "REFUSED", source=self.name,
                        message=f"{nid} : coordonnées MANQUANTES — jamais "
                                f"inventées (§4.2).")
                z = 0.0 if nd.z.is_missing else float(nd.z.value)
                r_nodes.append({"number": self._node_numbers[nid],
                                "x": float(nd.x.value),
                                "y": float(nd.y.value), "z": z})
            except Exception as exc:
                return OpReport("write_model", "ERROR", source=self.name,
                                message=f"{nid} : {exc}")

        # -- Barres (poutres) --
        self._bar_numbers.clear()
        self._numbers_bar.clear()
        bnum = 1
        r_bars = []
        skipped: List[str] = []
        for bid, bm in beams.items():
            s, e = bm.start_node, bm.end_node
            if s not in self._node_numbers or e not in self._node_numbers:
                skipped.append(f"{bid}: nœuds d'extrémité absents du pivot")
                continue
            self._bar_numbers[bid] = bnum
            self._numbers_bar[bnum] = bid
            r_bars.append({"number": bnum,
                           "start": self._node_numbers[s],
                           "end": self._node_numbers[e]})
            bnum += 1

        try:
            summary = rmodel.export_model(self.rc,
                                          {"nodes": r_nodes, "bars": r_bars})
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"export_model : {exc}")

        counts = {"nodes": summary.get("nodes", 0),
                  "bars": summary.get("bars", 0),
                  "columns_skipped": len(getattr(project, "columns", {}) or {}),
                  "slabs_skipped": len(getattr(project, "slabs", {}) or {})}
        status = "OK" if not skipped else "PARTIAL"
        msg = "modèle poussé dans Robot"
        if skipped:
            msg = f"{len(skipped)} barre(s) non transférée(s) : " + \
                  "; ".join(skipped[:4])
        if counts["columns_skipped"] or counts["slabs_skipped"]:
            msg += (f" | hors périmètre export vérifié : "
                    f"{counts['columns_skipped']} poteau(x), "
                    f"{counts['slabs_skipped']} dalle(s)")
        return OpReport("write_model", status, source=self.name,
                        target="robot", objects=counts, message=msg)

    # ------------------------------------------------------------------
    # LECTURE : Robot -> pivot
    # ------------------------------------------------------------------
    def read_model(self, project: Any) -> OpReport:
        """
        Tire le modèle Robot dans le Project SC-*.

        Les nœuds/bars importés reçoivent un SC-* stable ; la table de
        correspondance est conservée pour un aller-retour sans doublon.
        """
        if not self.connected:
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Non connecté (connect() requis).")
        from ..robot import model as rmodel
        try:
            # Symétrie avec write_model : la session doit être prête.
            # (un projet vide est alors lu honnêtement : 0 objet rapporté)
            self.ensure_project()
        except Exception as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"Ouverture projet Robot : {exc}")
        try:
            if not self.rc.is_project_open:
                return OpReport("read_model", "REFUSED", source=self.name,
                                message="Aucun projet Robot ouvert.")
            data = rmodel.import_model(self.rc)
        except Exception as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"import_model : {exc}")

        # -- Plan du modèle (niveaux, cas, charges, sections, matériaux,
        #    appuis, classification des barres) : collecte + vérification
        #    d'identité AVANT toute mutation du pivot — dérive -> REFUSED
        #    sans aucune modification (spec §5.4) --
        from . import plan as planmod
        try:
            plan = planmod.collect_plan(self.rc, source=self.name)
            apply_rep = planmod.apply_plan(self.rc, plan)
            if not apply_rep.ok:
                return OpReport("read_model", apply_rep.status,
                                source=self.name,
                                message="Modèle Robot modifié pendant la "
                                        "lecture (plan) : "
                                        + (apply_rep.message or ""))
        except Exception as exc:
            plan = None
            plan_err = str(exc)
        else:
            plan_err = ""

        r_nodes = data.get("nodes", [])
        r_bars = data.get("bars", [])

        # -- Réinitialise les tables --
        self._node_numbers.clear()
        self._numbers_node.clear()
        self._bar_numbers.clear()
        self._numbers_bar.clear()

        counts = {"nodes": 0, "bars": 0, "duplicates": 0}
        prov = Provenance.imported_from("Robot")

        # -- Nœuds : on doit cibler VRAIMENT project.nodes (un dict vide est
        #    falsy -> le motif `or {}` détacherait le conteneur, bug réel) --
        existing = getattr(project, "nodes", None)
        if not isinstance(existing, dict):
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Pivot sans conteneur `nodes` "
                                    "(dict) — objet non exploitable.")
        for rn in r_nodes:
            n = int(rn["number"])
            sc = f"SC-NODE-R{n:06d}"
            self._node_numbers[sc] = n
            self._numbers_node[n] = sc
            if sc in existing:
                counts["duplicates"] += 1
                continue
            node = Node(
                sc_id=sc,
                x=_tv(float(rn["x"]), prov),
                y=_tv(float(rn["y"]), prov),
                z=_tv(float(rn["z"]), prov),
            )
            existing[sc] = node
            counts["nodes"] += 1

        # -- Barres -> Poutre/Poteau (classification RÉELLE par
        #    I_OST_* Robot, TLB 27.0 ; section réelle liée si lue) --
        beams = getattr(project, "beams", None)
        if not isinstance(beams, dict):
            return OpReport("read_model", "REFUSED", source=self.name,
                            message="Pivot sans conteneur `beams` "
                                    "(dict) — objet non exploitable.")
        columns = getattr(project, "columns", None)
        if not isinstance(columns, dict):
            columns = {}
        sec_by_name: Dict[str, str] = {}
        mat_by_name: Dict[str, str] = {}
        if plan is not None:
            for _nm, cs in plan.sections.items():
                sec_by_name.setdefault(cs.name, cs.sc_id)
            for _nm, mt in plan.materials.items():
                mat_by_name.setdefault(mt.name, mt.sc_id)
        for rb in r_bars:
            bn = int(rb["number"])
            sc = f"SC-BEAM-R{bn:06d}"
            self._bar_numbers[sc] = bn
            self._numbers_bar[bn] = sc
            st_int = planmod.OST_UNDEFINED
            sec_name = ""
            if plan is not None:
                st_int, sec_name = plan.bar_types.get(
                    bn, (planmod.OST_UNDEFINED, ""))
            sec_id = sec_by_name.get(sec_name, "") if sec_name else ""
            mat_nm = plan.bar_materials.get(bn, "") if plan is not None else ""
            mat_id = mat_by_name.get(mat_nm, "") if mat_nm else ""
            if sc in beams or f"SC-COL-R{bn:06d}" in columns:
                counts["duplicates"] += 1
                continue
            s = self._numbers_node.get(int(rb["start"]))
            e = self._numbers_node.get(int(rb["end"]))
            if s is None or e is None:
                # nœud d'extrémité non résolvable -> signalé, jamais inventé
                counts.setdefault("unresolved", 0)
                counts["unresolved"] += 1
                continue
            if st_int == planmod.OST_COLUMN:
                columns[f"SC-COL-R{bn:06d}"] = Column(
                    sc_id=f"SC-COL-R{bn:06d}", start_node=s, end_node=e,
                    section=sec_id or None, material=mat_id or None)
                counts["columns"] = counts.get("columns", 0) + 1
            else:
                beams[sc] = Beam(sc_id=sc, start_node=s, end_node=e,
                                 section=sec_id or None,
                                 material=mat_id or None)
                if st_int in (planmod.OST_SLAB, planmod.OST_WALL):
                    # barre typée dalle/mur par Robot : comptée honnêtement,
                    # jamais devinée poutre
                    counts["other_structural"] = \
                        counts.get("other_structural", 0) + 1
            counts["bars"] += 1

        # -- Plan reporté dans le pivot (données RÉELLES, setdefault ;
        #    conteneur absent du pivot -> ignoré honnêtement) --
        def _merge(container_name: str, mapping) -> None:
            cont = getattr(project, container_name, None)
            if not isinstance(cont, dict):
                return
            added = 0
            for obj in mapping.values():
                if cont.setdefault(obj.sc_id, obj) is obj:
                    added += 1
            if added:
                counts[container_name] = counts.get(container_name, 0) + added

        if plan is not None:
            _merge("sections", plan.sections)
            _merge("materials", plan.materials)
            _merge("supports", plan.supports)
            _merge("load_cases", plan.load_cases)
            _merge("loads", plan.loads)
            _merge("storeys", plan.storeys)

        status = "OK" if not counts.get("unresolved") else "PARTIAL"
        msg = "modèle Robot importé"
        if plan is not None:
            pc = plan.counts
            msg += (f" — plan : {pc['storeys']} niveau(x), "
                    f"{pc['load_cases']} cas de charge, {pc['loads']} "
                    f"charge(s), {pc['sections']} section(s), "
                    f"{pc['materials']} matériau(x), {pc['supports']} "
                    f"appui(s), {counts.get('columns', 0)} poteau(x) "
                    f"(I_OST_COLUMN), {pc['beams']} poutre(s)")
            if plan.warnings:
                msg += f" ; avertissements: {'; '.join(plan.warnings)}"
        else:
            msg += f" ; plan NON lu : {plan_err}"
            status = "PARTIAL"
        if counts.get("unresolved"):
            msg += (f" ; {counts['unresolved']} barre(s) avec extrémité(s) "
                    f"non résolvable(s) — ignorée(s) sans invention")
        return OpReport("read_model", status, source="robot",
                        target=getattr(project, "sc_id", ""),
                        objects=counts, message=msg)

    # ------------------------------------------------------------------
    # RESULTATS (capacité séparée, vérifiée Phase 2)
    # ------------------------------------------------------------------
    def read_results(self, project: Any) -> OpReport:
        if not self.connected:
            return self._refuse(Capability.CONNECT)
        from ..robot import results as rres
        try:
            if not rres.results_available(self.rc):
                return OpReport("read_results", "REFUSED", source=self.name,
                                message="Aucun résultat calculé dans Robot "
                                        "(calculate() non exécuté).")
        except Exception as exc:
            return OpReport("read_results", "ERROR", source=self.name,
                            message=f"results_available : {exc}")
        return OpReport("read_results", "OK", source=self.name,
                        message="résultats disponibles (réactions/déplacements/"
                                "efforts vérifiés Phase 2) — lecture ciblée "
                                "à faire par cas de charge.")

    def write_loads(self, project: Any) -> OpReport:
        """Transfert partiel des charges (combinaisons NON vérifiées §19)."""
        if not self.connected:
            return self._refuse(Capability.CONNECT)
        from ..robot import loads as rloads
        try:
            self.ensure_project()
            info = rloads.export_dead_load_case(self.rc)
        except Exception as exc:
            return OpReport("write_loads", "ERROR", source=self.name,
                            message=f"export_dead_load_case : {exc}")
        return OpReport(
            "write_loads", "PARTIAL", source=self.name,
            objects={"dead_case": 1},
            message="cas de charge mort exporté ; combinaisons NON "
                    "transférées (Cases.CreateCombination non vérifié §19).")


def _tv(value: float, prov) -> Any:
    from ...core.tracked import TrackedValue
    return TrackedValue.of(float(value), "m", DataStatus.IMPORTED, prov)
