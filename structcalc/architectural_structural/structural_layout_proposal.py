# -*- coding: utf-8 -*-
"""
architectural_structural/structural_layout_proposal.py — Phase B (Module 71 §5).

Proposition du système porteur : poteaux, poutres, dalles, voiles, transfert.
Gère les VARIANTES (A trame régulière, B grande ouverture, C appuis modifiés,
D autre système) avec identifiant, version, hypothèses et raisons.

Règles (§5.2, §5.3) :
  - une proposition géométrique n'est JAMAIS une validation de résistance ;
  - le logiciel NE DÉPLACE PAS un poteau sans documenter la modification ;
  - chaque proposition enregistre sa raison.

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model_ext import ArchitecturalModel, DesignVariant
from .axis_grid_engine import GridProposal, build_grid


@dataclass
class ProposedMember:
    """Élément porteur proposé (non validé)."""
    kind: str                      # column | beam | slab | wall | transfer
    level_ref: Optional[str] = None
    start: Optional[Tuple[float, float, float]] = None
    end: Optional[Tuple[float, float, float]] = None
    span: Optional[float] = None
    reason: str = ""
    needs_study: bool = False      # portée à étudier (§5.2 étape 4)
    provisional: bool = True       # TJOURS provisoire tant que non calculé


@dataclass
class LayoutProposal:
    """Proposition de système porteur pour une variante."""
    variant_ref: Optional[str] = None
    members: List[ProposedMember] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[ProposedMember]:
        return [m for m in self.members if m.kind == kind]

    @property
    def n_columns(self) -> int:
        return len(self.by_kind("column"))

    @property
    def n_beams(self) -> int:
        return len(self.by_kind("beam"))

    @property
    def n_slabs(self) -> int:
        return len(self.by_kind("slab"))

    def long_spans(self, threshold: float = 6.0) -> List[ProposedMember]:
        """Portées nécessitant une étude approfondie (§5.2 étape 4)."""
        return [m for m in self.members
                if m.span is not None and m.span > threshold]

    def summary(self) -> dict:
        return {
            "columns": self.n_columns, "beams": self.n_beams,
            "slabs": self.n_slabs,
            "long_spans": len(self.long_spans()),
            "warnings": list(self.warnings),
        }


# Seuil de portée au-delà duquel une étude est signalée (donnée, pas vérité)
DEFAULT_SPAN_STUDY_THRESHOLD = 6.0


def propose_layout(model: ArchitecturalModel,
                   level_ref: Optional[str] = None,
                   grid: Optional[GridProposal] = None,
                   variant: Optional[DesignVariant] = None,
                   span_threshold: float = DEFAULT_SPAN_STUDY_THRESHOLD
                   ) -> LayoutProposal:
    """
    Propose le système porteur à partir de la trame.

    Produit poteaux (intersections), poutres (lignes d'axes), dalles
    (panneaux). Signale les portées longues. Marque TOUT provisoire :
    la proposition n'est pas une validation de résistance (§5.2).
    """
    gp = grid if grid is not None else build_grid(model)
    lp = LayoutProposal(variant_ref=variant.sc_id if variant else None)

    if not gp.column_spots:
        lp.reasons.append("Aucune intersection exploitable : proposition vide.")
        return lp

    # Altitude du niveau (si connue) pour la coordonnée z
    z = 0.0
    if level_ref and level_ref in model.levels:
        lv = model.levels[level_ref]
        if not lv.elevation.is_missing:
            z = float(lv.elevation.value)

    # Poteaux verticaux (alignement entre niveaux privilégié, §5.2)
    height = _level_height(model, level_ref)
    for (x, y) in gp.column_spots:
        lp.members.append(ProposedMember(
            kind="column", level_ref=level_ref,
            start=(x, y, z), end=(x, y, z + height),
            reason="Intersection d'axes alignée verticalement (§5.2)."))

    # Poutres (portée = longueur de la ligne)
    for (y, x1, x2) in gp.beam_lines_h:
        span = x2 - x1
        lp.members.append(ProposedMember(
            kind="beam", level_ref=level_ref,
            start=(x1, y, z), end=(x2, y, z), span=span,
            reason="Ligne d'axe horizontal entre intersections.",
            needs_study=span > span_threshold))
    for (x, y1, y2) in gp.beam_lines_v:
        span = y2 - y1
        lp.members.append(ProposedMember(
            kind="beam", level_ref=level_ref,
            start=(x, y1, z), end=(x, y2, z), span=span,
            reason="Ligne d'axe vertical entre intersections.",
            needs_study=span > span_threshold))

    # Dalles (panneaux)
    for (x1, y1, x2, y2) in gp.slab_panels:
        lp.members.append(ProposedMember(
            kind="slab", level_ref=level_ref,
            start=(x1, y1, z), end=(x2, y2, z),
            span=min(x2 - x1, y2 - y1),
            reason="Panneau délimité par la trame (épaisseur à calculer)."))

    # Portées longues -> étude approfondie (§5.2 étape 4)
    for m in lp.long_spans(span_threshold):
        lp.warnings.append(
            f"Portée {m.span:.2f} m > {span_threshold} m : étude "
            "approfondie requise (§5.2).")

    # Raisons globales
    lp.reasons.extend(gp.reasons)
    lp.reasons.append(
        "PROVISIONNEL : aucune résistance validée — dimensionnement sous "
        "responsabilité des professionnels compétents (§5.2).")

    # Traçabilité de la variante (§5.3)
    if variant is not None:
        variant.assumptions.append(
            f"Trame proposée pour le niveau {level_ref or 'tous'} "
            f"({lp.n_columns} poteaux, {lp.n_beams} poutres).")
        variant.description = variant.description or "Trame régulière"
    return lp


def _level_height(model: ArchitecturalModel,
                  level_ref: Optional[str]) -> float:
    """Hauteur d'étage (m). Valeur par défaut ASSUMÉE si absente (§4.2)."""
    if level_ref and level_ref in model.levels:
        lv = model.levels[level_ref]
        if not lv.height_above.is_missing:
            return float(lv.height_above.value)
    return 3.0   # hypothèse provisoire


def move_column_documented(variant: DesignVariant,
                           column_ref: str,
                           old_pos: Tuple[float, float],
                           new_pos: Tuple[float, float],
                           actor: str, reason: str) -> dict:
    """
    Déplace un poteau en DOCUMENTANT la modification (§5.3, §12).

    Interdit sans `reason` : le logiciel ne déplace jamais un poteau
    silencieusement. Trace old/new dans change_log de la variante.
    """
    if not reason.strip():
        raise ValueError(
            "Déplacement de poteau refusé : motif obligatoire (§5.3). "
            "Aucun déplacement automatique non documenté.")
    entry = {
        "element": column_ref,
        "old": {"x": old_pos[0], "y": old_pos[1]},
        "new": {"x": new_pos[0], "y": new_pos[1]},
        "actor": actor, "reason": reason,
        "consequences": "à mesurer sur les éléments dépendants (§12)",
    }
    variant.change_log.append(entry)
    variant.version += 1
    return entry


# ---------------------------------------------------------------------------
# Variantes (§5.3)
# ---------------------------------------------------------------------------

def create_variants(model: ArchitecturalModel) -> Dict[str, DesignVariant]:
    """
    Crée les 4 variantes de référence de la spécification (§5.3) :
      A trame régulière · B adaptation grande ouverture ·
      C modification d'appui · D autre système porteur.
    """
    specs = [
        ("A", "Trame régulière", True),
        ("B", "Adaptation à une grande ouverture", False),
        ("C", "Modification de la position de certains appuis", False),
        ("D", "Autre système porteur compatible", False),
    ]
    out: Dict[str, DesignVariant] = {}
    for code, desc, is_ref in specs:
        var = model.new_variant(description=f"Variante {code} : {desc}",
                                is_reference=is_ref)
        var.assumptions.append(desc)
        out[code] = var
    return out
