# -*- coding: utf-8 -*-
"""
integration/robot/results.py — Import des résultats de calcul (spec §5.3).

Arbre des résultats Robot 2027 VÉRIFIÉ par sondage (probe_full_pipeline) :
  - Structure.Results.Available                  [CONFIRMÉ : int]
  - Structure.Results.Nodes.Reactions.Value(n, case)  -> Fx,Fy,Fz,Mx,My,Mz
  - Structure.Results.Nodes.Displacements.Value(n, case)
  - Structure.Results.Bars.Forces.Value(bar, point)   -> nécessite 'Point'

Règle (spec §5.3 « contrôle de la complétude », §19) : les fonctions dont le
chaînage exact n'est pas démontré lèvent RobotResultsError explicite. Les
réactions/déplacements sont lues à un cas donné ; les UNITÉS sont LUES dans
Robot (`get_result_units`, PRUVÉ live) et ATTACHÉES à chaque résultat (§5.3).
"""

from __future__ import annotations

from typing import Optional

from .connection import RobotConnection


class RobotResultsError(Exception):
    """Erreur / statut non vérifié lors de l'import de résultats."""


# ---------------------------------------------------------------------------
# Unités RobotOM — VALEURS lues dans robotom.tlb + PRUVÉES par exécution
# (tools/probe_units_live.py : force=kN, moment=kN, displacement=cm,
#  length=m, stress=MN sur Robot 2027). Ne pas les supposer.
# ---------------------------------------------------------------------------

# IRobotUnitType
UNIT_STRUCTURE_DIMENSION = 1
UNIT_FORCE = 7
UNIT_MOMENT = 8
UNIT_STRESS = 9
UNIT_DISPLACEMENT = 10

_RESULT_UNIT_TYPES = (
    ("force", UNIT_FORCE),
    ("moment", UNIT_MOMENT),
    ("stress", UNIT_STRESS),
    ("displacement", UNIT_DISPLACEMENT),
    ("length", UNIT_STRUCTURE_DIMENSION),
)


def get_result_units(rc: RobotConnection) -> dict:
    """
    Lit les unités courantes de Robot via Preferences.Units.Get(type).Name.

    SIGNATURE PRUVÉE par exécution (tools/probe_units_live.py) :
    renvoie p.ex. {"force": "kN", "moment": "kN", "displacement": "cm",
    "length": "m", "stress": "MN"}. Une unité non lisible est None (INCONNUE,
    jamais supposée — spec §4.2, §5.3).

    Contrôle des unités (spec §5.3) : ces valeurs sont ATTACHÉES aux résultats
    importés pour qu'aucune grandeur ne soit présentée sans son unité réelle.
    """
    if not rc.is_project_open:
        raise RobotResultsError("Aucun projet ouvert.")
    try:
        server = rc.project.Preferences.Units
    except Exception as exc:
        raise RobotResultsError(
            f"Accès au gestionnaire d'unités (Preferences.Units) impossible : {exc}"
        ) from exc
    out = {}
    for key, utype in _RESULT_UNIT_TYPES:
        try:
            data = server.Get(int(utype))
            name = getattr(data, "Name", None)
            out[key] = str(name) if name is not None else None  # None = inconnu
        except Exception:
            out[key] = None   # unité INCONNUE — jamais une valeur inventée
    return out


def results_available(rc: RobotConnection) -> bool:
    """Vrai si Robot expose des résultats (Results.Available != 0)."""
    if not rc.is_project_open:
        raise RobotResultsError("Aucun projet ouvert.")
    return int(rc.structure.Results.Available) != 0


def import_reactions(rc: RobotConnection, case_number: int,
                     node_numbers: Optional[list[int]] = None) -> list[dict]:
    """
    Importe les réactions d'appui pour un cas de charge.

    CONFIRMÉ live (20/10) : Results.Nodes.Reactions.Value(node, case)
    renvoie un IRobotReactionData dont les membres sont en MAJUSCULES
    (FX, FY, FZ, MX, MY, MZ — dir()/_prop_map_get_) ; une lecture en
    minuscules (Fx…) levait une AttributeError avalée et retournait
    None partout (constaté live). Valeurs nulles = nœud non sollicité.

    Retourne une liste de {"node": int, "Fx": float, ..., "units": {...}}.
    Les unités (force, moment) sont LUES dans Robot et ATTACHÉES à chaque
    enregistrement (spec §5.3) — jamais supposées.
    """
    if not rc.is_project_open:
        raise RobotResultsError("Aucun projet ouvert.")
    if not results_available(rc):
        raise RobotResultsError(
            "Aucun résultat disponible (Results.Available = 0). "
            "Lancez d'abord un calcul valide avec des appuis et charges."
        )
    units = get_result_units(rc)
    reac = rc.structure.Results.Nodes.Reactions
    if node_numbers is None:
        node_numbers = _all_node_numbers(rc)
    out = []
    for n in node_numbers:
        try:
            rv = reac.Value(int(n), int(case_number))
        except Exception as exc:
            raise RobotResultsError(
                f"Lecture réaction nœud {n} cas {case_number} échouée : {exc}"
            ) from exc
        out.append({
            "node": int(n),
            "case": int(case_number),
            "Fx": _comp(rv, "Fx"),
            "Fy": _comp(rv, "Fy"),
            "Fz": _comp(rv, "Fz"),
            "Mx": _comp(rv, "Mx"),
            "My": _comp(rv, "My"),
            "Mz": _comp(rv, "Mz"),
            "units": {"force": units["force"], "moment": units["moment"]},
        })
    return out


