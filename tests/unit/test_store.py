# -*- coding: utf-8 -*-
"""
tests/unit/test_store.py — Tests de persistance SQLite (spec §16 restauration).

Vérifie le cycle sauvegarde -> chargement en conservant fidèlement :
  - les identifiants SC-* (stabilité),
  - les statuts et la provenance (traçabilité),
  - les références externes (mapping).

100 % indépendant de Robot (fichier temporaire).
"""

import os
import tempfile

from structcalc.core.model import Project, ExternalRef
from structcalc.core.status import DataStatus
from structcalc.core.store import ProjectStore


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)   # ProjectStore doit pouvoir le créer
    return path


def test_save_load_roundtrip_preserves_ids_and_status():
    db = _tmp_db()
    try:
        p = Project(sc_id="SC-PROJECT-000001", name="Immeuble Test")
        n1 = p.new_node(0, 0, 0)
        n2 = p.new_node(0, 3, 0)
        col = p.new_column(n1.sc_id, n2.sc_id, name="P1")
        col.height.set(3.0, DataStatus.PROVIDED)

        mat = p.new_material(kind="concrete", name="Béton")
        mat.fck.set(30, DataStatus.ASSUMED)   # hypothèse, tracée

        # Référence externe Robot (mapping)
        n1.add_external_ref(ExternalRef(software="Robot", version="40.0",
                                        external_id="7", match_status="MATCHED"))

        store = ProjectStore(db)
        n_written = store.save(p)
        assert n_written >= 4
        store.close()

        # Recharger
        with ProjectStore(db) as s2:
            loaded = s2.load()

        # IDs stables
        assert loaded.nodes[n1.sc_id].sc_id == n1.sc_id
        assert loaded.columns[col.sc_id].sc_id == col.sc_id
        # Coordonnées fidèles
        assert loaded.nodes[n1.sc_id].coordinates() == (0.0, 0.0, 0.0)
        assert loaded.nodes[n2.sc_id].coordinates() == (0.0, 3.0, 0.0)
        # Statut/provenance conservés (traçabilité)
        assert loaded.materials[mat.sc_id].fck.status == DataStatus.ASSUMED
        assert loaded.materials[mat.sc_id].fck.value == 30
        # Poteau + hauteur
        assert loaded.columns[col.sc_id].height.value == 3.0
        # Référence externe restaurée
        ref = loaded.nodes[n1.sc_id].ref_for("Robot")
        assert ref is not None and ref.external_id == "7"
    finally:
        if os.path.exists(db):
            os.remove(db)


def test_allocator_stable_after_reload():
    """Après rechargement, un nouvel objet continue la numérotation."""
    db = _tmp_db()
    try:
        p = Project(sc_id="SC-PROJECT-000001")
        p.new_node(0, 0, 0)
        p.new_node(1, 0, 0)
        with ProjectStore(db) as s:
            s.save(p)

        with ProjectStore(db) as s2:
            loaded = s2.load()
        new_node = loaded.new_node(9, 9, 9)
        assert new_node.sc_id == "SC-NODE-000003"   # pas de collision
    finally:
        if os.path.exists(db):
            os.remove(db)


def test_open_context_manager_and_count():
    db = _tmp_db()
    try:
        p = Project(sc_id="SC-PROJECT-000001")
        p.new_node(0, 0, 0)
        with ProjectStore(db) as store:
            store.save(p)
            assert store.count_objects() >= 1
    finally:
        if os.path.exists(db):
            os.remove(db)
