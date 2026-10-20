# -*- coding: utf-8 -*-
"""
tests/unit/test_column_design.py — Tests du moteur de dimensionnement poteaux (spec §10.4).

Vérifie : génération de candidates, classement, séparation viables/échouées,
statuts honnêtes (jamais « conforme » silencieux), rappel de recalcul global.
"""

import pytest

from structcalc.solver.column_design import (
    ColumnDesigner, ColumnVariant, ColumnMaterials, ColumnActions,
)
from structcalc.regulation.bael91r99.columns import ColumnMaterials as Mat
from structcalc.core.status import RegulatoryStatus


def _mat():
    return Mat(fck=30, fyk=500, E=200000)


def _actions(N=100.0):
    return ColumnActions(N=N, combination="1.35G+1.5Q")


def test_generate_candidates_grid():
    cands = ColumnDesigner.generate_candidates([20, 30], [0.01, 0.02])
    # 2 tailles x 2 ratios = 4
    assert len(cands) == 4
    labels = {c.designation for c in cands}
    assert any("20x20" in l for l in labels)


def test_design_variant_collects_checks():
    d = ColumnDesigner()
    v = ColumnVariant(b=30, h=30, As_provided_cm2=9.0)
    out = d.design_variant(v, height=3.0, buckling_y=3.0, buckling_z=3.0,
                           materials=_mat(), actions=_actions(N=500.0))
    # au moins 3 checks + 1 non-implémenté sismique
    assert len(out.checks) >= 4
    # le check sismique non implémenté est tracé
    assert "seismic_detailing" in out.to_validate


def test_slenderness_over_limit_flagged_for_validation():
    """
    Une colonne très élancée n'est PAS rejetée durement (l'article est non
    vérifié -> A_VALIDER, jamais un faux NON_CONFORME), mais elle est
    EXPLICITEMENT signalée pour validation ingénieur (spec §11.3).
    """
    d = ColumnDesigner()
    # très long et fine -> élancement élevé
    v = ColumnVariant(b=10, h=10, As_provided_cm2=1.0)
    out = d.design_variant(v, height=6.0, buckling_y=6.0, buckling_z=6.0,
                           materials=_mat(), actions=_actions(N=100.0))
    # L'élancement est signalé pour arbitrage (pas de rejet dur silencieux)
    assert "slenderness" in out.to_validate
    # et aucun check n'est prétendu CONFORME
    assert all(c.status != RegulatoryStatus.CONFORME for c in out.checks)


def test_ranking_excludes_failed():
    d = ColumnDesigner()
    actions = _actions(N=300.0)
    results = d.search(height=3.0, buckling_y=3.0, buckling_z=3.0,
                       materials=_mat(), actions=actions,
                       candidates=ColumnDesigner.generate_candidates(
                           [20, 30, 40], [0.01, 0.02]))
    # tous les retours sont des viables (is_candidate True)
    assert all(r.is_candidate for r in results)
    # rangs séquentiels croissants
    ranks = [r.rank for r in results]
    assert ranks == list(range(1, len(results) + 1))


def test_no_silent_conform_in_outcomes():
    """Aucun outcome ne peut contenir un CONFORME 'silencieux' des checks."""
    d = ColumnDesigner()
    v = ColumnVariant(b=30, h=30, As_provided_cm2=9.0)
    out = d.design_variant(v, 3.0, 3.0, 3.0, _mat(), _actions(N=300.0))
    for c in out.checks:
        # compression/élancement/armature : jamais CONFORME (article non vérifié)
        if c.check_id in ("compression_central", "slenderness", "min_reinforcement"):
            assert c.status != RegulatoryStatus.CONFORME


def test_requires_global_reanalysis_flag():
    d = ColumnDesigner()
    results = d.search(height=3.0, buckling_y=3.0, buckling_z=3.0,
                       materials=_mat(), actions=_actions(N=200.0))
    assert results, "aucune viable retournée"
    assert d.requires_global_reanalysis(results[0]) is True


def test_outcome_to_dict_shape():
    d = ColumnDesigner()
    v = ColumnVariant(b=25, h=25, As_provided_cm2=6.0)
    out = d.design_variant(v, 3.0, 3.0, 3.0, _mat(), _actions(N=200.0))
    dd = out.to_dict()
    assert dd["section"] == "25x25"
    assert "status_summary" in dd
    assert isinstance(dd["to_validate"], list)
