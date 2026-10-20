# -*- coding: utf-8 -*-
"""
regulation/rps2011/seismic.py — Paramètres sismiques RPS 2011 (spec §11.2).

STATUT DE VÉRIFICATION (règle absolue §0, §11.2)
-----------------------------------------------
Le RPS 2011 (Règlement Parasismique Algérien, version 2011/2014 révision)
définit accélération de référence, coefficients de site, spectre, etc. Les
valeurs par défaut ci-dessous sont des ORDRES DE GRANDEUR CANDIDATS destinés
au framework — elles DOIVENT être confirmées par l'ingénieur contre l'édition
officielle du RPS applicabe avant tout usage.

Règle §11.2 : chaque paramètre est relié à une donnée du projet OU à une
source réglementaire vérifiée — jamais inventé en silence. Le statut de chaque
paramètre est porté par `verified` et le résultat des contrôles en découle.

Le spectre de réponse n'est PAS codé en dur comme seule vérité : la fonction
`design_spectrum` documente la forme et exige des paramètres validés.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from ..base import Regulation, Article, VerificationResult
from ...core.status import RegulatoryStatus


class SiteClass(str, Enum):
    """Classes de sol du RPS (S1..S4 usuelles). À CONFIRMER sur l'édition."""
    S1 = "S1"   # rocher / sol très rigide
    S2 = "S2"   # sol moyen
    S3 = "S3"   # sol tendre
    S4 = "S4"   # sol mou / gélif (cas particulier)


# Coefficients de site — ORDRES DE GRANDEUR CANDIDATS (spec §11.2).
# CONFIRMÉ : nomenclature S1..S4 et tendance croissante S/Tc/Td.
# VALEURS EXACTES À CONFRONTER au fascicule RPS 2011/2014 officiel.
_SITE_COEFF_CANDIDATES: Dict[SiteClass, dict] = {
    SiteClass.S1: {"S": 1.0, "Tc": 0.15, "Td": 0.40},  # rocher / sol très rigide
    SiteClass.S2: {"S": 1.2, "Tc": 0.20, "Td": 0.50},  # sol moyen
    SiteClass.S3: {"S": 1.5, "Tc": 0.30, "Td": 0.70},  # sol tendre
    SiteClass.S4: {"S": 2.0, "Tc": 0.40, "Td": 1.00},  # sol mou / gélif
}


@dataclass
class SeismicParameters:
    """
    Paramètres sismiques d'un projet (spec §11.2).

    Toute valeur non fournie reste None (MISSING), jamais inventée.
    Chaque paramètre porte `verified` (source réglementaire confirmée ?).
    """
    ag: Optional[float] = None          # accélération de référence au roc (g)
    site_class: Optional[SiteClass] = None
    importance_factor: Optional[float] = None   # facteur d'importance
    behavior_factor: Optional[float] = None     # facteur de comportement q
    # Métadonnées de traçabilité
    source: str = ""                    # référence documentaire
    verified: bool = False              # paramètres confirmés ?

    def missing(self) -> list:
        out = []
        if self.ag is None:
            out.append("ag")
        if self.site_class is None:
            out.append("site_class")
        if self.importance_factor is None:
            out.append("importance_factor")
        if self.behavior_factor is None:
            out.append("behavior_factor")
        return out


