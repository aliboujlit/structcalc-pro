# -*- coding: utf-8 -*-
"""
tests/unit/test_model.py — Tests du modèle structurel interne (spec §3.1, §4).

100 % indépendants de Robot. Vérifient la stabilité des identifiants,
les données manquantes signalées (jamais inventées) et la cohérence.
"""

import pytest

from structcalc.core.model import Project, Column, Material
from structcalc.core.status import DataStatus
from structcalc.core.tracked import TrackedValue, Provenance


def test_ids_are_stable_and_unique():
    p = Project(sc_id="SC-PROJECT-000001")
    n1 = p.new_node(0, 0, 0)
    n2 = p.new_node(4, 0, 0)
    col = p.new_column(n1.sc_id, n2.sc_id)
    assert n1.sc_id == "SC-NODE-000001"
    assert n2.sc_id == "SC-NODE-000002"
    assert col.sc_id == "SC-COLUMN-000001"
    # indépendance des compteurs
    mat = p.new_material(kind="concrete")
    assert mat.sc_id == "SC-MATERIAL-000001"


def test_node_coordinates():
    p = Project(sc_id="SC-PROJECT-000001")
    n = p.new_node(1.5, 2.0, 3.0)
    assert n.coordinates() == (1.5, 2.0, 3.0)


def test_missing_node_coord_is_none():
    p = Project(sc_id="SC-PROJECT-000001")
    n = p.new_node(1.0, None, 0.0)   # y manquant
    assert n.coordinates() is None


def test_restore_allocator_prevents_id_collision():
    """Après chargement, régénérer un objet ne doit pas écraser un ID."""
    p = Project(sc_id="SC-PROJECT-000001")
    p.new_node(0, 0, 0)
    p.new_node(1, 0, 0)
    # Simuler un rechargement : on restaure depuis les IDs existants
    p2 = Project(sc_id="SC-PROJECT-000001")
    p2.nodes = {"SC-NODE-000001": None, "SC-NODE-000002": None}
    p2.restore_allocator()
    n = p2.new_node(9, 9, 9)
    assert n.sc_id == "SC-NODE-000003"


def test_material_missing_properties_reported_not_invented():
    """Une propriété absente doit être SIGNALÉE, jamais inventée."""
    mat = Material(sc_id="SC-MATERIAL-000001", kind="concrete")
    assert mat.is_complete() is False
    miss = mat.missing_properties()
    assert "fck" in miss and "fyd" in miss
    # La valeur reste manquante (None), pas 0 inventé
    assert mat.fck.value is None
    assert mat.fck.status == DataStatus.MISSING


def test_material_complete_when_provided():
    mat = Material(sc_id="SC-MATERIAL-000001", kind="concrete")
    mat.E.set(35000, DataStatus.PROVIDED)
    mat.fck.set(30, DataStatus.PROVIDED)
    mat.fyd.set(500, DataStatus.PROVIDED)
    mat.gamma_c.set(1.5, DataStatus.PROVIDED)
    mat.gamma_s.set(1.15, DataStatus.PROVIDED)
    assert mat.is_complete() is True
    assert mat.missing_properties() == []


def test_assumed_material_not_silently_validated():
    """Règle §4.2 : une hypothèse de matériau n'est pas validée en silence."""
    mat = Material(sc_id="SC-MATERIAL-000001")
    mat.fck.set(30, DataStatus.ASSUMED)
    with pytest.raises(ValueError):
        mat.fck.set(30, DataStatus.VALIDATED)
    # Passage par la voie explicite
    mat.fck.validate_assumption(30, validated_by="Ing. Martin")
    assert mat.fck.status == DataStatus.VALIDATED


def test_counts_and_data_gaps():
    p = Project(sc_id="SC-PROJECT-000001")
    p.new_node(0, 0, 0)
    p.new_material(kind="concrete")      # incomplet -> gap
    p.new_section(kind="rectangular")    # incomplet -> gap
    c = p.counts()
    assert c["nodes"] == 1
    assert c["materials"] == 1
    gaps = p.data_gaps()
    assert any(k.startswith("SC-MATERIAL") for k in gaps)
    assert any(k.startswith("SC-SECTION") for k in gaps)


def test_column_geometry_ready():
    p = Project(sc_id="SC-PROJECT-000001")
    n1 = p.new_node(0, 0, 0)
    n2 = p.new_node(0, 0, 3.0)
    col = p.new_column(n1.sc_id, n2.sc_id)
    # tant que la hauteur n'est pas renseignée -> pas prêt
    assert col.geometry_ready() is False
    col.height.set(3.0, DataStatus.PROVIDED)
    assert col.geometry_ready() is True


def test_external_ref_mapping():
    """Le mapping externe est séparé de l'ID interne (spec §4.1)."""
    from structcalc.core.model import ExternalRef
    p = Project(sc_id="SC-PROJECT-000001")
    n = p.new_node(0, 0, 0)
    n.add_external_ref(ExternalRef(software="Robot", version="40.0",
                                   external_id="42", match_status="MATCHED"))
    ref = n.ref_for("Robot")
    assert ref is not None
    assert ref.external_id == "42"
    # L'ID interne reste stable, indépendant de l'externe
    assert n.sc_id == "SC-NODE-000001"
