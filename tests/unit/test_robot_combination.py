# -*- coding: utf-8 -*-
"""
tests/unit/test_robot_combination.py — create_combination (Robot, spec §0 §19).

Teste la LOGIQUE (ordre positionnel, coefficients, chemins d'erreur) avec un
FAUX connecteur — AUCUNE connexion Robot/COM. La preuve d'exécution réelle est
dans tools/probe_create_combination_live.py.
"""

import pytest

from structcalc.integration.robot.loads import (
    RobotLoadsError,
    create_combination,
    COMB_TYPE_ULS,
    COMB_TYPE_ALS,
    CASE_NATURE_PERMANENT,
    CASE_NATURE_SNOW,
    CASE_ANALIZE_COMB_LINEAR,
)


class FakeCaseFactors:
    def __init__(self):
        self.added = []

    def New(self, case_no, coeff):
        self.added.append((case_no, coeff))


class FakeCombination:
    def __init__(self):
        self.CaseFactors = FakeCaseFactors()


class FakeCases:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.comb = FakeCombination()

    def CreateCombination(self, number, name, comb_type, case_nature,
                          case_analize_type):
        if self.fail:
            raise RuntimeError("COM failure")
        self.calls.append((number, name, comb_type, case_nature,
                           case_analize_type))
        return self.comb


class FakeStructure:
    def __init__(self, cases):
        self.Cases = cases


class FakeRC:
    def __init__(self, is_open=True, fail=False):
        self.is_project_open = is_open
        self.structure = FakeStructure(FakeCases(fail=fail))


def test_create_combination_positional_order():
    """L'ordre (number, name, comb_type, case_nature, case_analize_type) est
    transmis tel quel à Cases.CreateCombination (prouvé live)."""
    rc = FakeRC()
    res = create_combination(rc, 10, "ULS 1", factors=[(1, 1.35), (2, 1.5)],
                             comb_type=COMB_TYPE_ULS,
                             case_nature=CASE_NATURE_PERMANENT,
                             case_analize_type=CASE_ANALIZE_COMB_LINEAR)
    assert rc.structure.Cases.calls == [(10, "ULS 1", 0, 0, 0)]
    assert res["created"] is True


def test_factors_applied_as_list_and_dict():
    rc = FakeRC()
    create_combination(rc, 11, "A", factors=[(1, 1.35), (2, 1.5)])
    assert rc.structure.Cases.comb.CaseFactors.added == [(1, 1.35), (2, 1.5)]

    rc2 = FakeRC()
    create_combination(rc2, 12, "B", factors={1: 1.35, 2: 1.5})
    assert rc2.structure.Cases.comb.CaseFactors.added == [(1, 1.35), (2, 1.5)]


def test_distinct_enum_values_forwarded():
    """Les enums (ALS=2, SNOW=3, COMB=0) sont transmis sans transformation."""
    rc = FakeRC()
    create_combination(rc, 13, "C", factors=[],
                       comb_type=COMB_TYPE_ALS,
                       case_nature=CASE_NATURE_SNOW,
                       case_analize_type=CASE_ANALIZE_COMB_LINEAR)
    assert rc.structure.Cases.calls == [(13, "C", 2, 3, 0)]


def test_closed_project_raises():
    rc = FakeRC(is_open=False)
    with pytest.raises(RobotLoadsError):
        create_combination(rc, 20, "X", factors=[])


def test_com_failure_raises_not_fake_success():
    """Une erreur COM doit lever RobotLoadsError, jamais renvoyer un succès."""
    rc = FakeRC(fail=True)
    with pytest.raises(RobotLoadsError):
        create_combination(rc, 21, "Y", factors=[(1, 1.0)])
