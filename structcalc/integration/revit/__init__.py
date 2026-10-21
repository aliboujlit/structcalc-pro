# -*- coding: utf-8 -*-
"""
integration/revit/__init__.py — Intégration Revit (BIM bidirectionnel).

Modules :
  - protocol   : client Named Pipe NDJSON (\\.\pipe\structcalc_revit)
  - families   : mapping sections Robot -> familles Revit (JSON utilisateur)
  - writer     : écriture modèle + sections (APPLY_CHANGES)
  - reinforcement : écriture armatures (RebarDto) depuis plans ferraillage

PRÉREQUIS :
  1. Revit 2027+ ouvert avec add-in StructCalcRevitAddin chargé (LED verte)
  2. Fichier families_map.json complété par l'utilisateur
  3. pywin32 installé (dépendance du build)

FLUX TYPE :
  1. Robot -> read_model -> pivot
  2. Dimensionnement -> ReinforcementPlan (proposition A_VALIDER)
  3. write_model_to_revit(pivot, families_map, plans_ferraillage)
     -> crée FamilyInstance (si pas existants) + types sections + Rebar (A_VALIDER)
  4. Dans Revit : planning nomenclatures auto, paramètres partagés SC_*
"""

from .protocol import RevitPipeClient, RevitPipeError, RevitProtocolError
from .families import FamiliesMap, FamilyMapEntry, write_default_mapping
from .writer import write_model_to_revit, build_apply_changes_request, WriteReport
from .reinforcement import (
    build_rebar_sets, apply_reinforcement_to_revit, RebarSetDto
)

__all__ = [
    "RevitPipeClient", "RevitPipeError", "RevitProtocolError",
    "FamiliesMap", "FamilyMapEntry", "write_default_mapping",
    "write_model_to_revit", "build_apply_changes_request", "WriteReport",
    "build_rebar_sets", "apply_reinforcement_to_revit", "RebarSetDto",
]