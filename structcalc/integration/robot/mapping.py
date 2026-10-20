# -*- coding: utf-8 -*-
"""
integration/robot/mapping.py — Correspondance SC-* <-> Robot (spec §4.1, §5.2, §13).

Table de correspondance entre identifiants permanents STRUCTCALC et objets
Robot. Règles de la spec §4.1 :
  - un changement d'identifiant externe ne crée PAS automatiquement un nouvel
    objet interne si une correspondance fiable existe ;
  - les correspondances ambiguës sont SIGNALÉES, jamais résolues en silence.

Règle §13 : une absence d'objet dans un export incomplet ne signifie pas que
l'objet doit être supprimé. Aucune suppression sans règle explicite.

Indépendant de COM : travaille sur des dictionnaires (testable unitairement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ...core.model import ExternalRef


# Statuts de correspondance (spec §4.1)
MATCHED = "MATCHED"            # correspondance fiable établie
AMBIGUOUS = "AMBIGUOUS"        # plusieurs candidats -> arbitrage requis
UNMATCHED = "UNMATCHED"        # aucun partenaire
ORPHAN = "ORPHAN"              # objet externe sans partenaire interne


@dataclass
class MappingEntry:
    """Une ligne de correspondance SC-* <-> Robot."""
    sc_id: str
    robot_id: Optional[int] = None
    status: str = UNMATCHED
    robot_version: str = ""
    candidates: List[int] = field(default_factory=list)   # si AMBIGUOUS


@dataclass
class MappingTable:
    """
    Table de correspondance bidirectionnelle.

    Représente l'état du mapping entre le modèle interne et Robot. Gère la
    détection des ambiguïtés et le marquage des orphelins (aucune suppression
    automatique, spec §13).
    """
    software: str = "Robot"
    version: str = ""
    _by_sc: Dict[str, MappingEntry] = field(default_factory=dict)
    _by_robot: Dict[int, MappingEntry] = field(default_factory=dict)

    # -- Enregistrement --------------------------------------------------

    def link(self, sc_id: str, robot_id: int, status: str = MATCHED) -> MappingEntry:
        """Établit une correspondance explicite (après vérification)."""
        entry = MappingEntry(sc_id=sc_id, robot_id=int(robot_id), status=status,
                             robot_version=self.version)
        self._by_sc[sc_id] = entry
        self._by_robot[int(robot_id)] = entry
        return entry

    def mark_ambiguous(self, sc_id: str, candidates: List[int]) -> MappingEntry:
        """Signale une correspondance ambiguë (arbitrage requis, jamais auto)."""
        entry = MappingEntry(sc_id=sc_id, robot_id=None, status=AMBIGUOUS,
                             candidates=[int(c) for c in candidates],
                             robot_version=self.version)
        self._by_sc[sc_id] = entry
        return entry

    def mark_orphan(self, robot_id: int) -> MappingEntry:
        """
        Marque un objet Robot sans partenaire interne.

        Règle §13 : un orphelin n'est PAS supprimé automatiquement. Il est
        signalé pour arbitrage humain.
        """
        entry = MappingEntry(sc_id="", robot_id=int(robot_id), status=ORPHAN,
                             robot_version=self.version)
        self._by_robot[int(robot_id)] = entry
        return entry

    # -- Interrogation ---------------------------------------------------

    def robot_id_of(self, sc_id: str) -> Optional[int]:
        e = self._by_sc.get(sc_id)
        return e.robot_id if e and e.status == MATCHED else None

    def sc_id_of(self, robot_id: int) -> Optional[str]:
        e = self._by_robot.get(int(robot_id))
        return e.sc_id if e and e.status == MATCHED else None

    def entry_of(self, sc_id: str) -> Optional[MappingEntry]:
        return self._by_sc.get(sc_id)

    def status_of(self, sc_id: str) -> str:
        e = self._by_sc.get(sc_id)
        return e.status if e else UNMATCHED

    # -- Statistiques / audit -------------------------------------------

    def summary(self) -> Dict[str, int]:
        counts = {MATCHED: 0, AMBIGUOUS: 0, UNMATCHED: 0, ORPHAN: 0}
        for e in self._by_sc.values():
            counts[e.status] = counts.get(e.status, 0) + 1
        counts[ORPHAN] = sum(1 for e in self._by_robot.values()
                             if e.status == ORPHAN)
        return counts

    def issues(self) -> List[MappingEntry]:
        """Toutes les entrées nécessitant un arbitrage (ambiguës + orphelins)."""
        out = [e for e in self._by_sc.values() if e.status == AMBIGUOUS]
        out += [e for e in self._by_robot.values() if e.status == ORPHAN]
        return out

    def external_refs_for(self, sc_id: str) -> List[ExternalRef]:
        """Construit la liste ExternalRef (CORE) pour un objet mappé."""
        e = self._by_sc.get(sc_id)
        if not e:
            return []
        status = e.status
        return [ExternalRef(
            software=self.software, version=self.version,
            external_id=str(e.robot_id) if e.robot_id is not None else "",
            match_status=status,
        )]


def detect_unmatched(intern_ids: List[str], robot_ids: List[int],
                     table: MappingTable) -> dict:
    """
    Compare les ensembles interne/Robot et classe les écarts (spec §13).

    Retourne {"missing_in_robot": [...], "orphan_in_robot": [...],
              "matched": [...]}. NE supprime rien.
    """
    mapped_intern = {sc for sc in intern_ids
                     if table.status_of(sc) == MATCHED}
    mapped_robot = set(table._by_robot.keys())

    missing_in_robot = [sc for sc in intern_ids if sc not in mapped_intern]
    orphan_in_robot = [r for r in robot_ids if r not in mapped_robot]
    matched = [sc for sc in intern_ids if sc in mapped_intern]
    return {
        "matched": matched,
        "missing_in_robot": missing_in_robot,
        "orphan_in_robot": orphan_in_robot,
    }
