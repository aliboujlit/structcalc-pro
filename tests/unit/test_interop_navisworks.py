# -*- coding: utf-8 -*-
"""
tests/unit/test_interop_navisworks.py — Connecteur Navisworks (COM vérifié).

Faits vérifiés par sonde (probe_nw_step / probe_nw_discover) sur Navisworks
Manage 2027 : ProgID `Navisworks.Document.24` expose `Visible`, `OpenFile(1)`,
`SaveAs(1)`, et RIEN d'autre (pas de membre de modèle, §19).

Ces tests n'utilisent AUCUN logiciel : une FAUSSE app COM est injectée pour
vérifier la logique du connecteur (refus quand non connecté, refus fichier
absent, chemin OK, propagation d'erreur) et sa matrice de capacités honnête.
La détection registre est testée sans lancer Navisworks.
"""

from __future__ import annotations

from structcalc.integration.interop import (
    Capability, CapabilityStatus, NavisworksConnector, default_hub,
)


# ---------------------------------------------------------------------------
# Fausse app COM (aucun Dispatch réel)
# ---------------------------------------------------------------------------

class FakeNavisApp:
    """Fausse app Navisworks : enregistre OpenFile/SaveAs, Visible lisible."""

    def __init__(self):
        self.Visible = False
        self.opened = []
        self.saved = []

    def OpenFile(self, path):
        self.opened.append(path)

    def SaveAs(self, path):
        self.saved.append(path)


class FailingNavisApp:
    """Fausse app dont OpenFile/SaveAs lèvent (test de propagation d'erreur)."""

    Visible = False

    def OpenFile(self, path):
        raise RuntimeError("simulated OpenFile failure")

    def SaveAs(self, path):
        raise RuntimeError("simulated SaveAs failure")


def _connected(app):
    """Connecteur Navisworks branché sur une fausse app (sans COM)."""
    c = NavisworksConnector()
    c._app = app
    c._connected = True
    return c


# ---------------------------------------------------------------------------
# Détection (registre, sans lancement) + capacités honnêtes
# ---------------------------------------------------------------------------

def test_detect_is_registry_only_and_structural():
    """detect() renvoie une Detection cohérente SANS lancer Navisworks."""
    det = NavisworksConnector().detect()
    assert det.name == "navisworks"
    assert det.transport == "com"
    # automatable est un booléen réel (True si ProgIDs au registre)
    assert isinstance(det.automatable, bool)
    if det.automatable:
        assert det.installed is True
        assert any(p.startswith("Navisworks.Document") for p in det.progs)


def test_capabilities_read_write_model_not_supported():
    """§19 : aucun membre COM de modèle -> read/write_model NOT_SUPPORTED."""
    caps = NavisworksConnector().capabilities()
    assert caps[Capability.DETECT].status is CapabilityStatus.SUPPORTED
    assert caps[Capability.CONNECT].status is CapabilityStatus.SUPPORTED
    assert caps[Capability.READ_MODEL].status is CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.WRITE_MODEL].status is CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.READ_MODEL].usable is False
    assert caps[Capability.WRITE_MODEL].usable is False
    # motif non vide (jamais de refus muet)
    assert caps[Capability.READ_MODEL].detail


def test_read_write_model_refused_not_ok():
    """read_model/write_model renvoient un REFUSED explicite (pas de faux succès)."""
    c = _connected(FakeNavisApp())
    r_read = c.read_model(project=None)
    r_write = c.write_model(project=None)
    assert r_read.ok is False
    assert r_read.status in ("REFUSED", "NOT_IMPLEMENTED")
    assert r_write.ok is False
    assert r_write.status in ("REFUSED", "NOT_IMPLEMENTED")
    assert "navisworks" in r_read.message


# ---------------------------------------------------------------------------
# open_file / save_as / convert (logique, fausse app)
# ---------------------------------------------------------------------------

def test_open_file_refused_when_not_connected():
    c = NavisworksConnector()
    assert c.connected is False
    r = c.open_file("x.dwg")
    assert r.ok is False
    assert r.status == "REFUSED"


def test_open_file_refused_when_missing(tmp_path):
    c = _connected(FakeNavisApp())
    r = c.open_file(str(tmp_path / "absent.dwg"))
    assert r.ok is False
    assert r.status == "REFUSED"
    assert "introuvable" in r.message


def test_open_file_ok(tmp_path):
    src = tmp_path / "modele.dwg"
    src.write_bytes(b"fake")
    app = FakeNavisApp()
    c = _connected(app)
    r = c.open_file(str(src))
    assert r.ok is True
    assert app.opened == [str(src)]


def test_save_as_ok(tmp_path):
    dst = tmp_path / "modele.nwc"
    app = FakeNavisApp()
    c = _connected(app)
    r = c.save_as(str(dst))
    assert r.ok is True
    assert app.saved == [str(dst)]


def test_save_as_refused_when_not_connected():
    r = NavisworksConnector().save_as("x.nwc")
    assert r.ok is False
    assert r.status == "REFUSED"


def test_convert_ok(tmp_path):
    src = tmp_path / "modele.dwg"
    src.write_bytes(b"fake")
    dst = tmp_path / "modele.nwc"
    app = FakeNavisApp()
    c = _connected(app)
    r = c.convert(str(src), str(dst))
    assert r.ok is True
    assert app.opened == [str(src)]
    assert app.saved == [str(dst)]


def test_convert_reports_open_failure(tmp_path):
    src = tmp_path / "modele.dwg"
    src.write_bytes(b"fake")
    c = _connected(FailingNavisApp())
    r = c.convert(str(src), str(tmp_path / "out.nwc"))
    assert r.ok is False
    assert "OpenFile" in r.message


def test_convert_reports_save_failure(tmp_path):
    src = tmp_path / "modele.dwg"
    src.write_bytes(b"fake")

    class OpenOnlyOkApp:
        Visible = False

        def __init__(self):
            self.opened = []

        def OpenFile(self, path):
            self.opened.append(path)

        def SaveAs(self, path):
            raise RuntimeError("boom")

    c = _connected(OpenOnlyOkApp())
    r = c.convert(str(src), str(tmp_path / "out.nwc"))
    assert r.ok is False
    assert "SaveAs" in r.message


# ---------------------------------------------------------------------------
# Intégration hub : Navisworks sans route de géométrie
# ---------------------------------------------------------------------------

def test_default_hub_navisworks_no_geometry_routes():
    hub = default_hub()
    m = hub.routes()
    # navisworks n'est source ni cible d'aucun échange de géométrie
    for target, info in m["navisworks"].items():
        if target != "navisworks":
            assert info["feasible"] is False
            assert info["missing"]  # motif présent
    for source, row in m.items():
        if source != "navisworks" and "navisworks" in row:
            assert row["navisworks"]["feasible"] is False
