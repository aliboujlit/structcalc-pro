# -*- coding: utf-8 -*-
"""
tests/unit/test_mapping.py — Tests de la table de correspondance (spec §4.1, §13).

100 % indépendant de COM. Vérifie : unicité, ambiguïtés signalées, orphelins
jamais supprimés, détection d'écarts.
"""

from structcalc.integration.robot.mapping import (
    MappingTable, MATCHED, AMBIGUOUS, ORPHAN, UNMATCHED,
    detect_unmatched,
)


def test_link_and_lookup_bidirectional():
    t = MappingTable(version="40.0")
    t.link("SC-NODE-000001", 10)
    assert t.robot_id_of("SC-NODE-000001") == 10
    assert t.sc_id_of(10) == "SC-NODE-000001"
    assert t.status_of("SC-NODE-000001") == MATCHED


def test_ambiguous_is_flagged_not_resolved():
    """Une ambiguïté est SIGNALÉE, jamais résolue en silence (spec §4.1)."""
    t = MappingTable()
    t.mark_ambiguous("SC-NODE-000001", [10, 11, 12])
    assert t.status_of("SC-NODE-000001") == AMBIGUOUS
    # Pas de robot_id tant que non arbitré
    assert t.robot_id_of("SC-NODE-000001") is None
    assert t.entry_of("SC-NODE-000001").candidates == [10, 11, 12]
    assert len(t.issues()) == 1


def test_orphan_never_auto_deleted():
    """Un objet Robot orphelin est signalé, jamais supprimé (spec §13)."""
    t = MappingTable()
    t.mark_orphan(99)
    assert t.status_of("") == UNMATCHED   # pas de sc_id pour l'orphelin
    e = t.issues()
    assert any(x.status == ORPHAN and x.robot_id == 99 for x in e)
    # summary compte l'orphelin
    assert t.summary()[ORPHAN] == 1


def test_detect_unmatched_partitions_sets():
    t = MappingTable()
    t.link("SC-NODE-000001", 1)
    t.link("SC-NODE-000002", 2)
    intern = ["SC-NODE-000001", "SC-NODE-000002", "SC-NODE-000003"]
    robot = [1, 2, 7]
    rep = detect_unmatched(intern, robot, t)
    assert sorted(rep["matched"]) == ["SC-NODE-000001", "SC-NODE-000002"]
    assert rep["missing_in_robot"] == ["SC-NODE-000003"]
    assert rep["orphan_in_robot"] == [7]


def test_external_refs_reflect_status():
    t = MappingTable(version="40.0")
    t.link("SC-COLUMN-000001", 5)
    refs = t.external_refs_for("SC-COLUMN-000001")
    assert len(refs) == 1
    assert refs[0].external_id == "5"
    assert refs[0].match_status == MATCHED
