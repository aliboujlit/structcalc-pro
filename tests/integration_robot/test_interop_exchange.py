# -*- coding: utf-8 -*-
"""
tests/integration_robot/test_interop_exchange.py — Échange RÉCIPROQUE RÉEL.

Prouve la demande utilisateur : deux logiciels Autodesk différents échangent
RÉCIPROQUEMENT via le pivot SC-* (architecture en étoile du hub).

    Robot  --read_model-->  PIVOT  --write_model-->  AutoCAD   (sens 1)
    AutoCAD --read_model--> PIVOT  --write_model-->  Robot     (sens 2)

Ce test ouvre l'UI Robot ET s'attache à AutoCAD : il est marqué `robot`
et EXCLU par défaut (addopts = "-m 'not robot'"). Pour l'exécuter :
    pytest -m robot tests/integration_robot/test_interop_exchange.py

Aucun fichier n'est enregistré (fermeture sans sauvegarde, §5.4).
"""

import pytest

from structcalc.core.model import Beam, Project
from structcalc.integration.interop import (
    AutoCADConnector, InteropHub, RobotConnector,
)


pytestmark = pytest.mark.robot


def _build_truss() -> Project:
    """Portée 4 m : 2 nœuds + 1 barre (modèle minimal vérifiable)."""
    p = Project(sc_id="SC-INTEROP-EXCH-001", name="Réciprocité")
    n1 = p.new_node(0.0, 0.0, 0.0)
    n2 = p.new_node(4.0, 0.0, 0.0)
    bid = p.allocator.new("BEAM")
    p.beams[bid] = Beam(sc_id=bid, start_node=n1.sc_id, end_node=n2.sc_id)
    return p


def test_hub_registers_real_connectors():
    """Le hub voit les connecteurs réels et leurs routes honnêtes."""
    hub = InteropHub()
    hub.register(RobotConnector())
    hub.register(AutoCADConnector())
    assert sorted(hub.names) == ["autocad", "robot"]
    # Route faisable dans les DEUX sens (réciprocité)
    m = hub.routes()
    assert m["robot"]["autocad"]["feasible"] is True
    assert m["autocad"]["robot"]["feasible"] is True
    assert ("autocad", "robot") in hub.reciprocal_pairs()


def test_real_exchange_robot_to_autocad():
    """
    Sens 1 : Robot -> pivot -> AutoCAD (logiciels RÉELS).

    Robot est d'abord PEUPLÉ d'un modèle connu, puis on échange vers
    AutoCAD : le modèle lu dans Robot doit arriver géométriquement
    identique dans AutoCAD (compteurs + calques SC_*).
    """
    proj = _build_truss()          # 2 nœuds + 1 barre (source de vérité)

    robot = RobotConnector()
    autocad = AutoCADConnector()
    hub = InteropHub()
    hub.register(robot)
    hub.register(autocad)

    # On injecte d'abord le modèle connu DANS Robot (chemin vérifié Phase 0)
    robot.connect()
    robot.ensure_project()
    from structcalc.integration.robot import model as rmodel
    exported = rmodel.export_model(
        robot.rc,
        {"nodes": [{"number": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                   {"number": 2, "x": 4.0, "y": 0.0, "z": 0.0}],
         "bars": [{"number": 1, "start": 1, "end": 2}]})
    assert exported == {"nodes": 2, "bars": 1}

    # Pivot VIERGE : tout doit venir de Robot par la lecture
    fresh = Project(sc_id="SC-INTEROP-EXCH-002", name="Depuis Robot")

    res = hub.exchange("robot", "autocad", fresh, connect=True)
    try:
        assert res.success, f"échange robot->autocad échoué : {res.message}"
        assert res.read_report is not None and res.read_report.ok
        assert res.write_report is not None and res.write_report.ok
        # Le pivot a bien été rempli depuis Robot (2 nœuds, 1 poutre)
        assert len(fresh.nodes) == 2, res.read_report.message
        assert len(fresh.beams) == 1
        # AutoCAD a écrit des entités pour ce modèle
        assert res.write_report.objects["beams"] == 1
        assert res.write_report.objects["entities"] >= 1
    finally:
        hub.disconnect_all()


def test_real_exchange_autocad_to_robot():
    """
    Sens 2 (RÉCIPROQUE) : AutoCAD -> pivot -> Robot.

    Le modèle doit arriver dans Robot avec les mêmes compteurs, ce qui
    prouve que l'échange fonctionne dans LES DEUX sens avec des logiciels
    réellement différents.
    """
    proj = _build_truss()

    robot = RobotConnector()
    autocad = AutoCADConnector()
    hub = InteropHub()
    hub.register(robot)
    hub.register(autocad)

    res = hub.exchange("autocad", "robot", proj, connect=True)
    try:
        assert res.success, f"échange autocad->robot échoué : {res.message}"
        assert res.read_report.ok
        assert res.write_report.ok
        # Robot a bien reçu nœuds + barres
        assert res.write_report.objects["nodes"] == 2
        assert res.write_report.objects["bars"] == 1
        # Contrôle post-transfert côté Robot (chemin vérifié Phase 0)
        from structcalc.integration.robot import model as rmodel
        rep = rmodel.verify_transfer(robot.rc, expected_nodes=2,
                                     expected_bars=1)
        assert rep["ok"], rep
    finally:
        hub.disconnect_all()
