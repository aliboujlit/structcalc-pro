# -*- coding: utf-8 -*-
"""
tests/unit/test_interop_autocad_read.py — Non-régression read_model AutoCAD.

Bug corrigé : autocad.py importait paresseusement `from ..core.model import
Beam/Slab` (2 points -> structcalc.integration.core, INEXISTANT) au lieu de
`...core.model` (3 points -> structcalc.core.model). Comme l'import est dans
un try/except, l'échec était silencieux : les poutres/dalles n'étaient JAMAIS
créées à la lecture d'un DWG, seulement comptées en erreur.

Ce test reproduit la lecture d'un DWG via une FAUSSE session COM + un VRAI
Project, et vérifie que les poutres/sommets sont réellement créés (le bug
donnerait beams=0 + une erreur ModuleNotFoundError).
"""

from __future__ import annotations

import pytest

from structcalc.core.model import Project
from structcalc.integration.interop import AutoCADConnector, Capability


# ---------------------------------------------------------------------------
# Fausse session COM (mimique le surface utilisée par read_model)
# ---------------------------------------------------------------------------

class FakeLine:
    ObjectName = "AcDbLine"

    def __init__(self, layer, sp, ep):
        self.Layer = layer
        self.StartPoint = sp
        self.EndPoint = ep


class FakeModelSpace:
    def __init__(self, entities):
        self._ents = entities

    @property
    def Count(self):
        return len(self._ents)

    def Item(self, i):
        return self._ents[i]


class FakeDoc:
    def __init__(self, entities):
        self.ModelSpace = FakeModelSpace(entities)


class FakeDocs:
    def __init__(self, doc):
        self._doc = doc

    @property
    def Count(self):
        return 1

    def Item(self, i):
        return self._doc


class FakeApp:
    def __init__(self, entities):
        self.Documents = FakeDocs(FakeDoc(entities))


def _connected_autocad(entities):
    c = AutoCADConnector()
    c._app = FakeApp(entities)
    c._connected = True
    return c


# ---------------------------------------------------------------------------
# Test de non-régression : les poutres sont CRÉÉES (pas seulement comptées)
# ---------------------------------------------------------------------------

def test_read_model_creates_beams_and_nodes():
    """Une ligne SC_BEAM -> 1 poutre + 2 nœuds RÉELLEMENT dans le pivot."""
    # 2 extrémités distinctes -> 2 nœuds
    ents = [FakeLine("SC_BEAM", (0.0, 0.0, 0.0), (6.0, 0.0, 0.0))]
    c = _connected_autocad(ents)
    project = Project("SC-TEST-READ-0001")

    rep = c.read_model(project)

    assert rep.ok is True, rep.message
    # La poutre est CRÉÉE (bug corrigé) — avant : beams==0 + ModuleNotFound
    assert len(project.beams) == 1, f"beams={len(project.beams)} msg={rep.message}"
    assert rep.objects["beams"] == 1
    assert rep.objects["nodes"] == 2
    # Aucune erreur d'import résiduelle
    assert "ModuleNotFound" not in (rep.message or "")
    # Les objets portent des IDs stables SC-*
    bid = next(iter(project.beams))
    assert bid.startswith("SC-")
    nids = list(project.nodes)
    assert all(n.startswith("SC-NODE-") for n in nids)


def test_read_model_beam_geometry_correct():
    """La poutre relie bien les 2 nœuds aux bonnes coordonnées."""
    ents = [FakeLine("SC_BEAM", (1.0, 2.0, 0.0), (5.0, 2.0, 0.0))]
    c = _connected_autocad(ents)
    project = Project("SC-TEST-READ-0002")

    rep = c.read_model(project)
    assert rep.ok is True
    beam = next(iter(project.beams.values()))
    n1 = project.nodes[beam.start_node]
    n2 = project.nodes[beam.end_node]
    assert abs(n1.x.value - 1.0) < 1e-6
    assert abs(n2.x.value - 5.0) < 1e-6


def test_read_model_ignores_non_sc_layer():
    """Entité hors calque SC_* ignorée et COMPTE rapportée (pas inventée)."""
    ents = [FakeLine("0", (0.0, 0.0, 0.0), (6.0, 0.0, 0.0))]
    c = _connected_autocad(ents)
    project = Project("SC-TEST-READ-0003")

    rep = c.read_model(project)
    assert rep.ok is True
    assert len(project.beams) == 0
    assert rep.objects["ignored"] == 1


