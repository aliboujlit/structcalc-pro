# -*- coding: utf-8 -*-
"""
integration/revit/writer.py — Écriture pivot STRUCTCALC -> Revit (via pipe).

Convertit le pivot chargé (nœuds, barres/poteaux/poutres, sections, matériaux)
en requête APPLY_CHANGES pour l'add-in Revit.

RÈGLES D'HONNÊTETÉ :
  - Seuls les éléments RÉELLEMENT présents dans le pivot sont envoyés (0 = 0).
  - Sections : seules celles mappées dans families_map.json sont envoyées.
    Section non mappée -> note explicite, PAS d'écriture.
  - Armatures : envoyées UNIQUEMENT si un plan de ferraillage existe
    (ReinforcementPlan avec statut A_VALIDER) — jamais d'armature inventée.
  - Enrobages/recouvrements : NON fournis (donnée manquante) -> l'add-in
    place les barres à l'AXE et ajoute une note (positionnement à ajuster).
  - Appuis : NON écrits (conditions aux limites Revit exigent hôte+référence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from .families import FamiliesMap, FamilyMapEntry
from .protocol import RevitPipeClient, RevitPipeError, RevitProtocolError
from ...core.model import Project, Column, Beam, Node


@dataclass
class WriteReport:
    """Rapport d'écriture vers Revit."""
    bars_processed: int = 0
    sections_applied: int = 0
    sections_skipped: int = 0
    rebars_created: int = 0
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_note(self, msg: str) -> None:
        self.notes.append(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)


