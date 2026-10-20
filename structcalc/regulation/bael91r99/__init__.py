# -*- coding: utf-8 -*-
"""
regulation/bael91r99/__init__.py — Référentiel BAEL 91 révisé 99 (France).

Rappel de statut (spec §11.1, règle absolue §0) :
Les équations ci-dessous sont TRANSCRITES à partir des usages courants du
BAEL 91 révisé 99 pour les poteaux en béton armé. Chaque article porte un
drapeau `verified` et une note. Tant qu'un article n'a pas été confronté à
l'exemple de référence fourni ET au texte officiel, son statut reste
VERIFICATION_NON_IMPLEMENTE ou A_VALIDER — JAMAIS présenté comme conforme.

L'ingénieur doit confirmer chaque coefficient contre l'édition officielle
du BAEL 91 révisé 99 avant toute utilisation en production.
"""

from .columns import bael91r99, ColumnGeometry, ColumnMaterials, ColumnActions

__all__ = ["bael91r99", "ColumnGeometry", "ColumnMaterials", "ColumnActions"]
