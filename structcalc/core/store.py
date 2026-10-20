# -*- coding: utf-8 -*-
"""
core/store.py — Persistance SQLite du modèle interne (spec §3.1, §16).

Conserve le projet de façon reproductible : identifiants stables, statuts,
provenance. Permet la sauvegarde/restauration exigées par la spec §16
(« permettre la restauration d'un projet »).

Choix : une table générique `objects` (clé/valeur JSON) + une table
`external_refs` pour le mapping. Un schéma relationnel strict viendra si
les besoins de requête l'exigent ; la priorité Phase 1 est la fidélité
de la traçabilité (IDs, statuts, provenance), testée unitairement.

Aucune dépendance externe (sqlite3 de la stdlib).
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Iterable, List, Optional

from .model import Project, Node, Material, Column
from .status import DataStatus
from .tracked import TrackedValue, Provenance


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS objects (
    sc_id    TEXT PRIMARY KEY,
    kind     TEXT NOT NULL,
    name     TEXT DEFAULT '',
    data     TEXT NOT NULL           -- JSON du contenu sérialisé
);
CREATE TABLE IF NOT EXISTS external_refs (
    sc_id       TEXT NOT NULL,
    software    TEXT NOT NULL,
    version     TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    match_status TEXT DEFAULT 'UNMATCHED',
    PRIMARY KEY (sc_id, software)
);
"""


