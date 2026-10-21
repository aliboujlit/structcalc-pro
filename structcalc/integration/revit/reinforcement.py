# -*- coding: utf-8 -*-
"""
integration/revit/reinforcement.py — Armatures Revit depuis plans ferraillage.

Construit les RebarDto conformes au DTO add-in à partir de
`reporting.plan_ferraillage.ReinforcementPlan` (proposition A_VALIDER).

RÈGLES D'HONNÊTETÉ :
  - Chaque barre porte `layer` explicite ("Longitudinal" / "Stirrups").
  - `position` = 0.5 (axe) — enrobage NON fourni -> l'add-in place à l'axe
    et note "positionnement transversal à ajuster manuellement".
  - `count` = nombre de barres demandées — l'add-in crée 1 barre à l'axe
    et note "Count=N non appliqué sans enrobage".
  - Diamètre en mm (int) — norme HA usuelle (Ø12..Ø32).
  - Aucune armature inventée : seulement si ReinforcementPlan existe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from ...reporting.plan_ferraillage import ReinforcementPlan


@dataclass
class RebarSetDto:
    """
    Un ensemble d'armatures pour UN élément Revit (poteau/poutre/semelle).
    Conforme à BarChangeDto.Rebars (liste de RebarDto).
    """
    element_sc_id: str              # SC-ID de la barre/poteau
    rebars: List[Dict[str, Any]]    # liste de RebarDto


def build_rebar_sets(
    project: Any,
    reinforcement_plans: Dict[str, ReinforcementPlan]
) -> List[RebarSetDto]:
    """
    Construit la liste des RebarSetDto pour tous les éléments
    qui ont un plan de ferraillage.

    `reinforcement_plans` : {column_sc_id: ReinforcementPlan}
    """
    sets = []
    for sc_id, plan in reinforcement_plans.items():
        if not isinstance(plan, ReinforcementPlan):
            continue
        rebars = _plan_to_rebar_dtos(plan)
        if rebars:
            sets.append(RebarSetDto(element_sc_id=sc_id, rebars=rebars))
    return sets


def _plan_to_rebar_dtos(plan: ReinforcementPlan) -> List[Dict[str, Any]]:
    """Convertit un ReinforcementPlan en liste de RebarDto (DTO add-in)."""
    dtos = []

    # Barres longitudinales
    if plan.bar_count >= 2 and plan.bar_d_mm >= 6:
        dtos.append({
            "barId": 0,
            "diameterMm": int(round(plan.bar_d_mm)),
            "count": int(plan.bar_count),
            "position": 0.5,
            "layer": "Longitudinal",
        })

    # Cadres (stirrups)
    if plan.stirrup_d_mm >= 6:
        dtos.append({
            "barId": 0,
            "diameterMm": int(round(plan.stirrup_d_mm)),
            "count": 1,  # 1 armature fermée par position (l'add-in ne répartit pas)
            "position": 0.5,
            "layer": "Stirrups",
        })

    return dtos


def apply_reinforcement_to_revit(
    project: Any,
    reinforcement_plans: Dict[str, ReinforcementPlan],
    families_map_path: str,
    pipe_client: Optional[Any] = None
) -> Any:
    """
    Envoie UNIQUEMENT les armatures vers Revit (suppose sections déjà mappées).

    Utilise le même pipe client que write_model_to_revit.
    """
    from .writer import build_apply_changes_request, _scid_to_revit_id
    from .families import FamiliesMap
    from .protocol import RevitPipeClient, RevitPipeError, RevitProtocolError

    report_notes = []
    client = pipe_client
    own_client = False

    try:
        fmap = FamiliesMap.load(families_map_path)
        report_notes.append(f"Mapping familles : {len(fmap.sections)} sections")

        # Construire barChanges UNIQUEMENT avec rebars (pas de newSection)
        bar_changes = []
        for sc_id, plan in reinforcement_plans.items():
            fmap_entry = fmap.get(_get_section_name(project, _get_column_section(project, sc_id)))
            if fmap_entry is None:
                report_notes.append(f"{sc_id} : section non mappée -> armatures ignorées")
                continue

            rebars = _plan_to_rebar_dtos(plan)
            if not rebars:
                continue

            bar_changes.append({
                "elementId": _scid_to_revit_id(sc_id),
                "newSectionName": fmap_entry.type_name,
                "newSection": {},  # pas de changement de section
                "rebars": rebars,
            })

        if not bar_changes:
            return {"ok": False, "notes": ["Aucune armature à envoyer (sections non mappées ou plans absents)"]}

        if client is None:
            client = RevitPipeClient()
            own_client = True
            client.connect()

        request = {"barChanges": bar_changes, "nodeChanges": []}
        result = client.apply_changes(request)

        return {
            "ok": True,
            "bars_processed": len(bar_changes),
            "rebars_created": result.get("rebarsCreated", 0),
            "notes": report_notes + result.get("notes", []),
        }

    except (RevitPipeError, RevitProtocolError, FileNotFoundError) as exc:
        return {"ok": False, "error": str(exc), "notes": report_notes}
    except Exception as exc:
        return {"ok": False, "error": f"Inattendu : {exc}", "notes": report_notes}
    finally:
        if own_client and client:
            client.close()


def _get_section_name(project: Any, section_sc_id: str) -> Optional[str]:
    sections = getattr(project, "sections", {}) or {}
    sec = sections.get(section_sc_id)
    return sec.name if sec and sec.name else None


def _get_column_section(project: Any, column_sc_id: str) -> Optional[str]:
    columns = getattr(project, "columns", {}) or {}
    col = columns.get(column_sc_id)
    return col.section if col else None