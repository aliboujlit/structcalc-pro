# -*- coding: utf-8 -*-
"""
tests/integration_robot/test_model_roundtrip.py — Test d'intégration Robot.

VALIDÉ EN PHASE 0 sur Robot 2027. Vérifie un va-et-vient réel :
  connexion -> New(2D) -> export modèle -> relecture -> vérification -> fermeture.

Ce test ouvre l'UI Robot : il est marqué `robot` et EXCLU par défaut du
pytest (addopts = "-m 'not robot'"). Pour l'exécuter :
    pytest -m robot tests/integration_robot

Aucun fichier n'est enregistré (fermeture sans sauvegarde).
"""

import pytest

from structcalc.integration.robot import (
    RobotConnection,
    PROJECT_TYPE_FRAME_2D,
)
from structcalc.integration.robot import model as rmodel


pytestmark = pytest.mark.robot


def test_roundtrip_two_nodes_one_bar():
    """Modèle de test T1 : 2 nœuds + 1 barre, va-et-vient contrôlé."""
    with RobotConnection() as rc:
        rc.new_project(PROJECT_TYPE_FRAME_2D)
        assert rc.is_project_open

        # Modèle neutre à exporter
        model_in = {
            "nodes": [
                {"number": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"number": 2, "x": 4.0, "y": 0.0, "z": 0.0},
            ],
            "bars": [
                {"number": 1, "start": 1, "end": 2},
            ],
        }

        summary = rmodel.export_model(rc, model_in)
        assert summary == {"nodes": 2, "bars": 1}

        # Vérification post-transfert
        report = rmodel.verify_transfer(rc, expected_nodes=2, expected_bars=1)
        assert report["ok"], report

        # Relecture du contenu réel
        nodes = rmodel.import_nodes(rc)
        bars = rmodel.import_bars(rc)

        assert len(nodes) == 2
        assert len(bars) == 1

        by_num = {n["number"]: n for n in nodes}
        assert by_num[1]["x"] == pytest.approx(0.0)
        assert by_num[2]["x"] == pytest.approx(4.0)

        assert bars[0]["start"] == 1
        assert bars[0]["end"] == 2

    # Sortie du context manager : projet fermé sans sauvegarde.


def test_connection_info():
    """La connexion expose une version et l'état du projet."""
    with RobotConnection() as rc:
        info = rc.info()
        assert info["connecté"] is True
        assert info["projet_ouvert"] is False
        assert info.get("version"), "version Robot non lisible"