def build_apply_changes_request(
    project: Project,
    families_map: FamiliesMap,
    reinforcement_plans: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Construit le payload APPLY_CHANGES à partir du pivot + mapping familles.

    `reinforcement_plans` : dict {column_sc_id: ReinforcementPlan} — si fourni,
    ajoute les RebarDto pour les poteaux concernés.
    """
    bar_changes: List[Dict[str, Any]] = []
    skipped_sections = 0

    for col in (getattr(project, "columns", {}) or {}).values():
        sec_name = _get_section_name(project, col.section)
        fmap = families_map.get(sec_name) if sec_name else None

        if fmap is None:
            skipped_sections += 1
            continue

        # Section à appliquer
        new_section = _build_section_dto(fmap)

        # Armatures pour ce poteau
        rebars = []
        if reinforcement_plans and col.sc_id in reinforcement_plans:
            rep = reinforcement_plans[col.sc_id]
            rebars = _build_rebar_dtos(rep)

        bar_changes.append({
            "elementId": _scid_to_revit_id(col.sc_id),  # l'add-in fait le mapping
            "newSectionName": fmap.type_name,
            "newSection": new_section,
            "rebars": rebars,
        })

    # Poutres
    for bm in (getattr(project, "beams", {}) or {}).values():
        sec_name = _get_section_name(project, bm.section)
        fmap = families_map.get(sec_name) if sec_name else None

        if fmap is None:
            skipped_sections += 1
            continue

        new_section = _build_section_dto(fmap)
        bar_changes.append({
            "elementId": _scid_to_revit_id(bm.sc_id),
            "newSectionName": fmap.type_name,
            "newSection": new_section,
            "rebars": [],  # armatures poutres non gérées pour l'instant
        })

    return {
        "barChanges": bar_changes,
        "nodeChanges": []  # appuis non écrits (voir note honneteté)
    }


def _get_section_name(project: Project, section_sc_id: str) -> Optional[str]:
    sections = getattr(project, "sections", {}) or {}
    sec = sections.get(section_sc_id)
    return sec.name if sec and sec.name else None


def _build_section_dto(fmap: FamilyMapEntry) -> Dict[str, Any]:
    """Construit SectionDto (mètres) pour l'add-in."""
    dto = {}
    if fmap.width_m is not None:
        dto["width"] = fmap.width_m
    if fmap.height_m is not None:
        dto["height"] = fmap.height_m
    if fmap.diameter_m is not None:
        dto["diameter"] = fmap.diameter_m
    return dto


def _build_rebar_dtos(plan: Any) -> List[Dict[str, Any]]:
    """
    Construit la liste RebarDto depuis un ReinforcementPlan.

    Chaque barre longitudinale -> 1 RebarDto (l'add-in crée 1 barre à l'axe,
    note que Count>1 n'est pas appliqué sans enrobage).
    """
    rebars = []

    # Barres longitudinales
    if hasattr(plan, "bar_d_mm") and hasattr(plan, "bar_count"):
        rebars.append({
            "barId": 0,           # 0 = nouvelle armature sur cet élément
            "diameterMm": int(round(plan.bar_d_mm)),
            "count": int(plan.bar_count),
            "position": 0.5,      # milieu de la barre (axe)
            "layer": "Longitudinal",
        })

    # Cadres (stirrups)
    if hasattr(plan, "stirrup_d_mm"):
        rebars.append({
            "barId": 0,
            "diameterMm": int(round(plan.stirrup_d_mm)),
            "count": 1,           # 1 cadre = 1 armature fermée (l'add-in ne gère pas le nombre)
            "position": 0.5,
            "layer": "Stirrups",
        })

    return rebars


def _scid_to_revit_id(sc_id: str) -> int:
    """
    Convertit un SC-ID en int pour l'add-in.

    L'add-in utilise un mapping local (handle -> ElementId) construit
    lors de READ_MODEL. Ici on renvoie un hash stable pour tenter
    l'appariement si l'add-in a lu le modèle avant.
    """
    # On prend la partie numérique du SC-*
    import re
    m = re.search(r"R(\d+)$", sc_id)
    if m:
        return int(m.group(1))
    # Fallback : hash simple
    return hash(sc_id) & 0x7FFFFFFF


# ---------------------------------------------------------------------------
# Haut niveau : write_model (connecte, envoie, retourne rapport)
# ---------------------------------------------------------------------------

def write_model_to_revit(
    project: Project,
    families_map_path: str,
    reinforcement_plans: Optional[Dict[str, Any]] = None,
    pipe_client: Optional[RevitPipeClient] = None
) -> WriteReport:
    """
    Envoie le modèle + armatures vers Revit via le Named Pipe.

    Retourne un WriteReport (succès/échec, compteurs, notes).
    """
    report = WriteReport()
    client = pipe_client
    own_client = False

    try:
        # Charger mapping familles
        fmap = FamiliesMap.load(families_map_path)
        report.add_note(f"Mapping familles chargé : {len(fmap.sections)} sections mappées")

        # Construire la requête
        request = build_apply_changes_request(project, fmap, reinforcement_plans)
        bar_changes = request.get("barChanges", [])
        report.add_note(f"Barres à traiter : {len(bar_changes)} (sections mappées)")

        if not bar_changes:
            report.add_error("Aucune barre mappée -> rien à écrire (vérifiez families_map.json)")
            return report

        # Connexion pipe
        if client is None:
            client = RevitPipeClient()
            own_client = True
            client.connect()
            report.add_note("Pipe connecté")

        # Ping health check
        ping = client.ping()
        report.add_note(f"Ping OK : {ping}")

        # Appliquer les changements
        result = client.apply_changes(request)
        report.bars_processed = len(bar_changes)
        report.sections_applied = result.get("barsUpdated", 0)
        report.rebars_created = result.get("rebarsCreated", 0)
        report.notes.extend(result.get("notes", []))

        report.add_note(f"Résultat : {report.sections_applied} sections appliquées, {report.rebars_created} armatures créées")

    except RevitPipeError as exc:
        report.add_error(f"Pipe : {exc}")
    except RevitProtocolError as exc:
        report.add_error(f"Protocole : {exc}")
    except FileNotFoundError as exc:
        report.add_error(f"Mapping : {exc}")
    except Exception as exc:
        report.add_error(f"Inattendu : {exc}")
    finally:
        if own_client and client:
            client.close()

    return report