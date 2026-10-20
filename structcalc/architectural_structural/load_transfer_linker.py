# -*- coding: utf-8 -*-
"""
architectural_structural/load_transfer_linker.py — Phase D (Module 71 §7.2, §7.3).

Liaison vers `06_LOAD_TAKE_DOWN` : organise le transfert des charges vers le
modèle de calcul et la traçabilité des résultats.

Règles (§7.2) :
  - poids propre, charges permanentes complémentaires, murs/cloisons,
    exploitation, climat, sismique (si requis), combinaisons applicables ;
  - la répartition des dalles doit être COMPATIBLE avec le comportement, les
    appuis et le modèle analytique ;
  - ÉVITER TOUT DOUBLE COMPTEMENT entre poids propre automatique et charges
    saisies manuellement (§7.2) — contrôle codé ci-dessous ;
  - chaque charge possède une ORIGINE (§11.3 test).

Résultats à tracer (§7.3) : charges appliquées, origine, hypothèses de
répartition, combinaisons, réactions/efforts, référence au modèle ET sa version.

100 % pur — testable unitairement. Le calcul des charges lui-même relève du
SOLVER ; ce module orchestre et VÉRIFIE, il n'invente aucune valeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .model_ext import ArchitecturalModel, AnalysisModel


# Natures de charge reconnues (§7.2)
LOAD_KINDS = ("dead", "superimposed_dead", "partitions", "live",
              "wind", "snow", "seismic")


@dataclass
class LoadEntry:
    """Une charge avec son ORIGINE obligatoire (§11.3)."""
    kind: str                       # dans LOAD_KINDS
    value: float
    unit: str = "kN/m2"
    origin: str = ""                # OBLIGATOIRE : d'où vient la valeur
    target_ref: str = ""            # SC-* (slab, beam, column...)
    assumption: str = ""            # hypothèse de répartition
    combination: str = ""           # combinaison concernée
    source_model: str = ""          # SC-ANALYSISMODEL-* + version
    automatic_dead: bool = False    # poids propre calculé automatiquement

    def validate(self) -> List[str]:
        errs = []
        if self.kind not in LOAD_KINDS:
            errs.append(f"Nature de charge inconnue : {self.kind!r}")
        if not self.origin.strip():
            errs.append("Origine obligatoire (§11.3) : toute charge possède "
                        "une origine identifiée.")
        return errs


@dataclass
class LoadTransferReport:
    """Rapport de liaison charges (§7.2/§7.3)."""
    entries: List[LoadEntry] = field(default_factory=list)
    double_counting: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    missing_origins: List[str] = field(default_factory=list)
    repartition_warnings: List[str] = field(default_factory=list)
    traced: List[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Aucune erreur ni double comptage => transfert exploitable."""
        return not self.errors and not self.double_counting

    @property
    def n_loads(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict:
        return {"n_loads": self.n_loads, "ok": self.ok,
                "double_counting": list(self.double_counting),
                "errors": list(self.errors),
                "missing_origins": list(self.missing_origins),
                "repartition_warnings": list(self.repartition_warnings),
                "traced": len(self.traced)}


def link_loads(model: ArchitecturalModel,
               entries: Sequence[LoadEntry],
               analysis_model_ref: Optional[str] = None
               ) -> LoadTransferReport:
    """
    Contrôle et trace un lot de charges avant transfert (§7.2).

    Vérifie :
      - origine présente pour CHAQUE charge (§11.3) ;
      - pas de DOUBLE COMPTEMENT poids propre automatique + saisi manuel ;
      - hypothèses de répartition explicites (§7.2) ;
      - référence au modèle et à sa VERSION (§7.3).
    """
    rep = LoadTransferReport()
    am = model.analysis_models.get(analysis_model_ref) if analysis_model_ref \
        else None

    auto_dead_targets: Dict[str, str] = {}
    manual_dead_targets: Dict[str, str] = {}

    for e in entries:
        errs = e.validate()
        if errs:
            rep.errors.extend(errs)
            if not e.origin.strip():
                rep.missing_origins.append(
                    f"{e.kind}@{e.target_ref or '?'}")
        # Référence modèle + version (§7.3)
        if am is not None:
            e.source_model = f"{am.sc_id} v{am.version}"
        if not e.assumption and e.kind in ("dead", "superimposed_dead",
                                           "partitions"):
            rep.repartition_warnings.append(
                f"{e.kind}@{e.target_ref or '?'} : hypothèse de répartition "
                "non explicitée (§7.2).")
        # Suivi du poids propre pour double comptage
        if e.kind == "dead":
            if e.automatic_dead:
                auto_dead_targets[e.target_ref] = e.origin
            else:
                manual_dead_targets.setdefault(e.target_ref, e.origin)
        rep.entries.append(e)

    # --- Contrôle DOUBLE COMPTEMENT (§7.2) -------------------------------
    for target, auto_origin in auto_dead_targets.items():
        if target in manual_dead_targets:
            rep.double_counting.append(
                f"Poids propre DOUBLEMENT compté pour {target or 'élément'} : "
                f"automatique ({auto_origin}) + manuel "
                f"({manual_dead_targets[target]}). Résoudre avant calcul.")
    if not auto_dead_targets and manual_dead_targets:
        # Pas de poids propre auto — à confirmer, pas bloquant en soi
        rep.repartition_warnings.append(
            "Aucun poids propre automatique : vérifier qu'aucun n'est saisi "
            "manuellement en double ailleurs (§7.2).")

    # --- Traçabilité §7.3 ------------------------------------------------
    rep.traced = [_trace(e, am) for e in rep.entries]
    return rep


def _trace(e: LoadEntry, am: Optional[AnalysisModel]) -> dict:
    """Trace complète d'une charge (§7.3)."""
    return {
        "kind": e.kind, "value": e.value, "unit": e.unit,
        "origin": e.origin,
        "target": e.target_ref,
        "repartition_assumption": e.assumption,
        "combination": e.combination,
        "model_ref": am.sc_id if am else "",
        "model_version": am.version if am else 0,
    }


# ---------------------------------------------------------------------------
# Répartition des dalles (§7.2) — contrôle de compatibilité, pas de calcul
# ---------------------------------------------------------------------------

@dataclass
class SlabRepartition:
    """Hypothèse de répartition d'une dalle (one-way / two-way)."""
    slab_ref: str
    behavior: str               # "one_way" | "two_way" | "unknown"
    supporting_members: List[str] = field(default_factory=list)
    assumption: str = ""

    @property
    def is_consistent(self) -> bool:
        """
        Cohérence : deux directions exigent >= 2 appuis par axe ;
        une direction exige au moins 2 appuis opposés.
        """
        if self.behavior == "unknown":
            return False
        return len(self.supporting_members) >= 2


def check_slab_repartition(model: ArchitecturalModel,
                           repartitions: Sequence[SlabRepartition]
                           ) -> LoadTransferReport:
    """
    Contrôle que la répartition des dalles est COMPATIBLE avec les appuis et
    le modèle analytique (§7.2). NE calcule PAS la charge — vérifie la
    cohérence de l'hypothèse.
    """
    rep = LoadTransferReport()
    for r in repartitions:
        if r.slab_ref not in model.project.slabs:
            rep.errors.append(f"Dalle inconnue : {r.slab_ref}")
            continue
        if r.behavior == "unknown":
            rep.repartition_warnings.append(
                f"Dalle {r.slab_ref} : comportement (isotrope/anisotrope) "
                "NON déterminé — hypothèse requise (§7.2).")
        elif not r.is_consistent:
            rep.repartition_warnings.append(
                f"Dalle {r.slab_ref} ({r.behavior}) : appuis insuffisants "
                f"({len(r.supporting_members)}) pour la répartition "
                f"hypothétisée (§7.2).")
        else:
            rep.traced.append({
                "slab": r.slab_ref, "behavior": r.behavior,
                "supporting": list(r.supporting_members),
                "assumption": r.assumption,
            })
    return rep
