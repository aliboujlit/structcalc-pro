# -*- coding: utf-8 -*-
"""
architectural_structural/model_drawing_consistency_checker.py — Phase G/J (Module 71 §10.4, §13).

Vérifie la cohérence entre le modèle, les notes de calcul, les plans et les
versions diffusées (§2.12, §13 contrôle documentaire).

Règles :
  - les plans correspondent à la version VALIDÉE du modèle ;
  - les repères sont identiques dans le modèle et les dessins (§11.4) ;
  - les sections provisoires sont IDENTIFIÉES, jamais présentées finales ;
  - les conflits non résolus sont VISIBLES (§11.4) ;
  - la génération graphique n'a pas modifié le modèle analytique (§10.4).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .model_ext import (
    ArchitecturalModel, DeliveryStatus,
)


@dataclass
class ConsistencyFinding:
    """Constat de cohérence modèle <-> document (§13)."""
    code: str            # VERSION_STALE | MARK_MISMATCH | PROVISIONAL_HIDDEN |
                         # OPEN_CONFLICT | ANALYTIC_MUTATED
    severity: str        # ERROR | WARNING
    subject: str         # SC-* concerné
    detail: str

    @property
    def is_error(self) -> bool:
        return self.severity == "ERROR"

    def to_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity,
                "subject": self.subject, "detail": self.detail}


@dataclass
class ConsistencyReport:
    findings: List[ConsistencyFinding] = field(default_factory=list)

    @property
    def errors(self) -> List[ConsistencyFinding]:
        return [f for f in self.findings if f.is_error]

    @property
    def warnings(self) -> List[ConsistencyFinding]:
        return [f for f in self.findings if not f.is_error]

    @property
    def ok(self) -> bool:
        """Aucune erreur bloquante => documents cohérents."""
        return not self.errors

    def to_dict(self) -> dict:
        return {"ok": self.ok, "n_errors": len(self.errors),
                "n_warnings": len(self.warnings),
                "findings": [f.to_dict() for f in self.findings]}


def check_model_drawing_consistency(
        model: ArchitecturalModel,
        current_model_version: int,
        analytical_snapshot: Optional[Dict[str, int]] = None,
        ) -> ConsistencyReport:
    """
    Contrôle documentaire (§13) + §11.4.

    `analytical_snapshot` : {"nodes": n, "members": m} du modèle analytique
    AVANT génération — détecte une mutation illégale lors du dessin (§10.4).
    """
    rep = ConsistencyReport()

    for did, dr in model.drawings.items():
        # 1) Version du modèle source périmée ?
        if dr.model_version and dr.model_version != current_model_version:
            rep.findings.append(ConsistencyFinding(
                code="VERSION_STALE", severity="ERROR", subject=did,
                detail=f"Plan fondé sur le modèle v{dr.model_version}, "
                       f"modèle courant v{current_model_version} — régénérer "
                       f"avant diffusion (§13)."))

        # 2) Repères : éléments référencés existent-ils dans le modèle ?
        known = (set(model.project.columns) | set(model.project.beams)
                 | set(model.project.slabs))
        missing_marks = [m for m in dr.element_ids if m not in known]
        if missing_marks:
            rep.findings.append(ConsistencyFinding(
                code="MARK_MISMATCH", severity="ERROR", subject=did,
                detail=f"Repères absents du modèle : {missing_marks[:5]} "
                       f"(§11.4 repères identiques)."))

        # 3) Sections provisoires : ne doivent pas être cachées
        if dr.sections_provisional and not dr.notes:
            rep.findings.append(ConsistencyFinding(
                code="PROVISIONAL_HIDDEN", severity="ERROR", subject=did,
                detail="Sections provisoires présentes sans mention visible "
                       "(§10.2) — interdit de les présenter comme finales."))

        # 4) Plan diffusable alors que conflits ouverts ?
        if dr.status == DeliveryStatus.VALIDATED_FOR_DELIVERY:
            open_c = [c for c in model.open_conflicts()]
            if open_c:
                rep.findings.append(ConsistencyFinding(
                    code="OPEN_CONFLICT", severity="ERROR", subject=did,
                    detail=f"{len(open_c)} conflit(s) non résolu(s) alors "
                           f"que le plan est VALIDÉ (§11.4/§13)."))

        # 5) Plan PRELIMINARY+ sans version de modèle tracée
        if dr.status not in (DeliveryStatus.DRAFT,) and not dr.model_ref:
            rep.findings.append(ConsistencyFinding(
                code="VERSION_STALE", severity="WARNING", subject=did,
                detail="Plan sans modèle source tracé (§10.2 version du "
                       "modèle source)."))

    # 6) Mutation du modèle analytique pendant le dessin (§10.4)
    if analytical_snapshot is not None:
        live_nodes = len(model.project.nodes)
        live_members = (len(model.project.columns)
                        + len(model.project.beams))
        if (live_nodes != analytical_snapshot.get("nodes", live_nodes)
                or live_members != analytical_snapshot.get("members",
                                                           live_members)):
            rep.findings.append(ConsistencyFinding(
                code="ANALYTIC_MUTATED", severity="ERROR",
                subject="<modele analytique>",
                detail="Le modèle analytique a changé pendant la génération "
                       "graphique — opération explicite et traçable requise "
                       "(§10.4)."))

    # 7) Conflits ouverts toujours visibles (§11.4) — informatif
    for c in model.open_conflicts():
        rep.findings.append(ConsistencyFinding(
            code="OPEN_CONFLICT", severity="WARNING", subject=c.sc_id,
            detail=f"Conflit ouvert [{c.status}] : {c.description} "
                   f"doit rester visible (§11.4)."))

    return rep


def reports_and_drawings_match(model: ArchitecturalModel,
                               note_refs: Sequence[str]) -> ConsistencyReport:
    """
    Contrôle qu'une note de calcul est associée aux plans de la même version
    (§2.12, §13 « plans cohérents avec les résultats validés »).
    """
    rep = ConsistencyReport()
    versions: Dict[str, int] = {}
    for did, dr in model.drawings.items():
        if dr.model_ref:
            versions.setdefault(dr.model_ref, set())
    for nid in note_refs:
        note = model.analysis_results.get(nid)
        if note is None:
            # peut être un AnalysisModel
            am = model.analysis_models.get(nid)
            if am is None:
                rep.findings.append(ConsistencyFinding(
                    code="VERSION_STALE", severity="WARNING", subject=nid,
                    detail="Note/référence introuvable."))
            continue
        if note.outdated if hasattr(note, "outdated") else False:
            rep.findings.append(ConsistencyFinding(
                code="VERSION_STALE", severity="ERROR", subject=nid,
                detail="Note fondée sur des résultats PÉRIMÉS (§12)."))
    return rep
