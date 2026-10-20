# -*- coding: utf-8 -*-
"""
architectural_structural/axis_grid_engine.py — Phase A/B (Module 71 §3, §5).

Construit la trame structurelle à partir des axes normalisés : nœuds
d'intersection, positions de poteaux, lignes de poutres, panneaux de dalle.

Règles (§5.2) :
  - privilégier une organisation porteuse rationnelle ;
  - identifier les alignements possibles entre niveaux ;
  - enregistrer les RAISONS de chaque proposition.

Une proposition géométrique n'est JAMAIS une validation de résistance (§5.2).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .model_ext import ArchitecturalModel
from .geometry_normalization import spacing_between, dist2d as _dist


@dataclass
class GridProposal:
    """
    Résultat de la construction de trame.

    `reasons` documente POURQUOI chaque élément est proposé (§5.2 étape 8).
    """
    nodes: List[Tuple[float, float]] = field(default_factory=list)   # (x, y)
    column_spots: List[Tuple[float, float]] = field(default_factory=list)
    beam_lines_h: List[Tuple[float, float, float]] = field(default_factory=list)  # (y, x1, x2)
    beam_lines_v: List[Tuple[float, float, float]] = field(default_factory=list)  # (x, y1, y2)
    slab_panels: List[Tuple[float, float, float, float]] = field(default_factory=list)  # (x1,y1,x2,y2)
    spans: List[Tuple[str, str, float]] = field(default_factory=list)  # entraxes
    reasons: List[str] = field(default_factory=list)

    @property
    def n_columns(self) -> int:
        return len(self.column_spots)

    @property
    def n_panels(self) -> int:
        return len(self.slab_panels)

    def summary(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "columns": self.n_columns,
            "beam_lines": len(self.beam_lines_h) + len(self.beam_lines_v),
            "slab_panels": self.n_panels,
            "spans": len(self.spans),
            "reasons": list(self.reasons),
        }


def build_grid(model: ArchitecturalModel,
               exclude_openings: bool = True) -> GridProposal:
    """
    Construit la trame à partir des axes du modèle.

    - Intersection de chaque axe X × Y = nœud candidat ;
    - Poteaux aux intersections (alignement naturel entre niveaux) ;
    - Poutres le long des lignes d'axes entre intersections consécutives ;
    - Panneaux de dalle délimités par 4 intersections adjacentes ;
    - Entraxes CALCULÉES (spécification : 5,00 m pour le cas de référence).

    Si `exclude_openings`, une intersection tombant dans une trémie/gaine
    est EXCLUE des poteaux (raison tracée) — elle n'est pas supprimée du
    modèle, seulement non proposée comme poteau.
    """
    gp = GridProposal()

    xs = sorted(float(a.position.value) for a in model.axes.values()
                if a.direction == "X" and not a.position.is_missing)
    ys = sorted(float(a.position.value) for a in model.axes.values()
                if a.direction == "Y" and not a.position.is_missing)

    if len(xs) < 2 or len(ys) < 2:
        gp.reasons.append(
            "Trame incomplète : au moins 2 axes par direction requis — "
            "aucune proposition générée.")
        return gp

    # Entraxes calculées (contrôle du cas de référence 5,00 m)
    gp.spans = (spacing_between(list(model.axes.values()), "X")
                + spacing_between(list(model.axes.values()), "Y"))
    uniform = {round(d, 3) for _, _, d in gp.spans}
    if len(uniform) == 1:
        gp.reasons.append(
            f"Trame régulière détectée : entraxe constant {uniform.pop():.2f} m.")
    else:
        gp.reasons.append(
            "Trames inégales : " +
            ", ".join(f"{a}-{b}={d:.2f}m" for a, b, d in gp.spans))

    # Zones exclues (trémies) — rectangles d'ouverture
    exclusion_zones = _opening_zones(model) if exclude_openings else []

    # Intersections
    for x in xs:
        for y in ys:
            gp.nodes.append((x, y))
            if _in_zones(x, y, exclusion_zones):
                gp.reasons.append(
                    f"Point ({x:.2f},{y:.2f}) : intersection dans une trémie/"
                    "réservation — pas de poteau proposé.")
                continue
            gp.column_spots.append((x, y))

    # Poutres horizontales (y constant) entre colonnes consécutives
    for y in ys:
        xs_in = sorted({x for x, yy in gp.column_spots if abs(yy - y) < 1e-9}
                       | {x for x, yy in gp.nodes if abs(yy - y) < 1e-9})
        for x1, x2 in zip(xs_in, xs_in[1:]):
            gp.beam_lines_h.append((y, x1, x2))
    # Poutres verticales (x constant)
    for x in xs:
        ys_in = sorted({y for xx, y in gp.column_spots if abs(xx - x) < 1e-9}
                       | {y for xx, y in gp.nodes if abs(xx - x) < 1e-9})
        for y1, y2 in zip(ys_in, ys_in[1:]):
            gp.beam_lines_v.append((x, y1, y2))

    # Panneaux de dalle entre intersections adjacentes
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            gp.slab_panels.append((xs[i], ys[j], xs[i + 1], ys[j + 1]))

    gp.reasons.append(
        f"{len(gp.column_spots)} poteaux proposés aux intersections alignées "
        f"(alignement vertical privilégié, §5.2).")
    gp.reasons.append(
        f"{len(gp.slab_panels)} panneaux de dalle délimités par la trame.")
    return gp


def _opening_zones(model: ArchitecturalModel) -> List[Tuple[float, float, float, float]]:
    """Rectangles (x1, y1, x2, y2) des ouvertures non manquantes."""
    zones = []
    for op in model.openings.values():
        if any(v.is_missing for v in (op.cx, op.cy, op.width, op.depth)):
            continue
        cx, cy = float(op.cx.value), float(op.cy.value)
        w, d = float(op.width.value), float(op.depth.value)
        zones.append((cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2))
    return zones


def _in_zones(x: float, y: float,
              zones: Sequence[Tuple[float, float, float, float]]) -> bool:
    return any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in zones)


def aligned_across_levels(model: ArchitecturalModel,
                          level_columns: Dict[str, List[Tuple[float, float]]]
                          ) -> List[dict]:
    """
    Compare les positions de poteaux entre niveaux (§5.2 étape 2, §7.1).

    `level_columns` : {level_ref: [(x, y), ...]}.
    Retourne les écarts : [{x, y, status, ...}] avec status en
    ALIGNED / OFFSET / MISSING_UP / MISSING_DOWN. NE déclare jamais si un
    décalage est dangereux — il est seulement SIGNALÉ (§7.1).
    """
    order = sorted(level_columns.keys(),
                   key=lambda k: min((p[0] + p[1] for p in level_columns[k]),
                                     default=0))
    out: List[dict] = []
    if len(order) < 2:
        return out
    for lower, upper in zip(order, order[1:]):
        lp = level_columns[lower]
        up = level_columns[upper]
        for (x, y) in lp:
            nearest = _nearest((x, y), up)
            if nearest is None:
                out.append({"x": x, "y": y, "lower": lower, "upper": upper,
                            "status": "MISSING_UP",
                            "detail": "Poteau du niveau inférieur sans "
                                      "continuation au niveau supérieur."})
            elif _dist((x, y), nearest) > 0.05:
                out.append({"x": x, "y": y, "lower": lower, "upper": upper,
                            "status": "OFFSET",
                            "detail": f"Décalage {_dist((x,y), nearest):.3f} m "
                                      f"vers ({nearest[0]:.2f},{nearest[1]:.2f})."})
            else:
                out.append({"x": x, "y": y, "lower": lower, "upper": upper,
                            "status": "ALIGNED", "detail": "Aligné."})
        for (x, y) in up:
            if _nearest((x, y), lp) is None:
                out.append({"x": x, "y": y, "lower": lower, "upper": upper,
                            "status": "MISSING_DOWN",
                            "detail": "Poteau du niveau supérieur sans "
                                      "origine au niveau inférieur."})
    return out


def _nearest(pt, pts):
    if not pts:
        return None
    return min(pts, key=lambda q: _dist(pt, q))
