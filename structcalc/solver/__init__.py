# -*- coding: utf-8 -*-
"""
solver/__init__.py — Couche SOLVER (spec §3.3, §9, §10).

Gère les calculs et l'analyse des résultats : descente de charges,
combinaisons, dimensionnement, stabilité, enveloppes, comparaison de
variantes.

Règle (spec §3.3) : ne JAMAIS mélanger le solveur numérique avec le moteur
de règles réglementaires (couche REGULATION). Le solver APPELLE la
réglementation, ne la code pas.
"""

from .column_design import ColumnDesigner, ColumnVariant, DesignOutcome

__all__ = ["ColumnDesigner", "ColumnVariant", "DesignOutcome"]
