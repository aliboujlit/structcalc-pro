# -*- coding: utf-8 -*-
"""
regulation/__init__.py — Couche REGULATION (spec §3.4, §11).

Contient les référentiels réglementaires et les vérifications associées.

Règles de conception (spec §3.4, §11.3) :
  - Chaque référentiel précise titre, édition, domaine, date d'applicabilité,
    articles, équations, coefficients, unités, limites, source, état de
    validation, tests de référence.
  - Les données réglementaires ne sont PAS dispersées dans le code métier.
  - Aucun calcul n'est présenté comme conforme tant que sa méthode n'a pas
    été vérifiée (règle absolue, spec §0).

Développés séparément : BAEL 91 révisé 99 et RPS 2011.
"""

from .base import Regulation, Article, VerificationResult

__all__ = ["Regulation", "Article", "VerificationResult"]
