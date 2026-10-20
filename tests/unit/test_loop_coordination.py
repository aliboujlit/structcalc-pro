# -*- coding: utf-8 -*-
"""
tests/unit/test_loop_coordination.py — Mission Navisworks de la boucle
(v1.3) : conversion NWD RÉELLE quand le pivot porte un fichier source
existant ; refus MOTIVÉ sinon — aucun chemin inventé (spec §6), aucune
conversion fantôme.
"""

from structcalc.core.model import Project
from structcalc.integration.interop.base import OpReport
from structcalc.integration.interop.loop import (
    MISSION_COORDINATION, PROFILES, _mission_rows)


class _FakeNW:
    """Connecteur Navisworks factice : connect() + convert() enregistrés."""

    def __init__(self, ok=True):
        self.ok = ok
        self.connected_calls = 0
        self.converted = []

    def connect(self):
        self.connected_calls += 1

    def convert(self, src, dst):
        self.converted.append((src, dst))
        status = "OK" if self.ok else "ERROR"
        return OpReport("navisworks.convert", status, source="navisworks",
                        message=f"{src} -> {dst}")


class _Hub:
    def __init__(self, nw):
        self._nw = nw

    def get(self, key):
        assert key == "navisworks"
        return self._nw


def _rows(nw, project):
    return _mission_rows(_Hub(nw), "navisworks", project, True, "ok", 1)


def test_mission_profile_is_coordination():
    assert PROFILES["navisworks"].mission == MISSION_COORDINATION


def test_coordination_converts_real_source(tmp_path):
    src = tmp_path / "Plan-villa.dwg"
    src.write_bytes(b"DWG-factice")             # fichier RÉEL sur disque
    project = Project(sc_id="SC-P", name="p")
    project.source_file = str(src)
    nw = _FakeNW(ok=True)
    rows = _rows(nw, project)
    assert len(rows) == 1 and rows[0]["success"] is True
    assert nw.converted == [(str(src), str(src.with_suffix(".nwd")))]
    assert "Plan-villa.nwd" in rows[0]["message"]
    assert nw.connected_calls == 1


def test_coordination_refuses_without_source_file():
    project = Project(sc_id="SC-P", name="p")     # source_file vide
    nw = _FakeNW()
    rows = _rows(nw, project)
    assert rows[0]["success"] is False
    assert "source_file" in rows[0]["message"]
    assert nw.converted == []                     # AUCUNE conversion fantôme
    assert nw.connected_calls == 0                # même pas de connexion


def test_coordination_refuses_when_source_missing_on_disk():
    project = Project(sc_id="SC-P", name="p")
    project.source_file = r"C:\inexistant\plan.dwg"
    nw = _FakeNW()
    rows = _rows(nw, project)
    assert rows[0]["success"] is False
    assert nw.converted == []


def test_coordination_propagates_convert_failure(tmp_path):
    src = tmp_path / "plan.dwg"
    src.write_bytes(b"DWG")
    project = Project(sc_id="SC-P", name="p")
    project.source_file = str(src)
    nw = _FakeNW(ok=False)
    rows = _rows(nw, project)
    assert rows[0]["success"] is False            # jamais de faux succès
    assert nw.converted == [(str(src), str(src.with_suffix(".nwd")))]
