# -*- coding: utf-8 -*-
"""
interop/plan.py — Plan du modèle Robot : niveaux, cas de charge, charges,
sections, matériaux, appuis et classification des barres — lus par RobotOM
puis échangés Robot->Plan (demande utilisateur v1.3 : TOUS les éléments
structurels repris dans le programme).

Membres RobotOM UTILISÉS — tous VÉRIFIÉS en live
(tools/probe_plan_elements_live.py + probe_labels_bars_supports_live.py +
probe_bar_material_live.py, 20/10/2026) et enums lues dans robotom.tlb
(fichier gen_py) :
  - structure.Storeys (IRobotStoreyMngr) : len(), Get(i) -> Name/Level/Height
  - structure.Cases.GetAll().Count ; Cases.Get(i) -> Number/Name/Nature/Type
  - IRobotSimpleCase.Records (IRobotLoadRecordMngr) : Count, Get(i) ->
    IRobotLoadRecord {Type, Description, Objects.ToText(), GetValue(id)}
    — accessibles via REJEU DYNAMIQUE (le wrapper typé IRobotCase n'expose
    pas Records : constaté live « object has no attribute 'Records' » ;
    la chaîne prouvée loads.py passait déjà par la liaison tardive).
  - structure.Labels.GetAvailableNames(type) : IRobotNamesArray lu en
    Count/Get(i) — l'itération Python lève « This object does not support
    enumeration » (constaté live, v1.3.1) ; I_LT_NODE_SUPPORT=0,
    I_LT_BAR_SECTION=3, I_LT_BAR_MATERIAL=8
  - collection TYPÉE Bars.GetAll().Get(i) : barres 108/108 sur la villa
    (l'ancien serveur.Get(i) 1..Count rate les numéros gapés/hors range :
    78/108 classées — constaté live, v1.3.1)
  - bar.GetLabelName(3) -> nom de section RÉEL (ex. « C R30x30 ») ;
    bar.GetLabelName(8) -> matériau PORTÉ RÉEL (ex. « BETON25 »,
    108/108 barres villa — sondé live v1.3.1)
  - structure.Bars.GetStructuralType(n) -> I_OST_* (TLB) :
    UNDEFINED=0, BEAM=1, COLUMN=2, SLAB=4, WALL=5, GIRDER=6
  - node.GetLabelName(0) -> nom d'appui RÉEL (« Encastrement » ; com_error
    « Robot.Node - No label » = nœud SANS appui, normal) — voie primaire.
    Nodes.HasCalcSupport(n) existe mais renvoie TOUJOURS False sur la
    villa même avec appui (signal mort, v1.3.1) -> reste secondaire.

Honnêteté (spec §5/§6/§19) :
  - Lecture seule ; `apply_plan` = vérification d'identité (diff nul requis),
    AUCUNE écriture Robot, aucun save ;
  - valeurs de charge : index de valeur VÉRIFIÉ UNIQUEMENT pour
    I_LRT_BAR_UNIFORM (GetValue(2)=Fz, kN/m — chaîne prouvée loads.py) ;
    pour tout autre type : valeur MANQUANTE (jamais devinée), la
    description réelle de Robot reste dans `ref` (preuve).

Identifiants : SC-PLAN-*, SC-STOREY-*, SC-LOADCASE-*, SC-LOAD-*,
SC-SEC-*, SC-MAT-*, SC-SUPPORT-R* (stables, non denses — villa).
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...core.model import (CrossSection, ExternalRef, Load, LoadCase,
                           Material, Storey, Support)
from ...core.tracked import DataStatus, Provenance, TrackedValue
from ..robot.model import iter_objects
from .base import OpReport

_log = logging.getLogger("structcalc.interop.plan")

# ---------------------------------------------------------------------------
# Enums RobotOM — VALEURS LUES dans robotom.tlb (gen_py, 27.0) et confirmées
# par sondage live. Ne pas les deviner (spec §19).
# ---------------------------------------------------------------------------

# IRobotObjectStructuralType (Bars.GetStructuralType)
OST_UNDEFINED = 0
OST_BEAM = 1
OST_COLUMN = 2
OST_SLAB = 4
OST_WALL = 5
OST_GIRDER = 6
OST_LABELS = {OST_UNDEFINED: "undefined", OST_BEAM: "beam",
              OST_COLUMN: "column", OST_SLAB: "slab", OST_WALL: "wall",
              OST_GIRDER: "girder"}

# IRobotCaseNature (case.Nature)
CN_PERMANENT = 0
CN_EXPLOATATION = 1
CN_WIND = 2
CN_SNOW = 3
CN_TEMPERATURE = 4
CN_ACCIDENTAL = 5
CN_SEISMIC = 6
CASE_KINDS = {CN_PERMANENT: "dead", CN_EXPLOATATION: "live", CN_WIND: "wind",
              CN_SNOW: "snow", CN_TEMPERATURE: "temperature",
              CN_ACCIDENTAL: "accidental", CN_SEISMIC: "seismic"}

# IRobotLabelType (Labels.GetAvailableNames / GetLabelName)
LT_NODE_SUPPORT = 0
LT_BAR_SECTION = 3
LT_BAR_MATERIAL = 8

# IRobotLoadRecordType — types courants (TLB) ; valeur lisible seulem. pour
# BAR_UNIFORM (index 2 = Fz VÉRIFIÉ, loads.py).
LRT_BAR_UNIFORM = 5
LRT_KINDS = {
    0: "node_force", 1: "node_displacement", 2: "bar_dilatation",
    3: "bar_force_concentrated", 4: "bar_moment_distributed",
    5: "bar_uniform", 6: "bar_trapezoidale", 7: "bar_dead",
    8: "bar_thermal", 10: "node_velocity", 11: "node_acceleration",
    19: "linear_3d", 20: "node_auxiliary", 21: "linear",
    22: "in_3_points", 23: "node_force_in_point", 24: "pressure",
    25: "thermal_in_3_points", 26: "uniform", 28: "in_contour",
    30: "node_force_mass", 33: "bar_force_concentrated_mass",
    35: "bar_uniform_mass", 36: "bar_trapezoidale_mass",
    39: "mass_activation", 40: "spectrum_value",
    53: "mobile_point_force", 55: "mobile_distributed",
    69: "linear_on_edges", 70: "surface_on_object",
}
BAR_UNIFORM_UNIT = "kN/m"       # unité de la chaîne prouvée (kN, local z)

# Tolérance de verticale pour la déduction géométrique (m)
VERTICAL_TOL = 1e-6


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _tv(value: float, unit: str) -> TrackedValue:
    return TrackedValue.of(float(value), unit, DataStatus.IMPORTED,
                           Provenance.provided_by("Robot (RobotOM)"))


def _missing(unit: str = "") -> TrackedValue:
    return TrackedValue.missing(unit)


def _label_names(coll: Any) -> List[str]:
    """
    Noms d'une IRobotNamesArray (Labels.GetAvailableNames) :

    forme RÉELLE = Count/Get(i) 1-based (sondage live 20/10 — l'itération
    Python lève « This object does not support enumeration » et avait fait
    échouer tout le bloc labels en live, v1.3.0). Repli itération Python
    pour les piles de test (list) ; en dernier recours liste vide + trace.
    """
    try:
        n = int(coll.Count)
    except Exception:
        try:
            return [str(x) for x in coll]
        except Exception as exc:
            _log.warning("labels : collection illisible (%s)", exc)
            return []
    try:
        return [str(coll.Get(i)) for i in range(1, n + 1)]
    except Exception:
        try:
            return [str(x) for x in coll]
        except Exception as exc:
            _log.warning("labels Count=%s mais Get(i)/itération KO (%s)",
                         n, exc)
            return []


def _project_name(rc: Any) -> str:
    try:
        return str(rc.project.FileName or "")
    except Exception:
        return ""


def _records_mngr(case: Any) -> Optional[Any]:
    """
    Manager des records d'un cas (IRobotLoadRecordMngr), via rejeu DYNAMIQUE
    (wrapper typé IRobotCase sans Records — constaté live). Renvoie None si
    le cas n'expose pas de records (combinaison, cas mobile…).
    """
    try:
        import win32com.client.dynamic as _dyn
        dyn_case = _dyn.Dispatch(case._oleobj_)
        return dyn_case.Records
    except Exception:
        return None


@dataclass
class ModelPlan:
    """Plan du modèle tel que lu dans Robot (lecture seule, données réelles)."""
    plan_id: str = ""
    plan_name: str = ""
    storeys: Dict[str, Storey] = field(default_factory=dict)
    load_cases: Dict[str, LoadCase] = field(default_factory=dict)
    case_numbers: Dict[str, int] = field(default_factory=dict)   # SC -> Robot
    loads: Dict[str, Load] = field(default_factory=dict)
    sections: Dict[str, CrossSection] = field(default_factory=dict)   # par nom
    materials: Dict[str, Material] = field(default_factory=dict)      # par nom
    supports: Dict[int, Support] = field(default_factory=dict)        # par nœud
    bar_types: Dict[int, Tuple[int, str]] = field(default_factory=dict)  # n -> (OST, section)
    bar_materials: Dict[int, str] = field(default_factory=dict)   # n -> matériau PORTÉ (GetLabelName(8))
    sources: Dict[str, ExternalRef] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def counts(self) -> Dict[str, int]:
        ncol = sum(1 for st, _ in self.bar_types.values() if st == OST_COLUMN)
        nbeam = sum(1 for st, _ in self.bar_types.values()
                    if st in (OST_BEAM, OST_GIRDER))
        return {"storeys": len(self.storeys), "load_cases": len(self.load_cases),
                "loads": len(self.loads), "sections": len(self.sections),
                "materials": len(self.materials), "supports": len(self.supports),
                "bars": len(self.bar_types), "columns": ncol, "beams": nbeam}


def collect_plan(rc: Any, source: str = "Robot") -> ModelPlan:
    """
    Collecte complète du plan : lecture seule RobotOM. Chaque sous-système
    échoue indépendamment (avertissement honnête, jamais d'erreur masquée).
    """
    t0 = time.perf_counter()
    name = _project_name(rc)
    base = os.path.splitext(os.path.basename(name))[0] if name else ""
    base = re.sub(r"[^0-9A-Za-z_.-]+", "-", base).strip("-")
    plan_id = f"SC-PLAN-{base}" if base else f"SC-PLAN-R{int(time.time())}"
    plan = ModelPlan(plan_id=plan_id, plan_name=name or "(projet sans nom)")
    S = rc.structure

    # -- Niveaux (IRobotStoreyMngr) ----------------------------------------
    try:
        mn = S.Storeys
        for idx in range(1, len(mn) + 1):
            st_obj = mn.Get(idx)
            sname = str(st_obj.Name or f"Niveau {idx}")
            st = Storey(sc_id=f"SC-STOREY-{idx}", name=sname,
                        notes=f"lu via RobotOM ({source}, lecture seule)")
            st.level = _tv(_f(st_obj.Level), "m")
            st.height_above = _tv(_f(st_obj.Height), "m")
            plan.storeys[st.sc_id] = st
    except Exception as exc:
        plan.warnings.append(f"storeys: {exc}")

    # -- Cas de charge (IRobotCaseServer) ----------------------------------
    case_by_number: Dict[int, str] = {}
    try:
        cases = S.Cases
        n = int(cases.GetAll().Count)
        k = 0
        for i in range(1, n + 1):
            c = cases.Get(i)
            num = int(c.Number)
            nature = int(c.Nature)
            sc = f"SC-LOADCASE-{k}"
            k += 1
            lc = LoadCase(sc_id=sc, name=str(c.Name or f"cas {num}"),
                          kind=CASE_KINDS.get(nature, ""),
                          nature=f"IRobotCaseNature={nature}",
                          notes=f"lu via RobotOM ({source}, lecture seule)")
            plan.load_cases[sc] = lc
            plan.case_numbers[sc] = num
            case_by_number[num] = sc

            # -- Charges du cas (records) — rejeu dynamique ----------------
            recs = _records_mngr(c)
            if recs is None:
                continue
            try:
                nrec = int(recs.Count)
            except Exception:
                nrec = 0
            for j in range(1, nrec + 1):
                try:
                    rec = recs.Get(j)
                    rtype = int(rec.Type)
                    desc = str(getattr(rec, "Description", "") or "")
                    try:
                        objs = str(rec.Objects.ToText() or "")
                    except Exception:
                        objs = ""
                    value: Optional[float] = None
                    unit = ""
                    if rtype == LRT_BAR_UNIFORM:
                        # index 2 = Fz : SEUL index VÉRIFIÉ (loads.py)
                        value = _f(rec.GetValue(2))
                        unit = BAR_UNIFORM_UNIT
                    lsc = f"SC-LOAD-{num}-{j}"
                    ld = Load(sc_id=lsc, case_sc_id=case_by_number.get(num, ""),
                              kind=LRT_KINDS.get(rtype, f"type_{rtype}"),
                              value=(_tv(value, unit) if value is not None
                                     else _missing(unit)),
                              unit=unit, target="robot",
                              ref=(desc + (f" | objets: {objs}" if objs else "")
                                   ).strip(" |"),
                              notes=f"lu via RobotOM ({source}, lecture seule)")
                    plan.loads[lsc] = ld
                except Exception as exc:
                    plan.warnings.append(f"load {num}/{j}: {exc}")
    except Exception as exc:
        plan.warnings.append(f"load_cases: {exc}")

    # -- Sections / matériaux définis / appuis (Labels.GetAvailableNames) --
    #    v1.3.1 : IRobotNamesArray se lit en Count/Get(i) — l'itération
    #    Python échouait en live (« does not support enumeration ») et
    #    faisait tomber TOUT le bloc (materials=0, sections perdues).
    try:
        lab = S.Labels
        for nm in _label_names(lab.GetAvailableNames(LT_BAR_SECTION)):
            if nm not in plan.sections:
                plan.sections[nm] = CrossSection(
                    sc_id=f"SC-SEC-{nm}", name=nm, kind=nm,
                    notes=f"label de section DÉFINI dans le projet"
                          f" (RobotOM {source}, lecture seule)")
                # dimensions : non lues via le label -> TrackedValue MISSING
        # Matériaux : UNIQUEMENT ceux PORTÉS par des barres (GetLabelName(8)
        # dans le bloc barres) — GetAvailableNames(LT_BAR_MATERIAL) rend la
        # bibliothèque par défaut Robot (136 noms live : ALUM, BOIS, KERTO…),
        # ce n'est PAS la matière du projet -> jamais présenté comme telle.
        for i, nm in enumerate(_label_names(
                lab.GetAvailableNames(LT_NODE_SUPPORT))):
            plan.sources[f"SC-SRC-SUP-{i}"] = ExternalRef(
                software="Robot", external_id=str(nm))
    except Exception as exc:
        plan.warnings.append(f"labels: {exc}")

    # -- Barres : type structurel RÉEL (I_OST_*) + section + matériau -----
    #    v1.3.1 : collection TYPÉE GetAll().Get(i) (108/108 barres villa en
    #    live, dont numéros 109-138 ; l'ancien serveur.Get(i) 1..Count
    #    n'en classait que 78 — gaps 3,4,31-52 + hors range).
    try:
        bars = S.Bars
        for br in iter_objects(bars):
            try:
                bnum = int(br.Number)
            except Exception:
                continue
            try:
                st_int = int(bars.GetStructuralType(bnum))
            except Exception:
                st_int = OST_UNDEFINED
            sec = ""
            try:
                sec = str(br.GetLabelName(LT_BAR_SECTION) or "")
            except Exception:
                pass
            mat = ""
            try:
                mat = str(br.GetLabelName(LT_BAR_MATERIAL) or "")
            except Exception:
                pass
            plan.bar_types[bnum] = (st_int, sec)
            if mat:
                plan.bar_materials[bnum] = mat
            if sec and sec not in plan.sections:
                plan.sections[sec] = CrossSection(
                    sc_id=f"SC-SEC-{sec}", name=sec, kind=sec,
                    notes=f"section portée par une barre, lue via RobotOM "
                          f"({source}, lecture seule)")
            if mat:
                m = plan.materials.get(mat)
                if m is None:
                    plan.materials[mat] = Material(
                        sc_id=f"SC-MAT-{mat}", name=mat, kind="",
                        notes=f"matériau PORTÉ par une barre"
                              f" (GetLabelName(8), RobotOM {source},"
                              f" lecture seule)")
                elif "PORTÉ" not in m.notes:
                    m.notes = (f"matériau PORTÉ par des barres"
                               f" (utilisé dans le modèle ; défini dans"
                               f" Robot) — RobotOM {source}, lecture seule")
    except Exception as exc:
        plan.warnings.append(f"bars: {exc}")

    # -- Appuis de nœud : label RÉEL (« Encastrement »…) ------------------
    #    v1.3.1 : le sondage live prouve que Nodes.HasCalcSupport(n)
    #    renvoie TOUJOURS False sur la villa même avec appui (signal mort)
    #    ; la voie primaire est node.GetLabelName(I_LT_NODE_SUPPORT=0),
    #    qui lève « Robot.Node - No label » (com_error ATTENDUE) sur un
    #    nœud sans appui. HasCalcSupport reste signal secondaire.
    try:
        nodes = S.Nodes
        for nd in iter_objects(nodes):
            try:
                nnum = int(nd.Number)
            except Exception:
                continue
            sname = ""
            try:
                sname = str(nd.GetLabelName(LT_NODE_SUPPORT) or "")
            except Exception as exc:
                if "No label" not in str(exc):
                    plan.warnings.append(
                        f"node {nnum} GetLabelName: {exc}")
            has_calc = False
            try:
                has_calc = bool(nodes.HasCalcSupport(nnum))
            except Exception:
                has_calc = False
            if not sname and not has_calc:
                continue
            if sname:
                note = (f"appui « {sname} » lu par node.GetLabelName(0)"
                        f" (RobotOM {source}, lecture seule)")
            else:
                note = (f"appui détecté par Nodes.HasCalcSupport"
                        f" (RobotOM {source}, lecture seule) — nom de"
                        f" label non lu")
            plan.supports[nnum] = Support(
                sc_id=f"SC-SUPPORT-R{nnum}", name=sname, kind="robot",
                notes=note)
    except Exception as exc:
        plan.warnings.append(f"supports: {exc}")

    # -- Sources : sections/matières deviennent des ExternalRef ------------
    for i, nm in enumerate(plan.sections):
        plan.sources[f"SC-SRC-SEC-{i}"] = ExternalRef(
            software="Robot", external_id=str(nm))
    for i, nm in enumerate(plan.materials):
        plan.sources[f"SC-SRC-MAT-{i}"] = ExternalRef(
            software="Robot", external_id=str(nm))

    ms = (time.perf_counter() - t0) * 1000.0
    c = plan.counts
    _log.info(
        "interop.robot.plan collecte %s: %s niveau(x), %s cas, %s charge(s), "
        "%s section(s), %s matériau(x), %s appui(s), %s barre(s) (%s poteau(x), "
        "%s poutre(s)) [%.0f ms]%s",
        plan_id, c['storeys'], c['load_cases'], c['loads'], c['sections'],
        c['materials'], c['supports'], c['bars'], c['columns'], c['beams'], ms,
        f" ; avertissements: {'; '.join(plan.warnings)}" if plan.warnings else "")
    return plan


def apply_plan(rc: Any, plan: ModelPlan) -> OpReport:
    """
    Vérifie que le plan échangé correspond EXACTEMENT à l'état courant de
    Robot (diff nul requis) — sans aucune écriture Robot. Dérive -> REFUSED
    motivé : l'échange s'arrête proprement (spec §5.4).
    """
    t0 = time.perf_counter()
    if not plan.plan_id:
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Plan vide ou non fourni.")
    try:
        real = collect_plan(rc, source="Robot")
    except Exception as exc:
        return OpReport("apply_plan", "ERROR", source="Robot",
                        message=f"Lecture du plan Robot : {exc}")

    # -- Niveaux ------------------------------------------------------------
    rn = {st.name for st in real.storeys.values()}
    pn = {st.name for st in plan.storeys.values()}
    if rn != pn:
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Niveaux modifiés depuis l'échange "
                                f"(Robot={sorted(rn)}, plan={sorted(pn)}).")

    # -- Cas de charge (numéros + noms réels) -------------------------------
    rc_set = {(int(v), real.load_cases[k].name)
              for k, v in real.case_numbers.items()}
    pc_set = {(int(v), plan.load_cases[k].name)
              for k, v in plan.case_numbers.items()}
    if rc_set != pc_set:
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Cas de charge modifiés depuis l'échange "
                                f"(Robot={sorted(rc_set)}, plan={sorted(pc_set)}).")

    # -- Charges (identité exacte : cas, type, valeur, description) ---------
    def _lkey(ld: Load):
        return (ld.case_sc_id, ld.kind,
                None if ld.value.is_missing else ld.value.value, ld.ref)
    if {_lkey(v) for v in real.loads.values()} != {_lkey(v) for v in plan.loads.values()}:
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Charges modifiées depuis l'échange "
                                f"(Robot={len(real.loads)}, "
                                f"plan={len(plan.loads)}).")

    # -- Sections / matériaux ----------------------------------------------
    if set(real.sections) != set(plan.sections):
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Sections modifiées depuis l'échange "
                                f"(Robot={sorted(real.sections)}, "
                                f"plan={sorted(plan.sections)}).")
    if set(real.materials) != set(plan.materials):
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Matériaux modifiés depuis l'échange "
                                f"(Robot={sorted(real.materials)}, "
                                f"plan={sorted(plan.materials)}).")

    # -- Appuis + classification des barres --------------------------------
    if set(real.supports) != set(plan.supports):
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Appuis modifiés depuis l'échange "
                                f"(Robot={sorted(real.supports)}, "
                                f"plan={sorted(plan.supports)}).")
    if real.bar_types != plan.bar_types:
        return OpReport("apply_plan", "REFUSED", source="Robot",
                        message="Barres modifiées depuis l'échange "
                                f"(Robot={len(real.bar_types)} barre(s), "
                                f"plan={len(plan.bar_types)}).")

    ms = (time.perf_counter() - t0) * 1000.0
    c = plan.counts
    _log.info("interop.robot.plan apply %s: identique (%s niveau(x), %s cas, "
              "%s charge(s)) [%.0f ms]", plan.plan_id, c['storeys'],
              c['load_cases'], c['loads'], ms)
    return OpReport("apply_plan", "OK", source="Robot",
                    objects=plan.counts,
                    message=f"Plan identique à Robot (diff nul, aucune "
                            f"écriture) : {c['storeys']} niveau(x), "
                            f"{c['load_cases']} cas, {c['loads']} charge(s), "
                            f"{c['sections']} section(s), {c['materials']} "
                            f"matériau(x), {c['supports']} appui(s), "
                            f"{c['bars']} barre(s).")
