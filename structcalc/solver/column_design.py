# -*- coding: utf-8 -*-
"""
solver/column_design.py — Moteur de dimensionnement des poteaux (spec §10.4).

Rôle : moteur de RECHERCHE et de CLASSEMENT de sections candidates, en
appelant la couche REGULATION pour chaque vérification. Ne code AUCUNE formule
réglementaire ici (séparation spec §3.3).

Algorithme (spec §10.4) :
  1. générer les sections candidates ;
  2. vérifier les contraintes géométriques ;
  3. analyser l'élancement ;
  4. effectuer les calculs réglementaires applicables ;
  5. déterminer les armatures requises ;
  6. vérifier les armatures constructives ;
  7. contrôles parasismiques (si applicable) ;
  8. classer les variantes selon des critères EXPLICITES ;
  9. présenter à l'ingénieur ;
 10. signaler si un recalcul global est requis.

Règle §10.4 : ne PAS retenir automatiquement la plus petite section si elle
pose des problèmes de rigidité/stabilité/constructibilité. Le classement
EXPOSE les critères, il ne masque pas les compromis. Aucune section n'est
retenue « conforme » sans validation ingénieur.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..regulation.bael91r99.columns import (
    Bael91r99, ColumnGeometry, ColumnMaterials, ColumnActions,
)
from ..core.status import RegulatoryStatus


@dataclass
class ColumnVariant:
    """Une variante de section candidate pour un poteau."""
    b: float                      # largeur (cm)
    h: float                      # hauteur (cm)
    As_provided_cm2: float = 0.0  # armature longitudinale fournie
    label: str = ""

    @property
    def area_cm2(self) -> float:
        return self.b * self.h

    @property
    def designation(self) -> str:
        return self.label or f"{self.b:.0f}x{self.h:.0f}"


@dataclass
class DesignOutcome:
    """Résultat du dimensionnement d'une variante (traçable, spec §10.4)."""
    variant: ColumnVariant
    checks: List = field(default_factory=list)      # VerificationResult
    failed: List[str] = field(default_factory=list)  # ids des checks échoués
    missing_data: List[str] = field(default_factory=list)
    to_validate: List[str] = field(default_factory=list)  # à valider ingénieur
    ranking_score: Optional[float] = None
    rank: Optional[int] = None

    @property
    def is_candidate(self) -> bool:
        """Vrai si AUCUN check dur n'a échoué (les A_VALIDER restent ouverts)."""
        return not self.failed and not self.missing_data

    def status_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for c in self.checks:
            counts[c.status.value] = counts.get(c.status.value, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "section": self.variant.designation,
            "area_cm2": self.variant.area_cm2,
            "As_cm2": self.variant.As_provided_cm2,
            "candidate": self.is_candidate,
            "failed": self.failed,
            "missing": self.missing_data,
            "to_validate": self.to_validate,
            "rank": self.rank,
            "score": self.ranking_score,
            "status_summary": self.status_summary(),
        }


