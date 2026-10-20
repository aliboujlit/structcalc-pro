# -*- coding: utf-8 -*-
"""
integration/__init__.py — Couche INTEGRATION de STRUCTCALC PRO.

Contient les adaptateurs des logiciels externes (Robot, Revit, AutoCAD...).
Un adaptateur traduit les données externes vers le modèle interne CORE et
inversement, dans les limites de l'interface documentée.

Règle (spec §3.5) : cette couche dépend de CORE et des ponts COM/.NET.
Jamais l'inverse. CORE ne dépend ni de PyQt6, ni de Robot, ni de Revit.
"""

__all__ = ["robot"]
