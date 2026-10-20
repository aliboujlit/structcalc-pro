# -*- coding: utf-8 -*-
"""
core/coherence.py — Constats de cohérence du modèle interne (GUI v1.2 :
menu « Modèle > Vérifier la cohérence » + fin du « Workflow complet »).

Vérifie uniquement la COMPLÉTUDE et la COHÉRENCE INTERNE du pivot SC-*
(géométrie, références croisées, données fournies, hypothèses visibles).
AUCUNE formule réglementaire ici (§14.6) et AUCUNE conformité déclarée
(§20) : ce sont des constats de modèle, pas des vérifications BAEL/RPS.

Règles :
  - une donnée manquante est SIGNALÉE, jamais inventée (§4.2) ;
  - les valeurs ASSUMED sont listées visiblement (§4.5, jamais silencieuses) ;
  - « 0 constat » ne se traduit JAMAIS par « conforme ».
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class CoherenceFinding:
    """Constat sur le modèle (jamais un jugement de conformité)."""
    category: str      # ex. "Nœud sans géométrie complète"
    sc_id: str         # identifiant SC-* de l'objet concerné
    detail: str        # motif précis (donnée manquante)


def _height_derivable(col, nodes) -> bool:
    """Vrai si la hauteur du poteau est calculable depuis ses deux nœuds."""
    try:
        a = nodes.get(col.start_node)
        b = nodes.get(col.end_node)
        return (a is not None and b is not None
                and a.coordinates() is not None
                and b.coordinates() is not None)
    except Exception:
        return False


def _is_assumed(value: Any) -> bool:
    """Vrai si `value` est un TrackedValue au statut ASSUMED (§4.5).

    Utilise la propriété native `is_assumed` du core (jamais de recopie de
    la sémantique de statut).
    """
    flag = getattr(value, "is_assumed", None)
    if flag is None:
        return False
    try:
        return bool(flag)
    except Exception:
        return False


def _assumed_findings(project) -> List[CoherenceFinding]:
    """Valeurs supposées (ASSUMED) : hypothèses à valider, jamais cachées."""
    out: List[CoherenceFinding] = []
    containers = ("materials", "sections", "nodes", "columns", "beams",
                  "slabs", "walls", "supports", "storeys")
    for cname in containers:
        dct = getattr(project, cname, None)
        if not isinstance(dct, dict):
            continue
        for oid, obj in dct.items():
            try:
                attrs = vars(obj).items()
            except Exception:
                continue
            for attr, val in attrs:
                if attr.startswith("_"):
                    continue
                if _is_assumed(val):
                    out.append(CoherenceFinding(
                        "Valeur supposée (ASSUMED)", oid,
                        f"propriété « {attr} » : hypothèse à valider"))
    return out


def coherence_findings(project: Any) -> List[CoherenceFinding]:
    """Constats de cohérence du pivot — liste vide si aucun constat."""
    out: List[CoherenceFinding] = []
    if project is None:
        return out

    nodes = getattr(project, "nodes", {}) or {}

    # -- Nœuds sans géométrie complète (x/y/z) ---------------------------
    for nid, node in nodes.items():
        try:
            coords = node.coordinates()
        except Exception:
            coords = None
        if coords is None:
            out.append(CoherenceFinding(
                "Nœud sans géométrie complète", nid,
                "coordonnée(s) x/y/z manquante(s)"))

    # -- Poteaux : nœuds d'extrémité + hauteur dérivable + références -----
    for cid, col in getattr(project, "columns", {}).items():
        missing = []
        if col.start_node is None:
            missing.append("nœud de départ")
        if col.end_node is None:
            missing.append("nœud d'arrivée")
        if missing:
            out.append(CoherenceFinding(
                "Poteau sans géométrie complète", cid, ", ".join(missing)))
        elif col.height.is_missing and not _height_derivable(col, nodes):
            # La hauteur n'est flagrée QUE si elle n'est pas calculable
            # depuis les coordonnées des deux nœuds (jamais de faux positif
            # sur une géométrie pourtant dérivable).
            out.append(CoherenceFinding(
                "Poteau sans géométrie complète", cid,
                "hauteur manquante et non dérivable des nœuds"))
        for label, nid in (("début", col.start_node),
                           ("fin", col.end_node)):
            if nid is not None and nid not in nodes:
                out.append(CoherenceFinding(
                    "Référence de nœud inexistante", cid,
                    f"nœud de {label} « {nid} » absent du modèle"))

    # -- Barres/poutres : nœuds + section + références -------------------
    for bid, beam in getattr(project, "beams", {}).items():
        missing = []
        if beam.start_node is None:
            missing.append("nœud de départ")
        if beam.end_node is None:
            missing.append("nœud d'arrivée")
        if beam.section is None:
            missing.append("section")
        if missing:
            out.append(CoherenceFinding("Barre incomplète", bid,
                                        ", ".join(missing)))
        for label, nid in (("début", beam.start_node),
                           ("fin", beam.end_node)):
            if nid is not None and nid not in nodes:
                out.append(CoherenceFinding(
                    "Référence de nœud inexistante", bid,
                    f"nœud de {label} « {nid} » absent du modèle"))

    # -- Données manquantes (rapport §4.2 du modèle lui-même) ------------
    try:
        gaps = project.data_gaps()
    except Exception:
        gaps = {}
    for oid, props in gaps.items():
        out.append(CoherenceFinding("Données manquantes", oid,
                                    "propriété(s) : " + ", ".join(props)))

    # -- Hypothèses (ASSUMED, §4.5) --------------------------------------
    out.extend(_assumed_findings(project))
    return out


def format_findings(project: Any,
                    findings: List[CoherenceFinding]) -> str:
    """Rendu Markdown du rapport de cohérence (onglet Rapports)."""
    counts = project.counts() if project is not None else {}
    lines = ["## Vérification de cohérence du modèle", ""]
    if project is not None:
        lines.append(f"Projet : {getattr(project, 'name', '') or project.sc_id}")
        lines.append("")
    lines.append("| Élément | Nombre |")
    lines.append("|---|---:|")
    for k, v in counts.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    if not findings:
        lines.append("**Aucun constat** : géométrie, références croisées et "
                     "données fournies cohérentes sur les points contrôlés.")
    else:
        by_cat: Dict[str, List[CoherenceFinding]] = {}
        for f in findings:
            by_cat.setdefault(f.category, []).append(f)
        lines.append(f"**{len(findings)} constat(s)** — aucune donnée n'a "
                     "été inventée pour combler ces points :")
        lines.append("")
        lines.append("| Constat | Objet | Détail |")
        lines.append("|---|---|---|")
        for cat, items in by_cat.items():
            for f in items[:50]:
                lines.append(f"| {cat} | {f.sc_id} | {f.detail} |")
            if len(items) > 50:
                lines.append(f"| {cat} | … | +{len(items) - 50} autre(s) "
                             f"non listée(s) |")
    lines.append("")
    lines.append("> Ces constats portent sur la complétude du modèle interne "
                 "uniquement. AUCUNE conformité réglementaire (BAEL 91 r99 / "
                 "RPS 2011) n'est déclarée ici — voir le menu Réglementation "
                 "(articles marqués A_VALIDER tant que non vérifiés).")
    return "\n".join(lines)
