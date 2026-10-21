# -*- coding: utf-8 -*-
"""
tests/unit/test_exchange_navworks.py — Test de l'échange spécial
Navisworks (convertisseur DWG -> NWD) dans exchange_plan.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from structcalc.core.model import Project
from structcalc.integration.interop.base import OpReport, Capability
from structcalc.integration.interop.loop import (
    plan_loop, Selection, _exchange_to_navisworks, PROFILES,
)


class _FakeExporter:
    """Exportateur DWG factice (AutoCAD/Civil3D/AdvSteel)."""

    def __init__(self, name, write_ok=True):
        self.name = name
        self.write_ok = write_ok
        self._last_doc = None
        self.connected = False
        self.saved_path = None
        self.connected_calls = 0
        self.write_calls = 0

    def connect(self):
        self.connected = True
        self.connected_calls += 1

    def write_model(self, project):
        self.write_calls += 1
        if self.write_ok:
            self._last_doc = object()  # fake doc
            return OpReport("write_model", "OK", source=self.name,
                            message="OK")
        return OpReport("write_model", "ERROR", source=self.name,
                        message="write failed")

    def save_document(self, doc, path):
        self.saved_path = path
        # Créer le fichier pour que le test voie qu'il existe
        Path(path).write_bytes(b"DWG-FAKE")


class _FakeNW:
    def __init__(self, ok=True):
        self.ok = ok
        self.connected = False
        self.converted = []

    def connect(self):
        self.connected = True

    def convert(self, src, dst):
        self.converted.append((src, dst))
        status = "OK" if self.ok else "ERROR"
        return OpReport("convert", status if self.ok else "ERROR",
                        source="navisworks", message=f"{src} -> {dst}")


class _Hub:
    def __init__(self, exporter, nw):
        self._exporter = exporter
        self._nw = nw
        self.names = [exporter.name, "navisworks"]

    def get(self, key):
        if key == self._exporter.name:
            return self._exporter
        if key == "navisworks":
            return self._nw
        raise KeyError(key)


def _fake_step(order, source, target, phase):
    from structcalc.integration.interop.loop import LoopStep
    return type("Step", (), {
        "order": order,
        "source": source,
        "target": target,
        "phase": phase,
    })()


def test_exchange_to_navworks_success(tmp_path):
    """Échange vers Navisworks : export DWG + convert -> NWD."""
    project = Project(sc_id="SC-P", name="test")
    exporter = _FakeExporter("autocad")
    nw = _FakeNW(ok=True)
    hub = _Hub(exporter, nw)

    st = _fake_step(1, "autocad", "navisworks", "Conception -> Coordination")

    rows = _exchange_to_navisworks(hub, st, project, connect=True)

    # Vérifier la séquence : export DWG -> convert -> livrable NWD (3 lignes)
    assert len(rows) == 3  # export DWG + convert + mission NWD
    # row 0: export DWG
    assert rows[0]["action"].startswith("Export DWG (")
    assert rows[0]["success"] is True
    # row 1: convert
    assert rows[1]["action"] == "Convert DWG -> NWD (Navisworks)"
    assert rows[1]["success"] is True
    assert ".nwd" in rows[1]["message"]
    # row 2: mission NWD livrable
    assert rows[2]["action"] == "Livrable coordination NWD"
    assert rows[2]["success"] is True

    # Vérifier les appels
    assert exporter.connected_calls == 1
    assert exporter.write_calls == 1
    assert exporter.saved_path is not None
    # Le fichier DWG est nettoyé par le finally (normal) - vérifier le NWD
    assert nw.converted == [(exporter.saved_path, exporter.saved_path.replace(".dwg", ".nwd"))]


def test_exchange_to_navworks_no_exporter(tmp_path):
    """Aucun exportateur DWG dispo -> refus (revit n'est pas exportateur DWG)."""
    project = Project(sc_id="SC-P", name="test")
    nw = _FakeNW()
    # Hub avec revit comme exportateur (revit n'est PAS dans dwg_exporters)
    exporter = _FakeExporter("revit")
    hub = _Hub(exporter, nw)

    st = _fake_step(1, "revit", "navisworks", "Conception -> Coordination")

    rows = _exchange_to_navisworks(hub, st, project, connect=True)

    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "Aucun exportateur DWG disponible" in rows[0]["message"]


def test_exchange_to_navworks_exporter_failure(tmp_path):
    """Échec write_model de l'exportateur -> refus."""
    project = Project(sc_id="SC-P", name="test")
    exporter = _FakeExporter("autocad", write_ok=False)
    nw = _FakeNW()
    hub = _Hub(exporter, nw)

    st = _fake_step(1, "autocad", "navisworks", "Conception -> Coordination")

    rows = _exchange_to_navisworks(hub, st, project, connect=True)

    assert len(rows) == 1  # export DWG (échec) + pas de convert
    assert rows[0]["success"] is False
    assert "write_model autocad refusé" in rows[0]["message"]
    assert nw.converted == []


def test_exchange_to_navworks_convert_failure(tmp_path):
    """Échec conversion Navisworks -> signalé."""
    project = Project(sc_id="SC-P", name="test")
    exporter = _FakeExporter("autocad")
    nw = _FakeNW(ok=False)
    hub = _Hub(exporter, nw)

    st = _fake_step(1, "autocad", "navisworks", "Conception -> Coordination")

    rows = _exchange_to_navisworks(hub, st, project, connect=True)

    assert rows[1]["success"] is False
    assert rows[1]["step_failed"] == "write"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])