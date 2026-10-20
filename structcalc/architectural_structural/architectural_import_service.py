# -*- coding: utf-8 -*-
"""
architectural_structural/architectural_import_service.py — Phase A (Module 71 §4.1).

Service d'import architectural avec INTERFACES ABSTRAITES par format
(Revit, IFC, DWG/DXF, PDF) — règle §14 : les règles métier ne dépendent pas
directement d'un seul logiciel.

Règles (§4.1) :
  - adaptateurs DISTINCTS par format ;
  - un PDF / plan image N'EST PAS une géométrie exacte sans vérification des
    échelles, dimensions et repères (statut ASSUMED, jamais PROVIDED) ;
  - chaque adaptateur produit un `ImportReport` (unités, échelles, doublons,
    niveaux, axes, ouvertures, version) — §4.4.

Statut d'implémentation honnête (§19) : les adaptateurs IFC/DWG/PDF sont des
squelettes qui retournent une erreur EXPLICITE tant que le parsing réel n'est
pas branché. L'adaptateur `RawGeometry` (données fournies par le test) est
pleinement opérationnel et sert de référence.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List

from .model_ext import ArchitecturalModel
from .geometry_normalization import (
    ImportReport, ImportIssue, detect_scale, normalize_levels,
    normalize_axes, normalize_openings, flag_unknown_function,
)


class ArchitecturalImporter(abc.ABC):
    """
    Interface abstraite d'un adaptateur d'import architectural (§14).

    Implémente : `import_geometry(model) -> ImportReport`.
    Chaque format fournit sa propre implémentation.
    """

    #: identifiant du format (revit|ifc|dwg|pdf|raw)
    format_id: str = "abstract"
    #: True si l'adaptateur produit une géométrie EXACTE (vs inférente)
    exact: bool = False

    @abc.abstractmethod
    def import_geometry(self, model: ArchitecturalModel,
                        source: Any) -> ImportReport:
        """Importe la géométrie dans `model`. Retourne le rapport (§4.4)."""

    def _base_report(self) -> ImportReport:
        return ImportReport()


# ---------------------------------------------------------------------------
# Adaptateur de référence — géométrie fournie (données structurées)
# ---------------------------------------------------------------------------

class RawGeometryImporter(ArchitecturalImporter):
    """
    Importateur de référence : géométrie déjà structurée (dict).

    C'est l'adaptateur UTILISÉ PAR LES TESTS et le scénario pédagogique
    (Module 71 §3/§11). Pleinement opérationnel (exact=True).

    Attend `source` = {
        "unit": "m"|"cm"|...,
        "levels": [{"name", "elevation", "height"}],
        "axes_x": [0, 5, 10],
        "axes_y": [0, 5, 10],
        "openings": [{"kind","level","cx","cy","width","depth"}],
        "elements": [{"kind","level","function","outline"}],
    }
    """
    format_id = "raw"
    exact = True

    def import_geometry(self, model: ArchitecturalModel,
                        source: dict) -> ImportReport:
        rep = self._base_report()

        # 1) Unités / échelle (§4.4 — bloquant si inconnue)
        scale = detect_scale(source.get("unit", "m"), rep)

        # 2) Niveaux
        levels = normalize_levels(model, source.get("levels", []), rep, scale)
        level_ids = [lv.sc_id for lv in levels]
        level_by_name = {lv.name: lv.sc_id for lv in levels}

        # 3) Axes
        normalize_axes(model, source.get("axes_x", []),
                       source.get("axes_y", []), rep, scale)

        # 4) Ouvertures (level référencé par nom -> SC-*)
        raw_openings = []
        for o in source.get("openings", []):
            raw = dict(o)
            lname = raw.pop("level", None)
            if lname is not None:
                raw["level_ref"] = level_by_name.get(lname)
            raw_openings.append(raw)
        normalize_openings(model, raw_openings, rep, scale)

        # 5) Éléments architecturaux
        for e in source.get("elements", []):
            lname = e.get("level")
            model.new_arch_element(
                kind=e.get("kind", ""),
                level_ref=level_by_name.get(lname) if lname else None,
                structural_function=e.get("function", "UNKNOWN"),
                outline=[tuple(p) for p in e.get("outline", [])])

        # 6) Fonctions structurelles inconnues (§4.2)
        flag_unknown_function(model, rep)

        rep.elements_found = len(model.arch_elements)
        return rep


# ---------------------------------------------------------------------------
# Adaptateurs externes — statut explicite tant que non branchés (§19)
# ---------------------------------------------------------------------------

class RevitImporter(ArchitecturalImporter):
    """
    Adaptateur Revit (§4.1). Statut : NON IMPLÉMENTÉ pour l'extraction
    directe (Revit = .NET, pas de COM modèle, cf. integration/revit).

    Une fois l'intégration native ou l'add-in .NET disponible, implémenter
    `import_geometry` pour extraire niveaux/axes/éléments.
    """
    format_id = "revit"
    exact = True

    def import_geometry(self, model: ArchitecturalModel,
                        source: Any) -> ImportReport:
        rep = self._base_report()
        rep.issues.append(ImportIssue(
            code="ADAPTER_NOT_IMPLEMENTED",
            message="Import Revit NON IMPLÉMENTÉ : l'accès au modèle exige "
                    "l'intégration native Revit->Robot ou un add-in .NET "
                    "(§4.1, §6.3). Aucune géométrie inventée.",
            blocking=True))
        return rep


class IfcImporter(ArchitecturalImporter):
    """Adaptateur IFC (§4.1). Statut : parsing IFC NON IMPLÉMENTÉ (§19)."""
    format_id = "ifc"
    exact = True

    def import_geometry(self, model: ArchitecturalModel,
                        source: Any) -> ImportReport:
        rep = self._base_report()
        rep.issues.append(ImportIssue(
            code="ADAPTER_NOT_IMPLEMENTED",
            message="Import IFC NON IMPLÉMENTÉ : le parsing IFC (niveaux, "
                    "axes, IfcWall, IfcOpening...) n'est pas encore branché. "
                    "Aucune géométrie inventée.",
            blocking=True))
        return rep


class DwgImporter(ArchitecturalImporter):
    """
    Adaptateur DWG/DXF (§4.1). Statut : NON IMPLÉMENTÉ (§19).

    Un DWG 2D nécessite contrôle d'échelle et d'unités avant toute géométrie
    (§4.1 : vérification des échelles, dimensions et repères).
    """
    format_id = "dwg"
    exact = False     # plans 2D : échelle à vérifier

    def import_geometry(self, model: ArchitecturalModel,
                        source: Any) -> ImportReport:
        rep = self._base_report()
        rep.issues.append(ImportIssue(
            code="ADAPTER_NOT_IMPLEMENTED",
            message="Import DWG/DXF NON IMPLÉMENTÉ : lecture de polylignes + "
                    "contrôle d'échelle requis avant géométrie (§4.1). "
                    "Aucune géométrie inventée.",
            blocking=True))
        return rep


class PdfImporter(ArchitecturalImporter):
    """
    Adaptateur PDF/image (§4.1). Statut : NON IMPLÉMENTÉ (§19).

    Règle §4.1 : un PDF ou plan image N'EST PAS une géométrie exacte sans
    vérification des échelles, dimensions et repères → `exact=False` et
    toute géométrie inférée serait ASSUMED, jamais PROVIDED.
    """
    format_id = "pdf"
    exact = False

    def import_geometry(self, model: ArchitecturalModel,
                        source: Any) -> ImportReport:
        rep = self._base_report()
        rep.issues.append(ImportIssue(
            code="ADAPTER_NOT_IMPLEMENTED",
            message="Import PDF NON IMPLÉMENTÉ : une vectorisation serait "
                    "une GÉOMÉTRIE INFÉRÉE (ASSUMED, non PROVIDED) exigeant "
                    "vérification d'échelle/dimensions/repères (§4.1). "
                    "Aucune géométrie inventée.",
            blocking=True))
        return rep


# ---------------------------------------------------------------------------
# Registre d'adaptateurs
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, ArchitecturalImporter] = {}


def register(importer: ArchitecturalImporter) -> None:
    _REGISTRY[importer.format_id] = importer


def get_importer(format_id: str) -> ArchitecturalImporter:
    if format_id not in _REGISTRY:
        raise KeyError(
            f"Adaptateur d'import inconnu : {format_id!r}. "
            f"Disponibles : {sorted(_REGISTRY)}")
    return _REGISTRY[format_id]


def available_formats() -> List[str]:
    return sorted(_REGISTRY)


# Enregistrement par défaut
for _imp in (RawGeometryImporter(), RevitImporter(), IfcImporter(),
             DwgImporter(), PdfImporter()):
    register(_imp)


def import_architectural_source(model: ArchitecturalModel,
                                format_id: str,
                                source: Any) -> ImportReport:
    """
    Point d'entrée Phase A : importe selon le format, renvoie le rapport.

    `report.ok() == False` => erreur bloquante, CRÉATION DE MODÈLE
    STRUCTUREL INTERDITE (§4.4).
    """
    imp = get_importer(format_id)
    return imp.import_geometry(model, source)
