# -*- coding: utf-8 -*-
"""
regulation/base.py — Cadre du registre réglementaire (spec §3.4, §11).

Fournit les structures de base pour décrire un référentiel, ses articles et
ses vérifications, SANS coder de formule métier ici.

Règle absolue (spec §0, §11.3) : une vérification non implémentée ou non
vérifiée n'est JAMAIS présentée comme conforme. Le statut par défaut est
VERIFICATION_NON_IMPLEMENTE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..core.status import RegulatoryStatus, is_regulatory_pass


@dataclass(frozen=True)
class Article:
    """
    Un article réglementaire référencé.

    Conforme spec §3.4 : titre exact, édition, domaine, équation (texte),
    coefficients, unités, limites de validité, source documentaire, état de
    validation. L'équation est conservée en TEXTE (traçabilité), pas évaluée
    ici.
    """
    code: str                     # ex. "BAEL91r99 §III.2.3.1"
    title: str                    # intitulé exact
    equation_text: str = ""       # équation transcrite (texte, pour la fiche)
    variables: Dict[str, str] = field(default_factory=dict)  # nom -> signification
    units: Dict[str, str] = field(default_factory=dict)      # nom -> unité
    coefficients: Dict[str, float] = field(default_factory=dict)
    validity_limits: str = ""     # domaine de validité
    source_doc: str = ""          # référence documentaire exacte
    verified: bool = False        # transcrit et vérifié indépendamment ?
    verification_note: str = ""   # méthode de vérification / exemple de référence

    def status(self) -> RegulatoryStatus:
        """Statut de l'article : conforme seulement si vérifié."""
        if self.verified:
            return RegulatoryStatus.A_VALIDER   # vérifié techniquement,
            # mais l'application à un cas reste à valider par l'ingénieur
        return RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE


@dataclass
class VerificationResult:
    """
    Résultat d'une vérification réglementaire (spec §11.3).

    statut par défaut : VERIFICATION_NON_IMPLEMENTE (jamais conforme).
    """
    check_id: str
    article_code: str
    element_id: str = ""          # SC-* de l'élément vérifié
    combination: str = ""         # combinaison déterminante
    computed_value: Optional[float] = None
    limit_value: Optional[float] = None
    unit: str = ""
    margin: Optional[float] = None      # (limite - computed) ou ratio
    status: RegulatoryStatus = RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE
    message: str = ""
    reference_example: str = ""   # exemple de référence pour le test

    @property
    def passes(self) -> bool:
        """Vrai UNIQUEMENT si statut CONFORME (§11.3)."""
        return is_regulatory_pass(self.status)

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "article": self.article_code,
            "element": self.element_id,
            "combination": self.combination,
            "computed": self.computed_value,
            "limit": self.limit_value,
            "unit": self.unit,
            "margin": self.margin,
            "status": self.status.value,
            "passes": self.passes,
            "message": self.message,
        }


class Regulation:
    """
    Registre d'un référentiel réglementaire (spec §3.4).

    Regroupe : identité du référentiel + articles + fonctions de vérification.
    Une vérification non enregistrée reste NON_IMPLEMENTE (rare).
    """

    def __init__(self, key: str, title: str, edition: str, geography: str,
                 applicability_date: str = "", scope: str = ""):
        self.key = key
        self.title = title
        self.edition = edition
        self.geography = geography
        self.applicability_date = applicability_date
        self.scope = scope
        self.articles: Dict[str, Article] = {}
        self._checks: Dict[str, Callable] = {}

    # -- Articles ---------------------------------------------------------

    def register_article(self, article: Article) -> Article:
        self.articles[article.code] = article
        return article

    def article(self, code: str) -> Article:
        if code not in self.articles:
            raise KeyError(f"Article inconnu : {code}")
        return self.articles[code]

    # -- Vérifications ----------------------------------------------------

    def register_check(self, check_id: str, fn: Callable) -> Callable:
        """Enregistre une fonction de vérification sous un identifiant."""
        self._checks[check_id] = fn
        return fn

    def has_check(self, check_id: str) -> bool:
        return check_id in self._checks

    def run_check(self, check_id: str, **kwargs) -> VerificationResult:
        """
        Exécute une vérification enregistrée. Si elle n'existe pas, retourne
        explicitement un VERIFICATION_NON_IMPLEMENTE (règle §11.3).
        """
        if check_id not in self._checks:
            return VerificationResult(
                check_id=check_id, article_code="",
                status=RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE,
                message=f"Vérification '{check_id}' non implémentée pour "
                        f"{self.title}.",
            )
        return self._checks[check_id](**kwargs)

    # -- Métadonnées ------------------------------------------------------

    def identity(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "edition": self.edition,
            "geography": self.geography,
            "applicability": self.applicability_date,
            "scope": self.scope,
            "articles": len(self.articles),
            "checks_registered": sorted(self._checks.keys()),
        }

    def __repr__(self) -> str:   # pragma: no cover
        return f"<Regulation {self.key} {self.edition} ({len(self.articles)} arts)>"