class Rps2011(Regulation):
    """Référentiel RPS 2011 — module sismique."""

    def __init__(self):
        super().__init__(
            key="RPS2011",
            title="Règlement Parasismique",
            edition="RPS 2011 (à confirmer : 2011 / rév. 2014)",
            geography="Algérie (à confirmer)",
            applicability_date="2011",
            scope="Action sismique, spectre, analyse modale, ductilité, "
                  "contrôles sismiques des éléments",
        )
        self._register_articles()
        self._register_checks()

    def _register_articles(self):
        self.register_article(Article(
            code="RPS2011-SITE",
            title="Classification du sol et coefficients de site",
            equation_text="S, Tc, Td fonction de la classe de sol (S1..S4)",
            variables={"S": "coefficient de site", "Tc": "période de plateau",
                       "Td": "période de coupure"},
            validity_limits="Classes de sol S1..S4",
            source_doc="RPS 2011 — classification de site (À CONFIRMER)",
            verified=False,
            verification_note=("Classes S1..S4 CONFIRMÉES (nomenclature standard RPS). "
                               "Coefficients candidats : S={1.0,1.2,1.5,2.0}, Tc={0.15,0.20,0.30,0.40}, "
                               "Td={0.40,0.50,0.70,1.00} — À CONFRONTER au fascicule officiel RPS 2011/2014. "
                               "Facteur d'importance γI (1.0/1.2/1.4) et facteur de comportement q "
                               "(selon système structurel) — à confirmer."),
        ))
        self.register_article(Article(
            code="RPS2011-SPECTRUM",
            title="Spectre de réponse élastique",
            equation_text=("Sa(T) = ag * S * [1 + (Tmax/Tc - 1)*(2.5q-1)/(q-1)] "
                           "sur plateau ; décroissance en 1/T au-delà de Td. "
                           "Forme générique à CONFIRMER."),
            variables={"T": "période propre", "q": "facteur de comportement"},
            units={"Sa": "g"},
            validity_limits="Périodes du domaine élastique",
            source_doc="RPS 2011 — spectre de réponse (À CONFIRMER)",
            verified=False,
            verification_note=("Forme générique (plateau 2.5·ag·S, décroissance 1/T) CANDIDATE — "
                               "à confronter au fascicule RPS 2011/2014 (forme exacte, bornes, facteur q). "
                               "Facteur d'importance γI et facteur de comportement q (selon système : "
                               "portiques, murs, dual) — à confirmer sur l'édition."),
        ))

    def _register_checks(self):
        self.register_check("site_coefficients", self.check_site_coefficients)
        self.register_check("parameters_complete", self.check_parameters_complete)
        # Analyse modale, masses participantes, dérives, torsion, ductilité :
        # NON IMPLÉMENTÉS en Phase 5 -> statut explicite (spec §11.2, §11.3)

    def check_parameters_complete(self, params: SeismicParameters) -> VerificationResult:
        """Contrôle que tous les paramètres sismiques sont fournis (§11.2)."""
        miss = params.missing()
        if miss:
            status = RegulatoryStatus.DONNEES_MANQUANTES
            msg = f"Paramètres sismiques manquants : {', '.join(miss)}."
        elif not params.verified:
            status = RegulatoryStatus.A_VALIDER
            msg = ("Paramètres fournis mais NON confirmés sur l'édition "
                   "officielle du RPS (spec §11.2).")
        else:
            status = RegulatoryStatus.CONFORME
            msg = "Paramètres sismiques fournis et confirmés."
        return VerificationResult(
            check_id="parameters_complete", article_code="RPS2011-SITE",
            status=status, message=msg,
        )

    def check_site_coefficients(self, params: SeismicParameters) -> VerificationResult:
        """Retourne les coefficients de site (candidats) pour la classe donnée."""
        if params.site_class is None:
            return VerificationResult(
                check_id="site_coefficients", article_code="RPS2011-SITE",
                status=RegulatoryStatus.DONNEES_MANQUANTES,
                message="Classe de sol non renseignée.")
        co = _SITE_COEFF_CANDIDATES.get(params.site_class)
        if co is None:
            return VerificationResult(
                check_id="site_coefficients", article_code="RPS2011-SITE",
                status=RegulatoryStatus.METHODE_NON_APPLICABLE,
                message=f"Classe {params.site_class} inconnue.")
        status = RegulatoryStatus.A_VALIDER   # candidats, à confirmer
        return VerificationResult(
            check_id="site_coefficients", article_code="RPS2011-SITE",
            computed_value=co["S"], unit="-", status=status,
            message=(f"Classe {params.site_class.value}: S={co['S']}, "
                     f"Tc={co['Tc']}, Td={co['Td']} (CANDIDATS à confirmer)."),
        )

    def design_spectrum(self, T: float, params: SeismicParameters
                        ) -> VerificationResult:
        """
        Spectre de réponse (forme générique, à CONFIRMER).

        NON VÉRIFIÉ : la forme exacte (plateau, décroissance, bornes q) doit
        être confirmée. Tant que params.verified est faux, le statut est
        A_VALIDER — jamais présenté comme conforme.
        """
        if params.missing():
            return VerificationResult(
                check_id="design_spectrum", article_code="RPS2011-SPECTRUM",
                status=RegulatoryStatus.DONNEES_MANQUANTES,
                message=f"Paramètres manquants : {params.missing()}")
        co = _SITE_COEFF_CANDIDATES[params.site_class]
        ag, S = params.ag, co["S"]
        Tc, Td = co["Tc"], co["Td"]
        q = params.behavior_factor
        # Forme générique simplifiée (plateau + décroissance 1/T)
        if T <= 0:
            Sa = ag * S * 2.5
        elif T <= Tc:
            Sa = ag * S * 2.5
        elif T <= Td:
            # interpolation plateau -> début décroissance
            Sa = ag * S * 2.5 * (1.0 + (T - Tc) / (Td - Tc) * (1.0 / q - 1.0))
        else:
            Sa = ag * S * 2.5 * (Tc / T) / q
        status = RegulatoryStatus.A_VALIDER   # à confirmer
        return VerificationResult(
            check_id="design_spectrum", article_code="RPS2011-SPECTRUM",
            computed_value=Sa, unit="g", status=status,
            message=(f"Sa(T={T:.2f})≈{Sa:.3f} g (forme générique CANDIDATE : "
                     f"plateau 2.5·ag·S, décroissance ~1/T. "
                     f"ag={ag}, S={S}, q={q} — À CONFRONTER RPS 2011/2014)."),
        )


# Instance
rps2011 = Rps2011()
