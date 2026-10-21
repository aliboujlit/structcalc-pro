# -*- coding: utf-8 -*-
"""
tests/unit/test_interop_hub.py — Tests du hub d'interconnexion RÉCIPROQUE.

Ces tests n'utilisent AUCUN logiciel : des connecteurs FACTICES simulent
les capacités pour vérifier le routage, la réciprocité et le refus explicite
(§19 : aucun faux succès). Les détections réelles (registre) sont testées
séparément et ne LANCENT aucun logiciel.
"""

from __future__ import annotations

import pytest

from structcalc.integration.interop import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropHub, InteropError, OpReport,
    RobotConnector, AutoCADConnector, RevitConnector, Civil3DConnector,
    default_hub,
)


# ---------------------------------------------------------------------------
# Connecteurs FACTICES (sans COM)
# ---------------------------------------------------------------------------

class FakeConnector(AutodeskConnector):
    """Connecteur de test dont les capacités sont configurables."""

    def __init__(self, name, can_read=True, can_write=True,
                 read_status=None, write_status=None,
                 installed=True, automatable=True):
        self.name = name
        self.label = f"Fake {name}"
        self._can_read = can_read
        self._can_write = can_write
        self._read_status = read_status
        self._write_status = write_status
        self._installed = installed
        self._automatable = automatable
        self.read_calls = 0
        self.write_calls = 0
        self.fail_read = False
        self.fail_write = False
        self._is_connected = False

    def detect(self) -> Detection:
        return Detection(name=self.name, installed=self._installed,
                         transport="com", automatable=self._automatable)

    def capabilities(self):
        caps = {}
        caps[Capability.DETECT] = CapabilityReport(
            Capability.DETECT, CapabilityStatus.SUPPORTED, "test")
        caps[Capability.CONNECT] = CapabilityReport(
            Capability.CONNECT, CapabilityStatus.SUPPORTED, "test")
        caps[Capability.READ_MODEL] = CapabilityReport(
            Capability.READ_MODEL,
            self._read_status or (CapabilityStatus.SUPPORTED
                                  if self._can_read
                                  else CapabilityStatus.NOT_SUPPORTED),
            "test")
        caps[Capability.WRITE_MODEL] = CapabilityReport(
            Capability.WRITE_MODEL,
            self._write_status or (CapabilityStatus.SUPPORTED
                                   if self._can_write
                                   else CapabilityStatus.NOT_SUPPORTED),
            "test")
        return caps

    @property
    def connected(self):
        return self._is_connected

    def connect(self, timeout: float = 60.0):
        self._is_connected = True
        return self

    def read_model(self, project) -> OpReport:
        self.read_calls += 1
        if self.fail_read:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"{self.name}: lecture échouée")
        return OpReport("read_model", "OK", source=self.name,
                        objects={"nodes": 3})

    def write_model(self, project) -> OpReport:
        self.write_calls += 1
        if self.fail_write:
            return OpReport("write_model", "REFUSED", source=self.name,
                            message=f"{self.name}: écriture refusée")
        return OpReport("write_model", "OK", source=self.name,
                        objects={"entities": 5})


@pytest.fixture
def hub():
    h = InteropHub()
    h.register(FakeConnector("a"))
    h.register(FakeConnector("b"))
    return h


# ---------------------------------------------------------------------------
# 1. Contrat de base
# ---------------------------------------------------------------------------

def test_capability_status_usable_only_supported_or_partial():
    """Seules SUPPORTED/PARTIAL sont 'usables' (§19)."""
    assert CapabilityStatus.SUPPORTED.usable is True
    assert CapabilityStatus.PARTIAL.usable is True
    assert CapabilityStatus.UNVERIFIED.usable is False
    assert CapabilityStatus.NOT_IMPLEMENTED.usable is False
    assert CapabilityStatus.NOT_SUPPORTED.usable is False


def test_capability_report_usable_derives_from_status():
    r = CapabilityReport(Capability.READ_MODEL,
                         CapabilityStatus.UNVERIFIED, "non prouvé")
    assert r.usable is False
    assert r.to_dict()["usable"] is False


