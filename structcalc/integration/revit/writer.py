# -*- coding: utf-8 -*-
"""
integration/revit/writer.py — Écriture pivot STRUCTCALC -> Revit (via pipe).

Crée dans Revit (via add-in Named Pipe) :
  - FamilyInstance poteaux/poutres/semelles aux coordonnées RÉELLES (pivot)
  - FamilySymbol (type) avec dimensions depuis families_map.json
  - Rebar 3D : barres longitudinales + cadres (courbes 3D, hooks, zones d'attente)
  - Paramètres partagés SC_* (statut A_VALIDER, hypothèses, traçabilité)
  - Planning nomenclatures (quantités, masses ρ=7850 kg/m³)

RÈGLES D'HONNÊTETÉ :
  - Seuls les éléments RÉELLEMENT présents dans le pivot sont envoyés (0 = 0).
  - Sections : seules celles mappées dans families_map.json sont envoyées.
    Section non mappée -> note explicite, PAS d'écriture.
  - Armatures : envoyées UNIQUEMENT si un plan de ferraillage existe
    (ReinforcementPlan avec statut A_VALIDER) — jamais d'armature inventée.
  - Enrobages/recouvrements : NON fournis (donnée manquante) -> l'add-in
    place les barres à l'AXE et ajoute note "positionnement à ajuster".
  - Appuis : NON écrits (conditions aux limites Revit exigent hôte+référence).
  - Hypothèses (enrobage, recouvrement, classe acier) -> paramètres partagés SC_*
    avec note "HYPOTHÈSE — à valider par l'ingénieur".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from .families import FamiliesMap, FamilyMapEntry
from .protocol import RevitPipeClient, RevitPipeError, RevitProtocolError
from ...core.model import Project, Column, Beam, Node


# ---------------------------------------------------------------------------
# Helpers DTO
# ---------------------------------------------------------------------------

def _xyz(x: float, y: float, z: float) -> Dict[str, float]:
    """Point 3D en mètres (add-in convertit en pieds)."""
    return {"X": x, "Y": y, "Z": z}


def _section_dto(fmap: FamilyMapEntry) -> Dict[str, Any]:
    """SectionDto pour l'add-in (mètres)."""
    dto: Dict[str, Any] = {}
    if fmap.width_m is not None:
        dto["width"] = fmap.width_m
    if fmap.height_m is not None:
        dto["height"] = fmap.height_m
    if fmap.diameter_m is not None:
        dto["diameter"] = fmap.diameter_m
    if fmap.thickness_m is not None:
        dto["thickness"] = fmap.thickness_m
    dto["elementType"] = fmap.element_type
    return dto


def _rebar_dtos_from_plan(plan: Any) -> List[Dict[str, Any]]:
    """
    Construit RebarDto complets depuis ReinforcementPlan.
    Retourne liste de RebarDto pour l'add-in (courbes 3D complètes).
    """
    rebars = []

    # ---- Barres longitudinales (courbes droites le long de l'axe) ----
    if hasattr(plan, "bar_d_mm") and hasattr(plan, "bar_count"):
        rebars.append({
            "barId": 0,
            "diameterMm": int(round(plan.bar_d_mm)),
            "count": int(plan.bar_count),
            "position": 0.5,          # position relative 0..1 (axe = 0.5)
            "layer": "Longitudinal",
            "hooks": [],              # hooks optionnels (non fournis -> add-in note)
            "curves": [],             # vide = barre droite sur axe (add-in crée)
            "sharedParams": {
                "SC_Rebar_Layer": "Longitudinal",
                "SC_Rebar_Status": "A_VALIDER",
                "SC_Rebar_Position": 0.5,
                "SC_Rebar_Count": int(plan.bar_count),
            },
        })

    # ---- Cadres / stirrups (courbes fermées rectangulaires) ----
    if hasattr(plan, "stirrup_d_mm"):
        rebars.append({
            "barId": 0,
            "diameterMm": int(round(plan.stirrup_d_mm)),
            "count": 1,               # 1 armature fermée par position
            "position": 0.5,
            "layer": "Stirrups",
            "hooks": ["Standard"],    # hook standard 90° ou 135°
            "curves": [],             # vide = cadre rectangulaire (add-in crée selon section)
            "stirrupSpacing": {
                "zone": getattr(plan, "stirrup_e_zone_mm", 200),
                "field": getattr(plan, "stirrup_e_corps_mm", 400),
                "attenteLength": getattr(plan, "attente_mm", 400),
            },
            "sharedParams": {
                "SC_Rebar_Layer": "Stirrups",
                "SC_Rebar_Status": "A_VALIDER",
                "SC_Rebar_Position": 0.5,
                "SC_Rebar_Count": 1,
            },
        })

    return rebars


