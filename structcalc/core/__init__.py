# -*- coding: utf-8 -*-
"""
core/__init__.py — Couche CORE de STRUCTCALC PRO.

Contient le modèle interne et les règles générales de gestion des données.

Règle absolue (spec §3.1) : cette couche ne dépend NI de PyQt6, NI de Robot,
NI de Revit, NI de comtypes/pywin32. Elle est testable unitairement.

Objets principaux (spec §4) : Project, Building, Storey, Node, Column, Beam,
Slab, Wall, Material, CrossSection, Support, LoadCase, LoadCombination...
Chaque objet porte un identifiant permanent SC-* (voir ids.py) et, pour ses
propriétés importantes, un statut + une provenance (voir status.py, tracked.py).
"""

from .ids import IdAllocator, make_id
from .status import DataStatus, RegulatoryStatus
from .tracked import TrackedValue, Provenance

__all__ = [
    "IdAllocator",
    "make_id",
    "DataStatus",
    "RegulatoryStatus",
    "TrackedValue",
    "Provenance",
]
