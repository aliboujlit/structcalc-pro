# -*- coding: utf-8 -*-
"""
gui/__init__.py — Couche GUI PyQt6 (spec §3.6, §14).

Règle (spec §14.6) : l'interface présente les données et déclenche des
opérations métier. AUCUNE formule réglementaire dans les fenêtres. Les
opérations longues passent par des tâches pour garder l'UI réactive (§14.4).
"""

__all__ = ["main_window", "dashboard", "widgets"]
