# -*- coding: utf-8 -*-
"""
architectural_structural/design_variant_manager.py — Phase B/I (Module 71 §5.3, §12).

Gestion des variantes de conception : identifiant, VERSION, hypothèses,
conflits et résultats par variante. Compare les solutions (A trame régulière,
B grande ouverture, C appuis modifiés, D autre système).

Règles (§5.3) :
  - le logiciel NE DÉPLACE PAS automatiquement un poteau sans documenter la
    modification et MESURER ses conséquences sur les éléments dépendants ;
  - chaque variante reste traçable et comparable ;
  - une variante n'est jamais « validée » de façon silencieuse.

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .model_ext import (
    ArchitecturalModel, DesignVariant,
)
from .structural_layout_proposal import (
    LayoutProposal, move_column_documented,
)


@dataclass
class VariantComparison:
    """Comparaison structurée entre variantes (§5.3)."""
    variant_ref: str
    description: str
    version: int
    n_columns: int = 0
    n_beams: int = 0
    n_slabs: int = 0
    n_conflicts: int = 0
    n_open_conflicts: int = 0
    assumptions: List[str] = field(default_factory=list)
    change_count: int = 0
    has_analysis: bool = False
    is_reference: bool = False

    def to_dict(self) -> dict:
        return {"ref": self.variant_ref, "description": self.description,
                "version": self.version, "columns": self.n_columns,
                "beams": self.n_beams, "slabs": self.n_slabs,
                "conflicts": self.n_conflicts,
                "open_conflicts": self.n_open_conflicts,
                "assumptions": list(self.assumptions),
                "changes": self.change_count,
                "has_analysis": self.has_analysis,
                "is_reference": self.is_reference}


class VariantManager:
    """
    Gestionnaire des variantes (§5.3).

    - crée/référence les variantes ;
    - compare par critères EXPLICITES (conflits, changements, analyse) ;
    - interdit tout déplacement de poteau non documenté (délègue à
      `move_column_documented`) ;
    - suit les changements par variante avec versionnement.
    """

    def __init__(self, model: ArchitecturalModel):
        self.model = model
        self._layouts: Dict[str, LayoutProposal] = {}

    # -- Enregistrement ---------------------------------------------------
    def attach_layout(self, variant_ref: str,
                      layout: LayoutProposal) -> None:
        """Associe une proposition géométrique à une variante."""
        self._require(variant_ref)
        self._layouts[variant_ref] = layout
        v = self.model.variants[variant_ref]
        v.assumptions.append(
            f"Layout : {layout.n_columns} poteaux, {layout.n_beams} poutres, "
            f"{layout.n_slabs} dalles.")

    def layout_of(self, variant_ref: str) -> Optional[LayoutProposal]:
        return self._layouts.get(variant_ref)

    # -- Modification documentée (§5.3, §12) ------------------------------
    def move_column(self, variant_ref: str, column_ref: str,
                    old_pos, new_pos, actor: str, reason: str) -> dict:
        """
        Déplace un poteau dans une variante EN DOCUMENTANT (§5.3).
        Refuse sans motif — jamais de déplacement silencieux.
        """
        self._require(variant_ref)
        v = self.model.variants[variant_ref]
        entry = move_column_documented(v, column_ref, old_pos, new_pos,
                                       actor, reason)
        return entry

    # -- Association de conflits -----------------------------------------
    def attach_conflicts(self, variant_ref: str,
                         conflict_refs: Sequence[str]) -> None:
        self._require(variant_ref)
        v = self.model.variants[variant_ref]
        for c in conflict_refs:
            if c in self.model.conflicts and c not in v.conflict_ids:
                v.conflict_ids.append(c)

    # -- Comparaison (§5.3) -----------------------------------------------
    def compare(self, variant_refs: Optional[Sequence[str]] = None
                ) -> List[VariantComparison]:
        """
        Compare les variantes par critères EXPLICITES. N'ordonne PAS en
        choisissant un « gagnant » : expose les métriques pour arbitrage.
        """
        refs = list(variant_refs or self.model.variants.keys())
        out: List[VariantComparison] = []
        for ref in refs:
            v = self.model.variants.get(ref)
            if v is None:
                continue
            lay = self._layouts.get(ref)
            # Conflits attachés à la variante
            confs = [self.model.conflicts[c] for c in v.conflict_ids
                     if c in self.model.conflicts]
            open_c = [c for c in confs
                      if c.status not in ("VALIDATED_FOR_DELIVERY",
                                          "REJECTED")]
            out.append(VariantComparison(
                variant_ref=ref, description=v.description,
                version=v.version,
                n_columns=lay.n_columns if lay else 0,
                n_beams=lay.n_beams if lay else 0,
                n_slabs=lay.n_slabs if lay else 0,
                n_conflicts=len(confs), n_open_conflicts=len(open_c),
                assumptions=list(v.assumptions),
                change_count=len(v.change_log),
                has_analysis=bool(v.analysis_model_ref),
                is_reference=v.is_reference))
        return out

    def best_by_conflicts(self, variant_refs: Optional[Sequence[str]] = None
                          ) -> Optional[str]:
        """
        Variante avec le MOINS de conflits ouverts — critère EXPLICITE.
        NE considère pas cela comme une validation de résistance (§5.2).
        Ties => première trouvée (référence d'abord).
        """
        comps = self.compare(variant_refs)
        if not comps:
            return None
        ranked = sorted(comps, key=lambda c: c.n_open_conflicts)
        return ranked[0].variant_ref

    # -- Versionnement ----------------------------------------------------
    def new_version(self, variant_ref: str, reason: str) -> int:
        """Incrémente la version d'une variante (traçabilité §15)."""
        self._require(variant_ref)
        v = self.model.variants[variant_ref]
        v.version += 1
        v.change_log.append({"type": "VERSION_BUMP", "reason": reason})
        return v.version

    # -- Vue d'ensemble ---------------------------------------------------
    def summary(self) -> Dict[str, dict]:
        """Synthèse {variant_ref: metrics} pour affichage (§5.3)."""
        return {c.variant_ref: c.to_dict() for c in self.compare()}

    def _require(self, variant_ref: str) -> DesignVariant:
        if variant_ref not in self.model.variants:
            raise KeyError(f"Variante inconnue : {variant_ref}")
        return self.model.variants[variant_ref]
