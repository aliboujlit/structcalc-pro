# -*- coding: utf-8 -*-
"""
integration/robot/model.py — Import/export du modèle structurel Robot.

Fonctions validées en Phase 0 sur Robot 2027 (chemins API vérifiés) :
  - serveur de modèle : rc.structure  (== Project.Structure)
  - création          : nodes.Create(number, x, y, z)
                        bars.Create(number, start_node, end_node)
  - comptage          : nodes.GetAll().Count   (PAS .Count)
  - accès unitaire    : nodes.Get(number)      (PAS .Item(number))

Ce module ne référence AUCUN objet STRUCTCALC interne : il travaille sur des
dictionnaires neutres. La traduction vers le modèle CORE (Column, Beam...) est
le rôle de la couche INTEGRATION plus haut (mapping.py), pas ici.

TODO Phase 2 : sections, matériaux (via Structure.Labels), charges, résultats.
"""

from __future__ import annotations

from typing import Any, Iterable

from .connection import RobotConnection


class RobotModelError(Exception):
    """Erreur lors de l'import/export du modèle Robot."""


# ---------------------------------------------------------------------------
# Import (Robot -> dictionnaires neutres)
# ---------------------------------------------------------------------------

def import_nodes(rc: RobotConnection) -> list[dict]:
    """
    Extrait tous les nœuds du modèle courant.

    Retourne une liste de {"number": int, "x": float, "y": float, "z": float}.
    Voie préférée : binding TYPÉ RobotOM (coll.Get(i) renvoie l'objet
    IRobotNode — seules les collections typées sont lisibles, le dispatch
    dynamique ne sait pas). Repli dynamique : numéros de la collection
    puis Get(numero) ; toute erreur COM remonte (jamais masquée).
    """
    _require_project(rc)
    nodes = rc.structure.Nodes
    coll = nodes.GetAll()
    count = int(coll.Count)
    out: list[dict] = []
    try:
        first = coll.Get(1) if count else None
    except Exception:
        first = None
    if first is not None and hasattr(first, "Number") and hasattr(first, "X"):
        # Binding typé : l'objet nœud vient de la collection.
        for i in range(1, count + 1):
            nd = coll.Get(i)
            out.append({"number": int(nd.Number), "x": float(nd.X),
                        "y": float(nd.Y), "z": float(nd.Z)})
        return out
    # Repli dynamique (numéros réels si accessibles, sinon dense Phase 0).
    for n in _iter_numbers(nodes):
        nd = nodes.Get(n)
        out.append({"number": int(n), "x": float(nd.X),
                    "y": float(nd.Y), "z": float(nd.Z)})
    return out


def import_bars(rc: RobotConnection) -> list[dict]:
    """
    Extrait toutes les barres du modèle courant.

    Retourne une liste de {"number": int, "start": int, "end": int}.
    Même logique que import_nodes : typé d'abord (IRobotBar), repli
    dynamique ensuite.
    """
    _require_project(rc)
    bars = rc.structure.Bars
    coll = bars.GetAll()
    count = int(coll.Count)
    out: list[dict] = []
    try:
        first = coll.Get(1) if count else None
    except Exception:
        first = None
    if (first is not None and hasattr(first, "Number")
            and hasattr(first, "StartNode")):
        for i in range(1, count + 1):
            br = coll.Get(i)
            out.append({"number": int(br.Number),
                        "start": int(br.StartNode),
                        "end": int(br.EndNode)})
        return out
    for b in _iter_numbers(bars):
        br = bars.Get(b)
        out.append({"number": int(b), "start": int(br.StartNode),
                    "end": int(br.EndNode)})
    return out


def import_model(rc: RobotConnection) -> dict:
    """Import complet (nœuds + barres) sous forme de dict neutre."""
    return {
        "nodes": import_nodes(rc),
        "bars": import_bars(rc),
    }


# ---------------------------------------------------------------------------
# Export (dictionnaires neutres -> Robot)
# ---------------------------------------------------------------------------

