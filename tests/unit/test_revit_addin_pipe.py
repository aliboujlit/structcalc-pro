# -*- coding: utf-8 -*-
"""
tests/unit/test_revit_addin_pipe.py — Contrat du Named Pipe add-in Revit.

Ces tests utilisent un SERVEUR PIPE MOCKÉ (mode octet, NDJSON) sur un nom
de pipe UNIQUE par test : ils prouvent le comportement réel du connecteur
(sonde PING, retournement des capacités, import/export pivot, refus) sans
dépendre de Revit ni de l'add-in installé — déterminisme total (§17.2).

Règles vérifiées :
  - pipe absent  -> READ_MODEL/WRITE_MODEL NON utilisables + motif d'action ;
  - pipe présent -> capacités PARTIAL utilisables (vrai PING/NDJSON) ;
  - toute réponse hors contrat (JSON cassé, enveloppe sans success) ->
    REFUSED/ERROR, JAMAIS de faux succès ;
  - écriture sans lecture préalable -> REFUSÉE (aucun identifiant inventé) ;
  - unités : Revit (m) -> pivot (cm) à la lecture, pivot (cm) -> m à
    l'écriture.
"""

from __future__ import annotations

import json
import threading
import uuid

import pytest

win32pipe = pytest.importorskip("win32pipe")
win32file = pytest.importorskip("win32file")
pywintypes = pytest.importorskip("pywintypes")

from structcalc.core.model import Project
from structcalc.core.status import DataStatus
from structcalc.integration.interop.base import Capability, CapabilityStatus
from structcalc.integration.interop.revit import RevitConnector


# ---------------------------------------------------------------------------
# Serveur pipe mocké (mode octet, NDJSON, une instance par client)
# ---------------------------------------------------------------------------

class MockAddinServer:
    """Mini-serveur NDJSON reproduisant le contrat de l'add-in .NET."""

    ERROR_PIPE_CONNECTED = 535

    def __init__(self, pipe_name, handler):
        self.pipe_name = pipe_name
        self.handler = handler            # callable(command, payload, server)
        self.received = []                # (command, payload) vus
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # -- cycle de vie --
    def start(self):
        self._thread.start()
        assert self._ready.wait(10), "pipe mock non prêt"

    def stop(self):
        self._stop.set()
        # réveiller un ConnectNamedPipe bloqué
        try:
            h = win32file.CreateFile(
                fr"\\.\pipe\{self.pipe_name}", win32file.GENERIC_READ, 0, None,
                win32file.OPEN_EXISTING, 0, 0)
            win32file.CloseHandle(h)
        except Exception:
            pass

    # -- boucle serveur --
    def _run(self):
        first = True
        while not self._stop.is_set():
            handle = win32pipe.CreateNamedPipe(
                fr"\\.\pipe\{self.pipe_name}",
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE
                | win32pipe.PIPE_WAIT,
                1, 1 << 20, 1 << 20, 0, None)
            if first:
                self._ready.set()
                first = False
            try:
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error as e:
                    if getattr(e, "winerror", None) != self.ERROR_PIPE_CONNECTED:
                        raise
                self._serve_client(handle)
            finally:
                try:
                    win32file.CloseHandle(handle)
                except Exception:
                    pass

    def _serve_client(self, handle):
        buf = b""
        while not self._stop.is_set():
            try:
                _hr, chunk = win32file.ReadFile(handle, 65536)
            except pywintypes.error:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except ValueError:
                    resp = {"success": False, "data": None,
                            "error": "JSON illisible", "request_id": ""}
                else:
                    cmd = str(msg.get("command") or "")
                    payload = msg.get("payload") or ""
                    self.received.append((cmd, payload))
                    resp = self.handler(cmd, payload, self)
                try:
                    win32file.WriteFile(
                        handle, (json.dumps(resp) + "\n").encode("utf-8"))
                except pywintypes.error:
                    return


# ---------------------------------------------------------------------------
# Modèle Revit fictif (camelCase, unités Revit : m / m² / m⁴)
# ---------------------------------------------------------------------------

