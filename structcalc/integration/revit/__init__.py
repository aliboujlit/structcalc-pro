# -*- coding: utf-8 -*-
"""
integration/revit/__init__.py — Adaptateur Autodesk Revit (spec §6).

STATUT Phase 0/4 : Revit 2027 n'expose PAS d'API COM complète (contrairement
à Robot). Son API est .NET (RevitAPI.dll, 33 Mo), pilotable via un add-in.

Ce module documente les voies d'intégration et fournit un connecteur MINIMAL
honnête : il ouvre Revit si possible, mais l'extraction/écriture profonde
exige un add-in .NET (spec §6.3). Aucune fonction n'est présentée comme
opérationnelle sans preuve (spec §19).
"""

from .connection import RevitConnection, RevitConnectionError

__all__ = ["RevitConnection", "RevitConnectionError"]
