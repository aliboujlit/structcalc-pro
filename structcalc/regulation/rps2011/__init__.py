# -*- coding: utf-8 -*-
"""
regulation/rps2011/__init__.py — Référentiel RPS 2011 (réglementation parasismique).

Rappel de statut (spec §11.2, règle absolue §0) : modules séparés pour
paramètres sismiques, classification du site, spectre, analyse modale,
masses participantes, déplacements/dérives, torsion, régularité, ductilité,
dispositions constructives, contrôles sismiques des éléments.

Chaque paramètre est relié à une donnée du projet OU à une source
réglementaire vérifiée — JAMAIS inventé (spec §11.2).
"""

from .seismic import rps2011, SiteClass, SeismicParameters

__all__ = ["rps2011", "SiteClass", "SeismicParameters"]
