# -*- coding: utf-8 -*-
"""
tests/unit/test_revit_integration.py — Tests unitaires intégration Revit.

Teste le protocole NDJSON, le mapping familles, et le writer
avec de FAUX connecteurs (aucun Revit/COM requis).
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from structcalc.integration.revit.protocol import (
    RevitPipeClient, PipeEnvelope, RevitPipeError, RevitProtocolError,
)
from structcalc.integration.revit.families import (
    FamiliesMap, FamilyMapEntry, write_default_mapping,
)
from structcalc.integration.revit.writer import (
    build_apply_changes_request, WriteReport,
)
from structcalc.integration.interop.base import Capability, CapabilityStatus
from structcalc.core.model import Project, Column, Beam, Node, CrossSection
from structcalc.core.status import DataStatus
from structcalc.core.tracked import Provenance, TrackedValue
from structcalc.reporting.plan_ferraillage import ReinforcementPlan


# ---------------------------------------------------------------------------
# Fake pour le pipe (simule l'add-in Revit côté C#)
# ---------------------------------------------------------------------------

class _FakePipeServer:
    """Simule l'add-in Revit qui répond aux commandes NDJSON."""

    def __init__(self):
        self.responses: Dict[str, Dict] = {}
        self.received: list = []

    def set_response(self, command: str, envelope: PipeEnvelope):
        self.responses[command] = envelope

    def handle(self, line: str) -> str:
        self.received.append(line)
        req = json.loads(line)
        cmd = req.get("command")
        req_id = req.get("request_id", "")
        if cmd in self.responses:
            env = self.responses[cmd]
            env.request_id = req_id
            return json.dumps({
                "success": env.success,
                "data": env.data,
                "error": env.error,
                "request_id": env.request_id,
            })
        # Réponses par défaut
        if cmd == "PING":
            return json.dumps({
                "success": True,
                "data": {"pipe": "structcalc_revit", "listening": True, "clients": 1},
                "error": "",
                "request_id": req_id,
            })
        return json.dumps({
            "success": False,
            "data": None,
            "error": f"Commande inconnue: {cmd}",
            "request_id": req_id,
        })


class _FakeRevitPipeClient(RevitPipeClient):
    """Client pipe qui utilise un faux serveur en mémoire."""

    def __init__(self, fake_server: _FakePipeServer):
        super().__init__()
        self._fake = fake_server
        self._connected = True

    def _send_line(self, line: str) -> None:
        # Pas d'envoi réel, on simule la réponse
        pass

    def _read_line(self, timeout: float = 10.0) -> str:
        # On ne lit pas vraiment, on utilise la dernière requête envoyée
        if not hasattr(self, "_last_line"):
            raise RevitPipeError("Pas de requête envoyée")
        return self._fake.handle(self._last_line)

    def _request(self, command: str, payload: Any = None) -> Any:
        req_id = str(uuid.uuid4())[:8]
        msg = {
            "command": command,
            "payload": payload,
            "request_id": req_id,
        }
        self._last_line = json.dumps(msg, separators=(",", ":"))
        line = self._read_line()
        env = json.loads(line)
        envelope = PipeEnvelope(
            success=env.get("success", False),
            data=env.get("data"),
            error=env.get("error", ""),
            request_id=env.get("request_id", ""),
        )
        if not envelope.success:
            raise RevitProtocolError(f"Commande {command} échouée : {envelope.error}")
        return envelope.data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _tv(v):
    return TrackedValue.of(float(v), "m", DataStatus.IMPORTED, Provenance.imported_from("Robot"))


def _villa_fake() -> Project:
    p = Project(sc_id="SC-P", name="Villa-test")
    for i, (x, y) in enumerate([(0, 0), (6, 0), (6, 4), (0, 4)]):
        p.nodes[f"N{i}"] = Node(sc_id=f"N{i}", x=_tv(x), y=_tv(y), z=_tv(0.0))
        p.nodes[f"N{i}b"] = Node(sc_id=f"N{i}b", x=_tv(x), y=_tv(y), z=_tv(2.8))
    p.sections["S1"] = CrossSection(sc_id="S1", name="C R30x30")
    for i in range(4):
        p.columns[f"C{i}"] = Column(sc_id=f"C{i}", start_node=f"N{i}", end_node=f"N{i}b", section="S1")
    p.beams["B0"] = Beam(sc_id="B0", start_node="N0b", end_node="N1b", section="S1")
    return p


def test_families_map_load_save():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "families_map.json"
        write_default_mapping(str(path))
        fmap = FamiliesMap.load(str(path))
        assert fmap.version == 1
        assert fmap.default_beam_family == "Poutre_Rectangulaire"
        assert "C R30x30" in fmap.sections
        entry = fmap.sections["C R30x30"]
        assert entry.family == "Poteau_Rectangulaire"
        assert entry.type_name == "30x30"
        assert entry.width_m == 0.30
        assert entry.height_m == 0.30


def test_families_map_missing_file():
    with pytest.raises(FileNotFoundError):
        FamiliesMap.load("/nonexistent/families_map.json")


