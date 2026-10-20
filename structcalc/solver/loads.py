# -*- coding: utf-8 -*-
"""
solver/loads.py — Descente de charges et combinaisons internes (spec §9).

Chaînon entre les cas de charge (`LoadCase`), les combinaisons
(`LoadCombination`, §9.2) et les sollicitations d'élément (`ColumnActions`).

Règles respectées :
  - Les coefficients de combinaison sont lus dans `LoadCombination.factors`
    (définition EXACTE fournie), JAMAIS codés en dur ici (§9.2).
  - Les géométries de répartition (largeur tributaire, aire tributaire,
    nombre de niveaux) sont des ENTRÉES de l'ingénieur — jamais déduites ni
    inventées (§4.2). Une hypothèse de répartition serait une donnée ASSUMED.
  - Une combinaison référençant un cas sans valeur = donnée MANQUANTE signalée
    (pas un zéro silencieux).
  - Toutes les conversions d'unités sont explicites (§5.3).

Cas de référence (§17.2) : valeurs à calcul manuel dans les tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Résultat d'application de combinaison
# ---------------------------------------------------------------------------

@dataclass
class CombinationResult:
    """Issue d'une combinaison d'actions (traçable, honnête)."""
    value: float                            # effort combiné (unité du cas)
    expression: str                         # expression tracée
    contributions: Dict[str, float] = field(default_factory=dict)  # case -> γ*val
    missing_cases: List[str] = field(default_factory=list)         # cas sans valeur
    complete: bool = True                   # False si un cas manquant

    @property
    def is_missing_data(self) -> bool:
        return bool(self.missing_cases)


def apply_combination(case_values: Dict[str, float],
                      factors: Dict[str, float],
                      expression: str = "") -> CombinationResult:
    """
    Applique des coefficients γ aux valeurs par cas de charge.

    `case_values` : case_sc_id -> valeur (kN, kN/m, ... selon le sollicitation).
    `factors`     : case_sc_id -> coefficient (de `LoadCombination.factors`).

    Un cas présent dans `factors` mais absent de `case_values` est MIS EN
    REGISTRE (`missing_cases`) et `complete=False` : la somme n'est alors qu'une
    borne partielle, jamais un résultat complet présenté comme tel.
    """
    total = 0.0
    contrib: Dict[str, float] = {}
    missing: List[str] = []
    for case_id, gamma in factors.items():
        if case_id in case_values and case_values[case_id] is not None:
            part = gamma * case_values[case_id]
            contrib[case_id] = part
            total += part
        else:
            missing.append(case_id)
    return CombinationResult(
        value=total, expression=expression, contributions=contrib,
        missing_cases=missing, complete=(not missing),
    )


def apply_load_combination(case_values: Dict[str, float],
                           combination) -> CombinationResult:
    """
    Variante prenant directement un `LoadCombination` (§9.2) : lit son
    `expression` et ses `factors`. Ne devine aucun coefficient absent.
    """
    factors = dict(getattr(combination, "factors", {}) or {})
    expr = getattr(combination, "expression", "") or ""
    return apply_combination(case_values, factors, expression=expr)


# ---------------------------------------------------------------------------
# Descente de charges surfacique (aire -> ligne / point)
# ---------------------------------------------------------------------------

def line_load_from_area(q_kNm2: float, tributary_width_m: float) -> float:
    """
    Charge linéique sur une poutre (kN/m) à partir d'une charge surfacique
    q (kN/m²) et d'une largeur tributaire (m) FOURNIE par l'ingénieur.

    w = q × largeur_tributaire   [kN/m² × m = kN/m]
    """
    if tributary_width_m < 0:
        raise ValueError("largeur tributaire négative (donnée invalide).")
    return q_kNm2 * tributary_width_m


def point_load_from_area(q_kNm2: float, tributary_area_m2: float,
                         n_levels: int = 1) -> float:
    """
    Charge ponctuelle / axiale sur un appui (kN) à partir d'une charge
    surfacique q (kN/m²), d'une aire tributaire (m²) et du nombre de niveaux
    cumulés. Aire et niveaux sont des ENTRÉES, jamais déduites.

    P = q × aire × niveaux   [kN/m² × m² × - = kN]
    """
    if tributary_area_m2 < 0:
        raise ValueError("aire tributaire négative (donnée invalide).")
    if n_levels < 0:
        raise ValueError("nombre de niveaux négatif (donnée invalide).")
    return q_kNm2 * tributary_area_m2 * n_levels


# ---------------------------------------------------------------------------
# Descente de charges par étage (répartition multi-cas -> action d'élément)
# ---------------------------------------------------------------------------

@dataclass
class AreaLoad:
    """Charge surfacique d'un cas sur une zone (kN/m²)."""
    case_sc_id: str
    q_kNm2: float


def element_actions_from_area(area_loads: List[AreaLoad],
                              combination,
                              tributary_width_m: float = 0.0,
                              tributary_area_m2: float = 0.0,
                              n_levels: int = 1
                              ) -> Dict[str, CombinationResult]:
    """
    Descente de charges complète pour un élément :
      1. chaque charge surfacique -> action élémentaire (ligne ou point) ;
      2. application de la combinaison (§9.2) sur les actions par cas.

    Retourne {'line': CombinationResult, 'point': CombinationResult}
    selon la géométrie fournie (largeur tributaire => linéique ; aire
    tributaire => ponctuelle). Les canaux non sollicités sont omis.

    Les cas de la combinaison sans charge surfacique correspondante sont
    signalés manquants (jamais un zéro silencieux).
    """
    line_vals: Dict[str, float] = {}
    point_vals: Dict[str, float] = {}
    for al in area_loads:
        if tributary_width_m > 0:
            line_vals[al.case_sc_id] = line_load_from_area(al.q_kNm2,
                                                           tributary_width_m)
        if tributary_area_m2 > 0:
            point_vals[al.case_sc_id] = point_load_from_area(
                al.q_kNm2, tributary_area_m2, n_levels)

    out: Dict[str, CombinationResult] = {}
    if line_vals:
        out["line"] = apply_load_combination(line_vals, combination)
    if point_vals:
        out["point"] = apply_load_combination(point_vals, combination)
    return out
