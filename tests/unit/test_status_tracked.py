# -*- coding: utf-8 -*-
"""
tests/unit/test_status_tracked.py — Tests des statuts et de la traçabilité.

Vérifie les règles absolues de la spec :
  §4.2 : ASSUMED -> VALIDATED interdit silencieusement.
  §4.3 : provenance distinguant import / recalcul.
  §11.3 : VERIFICATION_NON_IMPLEMENTE n'est jamais conforme.
"""

import pytest

from structcalc.core.status import (
    DataStatus,
    RegulatoryStatus,
    can_transition,
    requires_explicit_validation,
    is_regulatory_pass,
)
from structcalc.core.tracked import TrackedValue, Provenance


# --- Règles de transition (§4.2) ------------------------------------------

def test_assumed_to_validated_is_forbidden_silently():
    assert can_transition(DataStatus.ASSUMED, DataStatus.VALIDATED) is False
    assert requires_explicit_validation(DataStatus.ASSUMED,
                                        DataStatus.VALIDATED) is True


def test_ordinary_transitions_allowed():
    assert can_transition(DataStatus.PROVIDED, DataStatus.VALIDATED) is True
    assert can_transition(DataStatus.IMPORTED, DataStatus.OUTDATED) is True


def test_tracked_set_blocks_forbidden_transition():
    v = TrackedValue(2.5, "cm", DataStatus.ASSUMED)
    with pytest.raises(ValueError):
        v.set(3.0, DataStatus.VALIDATED)


def test_explicit_validation_requires_responsible():
    v = TrackedValue(2.5, "cm", DataStatus.ASSUMED)
    with pytest.raises(ValueError):
        v.validate_assumption(3.0, validated_by="")   # responsable vide


def test_explicit_validation_succeeds_with_responsible():
    v = TrackedValue(2.5, "cm", DataStatus.ASSUMED)
    v.validate_assumption(3.0, validated_by="Ing. Dupont",
                          note="Section doublée après avis")
    assert v.status == DataStatus.VALIDATED
    assert v.value == 3.0
    assert v.provenance.validated_by == "Ing. Dupont"
    assert "avis" in v.provenance.note


def test_invalidate_marks_outdated():
    v = TrackedValue(30.0, "MPa", DataStatus.IMPORTED)
    v.invalidate(note="modèle modifié")
    assert v.status == DataStatus.OUTDATED


def test_history_is_kept():
    v = TrackedValue(1.0, "m", DataStatus.PROVIDED)
    v.set(2.0, DataStatus.CALCULATED)
    v.set(3.0, DataStatus.CALCULATED)
    assert len(v.history) >= 2


# --- Provenance (§4.3) -----------------------------------------------------

def test_provenance_distinguishes_import_vs_calc():
    imp = Provenance.imported_from("Robot", version="40.0.0.12707")
    calc = Provenance.calculated_by("descente de charges tributaire")
    assert imp.is_imported() is True
    assert calc.is_imported() is False
    # Les deux restent distinguables
    assert imp.source != calc.source


def test_missing_helpers():
    m = TrackedValue.missing("MPa")
    assert m.is_missing is True
    assert bool(m) is False
    ok = TrackedValue.of(30.0, "MPa", DataStatus.PROVIDED)
    assert bool(ok) is True


# --- Statuts réglementaires (§11.3) ---------------------------------------

def test_verification_non_implemente_is_never_pass():
    assert is_regulatory_pass(
        RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE) is False


def test_only_conforme_passes():
    for st in RegulatoryStatus:
        expected = (st == RegulatoryStatus.CONFORME)
        assert is_regulatory_pass(st) is expected
