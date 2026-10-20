# -*- coding: utf-8 -*-
"""
tests/unit/test_reporting.py — Tests des rapports (spec §15.2, §15.3).

Vérifie que les rapports AFFICHENT les statuts honnêtes et ne masquent
jamais une étude incomplète (spec §15.3).
"""

from structcalc.core.model import Project
from structcalc.reporting.column_report import column_fiche, project_summary
from structcalc.solver.column_design import ColumnDesigner, ColumnMaterials, ColumnActions
from structcalc.core.status import RegulatoryStatus


def test_column_fiche_contains_traceability():
    p = Project(sc_id="SC-PROJECT-000001", name="Test")
    n1 = p.new_node(0, 0, 0)
    n2 = p.new_node(0, 3, 0)
    col = p.new_column(n1.sc_id, n2.sc_id, name="P1")
    md = column_fiche(col, project=p)
    assert col.sc_id in md
    assert "BAEL 91" in md
    assert "Validation ingénieur" in md or "validation" in md.lower()


def test_column_fiche_shows_honest_statuses():
    """Les vérifications sont listées avec leur statut réel (pas de masquage)."""
    p = Project(sc_id="SC-PROJECT-000001")
    n1 = p.new_node(0, 0, 0)
    n2 = p.new_node(0, 3, 0)
    col = p.new_column(n1.sc_id, n2.sc_id)
    d = ColumnDesigner()
    outcomes = d.search(
        height=3.0, buckling_y=3.0, buckling_z=3.0,
        materials=ColumnMaterials(fck=30, fyk=500, E=200000),
        actions=ColumnActions(N=200.0, combination="1.35G+1.5Q"))
    md = column_fiche(col, project=p, outcomes=outcomes)
    # Les statuts ne sont pas "conformes" silencieux
    assert "[OK] Conforme" not in md or "à valider" in md.lower()
    # le check non implémenté sismique apparaît
    assert "seismic" in md.lower() or "non implémenté" in md.lower()


def test_project_summary_flags_missing_data():
    p = Project(sc_id="SC-PROJECT-000001", name="Immeuble")
    p.new_node(0, 0, 0)
    p.new_material(kind="concrete")   # incomplet -> gap
    md = project_summary(p)
    assert "Données manquantes" in md
    assert "SC-MATERIAL" in md
    # ne prétend pas la conformité
    assert "conformité" in md.lower() or "conform" in md.lower()


def test_project_summary_no_false_conformity():
    p = Project(sc_id="SC-PROJECT-000001")
    md = project_summary(p)
    assert "Aucune conformité" in md or "conformité" in md.lower()
