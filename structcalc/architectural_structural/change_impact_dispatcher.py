# -*- coding: utf-8 -*-
"""
architectural_structural/change_impact_dispatcher.py — Phase I (Module 71 §12).

Détermine les conséquences d'une modification architecturale ou structurelle
(ex. déplacement du poteau `P-B2`) et propage l'invalidation.

Règles (§12) :
  - les résultats affectés sont marqués PÉRIMÉS (OUTDATED) jusqu'au recalcul ;
  - le moteur NE SUPPOSE PAS que seuls les éléments directement connectés sont
    affectés : la propagation dépend du modèle et de la nature du changement ;
  - chaque impact est tracé (éléments, calculs invalidés, documents à
    régénérer) — spec §15 traçabilité.

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from .model_ext import (
    ArchitecturalModel, AnalysisResult, ConflictKind,
)


#: Natures de changement reconnues (§12)
CHANGE_MOVE_COLUMN = "MOVE_COLUMN"
CHANGE_REMOVE_COLUMN = "REMOVE_COLUMN"
CHANGE_CHANGE_SECTION = "CHANGE_SECTION"
CHANGE_CHANGE_SPAN = "CHANGE_SPAN"
CHANGE_MOVE_SUPPORT = "MOVE_SUPPORT"
CHANGE_ARCH_OPENING = "ARCH_OPENING"
CHANGE_GENERIC = "GENERIC"


@dataclass
class ImpactReport:
    """
    Rapport d'impact d'une modification (§12, §15).

    - `affected_elements` : SC-* potentiellement affectés ;
    - `invalidated_results` : SC-RESULT-* marqués périmés ;
    - `documents_to_regenerate` : SC-DRAWING-* à régénérer ;
    - `geotechnical` : fondations concernées (§12) ;
    - `stability` : stabilité globale à reconsidérer quand pertinent.
    """
    change_type: str = ""
    changed_ref: str = ""
    reason: str = ""
    actor: str = ""
    affected_elements: List[str] = field(default_factory=list)
    invalidated_results: List[str] = field(default_factory=list)
    documents_to_regenerate: List[str] = field(default_factory=list)
    conflicts_opened: List[str] = field(default_factory=list)
    needs_global_reanalysis: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def has_impact(self) -> bool:
        return bool(self.affected_elements or self.invalidated_results
                    or self.documents_to_regenerate)

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type,
            "changed_ref": self.changed_ref,
            "reason": self.reason, "actor": self.actor,
            "affected_elements": list(self.affected_elements),
            "invalidated_results": list(self.invalidated_results),
            "documents_to_regenerate": list(self.documents_to_regenerate),
            "conflicts_opened": list(self.conflicts_opened),
            "needs_global_reanalysis": self.needs_global_reanalysis,
            "notes": list(self.notes),
        }


def dispatch_change(
        model: ArchitecturalModel,
        change_type: str,
        changed_ref: str,
        reason: str = "",
        actor: str = "",
        ) -> ImpactReport:
    """
    Propage l'impact d'un changement (§12).

    1. Identifie les éléments affectés (connexions réelles du modèle) ;
    2. Ajoute les dépendances IMPLICITES (fondations, stabilité, documents) ;
    3. Marque les résultats PÉRIMÉS (outdated) jusqu'au recalcul ;
    4. Ouvre un conflit DOCUMENTAIRE pour chaque plan à régénérer ;
    5. Trace dans une Revision (§15).

    Une modification SANS motif est refusée (traçabilité §15).
    """
    if not reason.strip():
        raise ValueError(
            "Modification refusée : motif obligatoire (§15 traçabilité). "
            "Aucune modification silencieuse.")

    rep = ImpactReport(change_type=change_type, changed_ref=changed_ref,
                       reason=reason, actor=actor)

    # 1) Éléments directement connectés (via le modèle)
    direct = _directly_connected(model, changed_ref)
    rep.affected_elements.extend(direct)

    # 2) Dépendances implicites — propagation au-delà du direct (§12)
    implicit = _implicit_dependencies(model, change_type, changed_ref)
    for i in implicit:
        if i not in rep.affected_elements:
            rep.affected_elements.append(i)

    # 3) Nature du changement -> besoins particuliers
    if change_type in (CHANGE_MOVE_COLUMN, CHANGE_REMOVE_COLUMN,
                       CHANGE_MOVE_SUPPORT, CHANGE_CHANGE_SPAN):
        rep.needs_global_reanalysis = True
        rep.notes.append("Changement influençant rigidité/stabilité : "
                         "recalcul global probable (§10.4, §12).")

    # 4) Invalider les résultats (PÉRIMÉS jusqu'au recalcul, §12)
    for res in model.analysis_results.values():
        if res.outdated:
            continue
        if not res.available:
            continue
        # Tout résultat disponible devient périmé si le modèle change
        res.outdated = True
        rep.invalidated_results.append(res.sc_id)
    if rep.invalidated_results:
        rep.notes.append(f"{len(rep.invalidated_results)} résultat(s) marqué(s) "
                         f"PÉRIMÉ (OUTDATED) jusqu'au recalcul (§12).")

    # 5) Documents à régénérer + conflit documentaire ouvert
    for dr in model.drawings.values():
        rep.documents_to_regenerate.append(dr.sc_id)
        cf = model.new_conflict(
            ConflictKind.DOCUMENTARY,
            description=(f"Plan {dr.sc_id} à régénérer après modification "
                         f"{change_type} sur {changed_ref}."),
            level_ref=dr.level_ref, element_ids=[dr.sc_id, changed_ref],
            source="change_impact_dispatcher")
        cf.rule_ref = "§9.1/§12 conflit documentaire (modif non intégrée)"
        rep.conflicts_opened.append(cf.sc_id)

    # 6) Fondations (§12) — si des fondations existent, elles sont concernées
    if getattr(model.project, "foundations", None):
        rep.notes.append("Fondations concernées à reconsidérer (§12).")

    # 7) Traçabilité (§15)
    _trace_revision(model, rep)
    return rep


def _directly_connected(model: ArchitecturalModel,
                        ref: str) -> List[str]:
    """Éléments directement liés à `ref` (nœuds/poteaux/poutres)."""
    proj = model.project
    out: Set[str] = set()

    # Si c'est un poteau : ses 2 nœuds -> les autres membres sur ces nœuds
    if ref in proj.columns:
        col = proj.columns[ref]
        for n in (col.start_node, col.end_node):
            if not n:
                continue
            out.update(_members_at_node(proj, n))
        out.add(ref)
    elif ref in proj.beams:
        bm = proj.beams[ref]
        for n in (bm.start_node, bm.end_node):
            if not n:
                continue
            out.update(_members_at_node(proj, n))
        out.add(ref)
    elif ref in proj.nodes:
        out.update(_members_at_node(proj, ref))
    elif ref in proj.supports:
        out.add(ref)
    else:
        out.add(ref)
    return sorted(out)


def _members_at_node(proj, node_id: str) -> List[str]:
    out = []
    for cid, c in proj.columns.items():
        if node_id in (c.start_node, c.end_node):
            out.append(cid)
    for bid, b in proj.beams.items():
        if node_id in (b.start_node, b.end_node):
            out.append(bid)
    return out


def _implicit_dependencies(model: ArchitecturalModel, change_type: str,
                           ref: str) -> List[str]:
    """
    Dépendances IMPLICITES (§12) : le moteur ne suppose PAS que seuls les
    éléments directement connectés sont affectés.
    """
    out: Set[str] = set()
    # Tous les poteaux/poutres du modèle sont potentiellement concernés si
    # la rigidité/stabilité change (changement de portée, d'appui, de poteau)
    if change_type in (CHANGE_MOVE_COLUMN, CHANGE_REMOVE_COLUMN,
                       CHANGE_MOVE_SUPPORT, CHANGE_CHANGE_SPAN,
                       CHANGE_CHANGE_SECTION):
        out.update(model.project.columns.keys())
        out.update(model.project.beams.keys())
        out.update(model.project.supports.keys())
    # Changement architectural (ouverture) : éléments du même niveau
    if change_type == CHANGE_ARCH_OPENING:
        out.update(model.arch_elements.keys())
    return sorted(out)


def _trace_revision(model: ArchitecturalModel, rep: ImpactReport) -> str:
    """Enregistre une Revision (§15) et retourne son SC-*."""
    import datetime as _dt
    from .model_ext import Revision
    rid = model.new_id("REVISION")
    rev = Revision(
        sc_id=rid, subject_ref=rep.changed_ref,
        subject_kind=rep.change_type,
        actor=rep.actor, reason=rep.reason,
        timestamp=_dt.datetime.now().isoformat(timespec="seconds"),
        invalidated_results=list(rep.invalidated_results),
        regenerated_docs=list(rep.documents_to_regenerate))
    model.revisions[rid] = rev
    rep.notes.append(f"Revision {rid} enregistrée (§15).")
    return rid


def stale_results(model: ArchitecturalModel) -> List[AnalysisResult]:
    """Résultats périmés (§12) — à ne JAMAIS présenter comme valables."""
    return [r for r in model.analysis_results.values() if r.outdated]