FAKE_MODEL = {
    "projectName": "Maquette d'essai",
    "revitVersion": "Autodesk Revit 2027",
    "exportTime": "2026-10-18T10:00:00Z",
    "nodes": [
        {"id": 1, "name": "N1", "position": {"x": 0.0, "y": 0.0, "z": 0.0},
         "isSupport": True,
         "support": {"preset": "Pinned", "fixedX": True, "fixedY": True,
                     "fixedZ": True, "fixedRx": False, "fixedRy": False,
                     "fixedRz": False}},
        {"id": 2, "name": "N2", "position": {"x": 4.0, "y": 0.0, "z": 0.0},
         "isSupport": False},
    ],
    "bars": [
        {"id": 123, "startNodeId": 1, "endNodeId": 2, "name": "Poutre 1",
         "structuralType": "Beam",
         "section": {"name": "Béton 25x60", "shape": "Rectangular",
                     "width": 0.25, "height": 0.60},
         "material": {"name": "Béton C25/30", "type": "Concrete"},
         "loads": []},
        {"id": 124, "startNodeId": 1, "endNodeId": 2, "name": "Poteau 1",
         "structuralType": "Column",
         "section": {"name": "Béton 25x60", "shape": "Rectangular",
                     "width": 0.25, "height": 0.60},
         "material": {"name": "Béton C25/30", "type": "Concrete"},
         "loads": []},
        # extrémité non résolvable : doit être ignorée sans invention
        {"id": 125, "startNodeId": 1, "endNodeId": 999, "name": "Barre orpheline",
         "structuralType": "Beam", "section": None, "material": None,
         "loads": []},
    ],
    "loadCases": [{"name": "Charge permanente", "type": "Dead", "number": 1}],
    "notes": ["Matériaux : propriétés physiques non extraites (API 2027)."],
}


def ok_envelope(data, request_id=""):
    return {"success": True, "data": data, "error": "", "request_id": request_id}


def fail_envelope(error, request_id=""):
    return {"success": False, "data": None, "error": error,
            "request_id": request_id}


def default_handler(command, payload, server):
    """Comportement nominal d'un add-in sain."""
    if command == "PING":
        return ok_envelope({"status": "ok", "server": "structcalc_revit"})
    if command == "READ_MODEL":
        return ok_envelope(FAKE_MODEL)
    if command == "APPLY_CHANGES":
        n = len((json.loads(payload) if payload else {})
                .get("barChanges") or [])
        return ok_envelope({"barsUpdated": n, "nodesProcessed": 0,
                            "rebarsCreated": 0,
                            "notes": ["1 armature refusée (enrobage non fourni)"]})
    return fail_envelope(f"Commande inconnue : {command}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_addin():
    """Serveur mocké sain + connecteur pointé dessus (pipe unique)."""
    pipe = f"structcalc_t_{uuid.uuid4().hex[:12]}"
    server = MockAddinServer(pipe, default_handler)
    server.start()
    conn = RevitConnector(pipe_name=pipe, probe_ttl=0.0)
    try:
        yield server, conn
    finally:
        server.stop()


@pytest.fixture
def fresh_project():
    return Project(sc_id="SC-PROJECT-PIPE-01", name="Essai pipe")


# ---------------------------------------------------------------------------
# 1. Sonde et capacités dynamiques
# ---------------------------------------------------------------------------

def test_pipe_absent_refuses_model_with_actionable_motif():
    conn = RevitConnector(pipe_name=f"structcalc_absent_{uuid.uuid4().hex[:8]}",
                          probe_ttl=0.0)
    alive, motif = conn.probe_addin()
    assert alive is False
    assert "Actions" in motif and "deploy_revit_addin" in motif

    caps = conn.capabilities()
    assert caps[Capability.READ_MODEL].status == CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.WRITE_MODEL].status == CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.READ_MODEL].usable is False


def test_pipe_alive_flips_capabilities_to_usable(mock_addin):
    _server, conn = mock_addin
    alive, motif = conn.probe_addin()
    assert alive is True
    assert "PING" in motif

    caps = conn.capabilities()
    read, write = caps[Capability.READ_MODEL], caps[Capability.WRITE_MODEL]
    assert read.status == CapabilityStatus.PARTIAL and read.usable is True
    assert write.status == CapabilityStatus.PARTIAL and write.usable is True
    # la découverte reflète le transport réel (add-in = automatable)
    assert conn.detect().automatable is True


def test_probe_flips_back_when_server_stops(mock_addin):
    server, conn = mock_addin
    assert conn.probe_addin()[0] is True
    server.stop()
    alive, motif = conn.probe_addin()
    assert alive is False
    assert "Actions" in motif
    assert conn.capabilities()[Capability.READ_MODEL].usable is False


