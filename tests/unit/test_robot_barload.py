# -*- coding: utf-8 -*-
"""
tests/unit/test_robot_barload.py — apply_uniform_bar_load (Robot, spec §0 §19 §5.3).

Teste la CHAÎNE corrigée (New/Get/FromText/SetValue) avec un FAUX connecteur —
AUCUNE connexion Robot/COM. La preuve live est dans
tools/probe_bar_uniform_chain_live.py.

Corrige l'ancienne chaîne FAUSSE (Records.Create / rec.Objects= / rec.Fz=).
"""

import pytest

from structcalc.integration.robot.loads import (
    RobotLoadsError,
    apply_uniform_bar_load,
    I_LRT_BAR_UNIFORM,
)


class FakeObjects:
    def __init__(self, rec):
        self._rec = rec

    def FromText(self, txt):
        self._rec.objects_text = txt


class FakeRecord:
    def __init__(self):
        self.objects_text = None
        self.values = {}
        self.Objects = FakeObjects(self)

    def SetValue(self, idx, val):
        self.values[int(idx)] = float(val)

    def GetValue(self, idx):
        return self.values.get(int(idx))


class FakeRecords:
    def __init__(self, fail_new=False):
        self._recs = {}
        self._next = 1
        self.fail_new = fail_new
        self.created_types = []

    def New(self, rectype):
        if self.fail_new:
            raise RuntimeError("Records.New failure")
        self.created_types.append(int(rectype))
        idx = self._next
        self._next += 1
        self._recs[idx] = FakeRecord()
        return idx

    def Get(self, idx):
        return self._recs[int(idx)]


class FakeCase:
    def __init__(self, records):
        self.Records = records


class FakeCases:
    def __init__(self, case):
        self._case = case

    def Get(self, number):
        return self._case


class FakeStructure:
    def __init__(self, cases):
        self.Cases = cases


class FakeRC:
    def __init__(self, is_open=True, fail_new=False):
        self.is_project_open = is_open
        self._records = FakeRecords(fail_new=fail_new)
        self.structure = FakeStructure(FakeCases(FakeCase(self._records)))

    @property
    def records(self):
        return self._records


def test_bar_uniform_uses_correct_chain():
    """New(5) -> Get(idx) -> Objects.FromText -> SetValue(2, fz)."""
    rc = FakeRC()
    res = apply_uniform_bar_load(rc, case_number=1, bar_list="1", fz=-10.0)
    assert rc.records.created_types == [I_LRT_BAR_UNIFORM]      # type 5
    rec = rc.records.Get(res["record_index"])
    assert rec.objects_text == "1"                               # FromText
    assert rec.values[2] == -10.0                                # SetValue Fz
    assert res["rectype"] == I_LRT_BAR_UNIFORM
    assert res["value_index"] == 2
    assert res["applied"] is True


def test_confirmed_rectype_override():
    rc = FakeRC()
    res = apply_uniform_bar_load(rc, 1, "1,2", -5.0, confirmed_rectype=5)
    assert rc.records.created_types == [5]


def test_new_failure_raises_not_fake_success():
    rc = FakeRC(fail_new=True)
    with pytest.raises(RobotLoadsError):
        apply_uniform_bar_load(rc, 1, "1", -10.0)


def test_closed_project_raises():
    rc = FakeRC(is_open=False)
    with pytest.raises(RobotLoadsError):
        apply_uniform_bar_load(rc, 1, "1", -10.0)
