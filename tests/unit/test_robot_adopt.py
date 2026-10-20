# -*- coding: utf-8 -*-
"""
tests/unit/test_robot_adopt.py — Adoption lecture seule du projet live (§5.4).

Un projet Robot ouvert par une AUTRE session (votre travail) doit pouvoir
être LU par une session connectée — sans jamais être marqué comme ouvert
par nous (`opened_by_us=False` : toute écriture reste refusée, §5.4).
Correctif d'une incohérence constatée live : `is_project_open` répondait
True (projet live) alors que la lecture levait « Aucun projet ouvert ».
"""

from structcalc.integration.interop.robot import RobotConnector
from structcalc.integration.robot.connection import RobotConnection


class _FakeProj:
    def __init__(self, active=True):
        self.IsActive = active


class _FakeApp:
    def __init__(self, proj=None):
        self.Project = proj


def _conn_with(app, project=None, opened=False):
    """RobotConnection sans COM (jamais connecté — champs posés à la main)."""
    rc = RobotConnection()
    rc._connected = True
    rc._app = app
    rc._project = project
    rc._opened_project = opened
    return rc


def test_adopt_live_project_reads_but_never_owns():
    rc = _conn_with(_FakeApp(_FakeProj(True)))
    assert rc.adopt_live_project() is True
    assert rc.project is not None          # lecture possible
    assert rc.opened_by_us is False        # JAMAIS notre ouvrage (§5.4)


def test_adopt_live_project_false_without_app():
    rc = RobotConnection()                 # jamais connecté (sans COM)
    assert rc.adopt_live_project() is False


def test_adopt_live_project_false_when_no_active_project():
    rc = _conn_with(_FakeApp(_FakeProj(False)))
    assert rc.adopt_live_project() is False


def test_ensure_project_adopts_foreign_live_project_readonly():
    """Projet live étranger -> adopté pour LECTURE, aucun projet créé."""
    conn = RobotConnector()
    rc = _conn_with(_FakeApp(_FakeProj(True)))
    conn._rc = rc
    conn.ensure_project()                  # adopte, ne crée rien
    assert rc.opened_by_us is False
    assert rc._project is not None


def test_ensure_project_creates_when_none_open():
    conn = RobotConnector()
    calls = []

    class _FakeRC:
        is_project_open = False
        opened_by_us = False

        def new_project(self, t=4):
            calls.append(t)

        def adopt_live_project(self):      # ne doit PAS être appelé
            calls.append("adopt")

    conn._rc = _FakeRC()
    conn.ensure_project()
    assert calls == [conn.new_project_type]


def test_exe_path_strips_arguments_and_is_file():
    """Le chemin robot.exe doit POINTER vers un fichier réel (sans args)."""
    exe = RobotConnection._exe_path()
    assert isinstance(exe, str)
    if exe:                                # Robot présent (machine de dev)
        import os
        assert os.path.isfile(exe), exe
        assert " /" not in exe and ' "' not in exe   # arguments retirés