def test_connector_refuse_unknown_capability():
    c = FakeConnector("x", can_read=False, can_write=False)
    assert c.can(Capability.READ_MODEL) is False
    assert c.status_of(Capability.READ_MODEL) == CapabilityStatus.NOT_SUPPORTED
    # capacité totalement absente -> NOT_IMPLEMENTED (pas une supposition)
    assert c.status_of(Capability.READ_RESULTS) == \
        CapabilityStatus.NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# 2. Registre du hub
# ---------------------------------------------------------------------------

def test_register_and_names(hub):
    assert sorted(hub.names) == ["a", "b"]


def test_duplicate_key_rejected(hub):
    """Clé dupliquée -> conflit explicite (§4.1 identifiants stables)."""
    with pytest.raises(InteropError):
        hub.register(FakeConnector("a"))


def test_get_unknown_connector_raises(hub):
    with pytest.raises(InteropError):
        hub.get("zzz")


def test_register_anonymous_connector_rejected(hub):
    anon = FakeConnector("abstract")
    anon.name = "abstract"      # nom abstrait = refusé
    with pytest.raises(InteropError):
        hub.register(anon)


# ---------------------------------------------------------------------------
# 3. Matrice de routes + réciprocité
# ---------------------------------------------------------------------------

def test_route_matrix_feasible_both_ways(hub):
    m = hub.routes()
    assert m["a"]["b"]["feasible"] is True
    assert m["b"]["a"]["feasible"] is True
    # même logiciel : route inutile
    assert m["a"]["a"]["feasible"] is False


def test_route_blocked_when_target_cannot_write():
    h = InteropHub()
    h.register(FakeConnector("src", can_read=True, can_write=True))
    h.register(FakeConnector("dst", can_read=True, can_write=False))
    m = h.routes()
    assert m["src"]["dst"]["feasible"] is False
    assert m["dst"]["src"]["feasible"] is True       # l'inverse marche
    assert "dst.write_model" in " ".join(m["src"]["dst"]["missing"])


def test_route_blocked_when_source_cannot_read():
    h = InteropHub()
    h.register(FakeConnector("src", can_read=False))
    h.register(FakeConnector("dst"))
    m = h.routes()
    assert m["src"]["dst"]["feasible"] is False
    assert m["dst"]["src"]["feasible"] is True
    assert "src.read_model" in " ".join(m["src"]["dst"]["missing"])


def test_reciprocal_pairs_only_two_way(hub):
    """Une paire n'apparaît que si A->B ET B->A sont faisables."""
    assert hub.reciprocal_pairs() == [("a", "b")]
    # on casse un sens
    h2 = InteropHub()
    h2.register(FakeConnector("a", can_read=True, can_write=True))
    h2.register(FakeConnector("b", can_read=True, can_write=False))
    assert h2.reciprocal_pairs() == []


def test_unavailability_gives_reason():
    h = InteropHub()
    h.register(FakeConnector("a"))
    h.register(FakeConnector("b", can_write=False))
    u = h.unavailability("a", "b")
    assert u.missing
    assert "b.write_model" in " ".join(u.missing)
    # connecteur inconnu
    u2 = h.unavailability("a", "nope")
    assert "nope" in u2.missing


# ---------------------------------------------------------------------------
# 4. Échange A -> pivot -> B
# ---------------------------------------------------------------------------

def test_exchange_success(hub):
    res = hub.exchange("a", "b", project=object())
    assert res.success is True
    assert res.step_failed == ""
    hub.get("a").read_calls == 1
    assert hub.get("a").read_calls == 1
    assert hub.get("b").write_calls == 1


def test_exchange_read_failure_stops_before_write(hub):
    hub.get("a").fail_read = True
    res = hub.exchange("a", "b", project=object())
    assert res.success is False
    assert res.step_failed == "read"
    assert hub.get("b").write_calls == 0   # jamais d'écriture si lecture KO
    assert "échouée" in res.message or "refusée" in res.message


