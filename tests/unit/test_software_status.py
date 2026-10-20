# -*- coding: utf-8 -*-
"""
tests/unit/test_software_status.py — LEDs des logiciels (v1.3) : vert =
connecté VÉRIFIÉ, rouge = non connecté avec motif ; la détection ne lance
jamais rien ; la relance utilise les exécutables RÉELS et refuse les
doubles instances (spec §19).
"""

from structcalc.integration import software_status as ss


def test_revit_pipe_vrai_chemin_import_reel():
    """Le VRAI _revit_pipe importe ..detector_stub (corrigé v1.3.1) :
    l'ancien chemin .detector_stub levait ModuleNotFoundError en live —
    masqué en test par le monkeypatch. Doit renvoyer un bool SANS erreur
    d'import ici."""
    assert isinstance(ss._revit_pipe(), bool)


def _patch(monkeypatch, running=(), rot=(), pipe=False, exe=None,
           isfile=True):
    monkeypatch.setattr(ss, "_running",
                        lambda image: image.lower() in {r.lower() for r in running})
    monkeypatch.setattr(ss, "_rot", lambda prog: prog in rot)
    monkeypatch.setattr(ss, "_revit_pipe", lambda: pipe)
    monkeypatch.setattr(ss, "exe_for",
                        (lambda key: exe) if exe is not None
                        else (lambda key: f"C:/fake/{key}.exe"))
    monkeypatch.setattr(ss.os.path, "isfile", lambda p: isfile)


def test_all_red_when_nothing_running(monkeypatch):
    _patch(monkeypatch)
    rows = {s["key"]: s for s in ss.status_all()}
    assert len(rows) == 6
    for key, st in rows.items():
        assert st["connected"] is False, key
        assert st["detail"], key               # motif TOUJOURS présent


def test_robot_green_when_running(monkeypatch):
    _patch(monkeypatch, running=["robot.exe"])
    rows = {s["key"]: s for s in ss.status_all()}
    assert rows["robot"]["connected"] is True
    assert "PRUVÉ" in rows["robot"]["detail"]
    assert rows["autocad"]["connected"] is False


def test_acad_hosts_light_civil3d_and_advsteel_with_caveat(monkeypatch):
    _patch(monkeypatch, running=["acad.exe"])
    rows = {s["key"]: s for s in ss.status_all()}
    for key in ("autocad", "civil3d", "advsteel"):
        assert rows[key]["connected"] is True, key
    assert "hôte" in rows["civil3d"]["detail"]       # limite explicite


def test_revit_green_only_with_addin_pipe(monkeypatch):
    _patch(monkeypatch, running=["Revit.exe"], pipe=False)
    rows = {s["key"]: s for s in ss.status_all()}
    assert rows["revit"]["connected"] is False       # ROUGE sans add-in
    assert "MAIS" in rows["revit"]["detail"]
    _patch(monkeypatch, running=["Revit.exe"], pipe=True)
    rows = {s["key"]: s for s in ss.status_all()}
    assert rows["revit"]["connected"] is True
    assert "pipe" in rows["revit"]["detail"]


def test_navisworks_green_when_running(monkeypatch):
    _patch(monkeypatch, running=["Roamer.exe"])
    rows = {s["key"]: s for s in ss.status_all()}
    assert rows["navisworks"]["connected"] is True


def test_launch_missing_skips_connected_and_running(monkeypatch):
    launched = []
    _patch(monkeypatch, running=["robot.exe"], exe="C:/fake/app.exe")
    monkeypatch.setattr(ss.subprocess, "Popen",
                        lambda args: launched.append(args))
    res = {k: (ok, msg) for k, ok, msg in ss.launch_missing()}
    assert "robot" not in res                      # déjà actif : jamais relancé
    assert res["autocad"][0] is True               # lancé par l'exécutable réel
    assert launched and launched[0] == ["C:/fake/app.exe"]


def test_launch_missing_refuses_when_exe_absent(monkeypatch):
    launched = []
    _patch(monkeypatch, running=[], exe="", isfile=False)
    monkeypatch.setattr(ss.subprocess, "Popen",
                        lambda args: launched.append(args))
    res = {k: (ok, msg) for k, ok, msg in ss.launch_missing()}
    assert not launched
    assert all(ok is False for ok, _ in res.values())
    assert all("introuvable" in msg for _, msg in res.values())


def test_launch_running_but_not_connected_reports_instead(monkeypatch):
    """Revit actif sans add-in : aucun lancement de Revit (double instance
    interdit) ; les AUTRES logiciels manquants sont bien relancés."""
    launched = []
    _patch(monkeypatch, running=["Revit.exe"], pipe=False)
    monkeypatch.setattr(ss.subprocess, "Popen",
                        lambda args: launched.append(args))
    res = {k: (ok, msg) for k, ok, msg in ss.launch_missing()}
    assert "revit" in res and res["revit"][0] is False
    assert "déjà actif" in res["revit"][1]
    paths = [a[0] for a in launched]
    assert "C:/fake/revit.exe" not in paths      # JAMAIS de double instance
    assert len(paths) == 5                       # les 5 autres relancés