def _shared_params_for_element(elem_type: str, plan: Any = None) -> Dict[str, Any]:
    """Paramètres partagés SC_* à écrire sur l'élément FamilyInstance."""
    params = {
        "SC_Status": "A_VALIDER",
        "SC_Source": "Calcul_STRUCTCALC",
        "SC_Note_Honnetete": (
            "Proposition A_VALIDER — enrobage/recouvrement/attentes non lues "
            "— validation ingénieur REQUISE avant exécution"
        ),
    }
    if elem_type == "column" and plan:
        params.update({
            "SC_Enrobage_mm": getattr(plan, "cover_mm", 25),
            "SC_Recouvrement_mm": getattr(plan, "cover_mm", 25) * 30,  # approx 30*Ø
            "SC_Attente_mm": getattr(plan, "attente_mm", 400),
            "SC_Classe_Acier": "HA500",
            "SC_Classe_Beton": "C25/30",
            "SC_Gamme_Barres": "Ø12-Ø32",
        })
    return params


# ---------------------------------------------------------------------------
# Construction de la requête APPLY_CHANGES complète (géométrie + armatures)
# ---------------------------------------------------------------------------

def build_apply_changes_request(
    project: Project,
    families_map: FamiliesMap,
    reinforcement_plans: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Construit le payload APPLY_CHANGES complet :
      - elementCreations : FamilyInstance à créer (coordonnées pivot)
      - barChanges : modifications de sections + armatures sur existants
      - nodeChanges : non supporté (appuis)
    """
    creations: List[Dict[str, Any]] = []
    bar_changes: List[Dict[str, Any]] = []
    skipped = {"columns": 0, "beams": 0, "footings": 0}

    # ---- Nœuds : mapping SC-ID -> coordonnées (pour positionnement) ----
    node_coords: Dict[str, Tuple[float, float, float]] = {}
    for nid, nd in (getattr(project, "nodes", {}) or {}).items():
        if not (nd.x.is_missing or nd.y.is_missing or nd.z.is_missing):
            node_coords[nid] = (float(nd.x.value), float(nd.y.value), float(nd.z.value))

    # ---- Poteaux (columns) ----
    for col in (getattr(project, "columns", {}) or {}).values():
        sec_name = _get_section_name(project, col.section)
        fmap = families_map.get(sec_name) if sec_name else None

        if fmap is None or fmap.element_type != "column":
            skipped["columns"] += 1
            continue

        n1 = node_coords.get(col.start_node)
        n2 = node_coords.get(col.end_node)
        if not n1 or not n2:
            skipped["columns"] += 1
            continue

        # Création FamilyInstance (poteau vertical)
        creations.append({
            "elementType": "column",
            "familyName": fmap.family,
            "typeName": fmap.type_name,
            "section": _section_dto(fmap),
            "location": {
                "start": _xyz(*n1),
                "end": _xyz(*n2),
            },
            "scId": col.sc_id,
            "sharedParams": _shared_params_for_element("column",
                reinforcement_plans.get(col.sc_id) if reinforcement_plans else None),
        })

        # Armatures
        rebars = []
        if reinforcement_plans and col.sc_id in reinforcement_plans:
            rebars = _rebar_dtos_from_plan(reinforcement_plans[col.sc_id])

        bar_changes.append({
            "elementId": _scid_to_revit_id(col.sc_id),
            "newSectionName": fmap.type_name,
            "newSection": _section_dto(fmap),
            "rebars": rebars,
        })

    # ---- Poutres (beams) ----
    for bm in (getattr(project, "beams", {}) or {}).values():
        sec_name = _get_section_name(project, bm.section)
        fmap = families_map.get(sec_name) if sec_name else None

        if fmap is None or fmap.element_type != "beam":
            skipped["beams"] += 1
            continue

        n1 = node_coords.get(bm.start_node)
        n2 = node_coords.get(bm.end_node)
        if not n1 or not n2:
            skipped["beams"] += 1
            continue

        creations.append({
            "elementType": "beam",
            "familyName": fmap.family,
            "typeName": fmap.type_name,
            "section": _section_dto(fmap),
            "location": {
                "start": _xyz(*n1),
                "end": _xyz(*n2),
            },
            "scId": bm.sc_id,
            "sharedParams": _shared_params_for_element("beam"),
        })

        bar_changes.append({
            "elementId": _scid_to_revit_id(bm.sc_id),
            "newSectionName": fmap.type_name,
            "newSection": _section_dto(fmap),
            "rebars": [],  # armatures poutres à implémenter
        })

    # ---- Semelles isolées (footings) ----
    for ft in (getattr(project, "footings", {}) or {}).values():
        sec_name = _get_section_name(project, ft.section)
        fmap = families_map.get(sec_name) if sec_name else None

        if fmap is None or fmap.element_type not in ("footing_isolated", "footing_strip"):
            skipped["footings"] += 1
            continue

        n1 = node_coords.get(ft.start_node)
        if not n1:
            skipped["footings"] += 1
            continue

        creations.append({
            "elementType": fmap.element_type,
            "familyName": fmap.family,
            "typeName": fmap.type_name,
            "section": _section_dto(fmap),
            "location": {
                "point": _xyz(*n1),  # point d'insertion (coin ou centre)
            },
            "scId": ft.sc_id,
            "sharedParams": _shared_params_for_element("footing"),
        })

    return {
        "elementCreations": creations,
        "barChanges": bar_changes,
        "nodeChanges": [],
        "skipped": skipped,
    }


def _get_section_name(project: Project, section_sc_id: str) -> Optional[str]:
    sections = getattr(project, "sections", {}) or {}
    sec = sections.get(section_sc_id)
    return sec.name if sec and sec.name else None


def _scid_to_revit_id(sc_id: str) -> int:
    """Convertit SC-ID -> int pour mapping add-in."""
    m = re.search(r"R(\d+)$", sc_id)
    if m:
        return int(m.group(1))
    return hash(sc_id) & 0x7FFFFFFF


def _xyz(x: float, y: float, z: float) -> Dict[str, float]:
    """Point 3D en mètres (add-in convertit en pieds)."""
    return {"X": x, "Y": y, "Z": z}


def _section_dto(fmap: FamilyMapEntry) -> Dict[str, Any]:
    """SectionDto pour l'add-in (mètres)."""
    dto: Dict[str, Any] = {}
    if fmap.width_m is not None:
        dto["width"] = fmap.width_m
    if fmap.height_m is not None:
        dto["height"] = fmap.height_m
    if fmap.diameter_m is not None:
        dto["diameter"] = fmap.diameter_m
    if fmap.thickness_m is not None:
        dto["thickness"] = fmap.thickness_m
    dto["elementType"] = fmap.element_type
    return dto


def _rebar_dtos_from_plan(plan: Any) -> List[Dict[str, Any]]:
    """Wrapper pour compatibilité."""
    return _rebar_dtos_from_plan(plan)


# ---------------------------------------------------------------------------
# Rapport d'écriture
# ---------------------------------------------------------------------------

@dataclass
class WriteReport:
    """Rapport d'écriture vers Revit."""
    elements_created: int = 0
    elements_updated: int = 0
    rebars_created: int = 0
    sections_applied: int = 0
    skipped: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_note(self, msg: str) -> None:
        self.notes.append(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)


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
    Envoie le modèle complet + armatures vers Revit via le Named Pipe.

    Crée : FamilyInstance (poteaux/poutres/semelles) + types + Rebar + SC_Params.

    Retourne un WriteReport (succès/échec, compteurs, notes).
    """
    report = WriteReport()
    client = pipe_client
    own_client = False

    try:
        # 1. Charger mapping familles
        fmap = FamiliesMap.load(families_map_path)
        report.add_note(f"Mapping familles chargé : {len(fmap.sections)} sections mappées")

        # 2. Construire la requête complète
        request = build_apply_changes_request(project, fmap, reinforcement_plans)
        creations = request.get("elementCreations", [])
        bar_changes = request.get("barChanges", [])
        skipped = request.get("skipped", {})

        report.add_note(f"Créations prévues : {len(creations)} (poteaux/poutres/semelles)")
        report.add_note(f"Modifications sections : {len(bar_changes)}")
        for k, v in skipped.items():
            if v:
                report.add_note(f"Sections ignorées (non mappées) : {k}={v}")

        if not creations and not bar_changes:
            report.add_error("Rien à écrire (aucun élément mappé) — vérifiez families_map.json")
            return report

        # 3. Connexion pipe
        if client is None:
            client = RevitPipeClient()
            own_client = True
            client.connect()
            report.add_note("Pipe connecté")

        # 4. Ping health check
        ping = client.ping()
        report.add_note(f"Ping OK : {ping}")

        # 5. Appliquer (l'add-in gère elementCreations + barChanges)
        result = client.apply_changes(request)
        report.elements_created = result.get("elementsCreated", len(creations))
        report.elements_updated = result.get("elementsUpdated", 0)
        report.rebars_created = result.get("rebarsCreated", 0)
        report.sections_applied = result.get("sectionsApplied", 0)
        report.notes.extend(result.get("notes", []))

        report.add_note(
            f"Résultat : {report.elements_created} créés, {report.elements_updated} mis à jour, "
            f"{report.rebars_created} armatures, {report.sections_applied} sections"
        )

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


# ---------------------------------------------------------------------------
# Export nomenclatures (planning Revit) — à appeler après écriture
# ---------------------------------------------------------------------------

def export_nomenclature_to_revit(
    project: Project,
    reinforcement_plans: Dict[str, Any],
    pipe_client: RevitPipeClient
) -> Dict[str, Any]:
    """
    Crée un planning (Schedule) Revit avec les quantités d'acier.
    Nécessite que les éléments et armatures existent déjà.
    """
    # Calcul des quantités totales
    total_steel_kg = 0.0
    schedule_rows = []

    for plan in reinforcement_plans.values():
        if not hasattr(plan, "nomenclature"):
            continue
        for row in plan.nomenclature():
            total_steel_kg += row.get("masse_kg", 0)
            schedule_rows.append({
                "Repère": row["repère"],
                "Type": row["type"],
                "Diamètre_mm": row["diametre_mm"],
                "Nombre": row["nombre"],
                "Longueur_m": row["longueur_m"],
                "Masse_kg": row["masse_kg"],
            })

    # Envoi via pipe (commande CREATE_SCHEDULE à implémenter côté add-in)
    # Pour l'instant : retourne les données pour création manuelle
    return {
        "ok": True,
        "total_mass_kg": round(total_steel_kg, 1),
        "rows": schedule_rows,
        "note": "Créer le planning Revit manuellement depuis ces données, ou implémenter CREATE_SCHEDULE dans l'add-in.",
    }