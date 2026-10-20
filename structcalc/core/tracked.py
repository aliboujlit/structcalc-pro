# -*- coding: utf-8 -*-
"""
core/tracked.py — Valeurs traçables : statut + provenance (spec §4.2, §4.3).

Le cœur de la traçabilité STRUCTCALC. Une propriété importante n'est jamais
une valeur brute : c'est un `TrackedValue` qui associe :

  - la valeur et son unité ;
  - un statut (DataStatus, §4.2) ;
  - une provenance (Provenance, §4.3) : d'où vient la donnée, quel logiciel,
    quelle version, quelle date, quelle méthode, quelle validation.

Deux règles absolues encodées ici :
  §4.2 : une hypothèse (ASSUMED) ne devient JAMAIS VALIDATED silencieusement.
  §4.3 : les résultats importés et recalculés restent DISTINGUABLES.

Aucune dépendance externe.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from .status import (
    DataStatus,
    can_transition,
    requires_explicit_validation,
)


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Provenance:
    """
    Origine d'une donnée (spec §4.3).

    Permet de distinguer un résultat IMPORTÉ d'un logiciel d'un résultat
    RECALCULÉ par STRUCTCALC, et de tracer le logiciel, sa version, la date,
    la méthode et le statut de validation.
    """
    source: str = "STRUCTCALC"        # logiciel ou acteur d'origine
    version: str = ""                 # version du logiciel source
    external_id: str = ""             # identifiant externe (Robot/Revit) éventuel
    method: str = ""                  # méthode employée
    timestamp: str = field(default_factory=_now_iso)
    validated_by: str = ""            # responsable de la validation
    note: str = ""

    @classmethod
    def imported_from(cls, software: str, version: str = "",
                      external_id: str = "", **kw) -> "Provenance":
        """Provenance d'une donnée importée d'un logiciel tiers."""
        return cls(source=software, version=version,
                   external_id=external_id, **kw)

    @classmethod
    def calculated_by(cls, method: str, **kw) -> "Provenance":
        """Provenance d'une donnée recalculée par STRUCTCALC."""
        return cls(source="STRUCTCALC", method=method, **kw)

    @classmethod
    def provided_by(cls, actor: str, **kw) -> "Provenance":
        """Provenance d'une donnée fournie par un intervenant."""
        return cls(source=actor, **kw)

    def is_imported(self) -> bool:
        return self.source not in ("STRUCTCALC", "")


@dataclass
class TrackedValue:
    """
    Une valeur associée à son statut et sa provenance.

    >>> v = TrackedValue(30.0, "MPa", DataStatus.PROVIDED,
    ...                  Provenance.provided_by("Bétonnier"))
    >>> v.value
    30.0
    >>> v.status
    <DataStatus.PROVIDED: 'PROVIDED'>
    """
    value: Any
    unit: str = ""
    status: DataStatus = DataStatus.MISSING
    provenance: Provenance = field(default_factory=Provenance)
    history: list = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    @property
    def is_missing(self) -> bool:
        return self.status == DataStatus.MISSING or self.value is None

    @property
    def is_assumed(self) -> bool:
        return self.status == DataStatus.ASSUMED

    @property
    def is_validated(self) -> bool:
        return self.status == DataStatus.VALIDATED

    def __bool__(self) -> bool:
        return not self.is_missing

    # ------------------------------------------------------------------
    # Mutation (contrôlée)
    # ------------------------------------------------------------------
    def set(self, value: Any, status: DataStatus,
            provenance: Optional[Provenance] = None) -> "TrackedValue":
        """
        Change la valeur et le statut, en respectant les règles §4.2.

        Lève ValueError si la transition est interdite silencieusement
        (ex. ASSUMED -> VALIDATED), qui exige validate_assumption().
        """
        if not can_transition(self.status, status):
            raise ValueError(
                f"Transition de statut interdite : {self.status} -> {status}. "
                "Une hypothèse (ASSUMED) ne devient pas VALIDATED "
                "silencieusement : utilisez validate_assumption() avec une "
                "justification (spec §4.2)."
            )
        self._push_history()
        self.value = value
        self.status = status
        if provenance is not None:
            self.provenance = provenance
        return self

    def validate_assumption(self, value: Any, validated_by: str,
                            note: str = "",
                            provenance: Optional[Provenance] = None
                            ) -> "TrackedValue":
        """
        Validation EXPLICITE d'une hypothèse (spec §4.2).

        Seul chemin autorisé pour passer de ASSUMED à VALIDATED. Exige un
        responsable (`validated_by`) et laisse une trace dans l'historique.
        """
        if not validated_by.strip():
            raise ValueError(
                "La validation d'une hypothèse exige un responsable "
                "identifié (validated_by) — spec §4.2."
            )
        self._push_history()
        self.value = value
        self.status = DataStatus.VALIDATED
        if provenance is not None:
            self.provenance = provenance
        # On annote la validation dans la provenance
        self.provenance = replace(
            self.provenance,
            validated_by=validated_by,
            note=(self.provenance.note + (" | " if self.provenance.note else "")
                  + note).strip(" |"),
        )
        return self

    def invalidate(self, note: str = "") -> "TrackedValue":
        """Marque la donnée comme obsolète (OUTDATED) après modification."""
        self._push_history()
        self.status = DataStatus.OUTDATED
        if note:
            self.provenance = replace(
                self.provenance,
                note=(self.provenance.note + " | " + note).strip(" |"),
            )
        return self

    def _push_history(self) -> None:
        """Conserve l'état précédent dans l'historique (traçabilité)."""
        self.history.append({
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "source": self.provenance.source,
            "timestamp": self.provenance.timestamp,
        })
        # Garde-fou mémoire
        if len(self.history) > 100:
            del self.history[: len(self.history) - 100]

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "provenance": {
                "source": self.provenance.source,
                "version": self.provenance.version,
                "external_id": self.provenance.external_id,
                "method": self.provenance.method,
                "timestamp": self.provenance.timestamp,
                "validated_by": self.provenance.validated_by,
                "note": self.provenance.note,
            },
        }

    @classmethod
    def missing(cls, unit: str = "") -> "TrackedValue":
        """Fabrique une valeur manquante (statut MISSING)."""
        return cls(value=None, unit=unit, status=DataStatus.MISSING)

    @classmethod
    def of(cls, value: Any, unit: str, status: DataStatus,
           provenance: Optional[Provenance] = None) -> "TrackedValue":
        """Raccourci de construction."""
        return cls(value=value, unit=unit, status=status,
                   provenance=provenance or Provenance())
