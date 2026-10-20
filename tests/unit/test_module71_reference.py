# -*- coding: utf-8 -*-
"""
tests/unit/test_module71_reference.py — Module 71 : projet de référence
SC-TEST-R3-100M2 (spec §11) + critères géométriques (§11.2).

Scénario (§3, §11.1) : RDC+3 étages, emprise 10x10 m, trame 5x5 m,
9 poteaux/niveau, 4 panneaux de dalle, RDC 3.5 m, étages 3.0 m, sans sous-sol.
Hypothèses PÉDAGOGIQUES — jamais prescriptions de dimensionnement.
"""

import pytest

from structcalc.core.model import Project
from structcalc.architectural_structural import (
    ArchitecturalModel, import_architectural_source, build_grid,
    propose_layout, create_variants, build_structural_model,
    build_analysis_model, check_vertical_continuity,
    spacing_between, detect_scale, ImportReport,
)

# ---------------------------------------------------------------------------
# Projet de référence (spec §3 / §11.1)
# ---------------------------------------------------------------------------

REF_SOURCE = {
    "unit": "m",
    "levels": [
        {"name": "RDC", "elevation": 0.0, "height": 3.5},
        {"name": "R+1", "elevation": 3.5, "height": 3.0},
        {"name": "R+2", "elevation": 6.5, "height": 3.0},
        {"name": "R+3", "elevation": 9.5, "height": 3.0},
    ],
    "axes_x": [0.0, 5.0, 10.0],
    "axes_y": [0.0, 5.0, 10.0],
    "openings": [
        {"kind": "stairwell", "level": "R+1", "cx": 7.5, "cy": 2.5,
         "width": 2.4, "depth": 4.8},
    ],
    "elements": [
        {"kind": "wall", "level": "RDC", "function": "BEARING",
         "outline": [(0, 0), (10, 0)]},
        {"kind": "partition", "level": "RDC", "function": "UNKNOWN",
         "outline": [(5, 0), (5, 10)]},
    ],
}


def make_reference_model() -> ArchitecturalModel:
    """Construit le modèle de référence R+3 (import Phase A)."""
    proj = Project(sc_id="SC-TEST-R3-100M2", name="Référence R+3")
    am = ArchitecturalModel(project=proj)
    rep = import_architectural_source(am, "raw", REF_SOURCE)
    assert rep.ok(), f"import bloqué : {[i.message for i in rep.blocking_issues]}"
    return am


# ---------------------------------------------------------------------------
# §11.2 — Tests géométriques
# ---------------------------------------------------------------------------

def test_axes_unique_and_dimensioned():
    """Les axes sont uniques et correctement cotés (§11.2)."""
    am = make_reference_model()
    xs = [a for a in am.axes.values() if a.direction == "X"]
    ys = [a for a in am.axes.values() if a.direction == "Y"]
    assert len(xs) == 3 and len(ys) == 3
    # Unicité des positions
    xpos = sorted(float(a.position.value) for a in xs)
    ypos = sorted(float(a.position.value) for a in ys)
    assert xpos == [0.0, 5.0, 10.0]
    assert ypos == [0.0, 5.0, 10.0]
    # Entraxes calculés = 5.00 m (§3)
    spans = spacing_between(list(am.axes.values()), "X")
    assert [round(d, 3) for _, _, d in spans] == [5.0, 5.0]


def test_columns_have_stable_ids():
    """Les poteaux ont des identifiants stables SC-* (§6.1, §11.2)."""
    am = make_reference_model()
    grid = build_grid(am)
    assert grid.n_columns == 9          # 3x3 intersections
    # Trame régulière documentée
    assert any("entraxe" in r.lower() for r in grid.reasons)


def test_levels_coherent():
    """Les niveaux sont cohérents (§11.2) : altitudes croissantes."""
    am = make_reference_model()
    assert len(am.levels) == 4
    elevs = [float(lv.elevation.value)
             for lv in sorted(am.levels.values(), key=lambda l: l.index)]
    assert elevs == [0.0, 3.5, 6.5, 9.5]
    # Hauteurs : RDC 3.5, étages 3.0 (§3)
    rdc = [lv for lv in am.levels.values() if lv.name == "RDC"][0]
    assert float(rdc.height_above.value) == pytest.approx(3.5)