def export_nodes(rc: RobotConnection, nodes: Iterable[dict]) -> int:
    """
    Crée des nœuds dans Robot à partir d'une liste de dicts.

    Chaque dict doit contenir : number, x, y, z.
    Retourne le nombre de nœuds créés.
    """
    _require_project(rc)
    srv = rc.structure.Nodes
    count = 0
    for nd in nodes:
        try:
            number = int(nd["number"])
            x, y, z = float(nd.get("x", 0)), float(nd.get("y", 0)), float(nd.get("z", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise RobotModelError(f"Nœud invalide {nd!r} : {exc}") from exc
        srv.Create(number, x, y, z)
        count += 1
    return count


def export_bars(rc: RobotConnection, bars: Iterable[dict]) -> int:
    """
    Crée des barres dans Robot à partir d'une liste de dicts.

    Chaque dict doit contenir : number, start, end.
    Retourne le nombre de barres créées.
    """
    _require_project(rc)
    srv = rc.structure.Bars
    count = 0
    for br in bars:
        try:
            number = int(br["number"])
            start = int(br["start"])
            end = int(br["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RobotModelError(f"Barre invalide {br!r} : {exc}") from exc
        srv.Create(number, start, end)
        count += 1
    return count


def export_model(rc: RobotConnection, model: dict) -> dict:
    """
    Exporte nœuds puis barres (ordre imposé : les barres référencent des nœuds).

    Retourne un résumé {"nodes": n, "bars": m}.
    """
    n_nodes = export_nodes(rc, model.get("nodes", []))
    n_bars = export_bars(rc, model.get("bars", []))
    return {"nodes": n_nodes, "bars": n_bars}


# ---------------------------------------------------------------------------
# Comptage / vérification post-transfert
# ---------------------------------------------------------------------------

def count_nodes(rc: RobotConnection) -> int:
    """Nombre de nœuds (via GetAll().Count, chemin vérifié)."""
    _require_project(rc)
    return int(rc.structure.Nodes.GetAll().Count)


def count_bars(rc: RobotConnection) -> int:
    """Nombre de barres (via GetAll().Count, chemin vérifié)."""
    _require_project(rc)
    return int(rc.structure.Bars.GetAll().Count)


def verify_transfer(rc: RobotConnection, expected_nodes: int,
                    expected_bars: int) -> dict:
    """
    Contrôle post-transfert (spec §5.3 « validation après transfert »).

    Compare les compteurs attendus vs réels. Retourne un rapport de checks.
    """
    actual_nodes = count_nodes(rc)
    actual_bars = count_bars(rc)
    checks = {
        "nodes_match": actual_nodes == expected_nodes,
        "bars_match": actual_bars == expected_bars,
    }
    return {
        "expected": {"nodes": expected_nodes, "bars": expected_bars},
        "actual": {"nodes": actual_nodes, "bars": actual_bars},
        "checks": checks,
        "ok": all(checks.values()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_project(rc: RobotConnection) -> None:
    if not rc.is_project_open:
        raise RobotModelError(
            "Aucun projet Robot ouvert. Appeliez rc.new_project() d'abord."
        )


def _iter_numbers(server) -> list[int]:
    """
    Itère sur les NUMÉROS RÉELS des objets d'un serveur Robot.

    GetAll() renvoie une collection indexable (IRobotNumberCollection) dont
    les items SONT les numéros d'objet. On ne suppose JAMAIS une
    numérotation dense 1..N : constaté en live sur la villa (numérotation
    non dense — l'ancien supposé 1..N levait E_UNEXPECTED sur un nœud
    inexistant alors que GetAll().Count répondait correctement).
    Accesseurs essayés (1-based) : GetNumber, Item, appélable coll(i).
    Repli dense 1..N en dernier recours (comportement Phase 0, modèles
    historiques sans accesseur de collection exposé).
    """
    coll = server.GetAll()
    count = int(coll.Count)
    for accessor in ("GetNumber", "Item", "__call__"):
        try:
            if accessor == "__call__":
                get = lambda i: coll(i)  # noqa: E731 — dispatch appelable
            else:
                get = getattr(coll, accessor)
            return [int(get(i)) for i in range(1, count + 1)]
        except Exception:               # accesseur absent/échoue : suivant
            continue
    # Dernier recours : numérotation dense (Phase 0).
    return list(range(1, count + 1))


def iter_objects(server) -> list:
    """
    Objets RÉELS d'un serveur Robot (IRobotBar, IRobotNode, ...) :

    1. Voie préférée — collection TYPÉE GetAll().Get(i) : seuls les
       objets typés portent Number/GetLabelName (constaté live) ; sur la
       villa, 108/108 barres lues, dont les numéros non denses 109-138
       (v1.3.1 — l'ancien parcours serveur.Get(i) 1..Count n'en atteignait
       que 78 classées).
    2. Repli dynamique — serveur.Get(numéro RÉEL) via _iter_numbers
       (jamais de boucle dense 1..N sur un serveur à numéros gapés).

    Toute erreur COM remonte (jamais masquée) sauf l'absence d'objet
    unitaire qui borne la voie préférée.
    """
    coll = server.GetAll()
    count = int(coll.Count)
    try:
        first = coll.Get(1) if count else None
    except Exception:
        first = None
    if first is not None and hasattr(first, "Number"):
        return [coll.Get(i) for i in range(1, count + 1)]
    return [server.Get(n) for n in _iter_numbers(server)]
