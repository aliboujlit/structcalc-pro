# -*- coding: utf-8 -*-
"""
tests/unit/test_ids.py — Tests unitaires des identifiants SC-* (spec §4.1).

Tests 100 % indépendants (aucune connexion Robot).
"""

import pytest

from structcalc.core.ids import IdAllocator, make_id, parse_id


def test_make_id_format():
    assert make_id("NODE", 124) == "SC-NODE-000124"
    assert make_id("COLUMN", 37) == "SC-COLUMN-000037"
    assert make_id("SECTION", 21) == "SC-SECTION-000021"
    assert make_id("COMB", 14) == "SC-COMB-000014"


def test_make_id_accepts_lowercase_type():
    assert make_id("node", 5) == "SC-NODE-000005"


def test_make_id_rejects_negative():
    with pytest.raises(ValueError):
        make_id("NODE", -1)


def test_parse_id_roundtrip():
    sc_id = make_id("BEAM", 42)
    assert parse_id(sc_id) == ("BEAM", 42)


def test_parse_id_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_id("NODE-000001")          # pas de préfixe SC
    with pytest.raises(ValueError):
        parse_id("SC-NODE")              # trop court
    with pytest.raises(ValueError):
        parse_id("SC-NODE-XXXXXX")       # numéro non numérique


def test_allocator_sequential_per_type():
    alloc = IdAllocator()
    assert alloc.new("NODE") == "SC-NODE-000001"
    assert alloc.new("NODE") == "SC-NODE-000002"
    # Les compteurs sont indépendants par type
    assert alloc.new("BEAM") == "SC-BEAM-000001"


def test_allocator_restore_prevents_collision():
    """Après rechargement, le compteur doit repasser au-delà des IDs existants."""
    alloc = IdAllocator()
    alloc.restore(["SC-NODE-000005", "SC-NODE-000009", "SC-BEAM-000003"])
    assert alloc.new("NODE") == "SC-NODE-000010"
    assert alloc.new("BEAM") == "SC-BEAM-000004"


def test_allocator_snapshot_and_reload():
    alloc = IdAllocator()
    alloc.new("NODE")
    alloc.new("NODE")
    snap = alloc.snapshot()
    alloc2 = IdAllocator(start_state=snap)
    assert alloc2.new("NODE") == "SC-NODE-000003"


def test_allocator_validate():
    alloc = IdAllocator()
    assert alloc.validate(make_id("WALL", 1)) is True
    assert alloc.validate("n'importe quoi") is False