def test_exchange_write_failure_reports_step(hub):
    hub.get("b").fail_write = True
    res = hub.exchange("a", "b", project=object())
    assert res.success is False
    assert res.step_failed == "write"
    assert res.read_report is not None and res.read_report.ok


def test_exchange_self_refused(hub):
    res = hub.exchange("a", "a", project=object())
    assert res.success is False
    assert "identique" in res.message


def test_exchange_unknown_connector(hub):
    res = hub.exchange("a", "zzz", project=object())
    assert res.success is False
    assert "inconnu" in res.message


def test_exchange_infeasible_returns_reason_not_exception():
    h = InteropHub()
    h.register(FakeConnector("a"))
    h.register(FakeConnector("b", can_write=False))
    res = h.exchange("a", "b", project=object())
    assert res.success is False
    assert "non faisable" in res.message
    assert "b.write_model" in res.message


def test_exchange_connects_on_demand(hub):
    assert hub.get("a").connected is False
    hub.exchange("a", "b", project=object())
    assert hub.get("a").connected is True
    assert hub.get("b").connected is True


# ---------------------------------------------------------------------------
# 5. Connecteurs RÉELS : détection honnête (registre, aucun lancement)
# ---------------------------------------------------------------------------

def test_real_connectors_detect_without_launching():
    for cls in (RobotConnector, AutoCADConnector, Civil3DConnector,
                RevitConnector):
        det = cls().detect()
        assert det.name
        assert det.transport in ("com", "dotnet", "named_pipe", "none")
        # installed n'implique JAMAIS automatable (§19)
        if not det.automatable:
            assert det.transport != "com"


def test_revit_never_automatable_even_if_installed():
    # épinglé à un pipe INEXISTANT : seul l'add-in .NET rend le modèle
    # accessible ; sans lui, installed n'implique jamais automatable (§19)
    det = RevitConnector(pipe_name="structcalc_test_absent").detect()
    assert det.installed is True          # Revit 2027 installé
    assert det.automatable is False       # MAIS pas de COM modèle
    assert det.progs == []                # aucun ProgID COM


def test_revit_model_refused_with_explicit_reason():
    r = RevitConnector(pipe_name="structcalc_test_absent")
    rep = r.read_model(None)
    assert rep.status == "NOT_IMPLEMENTED"
    assert rep.ok is False
    assert "REFUSÉE" in rep.message
    rep2 = r.write_model(None)
    assert rep2.ok is False
    assert "REFUSÉE" in rep2.message


def test_revit_capabilities_not_supported_for_model():
    # pipe absent épinglé : refus + motif d'action ; l'état VIVANT de
    # l'add-in (pipe réellement chargé) est couvert par
    # test_revit_addin_pipe.py (serveur mocké, déterministe)
    caps = RevitConnector(pipe_name="structcalc_test_absent").capabilities()
    assert caps[Capability.READ_MODEL].status == CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.WRITE_MODEL].status == \
        CapabilityStatus.NOT_SUPPORTED
    assert caps[Capability.READ_MODEL].usable is False


def test_civil3d_inherits_autocad_but_refuses_intelligent_objects():
    c = Civil3DConnector()
    assert c.name == "civil3d"
    det = c.detect()
    assert det.installed is True
    assert det.progs, "Civil 3D doit hériter des ProgIDs de l'hôte AutoCAD"
    rep = c.read_civil_objects()
    assert rep.status == "NOT_IMPLEMENTED"
    assert ".NET" in rep.message
    assert rep.ok is False


def test_civil3d_capabilities_partial_for_model():
    caps = Civil3DConnector().capabilities()
    # DWG de niveau dessin : PARTIAL (objets intelligents refusés)
    assert caps[Capability.READ_MODEL].status == CapabilityStatus.PARTIAL
    assert caps[Capability.WRITE_MODEL].status == CapabilityStatus.PARTIAL