# ---------------------------------------------------------------------------
# 2. Lecture : import pivot avec statuts/provenance/units
# ---------------------------------------------------------------------------

def test_read_model_imports_pivot_with_real_statuses(mock_addin, fresh_project):
    _server, conn = mock_addin
    rep = conn.read_model(fresh_project)

    assert rep.status == "PARTIAL"          # 1 barre orpheline signalée
    assert rep.objects["nodes"] == 2
    assert rep.objects["beams"] == 1
    assert rep.objects["columns"] == 1
    assert rep.objects["unresolved"] == 1
    assert rep.objects["supports"] == 1
    assert rep.objects["sections"] == 1
    assert rep.objects["materials"] == 1
    assert rep.objects["load_cases"] == 1

    p = fresh_project
    # nœuds importés (mètres)
    n1 = p.nodes["SC-NODE-V000001"]
    assert float(n1.x.value) == 0.0 and n1.x.status == DataStatus.IMPORTED
    # appui : fixités RÉELLES du preset Pinned (translations seules)
    sup = p.supports["SC-SUPPORT-V000001"]
    assert sup.kind == "pinned"
    assert float(sup.dx.value) == 1.0 and float(sup.rz.value) == 0.0
    assert n1.support is sup
    # barre + poteau distingués, mapping d'identifiants conservé
    beam = p.beams["SC-BEAM-V000123"]
    col = p.columns["SC-COLUMN-V000124"]
    assert beam.start_node == "SC-NODE-V000001"
    assert beam.end_node == "SC-NODE-V000002"
    assert col.start_node == "SC-NODE-V000001"
    assert conn._bar_map == {"SC-BEAM-V000123": 123, "SC-COLUMN-V000124": 124}
    assert beam.external_refs[0].external_id == "123"
    # section : m (Revit) -> cm (pivot)
    sec = p.sections[beam.section]
    assert float(sec.b.value) == 25.0 and float(sec.h.value) == 60.0
    assert sec.b.unit == "cm" and sec.b.status == DataStatus.IMPORTED
    # portée calculée depuis les nœuds (CALCULATED, pas importée)
    assert float(beam.span.value) == 4.0
    assert beam.span.status == DataStatus.CALCULATED
    # matériau : physique RESTE manquante (Revit 2027 sans API vérifiée)
    mat = p.materials[beam.material]
    assert mat.kind == "concrete"
    assert mat.fck.is_missing and mat.E.is_missing
    # cas de charge
    lc = p.load_cases["SC-LCASE-V000001"]
    assert lc.kind == "dead" and lc.nature == "Dead"


def test_read_model_refused_by_addin_error_is_never_success(mock_addin,
                                                            fresh_project):
    server, conn = mock_addin
    server.handler = lambda c, p, s: (
        ok_envelope({"status": "ok"}) if c == "PING" else
        fail_envelope("Aucun document Revit actif — ouvrez un modèle (.rvt)"))
    rep = conn.read_model(fresh_project)
    assert rep.ok is False and rep.status == "REFUSED"
    assert "Aucun document Revit actif" in rep.message
    assert fresh_project.nodes == {}


def test_read_model_garbage_response_is_error_not_ok(mock_addin, fresh_project):
    server, conn = mock_addin
    server.handler = lambda c, p, s: (
        ok_envelope({"status": "ok"}) if c == "PING" else {"status": "ok"})
    rep = conn.read_model(fresh_project)
    assert rep.ok is False
    assert rep.status in ("REFUSED", "ERROR")
    assert fresh_project.nodes == {}


def test_read_model_without_pivot_refused_even_with_pipe(mock_addin):
    _server, conn = mock_addin
    rep = conn.read_model(None)
    assert rep.ok is False
    assert rep.status == "NOT_IMPLEMENTED"
    assert "REFUSÉE" in rep.message


# ---------------------------------------------------------------------------
# 3. Écriture : mappage obligatoire + conversions
# ---------------------------------------------------------------------------

def test_write_model_without_prior_read_refused(mock_addin, fresh_project):
    _server, conn = mock_addin
    rep = conn.write_model(fresh_project)
    assert rep.ok is False and rep.status == "REFUSED"
    assert "lisez d'abord" in rep.message
    assert "inventé" in rep.message


