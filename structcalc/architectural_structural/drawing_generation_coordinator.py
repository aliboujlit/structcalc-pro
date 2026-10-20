# -*- coding: utf-8 -*-
"""
architectural_structural/drawing_generation_coordinator.py — Phase G (Module 71 §10).

Génère les plans de COFFRAGE (et distingue ferraillage) à partir d'un modèle
structurel cohérent ET d'un état de validation EXPLICITE.

Règles (§10) :
  - les plans sont produits à partir d'un modèle validé ; un plan n'est JAMAIS
    validé parce qu'il a été généré automatiquement (§17) ;
  - les sections non calculées portent un statut PROVISOIRE visible (§10.2) ;
  - coffrage (géométrie béton) ≠ ferraillage (armatures) — cohérents mais non
    confondus (§10.3) ;
  - la génération graphique NE MODIFIE PAS le modèle analytique sans opération
    explicite et traçable (§10.4).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .model_ext import (
    ArchitecturalModel, Drawing, DeliveryStatus, Level,
)


# Types de plans du bâtiment de référence R+3 (§10.1)
R3_DRAWING_SET = [
    ("formwork", "Plan de coffrage — niveau des fondations"),
    ("formwork", "Plan de coffrage — RDC"),
    ("formwork", "Plan de coffrage — R+1"),
    ("formwork", "Plan de coffrage — R+2"),
    ("formwork", "Plan de coffrage — R+3"),
    ("formwork", "Plan de toiture et terrasses"),
    ("section", "Coupes structurales"),
    ("detail", "Détails particuliers"),
    ("schedule", "Tableaux des poteaux et poutres"),
    ("schedule", "Nomenclatures et repères"),
]


@dataclass
class DrawingContent:
    """Contenu minimal d'un plan (§10.2)."""
    drawing_ref: str
    kind: str
    title: str
    level_ref: Optional[str]
    status: DeliveryStatus
    model_ref: Optional[str]
    model_version: int
    units: str
    scale: str
    axes: List[str] = field(default_factory=list)
    levels: List[str] = field(default_factory=list)
    element_marks: List[str] = field(default_factory=list)
    provisional_sections: List[str] = field(default_factory=list)
    openings: List[str] = field(default_factory=list)
    validation_status: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def is_provisional(self) -> bool:
        return (bool(self.provisional_sections)
                or self.status in (DeliveryStatus.DRAFT,
                                   DeliveryStatus.PRELIMINARY))

    def to_dict(self) -> dict:
        return {
            "ref": self.drawing_ref, "kind": self.kind, "title": self.title,
            "level": self.level_ref, "status": self.status.value,
            "model_ref": self.model_ref, "model_version": self.model_version,
            "units": self.units, "scale": self.scale,
            "axes": list(self.axes), "elements": len(self.element_marks),
            "provisional_sections": list(self.provisional_sections),
            "openings": list(self.openings),
            "is_provisional": self.is_provisional,
            "validation_status": self.validation_status,
            "warnings": list(self.warnings),
        }


def generate_formwork_drawing(
        model: ArchitecturalModel,
        level_ref: Optional[str],
        title: str,
        model_ref: Optional[str] = None,
        model_version: int = 0,
        units: str = "cm",
        scale: str = "1:100",
        ) -> Drawing:
    """
    Crée un plan de coffrage (§10.1/§10.2) RATTACHÉ à une version de modèle.

    - Les sections non calculées sont marquées `sections_provisional` ;
    - statut initial DRAFT (aucune diffusion automatique) ;
    - NE MUTUE PAS le modèle analytique (§10.4).
    """
    dr = model.new_drawing(kind="formwork", level_ref=level_ref,
                           model_ref=model_ref,
                           model_version=model_version)
    dr.name = title or f"Plan de coffrage {level_ref or ''}"
    dr.format = "PDF"

    # Sections provisoires : poteaux/poutres du modèle SANS section assignée
    provisional = _provisional_sections(model, level_ref)
    dr.sections_provisional = provisional

    # Repères : éléments du niveau
    dr.element_ids = _level_elements(model, level_ref)

    # Avertissement §10.2 : sections non calculées visibles
    if provisional:
        dr.notes = (f"{len(provisional)} section(s) non calculée(s) — "
                    f"statut PROVISOIRE visible (§10.2).")
    return dr


