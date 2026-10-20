# -*- coding: utf-8 -*-
"""
tests/conftest.py — Configuration pytest STRUCTCALC PRO.

Ajoute la racine du projet au sys.path pour importer `structcalc`
sans installation. Sépare les tests unitaires des tests d'intégration Robot.
"""

import os
import sys

# Racine du dépôt (parent de tests/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
