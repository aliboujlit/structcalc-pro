# -*- coding: utf-8 -*-
"""
reporting/__init__.py — Couche REPORTING (spec §3.7, §15).

Produit : notes de calcul, fiches de vérification, tableaux, rapports de
conformité, nomenclatures, historiques, exports PDF/XLSX/CSV/JSON/MD.

Règle (spec §15.3) : « La génération d'un rapport ne doit pas transformer une
étude incomplète en document présenté comme conforme. » Le rapport AFFICHE les
statuts honnêtes (dont VERIFICATION_NON_IMPLEMENTE, DONNEES_MANQUANTES).
"""

from .column_report import column_fiche, project_summary

__all__ = ["column_fiche", "project_summary"]
