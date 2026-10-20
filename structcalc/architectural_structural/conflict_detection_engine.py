# -*- coding: utf-8 -*-
"""
architectural_structural/conflict_detection_engine.py — Phase F (Module 71 §9).

Détecte et suit les conflits architecture–structure. Chaque conflit est relié
à sa géométrie, aux règles applicables, aux résultats de calcul et aux
décisions de coordination (§9.2).

Familles (§9.1) : GEOMETRIC, STRUCTURAL, DOCUMENTARY.

Cycle de traitement (§9.3) porté par `Conflict.transition` (model_ext) :
  DETECTED → CLASSIFIED → ANALYZED → SOLUTIONS_PROPOSED → UNDER_REVIEW →
  APPROVED_FOR_CALCULATION → RECALCULATED → VERIFIED → VALIDATED_FOR_DELIVERY

Règle (§9.3) : une solution PROPOSÉE n'est jamais une solution APPROUVÉE sans
validation selon les responsabilités du projet.

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .model_ext import (
    ArchitecturalModel, Conflict, ConflictKind, Opening,
)


# ---------------------------------------------------------------------------
# Règles de détection géométrique (§9.1)
# ---------------------------------------------------------------------------

@dataclass
class Rect:
    """Rectangle axis-aligné (x1, y1, x2, y2) en mètres."""
    x1: float
    y1: float
    x2: float
    y2: float

    def intersects(self, other: "Rect", tol: float = 0.0) -> bool:
        return (self.x1 - tol < other.x2 and self.x2 + tol > other.x1 and
                self.y1 - tol < other.y2 and self.y2 + tol > other.y1)

    @classmethod
    def from_center(cls, cx, cy, w, d) -> "Rect":
        return cls(cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2)


def _opening_rect(op: Opening) -> Optional[Rect]:
    if any(v.is_missing for v in (op.cx, op.cy, op.width, op.depth)):
        return None
    return Rect.from_center(float(op.cx.value), float(op.cy.value),
                            float(op.width.value), float(op.depth.value))


def _column_rect(x: float, y: float, b: float, h: float) -> Rect:
    return Rect(x - b / 2, y - h / 2, x + b / 2, y + h / 2)


# ---------------------------------------------------------------------------
# Détection
# ---------------------------------------------------------------------------

def detect_column_vs_opening(
        model: ArchitecturalModel,
        column_positions: Sequence[dict]) -> List[Conflict]:
    """
    « Poteau devant une porte / devant une trémie » (§9.1 géométrique).

    `column_positions` : [{"ref": SC-*, "x", "y", "b", "h", "level"}].
    Le conflit est SIGNALÉ, l'élément n'est ni déplacé ni supprimé.
    """
    out: List[Conflict] = []
    for col in column_positions:
        b = col.get("b", 0.3)
        h = col.get("h", 0.3)
        crect = _column_rect(col["x"], col["y"], b, h)
        for op in model.openings.values():
            if col.get("level") and op.level_ref and \
                    op.level_ref != col.get("level"):
                continue
            orect = _opening_rect(op)
            if orect is None:
                continue
            if crect.intersects(orect):
                cf = model.new_conflict(
                    ConflictKind.GEOMETRIC,
                    description=(f"Poteau {col['ref']} chevauche l'ouverture "
                                 f"{op.sc_id} ({op.kind})."),
                    level_ref=op.level_ref,
                    element_ids=[col["ref"], op.sc_id],
                    source="conflict_detection_engine")
                cf.rule_ref = "§9.1 conflit géométrique (ouverture)"
                cf.severity = "PROVISIONAL"
                out.append(cf)
                op.conflicts_with.append(col["ref"])
    return out


def detect_beam_vs_clear_height(
        model: ArchitecturalModel,
        beam_z: Sequence[dict],
        required_clear_height: float) -> List[Conflict]:
    """
    « Poutre incompatible avec une hauteur libre » (§9.1 géométrique).

    `beam_z` : [{"ref", "z_bottom", "level", "x1","y1","x2","y2"}] — z_bottom
    en m sous le niveau. Compare avec la hauteur libre exigée.
    """
    out: List[Conflict] = []
    for bm in beam_z:
        zb = bm.get("z_bottom")
        if zb is None:
            continue
        clear = zb   # hauteur libre sous poutre (simplifié : z_bottom)
        if clear < required_clear_height:
            cf = model.new_conflict(
                ConflictKind.GEOMETRIC,
                description=(f"Poutre {bm['ref']} : hauteur libre "
                             f"{clear:.2f} m < exigée "
                             f"{required_clear_height:.2f} m."),
                level_ref=bm.get("level"),
                element_ids=[bm["ref"]],
                source="conflict_detection_engine")
            cf.rule_ref = "§9.1 conflit géométrique (hauteur libre)"
            out.append(cf)
    return out


def detect_stairwell_vs_beam(
        model: ArchitecturalModel,
        beams: Sequence[dict]) -> List[Conflict]:
    """
    « Trémie d'escalier incompatible avec une poutre » (§9.1 géométrique).
    `beams` : [{"ref", "rect": (x1,y1,x2,y2), "level"}].
    """
    out: List[Conflict] = []
    stair_openings = [o for o in model.openings.values()
                      if o.kind in ("stairwell", "stair", "shaft")]
    for op in stair_openings:
        orect = _opening_rect(op)
        if orect is None:
            continue
        for bm in beams:
            r = bm.get("rect")
            if not r:
                continue
            brect = Rect(r[0], r[1], r[2], r[3])
            if orect.intersects(brect):
                cf = model.new_conflict(
                    ConflictKind.GEOMETRIC,
                    description=(f"Trémie d'escalier {op.sc_id} incompatible "
                                 f"avec la poutre {bm['ref']}."),
                    level_ref=op.level_ref,
                    element_ids=[op.sc_id, bm["ref"]],
                    source="conflict_detection_engine")
                cf.rule_ref = "§9.1 conflit géométrique (trémie escalier)"
                out.append(cf)
                op.conflicts_with.append(bm["ref"])
    return out


def detect_structural_discontinuity(
        model: ArchitecturalModel,
        continuity_findings: Sequence[dict]) -> List[Conflict]:
    """
    « Élément porteur interrompu / appui absent » (§9.1 structurel).

    `continuity_findings` : dict issues de ContinuityReport.to_dict()["findings"].
    Aucun n'est déclaré dangereux — classifié STRUCTURAL et à analyser.
    """
    out: List[Conflict] = []
    structural_codes = {"INTERRUPTED", "NO_SUPPORT", "OFFSET",
                        "SECTION_CHANGE", "NO_FOUNDATION", "TRANSFER_POSSIBLE"}
    for f in continuity_findings:
        if f.get("code") not in structural_codes:
            continue
        cf = model.new_conflict(
            ConflictKind.STRUCTURAL,
            description=f.get("detail", f.get("code", "")),
            level_ref=f.get("lower") or f.get("upper"),
            element_ids=[r for r in (f.get("lower"), f.get("upper")) if r],
            source="vertical_continuity_checker")
        cf.rule_ref = f"§9.1 conflit structurel ({f.get('code')})"
        out.append(cf)
    return out


def detect_documentary_conflict(
        model: ArchitecturalModel,
        drawing_ids: Sequence[str],
        model_version: int) -> List[Conflict]:
    """
    « Plans de versions différentes / modèle != plan » (§9.1 documentaire).

    Compare la version du modèle SOURCE de chaque plan avec la version
    courante du modèle. Un plan périmé est signalé, pas régénéré en silence.
    """
    out: List[Conflict] = []
    for did in drawing_ids:
        dr = model.drawings.get(did)
        if dr is None:
            continue
        if dr.model_version != model_version:
            cf = model.new_conflict(
                ConflictKind.DOCUMENTARY,
                description=(f"Plan {did} fondé sur le modèle v"
                             f"{dr.model_version} alors que la version "
                             f"courante est v{model_version}."),
                level_ref=dr.level_ref,
                element_ids=[did],
                source="model_drawing_consistency_checker")
            cf.rule_ref = "§9.1 conflit documentaire (version divergente)"
            out.append(cf)
    return out


# ---------------------------------------------------------------------------
# Statistiques / suivi
# ---------------------------------------------------------------------------

def conflict_register(model: ArchitecturalModel) -> dict:
    """
    Registre des conflits (§9.2/§9.3) : répartition par famille et statut,
    liste des conflits NON résolus (jamais masqués).
    """
    by_kind: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for c in model.conflicts.values():
        by_kind[c.kind.value] = by_kind.get(c.kind.value, 0) + 1
        by_status[c.status] = by_status.get(c.status, 0) + 1
    return {
        "total": len(model.conflicts),
        "by_kind": by_kind,
        "by_status": by_status,
        "open": [c.sc_id for c in model.open_conflicts()],
        "blocking_delivery": [
            c.sc_id for c in model.open_conflicts()
            if c.status in ("DETECTED", "CLASSIFIED", "ANALYZED",
                            "SOLUTIONS_PROPOSED", "UNDER_REVIEW",
                            "APPROVED_FOR_CALCULATION", "RECALCULATED",
                            "VERIFIED", "UNRESOLVED")],
    }