def import_displacements(rc: RobotConnection, case_number: int,
                         node_numbers: Optional[list[int]] = None) -> list[dict]:
    """
    Importe les déplacements aux nœuds pour un cas de charge.

    CONFIRMÉ : Results.Nodes.Displacements est présent ; Value(node, case)
    supposé identique à Reactions. À valider sur modèle chargé.
    L'unité de déplacement est LUE dans Robot et ATTACHÉE (spec §5.3).
    """
    if not rc.is_project_open:
        raise RobotResultsError("Aucun projet ouvert.")
    if not results_available(rc):
        raise RobotResultsError("Aucun résultat disponible (Available = 0).")
    units = get_result_units(rc)
    disp = rc.structure.Results.Nodes.Displacements
    if node_numbers is None:
        node_numbers = _all_node_numbers(rc)
    out = []
    for n in node_numbers:
        try:
            dv = disp.Value(int(n), int(case_number))
        except Exception as exc:
            raise RobotResultsError(
                f"Lecture déplacement nœud {n} cas {case_number} : {exc}"
            ) from exc
        out.append({
            "node": int(n), "case": int(case_number),
            "UX": _f(getattr(dv, "UX", None)),
            "UY": _f(getattr(dv, "UY", None)),
            "UZ": _f(getattr(dv, "UZ", None)),
            "RX": _f(getattr(dv, "RX", None)),
            "RY": _f(getattr(dv, "RY", None)),
            "RZ": _f(getattr(dv, "RZ", None)),
            "units": {"displacement": units["displacement"]},
        })
    return out


def import_bar_forces(rc: RobotConnection, bar_number: int, case_number: int,
                      point: int = 1) -> dict:
    """
    Importe les efforts internes d'une barre à un point d'échantillonnage.

    CONFIRMÉ par erreur typée : Results.Bars.Forces.Value exige un argument
    'Point'. La lecture avec Value(bar, point) n'a PAS encore retourné de
    valeurs non nulles (calcul sans charge valide). Statut : structure connue,
    valeurs à valider sur modèle chargé.
    """
    if not rc.is_project_open:
        raise RobotResultsError("Aucun projet ouvert.")
    if not results_available(rc):
        raise RobotResultsError("Aucun résultat disponible (Available = 0).")
    forces = rc.structure.Results.Bars.Forces
    try:
        fv = forces.Value(int(bar_number), int(case_number), int(point))
    except Exception as exc:
        raise RobotResultsError(
            f"Lecture efforts barre {bar_number} cas {case_number} "
            f"point {point} : {exc}"
        ) from exc
    return {
        "bar": int(bar_number), "case": int(case_number), "point": int(point),
        "Fx": _comp(fv, "Fx"),
        "Fy": _comp(fv, "Fy"),
        "Fz": _comp(fv, "Fz"),
        "Mx": _comp(fv, "Mx"),
        "My": _comp(fv, "My"),
        "Mz": _comp(fv, "Mz"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(rv, base: str) -> Optional[float]:
    """
    Composante (FX/FY/FZ/MX/MY/MZ) d'un objet de résultat Robot.

    Le TLB RobotOM 27 expose ces membres en MAJUSCULES (FX…) — prouvé live
    20/10 (dir() + _prop_map_get_ sur IRobotReactionData). L'ancienne
    lecture `getattr(rv, "Fx", None)` levait une AttributeError AVALÉE et
    retournait None partout (réactions vides -> combinaisons vides ->
    dimensionnement non exécutable, constaté live). On essaie donc
    MAJUSCULES d'abord (forme réelle), puis la casse historique.
    """
    for name in (base.upper(), base.capitalize(), base):
        try:
            return _f(getattr(rv, name))
        except AttributeError:
            continue
    return None

def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _all_node_numbers(rc) -> list[int]:
    nodes = rc.structure.Nodes
    return list(range(1, int(nodes.GetAll().Count) + 1))