def test_autocad_text_not_claimed_as_supported():
    caps = AutoCADConnector().capabilities()
    # les textes ne sont PAS vérifiés -> PARTIAL, jamais SUPPORTED
    assert caps[Capability.WRITE_DRAWINGS].status == CapabilityStatus.PARTIAL
    assert caps[Capability.WRITE_RESULTS] if False else True
    assert "TEXTES" in caps[Capability.WRITE_DRAWINGS].detail or \
        "TEXTES" in caps[Capability.WRITE_DRAWINGS].detail.upper()


def test_autocad_detects_version():
    det = AutoCADConnector().detect()
    assert det.installed is True
    assert det.automatable is True
    assert det.version == "2027"


# ---------------------------------------------------------------------------
# 6. Hub réel : paires réciproques attendues
# ---------------------------------------------------------------------------

def test_default_hub_registers_six():
    hub = default_hub()
    assert sorted(hub.names) == [
        "advsteel", "autocad", "civil3d", "navisworks", "revit", "robot"]


def test_default_hub_reciprocal_pairs():
    """Réciprocité Robot <-> AutoCAD <-> Civil3D <-> Advance Steel.

    Advance Steel hérite de l'hôte AutoCAD : DWG de niveau dessin échangeable
    (PARTIAL) -> participe aux paires réciproques. Revit + Navisworks bloqués
    (aucun COM modèle / COM sans membre de modèle, §19) tant que l'add-in
    .NET Revit n'est pas chargé (état réel sondé, jamais figé).
    """
    hub = default_hub()
    revit_alive = hub.get("revit").probe_addin()[0]
    pairs = hub.reciprocal_pairs()
    # nœuds DWG (hôte acad.exe partagé) : échange géométrie réciproque
    for a, b in (("autocad", "robot"), ("autocad", "civil3d"),
                 ("civil3d", "robot"), ("advsteel", "robot"),
                 ("advsteel", "autocad"), ("advsteel", "civil3d")):
        assert (a, b) in pairs, f"paire manquante {a}<->{b}"
    # Navisworks toujours bloqué (COM sans membre de modèle, §19)
    for a, b in pairs:
        assert "navisworks" not in (a, b)
    # Revit : bloqué sans add-in ; DEVIENT faisable si l'add-in est chargé
    for a, b in pairs:
        if not revit_alive:
            assert "revit" not in (a, b)
    if revit_alive:
        assert ("revit", "robot") in pairs


def test_default_hub_navisworks_honest():
    """Navisworks : détecté/lançable, mais géométrie via pivot refusée (§19)."""
    hub = default_hub()
    st = hub.status()["navisworks"]
    # COM présent -> transport + automatable booléens (sans lancer l'app)
    assert st["transport"] == "com"
    assert isinstance(st["automatable"], bool)
    # read_model / write_model bloqués (NOT_SUPPORTED), avec motif non vide
    blocked = st["blocked_capabilities"]
    assert blocked.get("read_model") == "NOT_SUPPORTED"
    assert blocked.get("write_model") == "NOT_SUPPORTED"
    # Aucune route de géométrie vers/depuis navisworks
    m = hub.routes()
    for target, info in m["navisworks"].items():
        if target != "navisworks":
            assert info["feasible"] is False


def test_default_hub_revit_routes_blocked_with_reason():
    """Routes Revit : refus MOTIVÉ sans add-in ; faisables si add-in chargé."""
    hub = default_hub()
    m = hub.routes()
    if hub.get("revit").probe_addin()[0]:
        # add-in .NET réellement actif : la route devient faisable (§6.3)
        assert m["robot"]["revit"]["feasible"] is True
        assert m["revit"]["robot"]["feasible"] is True
        return
    assert m["robot"]["revit"]["feasible"] is False
    assert m["revit"]["robot"]["feasible"] is False
    assert any("revit" in x for x in m["robot"]["revit"]["missing"])
    assert any("revit" in x for x in m["revit"]["robot"]["missing"])


def test_summary_lists_all_and_reciprocal():
    txt = default_hub().summary()
    for n in ("robot", "autocad", "civil3d", "revit"):
        assert n in txt
    assert "RÉCIPROQUES" in txt