def test_find_doc_by_path_survives_document_fantome():
    """Live 20/10 : Documents.Item(i) d'un document laissé par la boucle
    lève une com_error -> l'ancien code cassait TOUTE la recherche
    (exception hors try) et le chargeur tentait une réouverture du
    document déjà ouvert -> dialogue modal AutoCAD -> blocage. Le document
    fantôme est maintenant sauté ; le vrai document ouvert est trouvé
    (lecture seule)."""
    from types import SimpleNamespace

    from structcalc.integration.interop.autocad import find_doc_by_path

    class Doc:
        def __init__(self, full):
            self.FullName = full

    class Docs:
        Count = 2

        def Item(self, i):
            if i == 0:
                raise RuntimeError(
                    "com_error -2147352567 (document fantome de la boucle)")
            return Doc(r"C:\projets\Plan-villa.dwg")

    app = SimpleNamespace(Documents=Docs())
    found = find_doc_by_path(app, r"C:\projets\plan-VILLA.dwg")
    assert found is not None
    assert found.FullName.endswith("Plan-villa.dwg")   # casse-insensible


# ---------------------------------------------------------------------------
# write_coffrage (v1.4) : plans de coffrage -> DWG
# ---------------------------------------------------------------------------

class _FakeEnt:
    Handle = "ABCD"

    def __init__(self, kind, pts):
        self.kind = kind
        self.pts = pts
        self.Layer = ""


class _FakeMSWrite:
    def __init__(self):
        self.ents = []

    @property
    def Count(self):
        return len(self.ents)

    def AddLightWeightPolyline(self, pts):
        e = _FakeEnt("poly", list(pts))
        self.ents.append(e)
        return e

    def AddLine(self, p1, p2):
        e = _FakeEnt("line", [list(p1), list(p2)])
        self.ents.append(e)
        return e


class _FakeLayers:
    def __init__(self):
        self.names = []

    def Add(self, name):
        self.names.append(name)
        return SimpleNamespace(Name=name)


class _FakeDocWrite:
    def __init__(self):
        self.ModelSpace = _FakeMSWrite()
        self.Layers = _FakeLayers()
        self.saved = None

    def Regen(self, _):
        pass

    def SaveAs(self, path, code):
        self.saved = (path, code)


class _FakeDocsWrite:
    def __init__(self):
        self.doc = _FakeDocWrite()

    @property
    def Count(self):
        return 1

    def Add(self):
        return self.doc


def _write_conn(monkeypatch=None):
    from types import SimpleNamespace
    c = AutoCADConnector()
    docs = _FakeDocsWrite()
    c._app = SimpleNamespace(Documents=docs)
    c._connected = True
    # _v6 (VARIANT pythoncom) n'est pas testable hors COM : forme plate
    from structcalc.integration.interop import autocad as acmod
    if monkeypatch is not None:
        monkeypatch.setattr(acmod, "_v6", lambda vals: list(vals))
    return c, docs.doc


def _coffrage_project():
    from structcalc.core.model import Column, Node, CrossSection
    from structcalc.core.status import DataStatus
    from structcalc.core.tracked import Provenance, TrackedValue

    def tv(v):
        return TrackedValue.of(float(v), "m", DataStatus.IMPORTED,
                               Provenance.imported_from("Robot"))
    p = Project("SC-TEST-COFF")
    p.nodes["N1"] = Node(sc_id="N1", x=tv(0), y=tv(0), z=tv(0))
    p.nodes["N2"] = Node(sc_id="N2", x=tv(0), y=tv(0), z=tv(2.8))
    p.sections["S1"] = CrossSection(sc_id="S1", name="C R30x30")
    p.columns["C1"] = Column(sc_id="C1", start_node="N1",
                             end_node="N2", section="S1")
    return p


def test_write_coffrage_draws_rectangles(monkeypatch):
    """Le plan de coffrage écrit un rectangle 0.30x0.30 par poteau."""
    c, doc = _write_conn(monkeypatch)
    rep = c.write_coffrage(_coffrage_project(), out_path=r"C:\x\c.dwg")
    assert rep.ok is True, rep.message
    polys = [e for e in doc.ModelSpace.ents if e.kind == "poly"]
    assert len(polys) == 1
    # rectangle : 4 sommets, dimensions 0.30 x 0.30 (R30x30 -> /100/2)
    xs = polys[0].pts[0::2]
    ys = polys[0].pts[1::2]
    assert max(xs) - min(xs) == pytest.approx(0.30, rel=1e-6)
    assert max(ys) - min(ys) == pytest.approx(0.30, rel=1e-6)


def test_write_coffrage_refuses_empty_project(monkeypatch):
    c, _doc = _write_conn(monkeypatch)
    rep = c.write_coffrage(Project("SC-EMPTY"))
    assert rep.ok is False
    assert "0 plan" in rep.message or "Aucun" in rep.message
