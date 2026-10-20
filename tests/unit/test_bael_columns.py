# -*- coding: utf-8 -*-
"""
tests/unit/test_bael_columns.py — Tests du module poteaux BAEL 91 r99 (spec §10, §17.2).

Vérifie surtout les RÈGLES DE STATUT (spec §0, §11.3) :
  - un article non vérifié ne produit JAMAIS « CONFORME » ;
  - flexion composée / second ordre NON implémentés => statut explicite ;
  - cas de référence comparés au calcul manuel (non-régression).
"""

import math
import pytest

from structcalc.regulation.bael91r99.columns import (
    Bael91r99, ColumnGeometry, ColumnMaterials, ColumnActions, REFERENCE_CASES,
)
from structcalc.core.status import RegulatoryStatus


@pytest.fixture
def reg():
    return Bael91r99()


def test_identity_declares_edition(reg):
    ident = reg.identity()
    assert ident["key"] == "BAEL91R99"
    assert "révisé 99" in ident["edition"]
    assert ident["geography"] == "France"


def test_compression_reference_case_matches_manual(reg):
    """Cas de référence : Nr = 0.6*fcd*Ac/1000 (sans acier)."""
    ref = REFERENCE_CASES[0]
    res = reg.check_compression_central(ref["geo"], ref["mat"],
                                        ColumnActions(N=0.0),
                                        As_total_cm2=ref["As_total_cm2"])
    # limit_value = Nr
    assert res.limit_value == pytest.approx(ref["expected_Nr_kN"],
                                            rel=ref["tolerance"])


def test_compression_never_conform_when_article_unverified(reg):
    """Règle §11.3 : article non vérifié => JAMAIS « CONFORME »."""
    geo = ColumnGeometry(25, 25, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)
    res = reg.check_compression_central(geo, mat, ColumnActions(N=200.0),
                                        As_total_cm2=0.0)
    assert res.status != RegulatoryStatus.CONFORME
    assert res.status == RegulatoryStatus.A_VALIDER


def test_compression_ratio_and_margin(reg):
    geo = ColumnGeometry(25, 25, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)   # fcd=20, Nr=750 kN
    res = reg.check_compression_central(geo, mat, ColumnActions(N=150.0),
                                        As_total_cm2=0.0)
    assert res.limit_value == pytest.approx(750.0)
    assert res.computed_value == pytest.approx(150.0)
    assert res.margin == pytest.approx(750.0 - 150.0)   # positif = marge


def test_slenderness_computation(reg):
    geo = ColumnGeometry(20, 40, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)
    res = reg.check_slenderness(geo, mat)
    # i_y = h/sqrt(12) = 40/3.464 = 11.547 ; lam_y = 300/11.547 = 25.98
    i_y = 40 / math.sqrt(12)
    lam_y = 300 / i_y
    assert res.computed_value == pytest.approx(max(lam_y, 300/(20/math.sqrt(12))))


def test_flexion_composed_implemented_but_a_valider(reg):
    """§10.3/§11.3 : flexion composée IMPLÉMENTÉE via diagramme d'interaction,
    mais article non vérifié => A_VALIDER (jamais CONFORME silencieux)."""
    geo = ColumnGeometry(40, 40, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)
    bars = [(5.0, 2.01), (5.0, 2.01), (15.0, 2.01), (15.0, 2.01),
            (25.0, 2.01), (25.0, 2.01), (35.0, 2.01), (35.0, 2.01)]
    res = reg.check_flexion_composed(geo, mat, ColumnActions(N=1500.0, My=40.0), bars)
    assert res.status == RegulatoryStatus.A_VALIDER      # non vérifié -> pas Conforme
    assert res.passes is False
    assert res.margin is not None and res.margin > 0      # dedans du diagramme


def test_unregistered_check_is_non_implemented(reg):
    """Règle §11.3 : une vérification non enregistrée => statut explicite."""
    res = reg.run_check("verif_qui_nexiste_pas")   # non enregistrée
    assert res.status == RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE
    assert res.passes is False


def test_min_reinforcement_flags_too_low(reg):
    geo = ColumnGeometry(25, 25, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)
    # Ac=625, As,min=0.001*625=0.625 ; donner 0.3 -> insuffisant
    res = reg.check_min_reinforcement(geo, mat, As_provided_cm2=0.3)
    assert res.status == RegulatoryStatus.NON_CONFORME


def test_min_reinforcement_ok_but_never_silent_conform(reg):
    geo = ColumnGeometry(25, 25, 3.0, 3.0, 3.0)
    mat = ColumnMaterials(fck=30, fyk=500, E=200000)
    res = reg.check_min_reinforcement(geo, mat, As_provided_cm2=5.0)
    # dans les bornes -> A_VALIDER (rho_min à confirmer, pas CONFORME silent)
    assert res.status == RegulatoryStatus.A_VALIDER


def test_material_strengths(reg):
    mat = ColumnMaterials(fck=30, fyk=500, E=200000, gamma_c=1.5, gamma_s=1.15)
    res = reg.check_material_strengths(mat)
    assert res.computed_value == pytest.approx(30 / 1.5)   # fcd
    assert res.limit_value == pytest.approx(500 / 1.15)    # fyd
