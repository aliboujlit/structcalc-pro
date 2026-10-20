# -*- coding: utf-8 -*-
"""
tests/unit/test_coherence.py — core/coherence.py (v1.2 « Modèle > Vérifier
la cohérence »).

Constats de cohérence du pivot : géométrie, références croisées, données
manquantes (§4.2), hypothèses ASSUMED visibles (§4.5). AUCUNE conformité
réglementaire n'y est déclarée (§20) — format_findings le rappelle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from structcalc.core.coherence import (
    CoherenceFinding, coherence_findings, format_findings,
)
from structcalc.core.model import Project
from structcalc.core.status import DataStatus
from structcalc.core.tracked import TrackedValue, Provenance


def _project(name="P") -> Project:
    return Project(sc_id="SC-PROJECT-000001", name=name)


def test_empty_project_has_no_findings():
    assert coherence_findings(_project()) == []


def test_none_project_is_safe():
    assert coherence_findings(None) == []


def test_complete_geometry_has_no_geometry_findings():
    p = _project()
    a = p.new_node(0.0, 0.0, 0.0)
    b = p.new_node(0.0, 0.0, 3.0)
    col = p.new_column(a.sc_id, b.sc_id)
    fs = coherence_findings(p)
    assert not any(f.sc_id == col.sc_id for f in fs)


def test_node_without_geometry_is_flagged():
    p = _project()
    p.new_node(0.0, 0.0, 0.0)
    vide = p.new_node()          # coordonnées manquantes (jamais inventées)
    fs = coherence_findings(p)
    assert any(f.sc_id == vide.sc_id
               and f.category.startswith("Nœud sans géométrie")
               for f in fs)


def test_column_height_missing_but_derivable_is_not_flagged():
    """Hauteur calculable depuis les coordonnées des nœuds = pas de constat."""
    p = _project()
    a = p.new_node(0.0, 0.0, 0.0)
    b = p.new_node(0.0, 0.0, 3.0)
    col = p.new_column(a.sc_id, b.sc_id)     # height restée MISSING
    fs = coherence_findings(p)
    assert not any(f.sc_id == col.sc_id for f in fs)


def test_column_height_missing_and_not_derivable_is_flagged():
    """Ni hauteur ni nœuds exploitables = constat honnête."""
    p = _project()
    col = p.new_column("SC-NODE-000001", "SC-NODE-000002")  # nœuds absents
    fs = coherence_findings(p)
    # La référence inexistante est signalée (les nœuds n'existent pas)
    assert any(f.sc_id == col.sc_id
               and f.category == "Référence de nœud inexistante"
               for f in fs)


def test_column_without_end_node_is_flagged():
    p = _project()
    a = p.new_node(0.0, 0.0, 0.0)
    col = p.new_column(a.sc_id, None)
    fs = coherence_findings(p)
    hit = [f for f in fs if f.sc_id == col.sc_id
           and f.category.startswith("Poteau")]
    assert hit and "nœud d'arrivée" in hit[0].detail


def test_dangling_node_reference_is_flagged():
    p = _project()
    a = p.new_node(0.0, 0.0, 0.0)
    p.new_column(a.sc_id, "SC-NODE-999999")   # référence inexistante
    fs = coherence_findings(p)
    assert any(f.category == "Référence de nœud inexistante"
               and "SC-NODE-999999" in f.detail for f in fs)


def test_beam_without_section_is_flagged():
    from structcalc.core.model import Beam
    p = _project()
    a = p.new_node(0.0, 0.0, 3.0)
    b = p.new_node(4.0, 0.0, 3.0)
    beam = Beam(sc_id="SC-BEAM-000001", start_node=a.sc_id,
                end_node=b.sc_id, section=None)
    p.beams[beam.sc_id] = beam
    fs = coherence_findings(p)
    assert any(f.sc_id == beam.sc_id and f.category == "Barre incomplète"
               and "section" in f.detail for f in fs)


def test_material_gap_is_flagged():
    p = _project()
    mat = p.new_material(kind="concrete")     # E/fck/fyd/gamma_* manquants
    fs = coherence_findings(p)
    assert any(f.category == "Données manquantes" and f.sc_id == mat.sc_id
               for f in fs)


def test_assumed_value_is_flagged_visibly():
    p = _project()
    n = p.new_node(0.0, 0.0, 0.0)
    n.x = TrackedValue.of(0.15, "m", DataStatus.ASSUMED,
                          Provenance.provided_by("test"))
    fs = coherence_findings(p)
    assert any(f.category == "Valeur supposée (ASSUMED)"
               and f.sc_id == n.sc_id and "x" in f.detail for f in fs)


def test_format_findings_declares_no_compliance():
    p = _project()
    md = format_findings(p, [])
    assert "Aucun constat" in md
    # AUCUNE conformité réglementaire déclarée (§20)
    assert "AUCUNE conformité réglementaire" in md


def test_format_findings_lists_findings_with_counts():
    p = _project()
    p.new_node()                     # 1 nœud sans géométrie
    findings = coherence_findings(p)
    md = format_findings(p, findings)
    assert "1 nœud" in md or "| nodes | 1 |" in md
    assert "Nœud sans géométrie complète" in md
    assert "aucune donnée n'a" in md.lower() or "aucune donnée n’est" in md.lower()


def test_findings_are_typed_and_immutable():
    f = CoherenceFinding("cat", "SC-X", "detail")
    assert f.category == "cat" and f.sc_id == "SC-X" and f.detail == "detail"