class ProjectStore:
    """
    Sauvegarde/charge un Project en SQLite.

    Usage :
        store = ProjectStore("mon_projet.db")
        store.save(project)
        loaded = store.load()
    """

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    def open(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ------------------------------------------------------------------
    # Sauvegarde
    # ------------------------------------------------------------------
    def save(self, project: Project) -> int:
        """
        Sauvegarde complète du projet (écrase l'état précédent pour ces IDs).

        Retourne le nombre d'objets écrits.
        """
        conn = self.open()
        count = 0
        # Métadonnées (compteurs d'identifiants pour stabilité)
        self._set_meta(conn, "id_allocator",
                       json.dumps(project.allocator.snapshot()))
        self._set_meta(conn, "project_sc_id", project.sc_id)
        self._set_meta(conn, "project_name", project.name)

        # Objet racine
        count += self._upsert(conn, project.sc_id, "PROJECT", project.name,
                              {"sc_id": project.sc_id, "name": project.name})
        # Nœuds
        for nid, node in project.nodes.items():
            payload = {
                "sc_id": node.sc_id,
                "name": node.name,
                "x": _tv(node.x), "y": _tv(node.y), "z": _tv(node.z),
            }
            count += self._upsert(conn, nid, "NODE", node.name, payload)
            self._save_ext_refs(conn, node.sc_id, node.external_refs)
        # Matériaux
        for mid, mat in project.materials.items():
            payload = {
                "sc_id": mat.sc_id, "name": mat.name, "kind": mat.kind,
                "concrete_class": mat.concrete_class, "steel_grade": mat.steel_grade,
                "E": _tv(mat.E), "fck": _tv(mat.fck), "fyd": _tv(mat.fyd),
                "gamma_c": _tv(mat.gamma_c), "gamma_s": _tv(mat.gamma_s),
            }
            count += self._upsert(conn, mid, "MATERIAL", mat.name, payload)
        # Sections
        for sid, sec in project.sections.items():
            payload = {
                "sc_id": sec.sc_id, "name": sec.name, "kind": sec.kind,
                "b": _tv(sec.b), "h": _tv(sec.h),
                "area": _tv(sec.area), "Iz": _tv(sec.Iz), "Iy": _tv(sec.Iy),
            }
            count += self._upsert(conn, sid, "SECTION", sec.name, payload)
        # Poteaux
        for cid, col in project.columns.items():
            payload = {
                "sc_id": col.sc_id, "name": col.name,
                "start_node": col.start_node, "end_node": col.end_node,
                "material": col.material, "section": col.section,
                "storey": col.storey, "height": _tv(col.height),
                "buckling_length_y": _tv(col.buckling_length_y),
                "buckling_length_z": _tv(col.buckling_length_z),
                "fixity_top": col.fixity_top, "fixity_bottom": col.fixity_bottom,
            }
            count += self._upsert(conn, cid, "COLUMN", col.name, payload)

        conn.commit()
        return count

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------
    def load(self) -> Project:
        """
        Charge un projet. Restaure l'allocateur pour garantir la stabilité
        des identifiants (spec §4.1).
        """
        conn = self.open()
        rows = conn.execute("SELECT * FROM objects").fetchall()
        by_kind: dict = {}
        for r in rows:
            by_kind.setdefault(r["kind"], []).append(r)

        # Métadonnées
        sc_id = self._get_meta(conn, "project_sc_id") or "SC-PROJECT-000001"
        name = self._get_meta(conn, "project_name") or ""
        project = Project(sc_id=sc_id, name=name)

        # Nœuds
        for r in by_kind.get("NODE", []):
            d = json.loads(r["data"])
            node = Node(sc_id=d["sc_id"], name=d.get("name", ""),
                        x=_from_tv(d["x"]), y=_from_tv(d["y"]),
                        z=_from_tv(d["z"]))
            node.external_refs = self._load_ext_refs(conn, node.sc_id)
            project.nodes[node.sc_id] = node
        # Matériaux
        for r in by_kind.get("MATERIAL", []):
            d = json.loads(r["data"])
            mat = Material(sc_id=d["sc_id"], name=d.get("name", ""),
                           kind=d.get("kind", ""),
                           concrete_class=d.get("concrete_class", ""),
                           steel_grade=d.get("steel_grade", ""),
                           E=_from_tv(d["E"]), fck=_from_tv(d["fck"]),
                           fyd=_from_tv(d["fyd"]),
                           gamma_c=_from_tv(d["gamma_c"]),
                           gamma_s=_from_tv(d["gamma_s"]))
            project.materials[mat.sc_id] = mat
        # Sections
        for r in by_kind.get("SECTION", []):
            d = json.loads(r["data"])
            from .model import CrossSection
            sec = CrossSection(sc_id=d["sc_id"], name=d.get("name", ""),
                               kind=d.get("kind", ""),
                               b=_from_tv(d["b"]), h=_from_tv(d["h"]),
                               area=_from_tv(d["area"]), Iz=_from_tv(d["Iz"]),
                               Iy=_from_tv(d["Iy"]))
            project.sections[sec.sc_id] = sec
        # Poteaux
        for r in by_kind.get("COLUMN", []):
            d = json.loads(r["data"])
            col = Column(sc_id=d["sc_id"], name=d.get("name", ""),
                         start_node=d.get("start_node"),
                         end_node=d.get("end_node"),
                         material=d.get("material"), section=d.get("section"),
                         storey=d.get("storey"),
                         height=_from_tv(d["height"]),
                         buckling_length_y=_from_tv(d["buckling_length_y"]),
                         buckling_length_z=_from_tv(d["buckling_length_z"]),
                         fixity_top=d.get("fixity_top", ""),
                         fixity_bottom=d.get("fixity_bottom", ""))
            project.columns[col.sc_id] = col

        # Restaurer l'allocateur (stabilité des IDs, spec §4.1)
        snap = self._get_meta(conn, "id_allocator")
        if snap:
            from .ids import IdAllocator
            project.allocator = IdAllocator(start_state=json.loads(snap))
        else:
            project.restore_allocator()

        return project

    # ------------------------------------------------------------------
    # Helpers SQL
    # ------------------------------------------------------------------
    @staticmethod
    def _set_meta(conn, key: str, value: str):
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))

    @staticmethod
    def _get_meta(conn, key: str) -> Optional[str]:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    @staticmethod
    def _upsert(conn, sc_id: str, kind: str, name: str, payload: dict) -> int:
        conn.execute(
            "INSERT INTO objects(sc_id, kind, name, data) VALUES(?,?,?,?) "
            "ON CONFLICT(sc_id) DO UPDATE SET kind=excluded.kind, "
            "name=excluded.name, data=excluded.data",
            (sc_id, kind, name or "", json.dumps(payload, ensure_ascii=False)))
        return 1

    @staticmethod
    def _save_ext_refs(conn, sc_id: str, refs: Iterable):
        for ref in refs:
            conn.execute(
                "INSERT OR REPLACE INTO external_refs"
                "(sc_id, software, version, external_id, match_status) "
                "VALUES(?,?,?,?,?)",
                (sc_id, ref.software, ref.version, ref.external_id,
                 ref.match_status))

    @staticmethod
    def _load_ext_refs(conn, sc_id: str):
        from .model import ExternalRef
        rows = conn.execute(
            "SELECT * FROM external_refs WHERE sc_id=?", (sc_id,)).fetchall()
        return [ExternalRef(software=r["software"], version=r["version"],
                            external_id=r["external_id"],
                            match_status=r["match_status"]) for r in rows]

    def count_objects(self) -> int:
        conn = self.open()
        row = conn.execute("SELECT COUNT(*) AS n FROM objects").fetchone()
        return int(row["n"])


# ---------------------------------------------------------------------------
# Sérialisation TrackedValue (JSON-safe)
# ---------------------------------------------------------------------------

def _tv(tval) -> Optional[dict]:
    """TrackedValue -> dict JSON-safe (ou None)."""
    if tval is None:
        return None
    return {
        "value": tval.value,
        "unit": tval.unit,
        "status": tval.status.value,
        "source": tval.provenance.source,
        "version": tval.provenance.version,
        "method": tval.provenance.method,
        "external_id": tval.provenance.external_id,
        "validated_by": tval.provenance.validated_by,
        "timestamp": tval.provenance.timestamp,
    }


def _from_tv(d: Optional[dict]) -> TrackedValue:
    """dict JSON-safe -> TrackedValue."""
    if d is None:
        return TrackedValue.missing()
    prov = Provenance(
        source=d.get("source", "STRUCTCALC"), version=d.get("version", ""),
        external_id=d.get("external_id", ""), method=d.get("method", ""),
        timestamp=d.get("timestamp", ""),
        validated_by=d.get("validated_by", ""))
    try:
        status = DataStatus(d.get("status", "MISSING"))
    except ValueError:
        status = DataStatus.MISSING
    return TrackedValue(value=d.get("value"), unit=d.get("unit", ""),
                        status=status, provenance=prov)