def test_write_model_sends_sections_in_meters(mock_addin, fresh_project):
    server, conn = mock_addin
    assert conn.read_model(fresh_project).status == "PARTIAL"

    # le bureau d'études réduire la poutre : 25x60 -> 30x70 (cm pivot)
    sec = fresh_project.sections[
        fresh_project.beams["SC-BEAM-V000123"].section]
    sec.b = sec.b.__class__.of(30.0, "cm", DataStatus.VALIDATED,
                               sec.b.provenance)
    sec.h = sec.h.__class__.of(70.0, "cm", DataStatus.VALIDATED,
                               sec.h.provenance)

    rep = conn.write_model(fresh_project)
    assert rep.ok is True
    assert rep.objects["bars_sent"] == 2        # poutre + poteau mappés
    assert rep.objects["bars_updated"] == 2
    assert rep.objects["skipped"] == 0

    # le serveur a bien reçu des largeurs en mètres (30 cm -> 0.30 m)
    cmd, payload = server.received[-1]
    assert cmd == "APPLY_CHANGES"
    changes = json.loads(payload)
    by_id = {c["elementId"]: c for c in changes["barChanges"]}
    assert set(by_id) == {123, 124}
    assert by_id[123]["newSection"]["width"] == pytest.approx(0.30)
    assert by_id[123]["newSection"]["height"] == pytest.approx(0.70)
    assert by_id[123]["newSectionName"] == "Béton 25x60"


def test_write_model_without_defined_sections_refused(mock_addin, fresh_project):
    server, conn = mock_addin

    # Profil métallique : Revit ne donne NI largeur NI hauteur -> section
    # présente mais NON définie -> jamais de valeurs devinées (§19)
    import copy
    bare_model = copy.deepcopy(FAKE_MODEL)
    for bar in bare_model["bars"]:
        if bar.get("section"):
            bar["section"] = {"name": bar["section"]["name"],
                              "shape": "Structural",
                              "width": None, "height": None}
    server.handler = lambda c, p, s: (
        ok_envelope({"status": "ok"}) if c == "PING" else
        ok_envelope(bare_model) if c == "READ_MODEL" else
        fail_envelope("ne devrait pas être appelé"))

    assert conn.read_model(fresh_project).status == "PARTIAL"
    # aucune section n'a de dimensions -> jamais de valeurs devinées
    rep = conn.write_model(fresh_project)
    assert rep.ok is False and rep.status == "REFUSED"
    assert "manquantes" in rep.message
    assert rep.objects["skipped"] == 2


def test_write_model_addin_refusal_is_reported(mock_addin, fresh_project):
    server, conn = mock_addin
    assert conn.read_model(fresh_project).status == "PARTIAL"
    sec = fresh_project.sections[
        fresh_project.beams["SC-BEAM-V000123"].section]
    sec.b = sec.b.__class__.of(30.0, "cm", DataStatus.VALIDATED,
                               sec.b.provenance)
    server.handler = lambda c, p, s: (
        ok_envelope({"status": "ok"}) if c == "PING" else
        fail_envelope("Transaction refusée : élément verrouillé"))
    rep = conn.write_model(fresh_project)
    assert rep.ok is False and rep.status == "REFUSED"
    assert "Transaction refusée" in rep.message


# ---------------------------------------------------------------------------
# 4. Protocole : tolérance contrôlée, enveloppe stricte
# ---------------------------------------------------------------------------

def test_client_parses_envelope_missing_optional_keys(mock_addin, fresh_project):
    server, conn = mock_addin
    # enveloppe SANS la clé "error" (tolérance documentée) : doit rester lisible
    server.handler = lambda c, p, s: (
        {"success": True, "data": {"status": "ok"}, "request_id": "x"}
        if c == "PING" else
        {"success": True, "data": FAKE_MODEL, "request_id": "x"})
    rep = conn.read_model(fresh_project)
    # PARTIAL (1 barre orpheline signalée) : honnête, jamais "OK" silencieux
    assert rep.status == "PARTIAL"
    assert rep.ok is False
    assert rep.objects["beams"] == 1


def test_ping_only_needs_alive_addin(mock_addin):
    _server, conn = mock_addin
    from structcalc.integration.interop.revit_addin_client import (
        RevitAddinClient)
    client = RevitAddinClient(pipe_name=conn.pipe_name)
    assert client.connect(retries=3, delay_s=0.1)
    try:
        assert client.ping() is True
    finally:
        client.disconnect()
