# -*- coding: utf-8 -*-
"""
integration/robot/__init__.py — Adaptateur Autodesk Robot Structural Analysis.

Modules (spec §5.2) :
  - connection.py    : connexion/fermeture, ouverture de projet  [Phase 0 ✓]
  - model.py         : import/export nœuds, barres, sections     [Phase 2]
  - loads.py         : export cas de charges, combinaisons       [Phase 2]
  - results.py       : import efforts, réactions, déplacements   [Phase 2]
  - mapping.py       : correspondance SC-* <-> Robot             [Phase 2]
  - validation.py    : contrôles post-transfert                  [Phase 2]

Attention : seule connection.py est validée en Phase 0. Les autres sont
des squelettes à implémenter et tester en Phase 2, conformément à la
règle « aucune fonctionnalité d'intégration déclarée avant vérification ».
"""

from .connection import (
    RobotConnection,
    RobotConnectionError,
    PROJECT_TYPE_FRAME_2D,
    PROJECT_TYPE_TRUSS_2D,
    PROJECT_TYPE_FRAME_3D,
)
from . import model, loads, results

__all__ = [
    "RobotConnection",
    "RobotConnectionError",
    "PROJECT_TYPE_FRAME_2D",
    "PROJECT_TYPE_TRUSS_2D",
    "PROJECT_TYPE_FRAME_3D",
    "model",
    "loads",
    "results",
]
