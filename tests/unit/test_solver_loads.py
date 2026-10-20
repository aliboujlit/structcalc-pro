# -*- coding: utf-8 -*-
"""
tests/unit/test_solver_loads.py — Descente de charges + combinaisons (spec §9).

Cas de référence à calcul manuel (§17.2) + règles d'honnêteté :
  - coefficients lus de la combinaison, jamais codés en dur (§9.2) ;
  - cas sans valeur -> signalés manquants, pas un zéro silencieux ;
  - géométrie de répartition = entrée, jamais déduite (§4.2).
"""

import pytest

from structcalc.solver.loads import (
    CombinationResult,
    apply_combination,
    apply_load_combination,
    line_load_from_area,
    point_load_from_area,
    element_actions_from_area,
    AreaLoad,
)


class FakeCombination:
    """Combinaison type (fournie, pas codée en dur par le moteur)."""
    expression = "1.35 G + 1.5 Q"
    factors = {"G": 1.35, "Q": 1.5}


def test_apply_combination_reference_value():
    """1.35*100 + 1.5*60 = 135 + 90 = 225 (calcul manuel)."""
    res = apply_combination({"G": 100.0, "Q": 60.0}, {"G": 1.35, "Q": 1.5})
    assert res.value == pytest.approx(225.0)
    assert res.complete is True and res.missing_cases == []


def test_missing_case_flagged_not_silent_zero():
    """Q absent -> manquant signalé, valeur = borne PARTIELLE, pas complet."""
    res = apply_combination({"G": 100.0}, {"G": 1.35, "Q": 1.5})
    assert res.complete is False
    assert res.missing_cases == ["Q"]
    assert res.is_missing_data is True
    assert res.value == pytest.approx(135.0)   # partiel (Q non compté)


def test_coefficients_read_from_combination():
    """Les γ viennent de la combinaison (§9.2), pas de constantes moteur."""
    res = apply_load_combination({"G": 100.0, "Q": 60.0}, FakeCombination())
    assert res.expression == "1.35 G + 1.5 Q"
    assert res.value == pytest.approx(225.0)


def test_line_load_from_area_reference():
    """w = q * largeur = 8 * 3 = 24 kN/m."""
    assert line_load_from_area(8.0, 3.0) == pytest.approx(24.0)


def test_point_load_from_area_reference():
    """P = q * aire * niveaux = 8 * 12 * 3 = 288 kN."""
    assert point_load_from_area(8.0, 12.0, n_levels=3) == pytest.approx(288.0)


def test_negative_inputs_rejected():
    """Donnée de géométrie négative = invalide, jamais propagée silencieusement."""
    with pytest.raises(ValueError):
        line_load_from_area(8.0, -1.0)
    with pytest.raises(ValueError):
        point_load_from_area(8.0, -5.0)
    with pytest.raises(ValueError):
        point_load_from_area(8.0, 5.0, n_levels=-1)


def test_element_actions_from_area_end_to_end():
    """Descente complète : surfacique -> ligne/point -> combinaison."""
    loads = [AreaLoad("G", 6.0), AreaLoad("Q", 3.0)]
    out = element_actions_from_area(
        loads, FakeCombination(),
        tributary_width_m=4.0, tributary_area_m2=10.0, n_levels=2)
    # ligne : (1.35*6 + 1.5*3) * 4 = (8.1+4.5)*4 = 12.6*4 = 50.4 kN/m
    assert out["line"].value == pytest.approx(50.4)
    # point : ((1.35*6 + 1.5*3) en surfacique) puis * aire * niveaux
    #   surfacique combinée = 12.6 kN/m² ; * 10 m² * 2 = 252 kN
    assert out["point"].value == pytest.approx(252.0)
    assert out["line"].complete and out["point"].complete


def test_element_actions_missing_combination_case():
    """Combinaison réclame un cas absent des charges -> manquant signalé."""
    loads = [AreaLoad("G", 6.0)]           # Q absent
    out = element_actions_from_area(
        loads, FakeCombination(), tributary_width_m=4.0)
    assert out["line"].complete is False
    assert "Q" in out["line"].missing_cases
