# -*- coding: utf-8 -*-
"""
architectural_structural/structural_model_builder.py — Phase C (Module 71 §6).

Convertit la proposition architecturale/structurelle dans le modèle interne
CANONIQUE STRUCTCALC (Project CORE + objets étendus).

Distinctions exigées (§6.2) — LIÉES mais NON interchangeables :
  géométrie architecturale ≠ physique ≠ analytique ≠ graphique ≠ ferraillage.

Règles :
  - identifiants stables `SC-*` indépendants de Revit/Robot (§6.1) ;
  - relations internes <-> externes conservées (§6.1) ;
  - hypothèses de liaison VISIBLES et modifiables par l'ingénieur (§6.2) ;
  - toute donnée non fournie reste MISSING (jamais inventée).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.status import DataStatus
from ..core.tracked import TrackedValue, Provenance
from ..core.model import Beam, Slab
from .model_ext import (
    ArchitecturalModel, AnalysisModel,
)
from .geometry_normalization import dist3d as _dist
from .structural_layout_proposal import LayoutProposal, ProposedMember


@dataclass
class BuildReport:
    """Rapport de construction du modèle (traçabilité §6)."""
    nodes_created: int = 0
    columns_created: int = 0
    beams_created: int = 0
    slabs_created: int = 0
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    node_index: Dict[Tuple[int, int, int], str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"nodes": self.nodes_created, "columns": self.columns_created,
                "beams": self.beams_created, "slabs": self.slabs_created,
                "assumptions": list(self.assumptions),
                "warnings": list(self.warnings)}


def build_structural_model(
        model: ArchitecturalModel,
        layout: LayoutProposal,
        level_ref: Optional[str] = None,
        material_ref: Optional[str] = None,
        section_ref: Optional[str] = None,
        ) -> BuildReport:
    """
    Convertit une LayoutProposal en objets CORE (nodes/columns/beams/slabs).

    - Les nœuds sont DÉDUPLICATIFS (même coordonnée => même SC-NODE) ;
    - Les poteaux/poutres référencent start/end SC-NODE (§6.1) ;
    - `material`/`section` restent None si non fournis (MISSING, pas inventé) ;
    - Une hypothèse de liaison par défaut est TRACÉE (§6.2), jamais cachée.
    """
    rep = BuildReport()

    for m in layout.members:
        if m.kind == "column":
            _add_column(model, m, level_ref, material_ref, section_ref, rep)
        elif m.kind == "beam":
            _add_beam(model, m, level_ref, material_ref, section_ref, rep)
        elif m.kind == "slab":
            _add_slab(model, m, level_ref, material_ref, rep)

    # Hypothèse de liaison visible (§6.2)
    rep.assumptions.append(
        "Liaison poteau-poutre/poutre-dalle : nœud commun — hypothèse "
        "modèle à confirmer par l'ingénieur autorisé (§6.2).")
    if material_ref is None:
        rep.warnings.append("Aucun matériau assigné : propriétés MISSING "
                            "(non inventées).")
    if section_ref is None:
        rep.warnings.append("Aucune section assignée : sections MISSING "
                            "(non inventées).")
    return rep


def _key(p) -> Tuple[int, int, int]:
    return (round(p[0] * 1000), round(p[1] * 1000), round(p[2] * 1000))


def _ensure_node(model: ArchitecturalModel, p, rep: BuildReport) -> str:
    """Nœud déduplicatif : même coordonnée -> même SC-NODE (§6.1)."""
    k = _key(p)
    if k in rep.node_index:
        return rep.node_index[k]
    node = model.project.new_node(p[0], p[1], p[2])
    rep.node_index[k] = node.sc_id
    rep.nodes_created += 1
    return node.sc_id


def _add_column(model, m: ProposedMember, level_ref, material_ref,
                section_ref, rep: BuildReport):
    if m.start is None or m.end is None:
        rep.warnings.append("Poteau sans coordonnées complètes : ignoré.")
        return
    n1 = _ensure_node(model, m.start, rep)
    n2 = _ensure_node(model, m.end, rep)
    col = model.project.new_column(n1, n2)
    col.storey = level_ref
    height = abs(m.end[2] - m.start[2])
    col.height = TrackedValue.of(height, "m", DataStatus.CALCULATED,
                                 Provenance.calculated_by("diff_z"))
    # Longueurs de flambement ASSUMÉES = hauteur tant que non justifiées (§4.2)
    col.buckling_length_y = TrackedValue.of(
        height, "m", DataStatus.ASSUMED,
        Provenance.calculated_by("hypothèse ly = h"))
    col.buckling_length_z = TrackedValue.of(
        height, "m", DataStatus.ASSUMED,
        Provenance.calculated_by("hypothèse lz = h"))
    col.material = material_ref
    col.section = section_ref
    rep.columns_created += 1


def _add_beam(model, m: ProposedMember, level_ref, material_ref,
              section_ref, rep: BuildReport):
    if m.start is None or m.end is None:
        rep.warnings.append("Poutre sans coordonnées complètes : ignorée.")
        return
    n1 = _ensure_node(model, m.start, rep)
    n2 = _ensure_node(model, m.end, rep)
    bid = model.project.allocator.new("BEAM")
    beam = Beam(sc_id=bid, start_node=n1, end_node=n2,
                material=material_ref, section=section_ref)
    span = m.span if m.span is not None else _dist(m.start, m.end)
    beam.span = TrackedValue.of(span, "m", DataStatus.CALCULATED,
                                Provenance.calculated_by("distance"))
    model.project.beams[bid] = beam
    rep.beams_created += 1


def _add_slab(model, m: ProposedMember, level_ref, material_ref,
              rep: BuildReport):
    if m.start is None or m.end is None:
        rep.warnings.append("Dalle sans contour complet : ignorée.")
        return
    x1, y1, z = m.start
    x2, y2, _ = m.end
    corners = [(x1, y1, z), (x2, y1, z), (x2, y2, z), (x1, y2, z)]
    node_ids = [_ensure_node(model, c, rep) for c in corners]
    sid = model.project.allocator.new("SLAB")
    slab = Slab(sc_id=sid, node_ids=node_ids, material=material_ref)
    # Épaisseur NON fournie -> MISSING (§10.1 : à déterminer par le calcul)
    slab.thickness = TrackedValue.missing("cm")
    model.project.slabs[sid] = slab
    rep.slabs_created += 1


# ---------------------------------------------------------------------------
# Modèle analytique (§6.2)
# ---------------------------------------------------------------------------

def build_analysis_model(
        model: ArchitecturalModel,
        variant_ref: Optional[str] = None,
        assumptions: Optional[List[str]] = None,
        ) -> AnalysisModel:
    """
    Crée le modèle ANALYTIQUE destiné au solveur (distinct du physique, §6.2).

    Rassemble nœuds + éléments (poteaux + poutres) + hypothèses de liaison.
    Versionné : toute modification produit une nouvelle version et rend les
    résultats antérieurs périmés (Phase I).
    """
    am_id = model.new_id("ANALYSISMODEL")
    node_ids = list(model.project.nodes.keys())
    member_ids = list(model.project.columns.keys()) + \
        list(model.project.beams.keys())
    support_ids = list(model.project.supports.keys())

    ams = [f"Représentation ANALYTIQUE (§6.2) — non interchangeable avec "
           "la géométrie architecturale/physique/graphique."]
    ams.extend(assumptions or [])

    am = AnalysisModel(
        sc_id=am_id, name=f"Modèle analytique v1",
        version=1, node_ids=node_ids, member_ids=member_ids,
        support_ids=support_ids, assumptions=ams,
        source_variant=variant_ref,
        created_from="structural_model_builder")
    model.analysis_models[am_id] = am
    return am


def next_analysis_version(model: ArchitecturalModel,
                          base_ref: str,
                          reason: str = "") -> AnalysisModel:
    """
    Produit une NOUVELLE version du modèle analytique (Phase I / §6.2).

    Incrémenté après une modification : les anciens résultats deviennent
    périmés (marqués par change_impact_dispatcher).
    """
    if base_ref not in model.analysis_models:
        raise KeyError(f"Modèle analytique inconnu : {base_ref}")
    base = model.analysis_models[base_ref]
    am_id = model.new_id("ANALYSISMODEL")
    am = AnalysisModel(
        sc_id=am_id, name=f"Modèle analytique v{base.version + 1}",
        version=base.version + 1,
        node_ids=list(base.node_ids), member_ids=list(base.member_ids),
        support_ids=list(base.support_ids),
        assumptions=list(base.assumptions) + ([reason] if reason else []),
        source_variant=base.source_variant, created_from=reason or "revision")
    model.analysis_models[am_id] = am
    return am
