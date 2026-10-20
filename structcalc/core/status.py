# -*- coding: utf-8 -*-
"""
core/status.py — Statuts des données et des vérifications (spec §4.2, §11.3).

Deux familles de statuts distincts :

1. DataStatus (§4.2) — statut d'une DONNÉE / propriété :
   PROVIDED, IMPORTED, CALCULATED, ASSUMED, VALIDATED, MISSING, CONFLICT,
   OUTDATED, NOT_APPLICABLE.

   Règle absolue (§4.2) : « Une hypothèse (ASSUMED) ne doit jamais être
   transformée silencieusement en donnée validée (VALIDATED). »

2. RegulatoryStatus (§11.3) — statut d'une VÉRIFICATION réglementaire :
   CONFORME, NON_CONFORME, DONNEES_MANQUANTES, METHODE_NON_APPLICABLE,
   VERIFICATION_NON_IMPLEMENTE, A_VALIDER.

   Règle absolue (§11.3) : « Une vérification non implémentée ne doit jamais
   être considérée comme satisfaite. » VERIFICATION_NON_IMPLEMENTE n'est donc
   JAMAIS traité comme conforme.

Aucune dépendance externe. 100 % testable unitairement.
"""

from __future__ import annotations

import enum


class DataStatus(str, enum.Enum):
    """Statut de provenance/certitude d'une donnée (spec §4.2)."""

    PROVIDED = "PROVIDED"                  # fournie par un intervenant
    IMPORTED = "IMPORTED"                  # importée d'un logiciel
    CALCULATED = "CALCULATED"              # calculée par le logiciel
    ASSUMED = "ASSUMED"                    # hypothèse provisoire
    VALIDATED = "VALIDATED"                # validée par un responsable
    MISSING = "MISSING"                    # manquante
    CONFLICT = "CONFLICT"                  # contradictoire
    OUTDATED = "OUTDATED"                  # obsolète après modification
    NOT_APPLICABLE = "NOT_APPLICABLE"      # non applicable au contexte

    def __str__(self) -> str:   # pragma: no cover
        return self.value


class RegulatoryStatus(str, enum.Enum):
    """Statut d'une vérification réglementaire (spec §11.3)."""

    CONFORME = "CONFORME"
    NON_CONFORME = "NON_CONFORME"
    DONNEES_MANQUANTES = "DONNEES_MANQUANTES"
    METHODE_NON_APPLICABLE = "METHODE_NON_APPLICABLE"
    VERIFICATION_NON_IMPLEMENTE = "VERIFICATION_NON_IMPLEMENTE"
    A_VALIDER = "A_VALIDER"

    def __str__(self) -> str:   # pragma: no cover
        return self.value


# --- Règles métier encodant les interdits de la spec ----------------------

# Transitions de statut interdites pour une donnée (§4.2).
# Une hypothèse ne devient pas VALIDATED silencieusement : il faut un acte
# explicite de validation (validate_assumption) qui documente l'origine.
_FORBIDDEN_SILENT_TRANSITIONS = {
    (DataStatus.ASSUMED, DataStatus.VALIDATED),
}


def can_transition(old: DataStatus, new: DataStatus) -> bool:
    """
    Vrai si la transition de statut est autorisée de façon « silencieuse ».

    La transition ASSUMED -> VALIDATED est INTERDITE ici : elle exige la
    fonction explicite `require_explicit_validation`, qui force la saisie
    d'une justification (spec §4.2).
    """
    return (old, new) not in _FORBIDDEN_SILENT_TRANSITIONS


def requires_explicit_validation(old: DataStatus, new: DataStatus) -> bool:
    """Vrai si la transition exige une validation explicite documentée."""
    return (old, new) in _FORBIDDEN_SILENT_TRANSITIONS


def is_regulatory_pass(status: RegulatoryStatus) -> bool:
    """
    Vrai UNIQUEMENT si la vérification réglementaire est franchie.

    Exclut explicitement VERIFICATION_NON_IMPLEMENTE (§11.3 : une vérification
    non implémentée n'est jamais satisfaite), ainsi que DONNEES_MANQUANTES,
    METHODE_NON_APPLICABLE et A_VALIDER.
    """
    return status == RegulatoryStatus.CONFORME


# Regroupement pratique pour l'affichage / les rapports.
DATA_STATUS_LABELS_FR = {
    DataStatus.PROVIDED: "Fournie",
    DataStatus.IMPORTED: "Importée",
    DataStatus.CALCULATED: "Calculée",
    DataStatus.ASSUMED: "Hypothèse",
    DataStatus.VALIDATED: "Validée",
    DataStatus.MISSING: "Manquante",
    DataStatus.CONFLICT: "Contraire",
    DataStatus.OUTDATED: "Obsolète",
    DataStatus.NOT_APPLICABLE: "Non applicable",
}

REGULATORY_STATUS_LABELS_FR = {
    RegulatoryStatus.CONFORME: "Conforme",
    RegulatoryStatus.NON_CONFORME: "Non conforme",
    RegulatoryStatus.DONNEES_MANQUANTES: "Données manquantes",
    RegulatoryStatus.METHODE_NON_APPLICABLE: "Méthode non applicable",
    RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE: "Vérification non implémentée",
    RegulatoryStatus.A_VALIDER: "À valider",
}