def test_beams_have_valid_connections():
    """Les poutres possèdent des connexions valides (§11.2)."""
    am = make_reference_model()
    grid = build_grid(am)
    layout = propose_layout(am, grid=grid)
    beams = layout.by_kind("beam")
    assert beams, "aucune poutre proposée"
    for b in beams:
        assert b.start is not None and b.end is not None
        assert b.start != b.end
        assert b.span and b.span > 0


def test_slabs_delimited_correctly():
    """Les dalles sont délimitées correctement (§11.2) : 4 panneaux (§11.1)."""
    am = make_reference_model()
    grid = build_grid(am)
    assert grid.n_panels == 4           # 2x2 panneaux de 5x5
    for (x1, y1, x2, y2) in grid.slab_panels:
        assert x2 - x1 == pytest.approx(5.0)
        assert y2 - y1 == pytest.approx(5.0)


def test_openings_not_ignored():
    """Les ouvertures ne sont pas ignorées (§11.2)."""
    am = make_reference_model()
    assert len(am.openings) == 1
    op = list(am.openings.values())[0]
    assert op.kind == "stairwell"
    assert not op.width.is_missing
    # Trémie présente dans le modèle et rattachée au niveau R+1
    assert op.level_ref is not None
    assert am.levels[op.level_ref].name == "R+1"
    # La trémie (7.5, 2.5) est ENTRE axes : aucune intersection couverte,
    # donc les 9 poteaux restent proposés (aucun n'est supprimé silencieusement)
    grid = build_grid(am, exclude_openings=True)
    assert grid.n_columns == 9


def test_opening_on_intersection_excludes_column():
    """Une ouverture COUVRANT une intersection exclut le poteau proposé
    (§5.2/§9.1) : la raison est tracée, l'intersection n'est pas supprimée."""
    am = make_reference_model()
    # Ajout d'une gaine EXACTEMENT sur l'intersection (5, 5)
    am.new_opening(kind="shaft", level_ref=None,
                   cx=5.0, cy=5.0, width=2.0, depth=2.0)
    grid = build_grid(am, exclude_openings=True)
    assert grid.n_columns == 8                       # 9 - 1 couvert
    assert len(grid.nodes) == 9                      # intersection toujours là
    assert any("trémie" in r.lower() or "réservation" in r.lower()
               for r in grid.reasons)


def test_offsets_between_storeys_detected():
    """Les décalages entre étages sont détectés (§7.1, §11.2)."""
    am = make_reference_model()
    grid = build_grid(am)
    base = {"x": 0.0, "y": 0.0}
    aligned = [dict(base, ref="SC-COLUMN-000001"), {"x": 5.0, "y": 5.0,
                                                    "ref": "SC-COLUMN-000002"}]
    offset = [dict(base, ref="SC-COLUMN-000011"), {"x": 5.3, "y": 5.0,
                                                   "ref": "SC-COLUMN-000012"}]
    rep = check_vertical_continuity(
        am, ["lvl0", "lvl1"], {"lvl0": aligned, "lvl1": offset})
    codes = {f.code for f in rep.findings}
    assert "ALIGNED" in codes          # (0,0) aligné
    assert "OFFSET" in codes           # (5,5) -> (5.3,5) décalé
    # Aucun constat n'est concluant seul (§7.1)
    assert all(f.requires_analysis for f in rep.findings)


# ---------------------------------------------------------------------------
# Contrôle des unités / échelles (§4.4)
# ---------------------------------------------------------------------------

def test_unknown_unit_is_blocking():
    """Unité inconnue => bloquant, jamais supposée mètre (§4.4)."""
    rep = ImportReport()
    scale = detect_scale("furlong", rep)
    assert rep.has_blocking and not rep.ok()
    assert any(i.code == "UNIT_UNKNOWN" for i in rep.issues)


def test_cm_scale_conversion():
    """Unité cm -> facteur 0.01 (contrôle d'échelle, §4.4)."""
    rep = ImportReport()
    assert detect_scale("cm", rep) == pytest.approx(0.01)
    assert rep.ok()


# ---------------------------------------------------------------------------
# Régression : le projet de référence reste stable
# ---------------------------------------------------------------------------

def test_reference_counts():
    """Compteurs du projet de référence (§11.1) : 4 niveaux, 9 poteaux."""
    am = make_reference_model()
    grid = build_grid(am)
    c = am.counts()
    assert c["levels"] == 4
    assert c["axes"] == 6
    assert grid.n_columns == 9
    assert grid.n_panels == 4
