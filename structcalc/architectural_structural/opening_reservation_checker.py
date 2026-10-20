# -*- coding: utf-8 -*-
"""
architectural_structural/opening_reservation_checker.py — Phase A/F (Module 71 §4, §9).

Contrôle des ouvertures, trémies, portes/fenêtres et réservations/gaines
vis-à-vis des éléments structurels.

Familles de conflits couvertes (§9.1 géométrique) :
  - poteau devant une porte ;
  - poutre/poteau traversant une ouverture ;
  - trémie d'escalier incompatible avec une poutre ;
  - gaines et réservations incompatibles avec des éléments structurels.

Règle : les conflits sont SIGNALÉS. Aucune ouverture n'est supprimée et aucun
élément structurel n'est déplacé en silence (§5.3, §9.3).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .model_ext import ArchitecturalModel
from .conflict_detection_engine import Rect, _opening_rect


@dataclass
class OpeningCheck:
    """Constat pour une ouverture."""
    opening_ref: str
    kind: str
    level_ref: Optional[str]
    code: str                      # CLEAR | BLOCKED | SHAFT_NEAR | UNKNOWN
    detail: str
    conflicting: List[str] = field(default_factory=list)

    @property
    def is_conflict(self) -> bool:
        return self.code != "CLEAR"

    def to_dict(self) -> dict:
        return {"opening": self.opening_ref, "kind": self.kind,
                "level": self.level_ref, "code": self.code,
                "detail": self.detail, "conflicting": list(self.conflicting)}


@dataclass
class OpeningReport:
    checks: List[OpeningCheck] = field(default_factory=list)

    @property
    def conflicts(self) -> List[OpeningCheck]:
        return [c for c in self.checks if c.is_conflict]

    @property
    def clear(self) -> List[OpeningCheck]:
        return [c for c in self.checks if not c.is_conflict]

    @property
    def summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.checks:
            out[c.code] = out.get(c.code, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {"summary": self.summary,
                "checks": [c.to_dict() for c in self.checks],
                "n_conflicts": len(self.conflicts)}


def check_openings_against_members(
        model: ArchitecturalModel,
        member_rects: Sequence[dict],
        clear_opening_ids: Optional[Sequence[str]] = None,
        ) -> OpeningReport:
    """
    Vérifie chaque ouverture contre les éléments structurels.

    `member_rects` : [{"ref", "kind": column|beam, "rect": Rect ou tuple,
                       "level"}] — emprises des éléments (plan).
    `clear_opening_ids` : ouvertures explicitement autorisées (déjà traitées).

    Codes :
      - CLEAR     : aucune interférence ;
      - BLOCKED   : élément structurel dans l'emprise de l'ouverture ;
      - UNKNOWN   : géométrie de l'ouverture manquante (MISSING, §4.2).
    """
    rep = OpeningReport()
    cleared = set(clear_opening_ids or [])

    for op in model.openings.values():
        rect = _opening_rect(op)
        if rect is None:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="UNKNOWN",
                detail="Géométrie de l'ouverture incomplète (MISSING) — "
                       "donnée non inventée (§4.2)."))
            continue

        if op.sc_id in cleared:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="CLEAR",
                detail="Ouverture explicitement autorisée (déjà traitée)."))
            continue

        hit: List[str] = []
        for mr in member_rects:
            if op.level_ref and mr.get("level") and \
                    mr["level"] != op.level_ref:
                continue
            mrect = _as_rect(mr.get("rect"))
            if mrect is None:
                continue
            if rect.intersects(mrect):
                hit.append(mr["ref"])

        if hit:
            op.conflicts_with.extend([h for h in hit
                                      if h not in op.conflicts_with])
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="BLOCKED",
                detail=f"{len(hit)} élément(s) structurel(s) dans l'emprise "
                       "de l'ouverture — conflit à coordonner (§9.1).",
                conflicting=hit))
        else:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="CLEAR",
                detail="Aucune interférence structurelle détectée."))
    return rep


def check_shaft_near_member(model: ArchitecturalModel,
                            member_positions: Sequence[dict],
                            clearance: float = 0.10) -> OpeningReport:
    """
    Gaine / réservation trop proche d'un élément (§9.1 « gaines et
    réservations incompatibles »). `clearance` en m (donnée réglable).
    """
    rep = OpeningReport()
    shafts = [o for o in model.openings.values()
              if o.kind in ("shaft", "reserved", "gaine")]
    for op in shafts:
        rect = _opening_rect(op)
        if rect is None:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="UNKNOWN", detail="Gaine sans géométrie (MISSING)."))
            continue
        grown = Rect(rect.x1 - clearance, rect.y1 - clearance,
                     rect.x2 + clearance, rect.y2 + clearance)
        near = []
        for mp in member_positions:
            mrect = _as_rect(mp.get("rect")) or _as_rect(
                (mp["x"], mp["y"], mp.get("b", 0.3), mp.get("h", 0.3)))
            if mrect is None:
                continue
            if grown.intersects(mrect):
                near.append(mp["ref"])
        if near:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="BLOCKED",
                detail=f"Gaine à moins de {clearance} m d'un élément "
                       f"structurel : {', '.join(near)}.",
                conflicting=near))
        else:
            rep.checks.append(OpeningCheck(
                opening_ref=op.sc_id, kind=op.kind, level_ref=op.level_ref,
                code="CLEAR", detail="Gaine hors zone structurelle."))
    return rep


def _as_rect(v) -> Optional[Rect]:
    if v is None:
        return None
    if isinstance(v, Rect):
        return v
    if isinstance(v, (tuple, list)) and len(v) == 4:
        return Rect(*[float(t) for t in v])
    return None