def generate_drawing_set(model: ArchitecturalModel,
                         model_ref: Optional[str] = None,
                         model_version: int = 0,
                         include_foundation: bool = True) -> List[Drawing]:
    """
    Génère la série de plans du bâtiment de référence R+3 (§10.1).

    Les fondations ne sont JAMAIS déduites d'une trame de poteaux (§10.1) :
    si aucune géotechnique n'est fournie, le plan de fondation porte un
    avertissement explicite.
    """
    out: List[Drawing] = []
    level_items = sorted(model.levels.items(),
                         key=lambda kv: (kv[1].index, kv[1].sc_id))

    for kind, title in R3_DRAWING_SET:
        if kind == "schedule":
            # Tableaux/nomenclatures : plans non géométriques
            dr = model.new_drawing(kind="schedule", level_ref=None,
                                   model_ref=model_ref,
                                   model_version=model_version)
            dr.name = title
            dr.notes = "Nomenclature générée depuis le modèle — non diffusable "
            dr.notes += "sans validation (§17)."
            out.append(dr)
            continue
        if kind == "section" or kind == "detail":
            dr = model.new_drawing(kind=kind, level_ref=None,
                                   model_ref=model_ref,
                                   model_version=model_version)
            dr.name = title
            dr.sections_provisional = _provisional_sections(model, None)
            # La mention provisoire DOIT être visible (§10.2) — sinon le
            # contrôle documentaire signale PROVISIONAL_HIDDEN.
            if dr.sections_provisional:
                dr.notes = (f"{len(dr.sections_provisional)} section(s) non "
                            f"calculée(s) — statut PROVISOIRE (§10.2).")
            out.append(dr)
            continue
        if "fondations" in title.lower():
            if not include_foundation:
                continue
            dr = model.new_drawing(kind="formwork", level_ref=None,
                                   model_ref=model_ref,
                                   model_version=model_version)
            dr.name = title
            dr.notes = ("Fondations : NE PAS déduire d'une trame seule — "
                        "réactions + étude géotechnique requises (§10.1).")
            out.append(dr)
            continue
        if "toiture" in title.lower():
            dr = model.new_drawing(kind="formwork", level_ref=None,
                                   model_ref=model_ref,
                                   model_version=model_version)
            dr.name = title
            out.append(dr)
            continue
        # Plans de niveau : associer au niveau dont le titre contient le nom
        target = _match_level(model, title)
        dr = generate_formwork_drawing(
            model, target.sc_id if target else None, title,
            model_ref=model_ref, model_version=model_version)
        out.append(dr)
    return out


def drawing_content(model: ArchitecturalModel, drawing_ref: str) -> DrawingContent:
    """Construit le contenu détaillé d'un plan (§10.2)."""
    dr = model.drawings[drawing_ref]
    axes = [a.label for a in model.axes.values() if a.label]
    levels = [lv.name for lv in model.levels.values()]
    openings = [o.sc_id for o in model.openings.values()
                if not dr.level_ref or o.level_ref == dr.level_ref]
    warnings: List[str] = []
    if dr.sections_provisional:
        warnings.append("Sections non calculées : statut provisoire "
                        "visible (§10.2).")
    if dr.status not in (DeliveryStatus.VALIDATED_FOR_DELIVERY,):
        warnings.append(f"Plan en statut {dr.status.value} : NON diffusable "
                        "comme définitif (§13).")
    return DrawingContent(
        drawing_ref=dr.sc_id, kind=dr.kind, title=dr.name,
        level_ref=dr.level_ref, status=dr.status,
        model_ref=dr.model_ref, model_version=dr.model_version,
        units="cm", scale="1:100",
        axes=axes, levels=levels, element_marks=list(dr.element_ids),
        provisional_sections=list(dr.sections_provisional),
        openings=openings, validation_status=dr.status.value,
        warnings=warnings)


def is_formwork_vs_rebar(drawing_ref_kind: str) -> dict:
    """
    Rappel de distinction coffrage / ferraillage (§10.3) — les deux documents
    doivent être cohérents mais NON confondus.
    """
    return {
        "formwork": {
            "content": "géométrie en béton : dimensions, niveaux, sections, "
                       "appuis, ouvertures",
            "depends_on": "modèle structurel validé",
        },
        "rebar": {
            "content": "armatures, ancrages, recouvrements, détails de mise "
                       "en œuvre",
            "depends_on": "calculs + règles constructives applicables",
        },
        "rule": "Cohérents mais non confondus (§10.3).",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provisional_sections(model: ArchitecturalModel,
                          level_ref: Optional[str]) -> List[str]:
    """Éléments sans section assignée => sections à statut provisoire."""
    out: List[str] = []
    for cid, col in model.project.columns.items():
        if level_ref and col.storey and col.storey != level_ref:
            continue
        if not col.section:
            out.append(cid)
    for bid, bm in model.project.beams.items():
        if not bm.section:
            out.append(bid)
    return out


def _level_elements(model: ArchitecturalModel,
                    level_ref: Optional[str]) -> List[str]:
    out: List[str] = []
    if level_ref:
        out.extend(c for c, col in model.project.columns.items()
                   if col.storey == level_ref)
    else:
        out.extend(model.project.columns.keys())
        out.extend(model.project.beams.keys())
    return out


def _match_level(model: ArchitecturalModel, title: str) -> Optional[Level]:
    t = title.upper()
    for lv in model.levels.values():
        if lv.name and lv.name.upper() in t:
            return lv
    return None
