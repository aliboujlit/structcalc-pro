# -*- coding: utf-8 -*-
"""
tests/unit/test_interaction.py — Diagramme d'interaction N/M + 2ᵉ ordre (spec §10.3, §11.3, §17.2).

Valide la COHÉRENCE INTERNE de la méthodologie (pas la conformité réglementaire,
qui reste gate sur verified=False) par des cas de référence à calcul manuel :
  - bornes compression/traction pures = valeurs théoriques ;
  - conversion d'unités MPa·cm² -> kN explicite (spec §5.3) ;
  - moment résistant positif à N=0 ;
  - amplification du 2ᵉ ordre > 1 et instabilité N ≥ N_cr ;
  - charge critique Euler N_cr = π²EI/l0².
"""

import math
import pytest

from structcalc.regulation.bael91r99.interaction import (
    K_MPA_CM2_TO_KN,
    RectSection,
    DesignMaterials,
    SectionModel,
    SecondOrderInput,
    interaction_diagram,
    capacity_at_normal,
    critical_buckling_load,
    second_order_moment,
)


@pytest.fixture
def sec_mat():
    # Poteau 40x40, 8 barres H16 (2.01 cm2) à d = 5/15/25/35 cm
    fcd = 30.0 / 1.5        # 20 MPa
    fyd = 500.0 / 1.15      # 434.78 MPa
    mat = DesignMaterials(fcd=fcd, fyd=fyd, Es=200000.0)
    bars = [(5.0, 2.01), (5.0, 2.01), (15.0, 2.01), (15.0, 2.01),
            (25.0, 2.01), (25.0, 2.01), (35.0, 2.01), (35.0, 2.01)]
    sec = RectSection(b=40.0, h=40.0, bars=bars)
    return sec, mat


def test_unit_conversion_constant():
    """1 kN = 10 MPa.cm² (1 MPa.cm² = 100 N) — contrôle des unités §5.3."""
    assert K_MPA_CM2_TO_KN == 10.0
    # 0.6*fcd[MPa]*Ac[cm2] sur 25x25, fcd=20 -> 7500 MPa.cm2 = 750 kN
    Nr_kN = 0.6 * 20.0 * (25.0 * 25.0) / K_MPA_CM2_TO_KN
    assert Nr_kN == pytest.approx(750.0)


def test_pure_compression_boundary(sec_mat):
    """Borne compression max = η·fcd·Ac + fyd·As (tous les aciers comprimés)."""
    sec, mat = sec_mat
    diag = interaction_diagram(sec, mat, n_points=60)
    N_max = diag[0][0]
    theo = (0.85 * mat.fcd * sec.Ac + mat.fyd * sec.As_total) / K_MPA_CM2_TO_KN
    assert N_max == pytest.approx(theo, rel=1e-6)
    assert N_max > 3000.0     # ~3419 kN, physiquement plausible


def test_pure_tension_boundary(sec_mat):
    """Borne traction min = −fyd·As (béton non fissuré négligé en traction)."""
    sec, mat = sec_mat
    diag = interaction_diagram(sec, mat, n_points=60)
    N_min = diag[-1][0]
    theo = -(mat.fyd * sec.As_total) / K_MPA_CM2_TO_KN
    assert N_min == pytest.approx(theo, rel=1e-6)
    assert N_min < 0.0


def test_diagram_normal_decreasing(sec_mat):
    """Les points sont triés par N décroissant (compression -> traction)."""
    sec, mat = sec_mat
    diag = interaction_diagram(sec, mat, n_points=80)
    Ns = [n for n, _ in diag]
    assert Ns == sorted(Ns, reverse=True)


def test_moment_at_zero_normal_positive(sec_mat):
    """À N=0, le moment résistant est strictement positif et plausible."""
    sec, mat = sec_mat
    Mr = capacity_at_normal(sec, mat, 0.0)
    assert Mr is not None and Mr > 0.0
    assert 10.0 < Mr < 200.0   # ~30 kN.m pour un 40x40 biaxial simple


def test_capacity_out_of_range_returns_none(sec_mat):
    """N au-delà du domaine -> None (pas de faux chiffre)."""
    sec, mat = sec_mat
    assert capacity_at_normal(sec, mat, 1.0e9) is None


def test_critical_buckling_load_euler():
    """N_cr = π²·EI / l0²."""
    N_cr = critical_buckling_load(2.0e6, 3.0)
    assert N_cr == pytest.approx(math.pi ** 2 * 2.0e6 / 9.0, rel=1e-9)


def test_second_order_amplifies_moment():
    """M2 > M1 (amplification nominale) et N_cr correct."""
    inp = SecondOrderInput(N_ed_kN=800.0, M1_kNm=50.0, l0_m=3.0, EI_kNm2=2.0e6)
    res = second_order_moment(inp)
    assert res["stable"] is True
    assert res["M2_kNm"] > 50.0
    assert res["amplification"] > 1.0
    assert res["N_cr_kN"] == pytest.approx(math.pi ** 2 * 2.0e6 / 9.0, rel=1e-9)


def test_second_order_instability_when_N_ge_Ncr():
    """N ≥ N_cr -> instabilité explicite (M2 non fini, jamais un succès)."""
    inp = SecondOrderInput(N_ed_kN=3.0e6, M1_kNm=50.0, l0_m=3.0, EI_kNm2=2.0e6)
    res = second_order_moment(inp)
    assert res["stable"] is False
    assert res["M2_kNm"] is None
    assert "instabilité" in res["reason"]


def test_section_model_is_parametrized():
    """Les coefficients de méthode sont PARAMÉTRÉS (spec §3.4), pas en dur."""
    m = SectionModel(lam_block=0.8, eta_block=0.85, eps_cu=0.0035, alpha_cc=1.0)
    assert m.lam_block == 0.8 and m.eta_block == 0.85
    # une valeur non par défaut est acceptée (aucune n'est unique vérité)
    m2 = SectionModel(lam_block=0.7, eta_block=0.80)
    assert m2.lam_block == 0.7
