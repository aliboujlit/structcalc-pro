# -*- coding: utf-8 -*-
"""
integration/revit/families.py — Mapping sections Robot → familles Revit.

PRINCIPE D'HONNÊTETÉ ABSOLU :
  - Le programme NE FOURNIT AUCUNE famille Revit.
  - L'utilisateur DOIT fournir un fichier de mapping JSON (ex. families_map.json)
    qui associe chaque nom de section Robot à un FamilySymbol Revit EXISTANT.
  - Si une section n'est pas mappée -> REFUS EXPLICITE (aucune section inventée,
    aucune duplication à l'aveugle sans validation utilisateur).

Format du mapping JSON (fourni par l'utilisateur) :
{
  "version": 1,
  "default_beam_family": "Poutre_Rectangulaire",   // famille de secours pour création
  "default_column_family": "Poteau_Rectangulaire",
  "default_footing_isolated_family": "Semelle_Isolée",
  "default_footing_strip_family": "Semelle_Filante",
  "sections": {
    "C R30x30": { "family": "Poteau_Rectangulaire", "type_name": "30x30",
                  "width_m": 0.30, "height_m": 0.30, "element_type": "column" },
    "B R20x35": { "family": "Poutre_Rectangulaire", "type_name": "20x35",
                  "width_m": 0.20, "height_m": 0.35, "element_type": "beam" },
    "F ISOL 100x100x40": { "family": "Semelle_Isolée", "type_name": "100x100x40",
                           "width_m": 1.0, "height_m": 1.0, "thickness_m": 0.4,
                           "element_type": "footing_isolated" },
    ...
  }
}

Si "type_name" existe dans le document -> utilisé.
Sinon -> l'add-in essaie de le créer par duplication (fallback) MAIS
un avertissement est émis (traçabilité).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class FamilyMapEntry:
    """Une entrée de mapping : section Robot -> famille/type Revit."""
    family: str              # Nom de la famille Revit (ex. "Poteau_Rectangulaire")
    type_name: str           # Nom du type/symbole (ex. "30x30")
    # Paramètres optionnels à forcer sur le type (mètres)
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    diameter_m: Optional[float] = None
    thickness_m: Optional[float] = None  # pour semelles
    element_type: str = "column"         # "column" | "beam" | "footing_isolated" | "footing_strip"


@dataclass
class FamiliesMap:
    """Mapping complet sections -> familles Revit."""
    version: int = 1
    default_beam_family: str = "Poutre_Rectangulaire"
    default_column_family: str = "Poteau_Rectangulaire"
    default_footing_isolated_family: str = "Semelle_Isolée"
    default_footing_strip_family: str = "Semelle_Filante"
    sections: Dict[str, FamilyMapEntry] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def load(cls, path: str) -> "FamiliesMap":
        """Charge le mapping depuis un fichier JSON (UTF-8)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Mapping familles introuvable : {p}")
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = {}
        for sec_name, entry in data.get("sections", {}).items():
            entries[sec_name] = FamilyMapEntry(
                family=entry["family"],
                type_name=entry["type_name"],
                width_m=entry.get("width_m"),
                height_m=entry.get("height_m"),
                diameter_m=entry.get("diameter_m"),
                thickness_m=entry.get("thickness_m"),
                element_type=entry.get("element_type", "column"),
            )
        return cls(
            version=data.get("version", 1),
            default_beam_family=data.get("default_beam_family", "Poutre_Rectangulaire"),
            default_column_family=data.get("default_column_family", "Poteau_Rectangulaire"),
            default_footing_isolated_family=data.get("default_footing_isolated_family", "Semelle_Isolée"),
            default_footing_strip_family=data.get("default_footing_strip_family", "Semelle_Filante"),
            sections=entries,
            notes=data.get("notes", ""),
        )

    def get(self, section_name: str) -> Optional[FamilyMapEntry]:
        """Retourne l'entrée de mapping pour une section Robot, ou None."""
        if not section_name:
            return None
        return self.sections.get(section_name)

    def has_mapping(self, section_name: str) -> bool:
        return section_name in self.sections


# ---------------------------------------------------------------------------
# Mapping par défaut COMPLET pour la Villa (exemple à copier/coller par l'utilisateur)
# ---------------------------------------------------------------------------

DEFAULT_MAPPING_JSON = """{
  "version": 1,
  "default_beam_family": "Poutre_Rectangulaire",
  "default_column_family": "Poteau_Rectangulaire",
  "default_footing_isolated_family": "Semelle_Isolée",
  "default_footing_strip_family": "Semelle_Filante",
  "notes": "À COMPLÉTER par l'utilisateur : associer CHAQUE section Robot à une famille/type Revit existant. Aucune section non mappée ne sera écrite. Les familles doivent exister dans le projet Revit (ou être chargées). Les dimensions (width_m, height_m, diameter_m, thickness_m) sont en MÈTRES. element_type ∈ {column, beam, footing_isolated, footing_strip}.",
  "sections": {
    "C R30x30": { "family": "Poteau_Rectangulaire", "type_name": "30x30", "width_m": 0.30, "height_m": 0.30, "element_type": "column" },
    "C R40x40": { "family": "Poteau_Rectangulaire", "type_name": "40x40", "width_m": 0.40, "height_m": 0.40, "element_type": "column" },
    "C R50x50": { "family": "Poteau_Rectangulaire", "type_name": "50x50", "width_m": 0.50, "height_m": 0.50, "element_type": "column" },
    "B R20x35": { "family": "Poutre_Rectangulaire", "type_name": "20x35", "width_m": 0.20, "height_m": 0.35, "element_type": "beam" },
    "B R20x40": { "family": "Poutre_Rectangulaire", "type_name": "20x40", "width_m": 0.20, "height_m": 0.40, "element_type": "beam" },
    "B R25x50": { "family": "Poutre_Rectangulaire", "type_name": "25x50", "width_m": 0.25, "height_m": 0.50, "element_type": "beam" },
    "F ISOL 100x100x40": { "family": "Semelle_Isolée", "type_name": "100x100x40", "width_m": 1.00, "height_m": 1.00, "thickness_m": 0.40, "element_type": "footing_isolated" },
    "F ISOL 120x120x45": { "family": "Semelle_Isolée", "type_name": "120x120x45", "width_m": 1.20, "height_m": 1.20, "thickness_m": 0.45, "element_type": "footing_isolated" },
    "F FIL 60x40": { "family": "Semelle_Filante", "type_name": "60x40", "width_m": 0.60, "height_m": 0.40, "element_type": "footing_strip" },
    "F FIL 80x45": { "family": "Semelle_Filante", "type_name": "80x45", "width_m": 0.80, "height_m": 0.45, "element_type": "footing_strip" }
  }
}"""


def write_default_mapping(path: str) -> str:
    """Écrit un fichier d'exemple de mapping (l'utilisateur DOIT le compléter avec SES familles Revit)."""
    Path(path).write_text(DEFAULT_MAPPING_JSON, encoding="utf-8")
    return path