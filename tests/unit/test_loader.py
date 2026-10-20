# -*- coding: utf-8 -*-
"""
tests/unit/test_loader.py — interop/loader.py (v1.2 « Projet > Ouvrir… »).

Le chargeur est testable SANS COM : les classes connecteur sont injectées
(robot_cls / autocad_cls). Vérifie les règles absolues :
  - aucune exception n'est levée vers le GUI (tout devient LoadResult) ;
  - refus motivés : fichier absent, format inconnu, projet Robot étranger ;
  - fermeture SANS save — et UNIQUEMENT de ce que NOUS avons ouvert ;
  - un document déjà ouvert est réutilisé en lecture seule, jamais fermé ;
  - 0 objet lu = 0 objet rapporté (aucun inventé).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from structcalc.integration.interop.base import OpReport
from structcalc.integration.interop.loader import LoadResult, load_project_file


# ---------------------------------------------------------------------------
# Fakes — Robot (.rtd)
# ---------------------------------------------------------------------------

class FakeRC:
    """ RobotConnection simplifié (open/close/flags)."""

    def __init__(self, foreign=False):
        self.foreign = foreign
        self._open = False
        self.closed_with_save = None

    @property
    def is_project_open(self):
        return self.foreign or self._open

    @property
    def opened_by_us(self):
        return self._open

    def open_project(self, path):
        self._open = True
        return object()

    def close_project(self, save=False):
        self.closed_with_save = save
        self._open = False


class FakeRobot:
    def __init__(self, foreign=False, read_ok=True):
        self.rc = FakeRC(foreign=foreign)
        self.read_ok = read_ok
        self.disconnected = False

    def connect(self, timeout=60.0):
        return self

    def read_model(self, project):
        if not self.read_ok:
            return OpReport("read_model", "REFUSED", message="projet vide")
        project.new_node(0.0, 0.0, 0.0)
        project.new_node(3.0, 0.0, 0.0)
        return OpReport("read_model", "OK", objects={"nodes": 2})

    def disconnect(self):
        self.disconnected = True


# ---------------------------------------------------------------------------
# Fakes — AutoCAD (.dwg)
# ---------------------------------------------------------------------------

class FakeDoc:
    def __init__(self, name="Plan.dwg", full=""):
        self.Name = name
        self.FullName = full
        self.closed = False
        self.closed_with_save = None

    def Close(self, save=False):  # noqa: N802 — nom de l'API COM
        self.closed = True
        self.closed_with_save = save


class FakeDocs:
    def __init__(self, docs):
        self._docs = list(docs)

    @property
    def Count(self):
        return len(self._docs)

    def Item(self, i):  # noqa: N802 — nom de l'API COM
        return self._docs[i]


class FakeApp:
    def __init__(self, docs):
        self.Documents = FakeDocs(docs)


class FakeAutoCAD:
    def __init__(self, app, attach_only=False, read_ok=True):
        self.app = app
        self.read_ok = read_ok
        self.opened = []
        self.disconnected = False
        self.read_doc = None

    def connect(self, timeout=90.0):
        return self

    def open_document(self, path):
        doc = FakeDoc(name=Path(path).name, full=str(path))
        self.opened.append(doc)
        return doc

    def read_model(self, project, document=None):
        self.read_doc = document
        if not self.read_ok:
            return OpReport("read_model", "REFUSED", message="doc illisible")
        project.new_node(1.0, 2.0, 0.0)
        return OpReport("read_model", "OK", objects={"nodes": 1})

    def close_document(self, doc, save=False):
        doc.closed = True
        doc.closed_with_save = save

    def disconnect(self):
        self.disconnected = True


# ---------------------------------------------------------------------------
# .rtd (Robot)
# ---------------------------------------------------------------------------

def test_rtd_success_opens_and_closes_without_save(tmp_path):
    rtd = tmp_path / "villa.rtd"
    rtd.write_bytes(b"fake")
    conn = FakeRobot()
    res = load_project_file(rtd, robot_cls=lambda: conn)
    assert res.ok and res.project is not None
    assert "villa.rtd" in res.message and "2 nœud" in res.message
    # Fermeture sans save — uniquement le projet que NOUS avons ouvert
    assert conn.rc.closed_with_save is False
    assert conn.disconnected


def test_rtd_refuses_foreign_open_project(tmp_path):
    rtd = tmp_path / "villa.rtd"
    rtd.write_bytes(b"fake")
    conn = FakeRobot(foreign=True)
    res = load_project_file(rtd, robot_cls=lambda: conn)
    assert not res.ok and res.project is None
    assert ("session étrangère" in res.message
            or "déjà ouvert" in res.message)
    # Aucune ouverture/fermeture forcée du projet étranger (§5.4)
    assert conn.rc.closed_with_save is None
    assert conn.disconnected


def test_rtd_read_refused_is_not_a_false_success(tmp_path):
    rtd = tmp_path / "vide.rtd"
    rtd.write_bytes(b"fake")
    conn = FakeRobot(read_ok=False)
    res = load_project_file(rtd, robot_cls=lambda: conn)
    assert not res.ok and res.project is None
    assert "projet vide" in res.message


# ---------------------------------------------------------------------------
# .dwg (AutoCAD)
# ---------------------------------------------------------------------------

def test_dwg_opens_and_closes_only_what_we_opened(tmp_path):
    dwg = tmp_path / "Plan-villa.dwg"
    dwg.write_bytes(b"fake")
    app = FakeApp(docs=[])
    holder = {}

    def factory(attach_only=False):
        c = FakeAutoCAD(app, attach_only=attach_only)
        holder["c"] = c
        return c

    res = load_project_file(dwg, autocad_cls=factory)
    assert res.ok and res.project is not None
    c = holder["c"]
    assert len(c.opened) == 1 and c.read_doc is c.opened[0]
    # Notre document est fermé sans save
    assert c.opened[0].closed and c.opened[0].closed_with_save is False
    assert c.disconnected


def test_dwg_already_open_is_reused_and_never_closed(tmp_path):
    dwg = tmp_path / "Plan-villa.dwg"
    dwg.write_bytes(b"fake")
    existing = FakeDoc(name="Plan-villa.dwg", full=str(dwg))
    app = FakeApp(docs=[existing])
    holder = {}

    def factory(attach_only=False):
        c = FakeAutoCAD(app, attach_only=attach_only)
        holder["c"] = c
        return c

    res = load_project_file(dwg, autocad_cls=factory)
    assert res.ok
    c = holder["c"]
    # Pas de ré-ouverture : lecture ciblée sur l'existant
    assert c.opened == [] and c.read_doc is existing
    # Document pré-existant JAMAIS fermé (§5.4)
    assert not existing.closed
    assert "LECTURE SEULE" in res.message


def test_dwg_zero_objects_reported_honestly(tmp_path):
    dwg = tmp_path / "archi.dwg"
    dwg.write_bytes(b"fake")

    class EmptyAutoCAD(FakeAutoCAD):
        def read_model(self, project, document=None):
            self.read_doc = document
            return OpReport("read_model", "OK", objects={})

    app = FakeApp(docs=[])
    res = load_project_file(
        dwg, autocad_cls=lambda attach_only=False: EmptyAutoCAD(app))
    assert res.ok
    assert res.counts["nodes"] == 0 and res.counts["beams"] == 0
    # Zéro objet = rapporté honnêtement (aucun inventé)
    assert "0 objet" in res.message


def test_dwg_read_refused_is_not_a_false_success(tmp_path):
    dwg = tmp_path / "illisible.dwg"
    dwg.write_bytes(b"fake")
    app = FakeApp(docs=[])
    res = load_project_file(
        dwg, autocad_cls=lambda attach_only=False:
            FakeAutoCAD(app, read_ok=False))
    assert not res.ok and res.project is None
    assert "doc illisible" in res.message


# ---------------------------------------------------------------------------
# Refus génériques
# ---------------------------------------------------------------------------

def test_missing_file_refused():
    res = load_project_file("Z:/n'existe/pas.dwg")
    assert not res.ok and "introuvable" in res.message


def test_unsupported_format_refused(tmp_path):
    p = tmp_path / "model.rvt"
    p.write_bytes(b"fake")
    res = load_project_file(p)
    assert not res.ok and "format non pris en charge" in res.message


def test_exception_becomes_error_result_not_raised(tmp_path):
    rtd = tmp_path / "boom.rtd"
    rtd.write_bytes(b"fake")

    class BoomRobot(FakeRobot):
        def connect(self, timeout=60.0):
            raise RuntimeError("Robot absent")

    res = load_project_file(rtd, robot_cls=BoomRobot)
    assert isinstance(res, LoadResult) and not res.ok
    assert "Robot absent" in res.message


# ---------------------------------------------------------------------------
# Lecture PARTIALE : chargée + dévoilée (jamais un faux plein succès)
# ---------------------------------------------------------------------------

def test_rtd_partial_read_is_loaded_with_disclosure(tmp_path):
    rtd = tmp_path / "partiel.rtd"
    rtd.write_bytes(b"fake")

    class PartialRobot(FakeRobot):
        def read_model(self, project):
            project.new_node(0.0, 0.0, 0.0)
            return OpReport("read_model", "PARTIAL",
                            message="1 barre avec extrémité non résolvable")

    conn = PartialRobot()
    res = load_project_file(rtd, robot_cls=lambda: conn)
    assert res.ok and res.status == "PARTIAL"
    assert "PARTIELLEMENT" in res.message
    assert "1 barre avec extrémité" in res.message
    # ce qui a pu être lu est bien présent (aucun inventé)
    assert res.counts["nodes"] == 1


def test_dwg_partial_read_is_loaded_with_disclosure(tmp_path):
    dwg = tmp_path / "partiel.dwg"
    dwg.write_bytes(b"fake")

    class PartialAutoCAD(FakeAutoCAD):
        def read_model(self, project, document=None):
            self.read_doc = document
            project.new_node(1.0, 2.0, 0.0)
            return OpReport("read_model", "PARTIAL",
                            message="42 entité(s) non traitée(s)")

    app = FakeApp(docs=[])
    res = load_project_file(
        dwg, autocad_cls=lambda attach_only=False: PartialAutoCAD(app))
    assert res.ok and res.status == "PARTIAL"
    assert "PARTIELLEMENT" in res.message and "42 entité" in res.message