class ColumnDesigner:
    """
    Moteur de recherche de sections pour poteaux.

    Appelle le référentiel BAEL (couche REGULATION) pour chaque vérification.
    Aucune formule réglementaire n'est codée ici.
    """

    def __init__(self, regulation: Optional[Bael91r99] = None):
        self.reg = regulation or Bael91r99()

    # ------------------------------------------------------------------
    # Génération de candidates (spec §10.4 étape 1)
    # ------------------------------------------------------------------
    @staticmethod
    def generate_candidates(sizes_cm: Optional[List[float]] = None,
                            reinforcement_ratios: Optional[List[float]] = None
                            ) -> List[ColumnVariant]:
        """
        Produit une grille de sections candidates (carrées/rectangulaires).

        Tailles et ratios SONT des données d'entrée réglables, pas des vérités.
        """
        sizes = sizes_cm or [20, 25, 30, 35, 40, 45, 50]
        ratios = reinforcement_ratios or [0.01, 0.015, 0.02, 0.03]
        out: List[ColumnVariant] = []
        for s in sizes:
            for r in ratios:
                out.append(ColumnVariant(b=float(s), h=float(s),
                                         As_provided_cm2=r * s * s,
                                         label=f"{s}x{s} r{r*100:.1f}%"))
        return out

    # ------------------------------------------------------------------
    # Dimensionnement d'une variante (spec §10.4 étapes 2-7)
    # ------------------------------------------------------------------
    def design_variant(self, variant: ColumnVariant,
                       height: float, buckling_y: float, buckling_z: float,
                       materials: ColumnMaterials,
                       actions: ColumnActions) -> DesignOutcome:
        """
        Évalue une variante : géométrie -> élancement -> compression ->
        armatures. Collecte les VerificationResult avec statuts honnêtes.
        """
        geo = ColumnGeometry(b=variant.b, h=variant.h, height=height,
                             buckling_length_y=buckling_y,
                             buckling_length_z=buckling_z)
        out = DesignOutcome(variant=variant)

        # 2. Contrainte géométrique basique : section > 0
        if variant.b <= 0 or variant.h <= 0:
            out.failed.append("geometry")
            return out

        # 3. Élancement
        res_elam = self.reg.check_slenderness(geo, materials)
        out.checks.append(res_elam)
        if res_elam.status == RegulatoryStatus.NON_CONFORME:
            out.failed.append("slenderness")
        elif res_elam.status == RegulatoryStatus.A_VALIDER:
            out.to_validate.append("slenderness")

        # 4-5. Compression centrale (filtre initial, spec §10.2)
        res_comp = self.reg.check_compression_central(
            geo, materials, actions, As_total_cm2=variant.As_provided_cm2)
        out.checks.append(res_comp)
        if res_comp.status == RegulatoryStatus.NON_CONFORME:
            out.failed.append("compression")
        elif res_comp.status == RegulatoryStatus.A_VALIDER:
            out.to_validate.append("compression")

        # 6. Armatures constructives (min/max)
        res_reinf = self.reg.check_min_reinforcement(
            geo, materials, variant.As_provided_cm2)
        out.checks.append(res_reinf)
        if res_reinf.status == RegulatoryStatus.NON_CONFORME:
            out.failed.append("reinforcement")
        elif res_reinf.status == RegulatoryStatus.A_VALIDER:
            out.to_validate.append("reinforcement")

        # 7. Contrôles parasismiques : non implémentés (spec §11.3) -> trace
        res_seis = self.reg.run_check("seismic_detailing")
        out.checks.append(res_seis)
        if res_seis.status == RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE:
            out.to_validate.append("seismic_detailing")

        # Score de classement : ratio de capacité (plus bas = plus de marge)
        out.ranking_score = self._score(res_comp, res_elam, variant)
        return out

    def _score(self, res_comp, res_elam, variant) -> float:
        """
        Score de classement EXPLICITE (spec §10.4 étape 8).

        Critères combinés (documentés) :
          - ratio de compression (N/Nr) : plus bas = plus de marge ;
          - pénalité d'élancement élevé ;
          - préférence modérée pour les petites sections (économie).
        Critères visibles, pas masqués. L'ingénieur arbitre.
        """
        comp_ratio = 0.0
        if res_comp.limit_value and res_comp.limit_value > 0:
            comp_ratio = (res_comp.computed_value or 0) / res_comp.limit_value
        lam = res_elam.computed_value or 0.0
        elam_penalty = max(0.0, (lam - 100.0) / 100.0)   # pénalise λ>100
        area = variant.area_cm2
        # Combinaison pondérée (poids documentés)
        return comp_ratio * 1.0 + elam_penalty * 0.3 + (area / 1000.0) * 0.1

    # ------------------------------------------------------------------
    # Recherche globale (spec §10.4 étapes 1-9)
    # ------------------------------------------------------------------
    def search(self, height: float, buckling_y: float, buckling_z: float,
               materials: ColumnMaterials, actions: ColumnActions,
               candidates: Optional[List[ColumnVariant]] = None
               ) -> List[DesignOutcome]:
        """
        Dimensionne toutes les candidates, écarte les échecs durs, CLASSE
        les viables. NE retient PAS « automatiquement » la plus petite :
        expose le classement et les points à valider (spec §10.4).
        """
        cands = candidates or self.generate_candidates()
        outcomes = [self.design_variant(v, height, buckling_y, buckling_z,
                                        materials, actions) for v in cands]

        # Séparer viables / échouées
        viables = [o for o in outcomes if o.is_candidate]
        viables.sort(key=lambda o: (o.ranking_score is None,
                                    o.ranking_score))
        for i, o in enumerate(viables, start=1):
            o.rank = i
        return viables

    def requires_global_reanalysis(self, best: DesignOutcome) -> bool:
        """
        Vrai si le choix de section peut influencer la structure globale
        (rigidité/stabilité) et imposer un recalcul global (spec §10.4 étape 10).

        Toute section retenue le signale : l'ingénieur doit relancer
        l'analyse globale si la rigidité a changé.
        """
        return best.is_candidate