def test_build_apply_changes_request_with_mapping():
    p = _villa_fake()
    fmap = FamiliesMap(
        version=1,
        default_beam_family="Poutre_Rectangulaire",
        sections={
            "C R30x30": FamilyMapEntry(
                family="Poteau_Rectangulaire", type_name="30x30",
                width_m=0.30, height_m=0.30),
        },
    )
    request = build_apply_changes_request(p, fmap)
    assert "barChanges" in request
    # 4 poteaux + 1 poutre (B0) utilisent la section "C R30x30" mappée
    assert len(request["barChanges"]) == 5
    for bc in request["barChanges"]:
        assert bc["newSectionName"] == "30x30"
        assert "width" in bc["newSection"]
        assert bc["newSection"]["width"] == 0.30


def test_build_apply_changes_request_skips_unmapped():
    p = _villa_fake()
    fmap = FamiliesMap(version=1, default_beam_family="Poutre", sections={})
    request = build_apply_changes_request(p, fmap)
    assert len(request["barChanges"]) == 0  # aucune section mappée


def test_reinforcement_plan_to_rebar_dtos():
    plan = ReinforcementPlan(
        column_id="SC-COL-R000001", b_cm=50, h_cm=50, height_m=3.0,
        as_required_cm2=75.0, bar_d_mm=32.0, bar_count=10,
        stirrup_d_mm=8.0, stirrup_e_zone_mm=200.0, stirrup_e_corps_mm=400.0,
    )
    from structcalc.integration.revit.reinforcement import _plan_to_rebar_dtos
    dtos = _plan_to_rebar_dtos(plan)
    assert len(dtos) == 2
    assert dtos[0]["layer"] == "Longitudinal"
    assert dtos[0]["diameterMm"] == 32
    assert dtos[0]["count"] == 10
    assert dtos[1]["layer"] == "Stirrups"
    assert dtos[1]["diameterMm"] == 8


def test_write_report_ok_partial():
    r = WriteReport()
    r.bars_processed = 4
    r.sections_applied = 4
    r.rebars_created = 8
    r.add_note("OK")
    assert r.ok is True

    r2 = WriteReport()
    r2.add_error("Pipe failed")
    assert r2.ok is False


def test_pipe_envelope_serialization():
    env = PipeEnvelope.ok({"foo": "bar"}, "req123")
    assert env.success is True
    assert env.data == {"foo": "bar"}
    assert env.request_id == "req123"

    env2 = PipeEnvelope.fail("Erreur test", "req456")
    assert env2.success is False
    assert env2.error == "Erreur test"
    assert env2.data is None


# Test d'intégration avec faux pipe (simule la boucle complète)
def test_write_model_to_revit_fake_pipe():
    import uuid
    from structcalc.integration.revit.writer import write_model_to_revit

    p = _villa_fake()
    with tempfile.TemporaryDirectory() as tmp:
        fmap_path = Path(tmp) / "families_map.json"
        write_default_mapping(str(fmap_path))

        fake_server = _FakePipeServer()
        # Réponse PING
        fake_server.set_response("PING", PipeEnvelope.ok(
            {"pipe": "structcalc_revit", "listening": True, "clients": 1}, "ping1"))
        # Réponse APPLY_CHANGES
        fake_server.set_response("APPLY_CHANGES", PipeEnvelope.ok(
            {"barsUpdated": 4, "nodesProcessed": 0, "rebarsCreated": 8,
             "notes": ["4 barres modifiées", "8 armatures créées"]}, "apply1"))

        client = _FakeRevitPipeClient(fake_server)

        # Mock du ReinforcementPlan pour un poteau
        plans = {}
        col = p.columns["C0"]
        plans[col.sc_id] = ReinforcementPlan(
            column_id=col.sc_id, b_cm=50, h_cm=50, height_m=2.8,
            as_required_cm2=75.0, bar_d_mm=32.0, bar_count=10,
            stirrup_d_mm=8.0, stirrup_e_zone_mm=200.0, stirrup_e_corps_mm=400.0,
        )

        report = write_model_to_revit(p, str(fmap_path), reinforcement_plans=plans, pipe_client=client)

        assert report.ok is True
        assert report.bars_processed == 5  # 4 poteaux + 1 poutre (même section mappée)
        assert report.sections_applied == 4
        assert report.rebars_created == 8


# Test que le connecteur Revit refuse proprement sans pipe accessible
def test_revit_connector_refuse_without_pipe():
    from structcalc.integration.interop.revit import RevitConnector

    conn = RevitConnector(families_map_path="/nonexistent.json")
    det = conn.detect()
    # Si Revit est installé mais pipe inaccessible : installed=True, automatable=False
    # Le test vérifie que la matrice de capacités reflète l'état réel du pipe
    assert det.automatable is False

    caps = conn.capabilities()
    # Sans pipe utilisable : CONNECT, READ_MODEL, WRITE_MODEL = NOT_IMPLEMENTED
    assert caps[Capability.DETECT].status == CapabilityStatus.SUPPORTED
    for cap in (Capability.CONNECT, Capability.READ_MODEL, Capability.WRITE_MODEL):
        assert caps[cap].status == CapabilityStatus.NOT_IMPLEMENTED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])