# -*- coding: utf-8 -*-
"""
tests/unit/test_rps2011.py — Tests du module sismique RPS 2011 (spec §11.2).

Vérifie les règles de statut (§11.2, §11.3) : paramètres manquants signalés,
valeurs candidates JAMAIS présentées comme conformes, modules non implémentés
explicites.
"""

import pytest

from structcalc.regulation.rps2011.seismic import (
    Rps2011, SeismicParameters, SiteClass,
)
from structcalc.core.status import RegulatoryStatus


@pytest.fixture
def reg():
    return Rps2011()


def test_identity(reg):
    assert reg.identity()["key"] == "RPS2011"
    assert "sismique" in reg.identity()["scope"].lower() or "seism" in reg.identity()["scope"].lower() or "Action" in reg.identity()["scope"]


def test_missing_parameters_flagged(reg):
    p = SeismicParameters(ag=0.25)   # reste 3 manquants
    res = reg.check_parameters_complete(p)
    assert res.status == RegulatoryStatus.DONNEES_MANQUANTES
    assert "site_class" in res.message


def test_unverified_params_never_conform(reg):
    """Règle §11.2 : paramètres non confirmés => A_VALIDER, pas CONFORME."""
    p = SeismicParameters(ag=0.25, site_class=SiteClass.S2,
                          importance_factor=1.0, behavior_factor=6.0,
                          verified=False)
    res = reg.check_parameters_complete(p)
    assert res.status == RegulatoryStatus.A_VALIDER


def test_verified_params_can_be_conform(reg):
    p = SeismicParameters(ag=0.25, site_class=SiteClass.S2,
                          importance_factor=1.0, behavior_factor=6.0,
                          verified=True)
    res = reg.check_parameters_complete(p)
    assert res.status == RegulatoryStatus.CONFORME


def test_site_coefficients_are_candidates(reg):
    p = SeismicParameters(ag=0.25, site_class=SiteClass.S3,
                          importance_factor=1.0, behavior_factor=6.0)
    res = reg.check_site_coefficients(p)
    # candidats -> A_VALIDER, jamais CONFORME
    assert res.status == RegulatoryStatus.A_VALIDER
    assert "CANDIDATS" in res.message


def test_spectrum_never_conform_when_unverified(reg):
    p = SeismicParameters(ag=0.25, site_class=SiteClass.S2,
                          importance_factor=1.0, behavior_factor=6.0,
                          verified=False)
    res = reg.design_spectrum(0.5, p)
    assert res.status != RegulatoryStatus.CONFORME
    assert res.computed_value is not None


def test_spectrum_missing_params(reg):
    p = SeismicParameters(ag=0.25)   # incomplet
    res = reg.design_spectrum(0.5, p)
    assert res.status == RegulatoryStatus.DONNEES_MANQUANTES


def test_modal_analysis_not_implemented(reg):
    """Règle §11.3 : analyse modale non implémentée => statut explicite."""
    res = reg.run_check("modal_analysis")
    assert res.status == RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE
    assert res.passes is False


def test_drift_check_not_implemented(reg):
    res = reg.run_check("drift_limit")
    assert res.status == RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE
