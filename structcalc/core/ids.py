# -*- coding: utf-8 -*-
"""
core/ids.py — Identifiants permanents STRUCTCALC (spec §4.1).

Format vérifié dans la spec §4.1 :
    SC-NODE-000124
    SC-COLUMN-000037
    SC-SECTION-000021
    SC-COMB-000014

Règles :
  - préfixe SC
  - type d'objet en MAJUSCULES
  - numéro séquentiel sur 6 chiffres (zéro-gauche), extensible

L'identifiant est PERMANENT : il ne change jamais, même si l'identifiant
externe (Robot/Revit) change. C'est la clé de voûte du mapping (spec §4.1).

L'allocateur garde un compteur par type pour éviter toute collision, même
après rechargement d'un projet (le compteur peut être restauré depuis la base).
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional


# Types d'objets reconnus (spec §3.1 + §4.1). Extensible.
KNOWN_TYPES = {
    "PROJECT", "BUILDING", "STOREY", "GRID",
    "NODE", "COLUMN", "BEAM", "SLAB", "WALL", "FOUNDATION",
    "MATERIAL", "SECTION", "SUPPORT",
    "LOADCASE", "COMB", "ANALYSISMODEL", "RESULT",
    "CHECK", "REINFORCEMENT", "DOCUMENT", "REVISION", "ISSUE",
    # Module 71 (architectural -> structurel) — types ajoutés
    "AXIS", "ARCHELEM", "OPENING", "STAIR",
    "CONFLICT", "VARIANT", "DRAWING", "APPROVAL",
}

_WIDTH = 6   # largeur du numéro (000124)


def make_id(obj_type: str, number: int) -> str:
    """
    Construit un identifiant SC-<TYPE>-<numéro sur 6 chiffres>.

    >>> make_id("NODE", 124)
    'SC-NODE-000124'
    >>> make_id("COLUMN", 37)
    'SC-COLUMN-000037'
    """
    t = str(obj_type).upper().strip()
    if not t:
        raise ValueError("obj_type vide.")
    n = int(number)
    if n < 0:
        raise ValueError(f"Numéro négatif non autorisé : {n}")
    return f"SC-{t}-{n:0{_WIDTH}d}"


def parse_id(sc_id: str) -> tuple[str, int]:
    """
    Décompose un identifiant SC-* -> (type, numéro).

    >>> parse_id("SC-NODE-000124")
    ('NODE', 124)
    """
    parts = str(sc_id).split("-")
    if len(parts) != 3 or parts[0] != "SC":
        raise ValueError(f"Identifiant STRUCTCALC invalide : {sc_id!r}")
    obj_type = parts[1]
    try:
        number = int(parts[2])
    except ValueError as exc:
        raise ValueError(f"Numéro invalide dans {sc_id!r}") from exc
    return obj_type, number


class IdAllocator:
    """
    Allocateur d'identifiants, compteur par type d'objet.

    Garantit l'unicité et la stabilité. Le compteur peut être initialisé
    depuis l'état existant (restore) pour éviter les collisions après
    rechargement d'un projet sauvegardé.

    Usage :
        alloc = IdAllocator()
        nid = alloc.new("NODE")     # SC-NODE-000001
        bid = alloc.new("BEAM")     # SC-BEAM-000001
    """

    def __init__(self, start_state: Optional[Dict[str, int]] = None):
        self._counters: Dict[str, int] = {}
        if start_state:
            for k, v in start_state.items():
                self._counters[str(k).upper()] = int(v)

    def new(self, obj_type: str) -> str:
        """Alloue le prochain identifiant pour un type donné."""
        t = str(obj_type).upper().strip()
        next_num = self.peek(t) + 1
        self._counters[t] = next_num
        return make_id(t, next_num)

    def peek(self, obj_type: str) -> int:
        """Retourne le dernier numéro alloué pour ce type (0 si aucun)."""
        return self._counters.get(str(obj_type).upper().strip(), 0)

    def restore(self, existing_ids: Iterable[str]) -> None:
        """
        Repousse les compteurs au-delà des identifiants déjà utilisés.

        Appeler après chargement d'un projet pour éviter les collisions.
        """
        for sc_id in existing_ids:
            try:
                obj_type, number = parse_id(sc_id)
            except ValueError:
                continue   # on ignore les IDs non standard
            if number > self.peek(obj_type):
                self._counters[obj_type] = number

    def snapshot(self) -> Dict[str, int]:
        """État des compteurs (persistable en base)."""
        return dict(self._counters)

    def validate(self, sc_id: str) -> bool:
        """Vrai si l'identifiant est bien formé."""
        try:
            parse_id(sc_id)
            return True
        except ValueError:
            return False
