# -*- coding: utf-8 -*-
"""
core/model.py — Objet structurel interne (spec §3.1, §4).

Modèle indépendant de tout logiciel tiers (pas de PyQt6, ni Robot, ni Revit).
Chaque objet porte :
  - un identifiant permanent SC-* (ids.py) ;
  - des propriétés importantes en TrackedValue (statut + provenance, §4.2/§4.3) ;
  - des identifiants externes séparés (mapping Robot/Revit, §4.1).

La traduction vers/from Robot est le rôle de INTEGRATION (mapping.py).
Ici, aucune référence à une API externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .ids import IdAllocator
from .status import DataStatus
from .tracked import TrackedValue, Provenance


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class ExternalRef:
    """
    Identifiant externe d'un objet (spec §4.1).

    Un changement d'identifiant externe ne crée PAS automatiquement un nouvel
    objet interne si une correspondance fiable existe — c'est le rôle du
    mapping (mapping.py) et de la synchronisation.
    """
    software: str                 # "Robot", "Revit", "AutoCAD"...
    version: str = ""
    external_id: str = ""
    transferred_at: str = ""
    model_version: str = ""
    match_status: str = "UNMATCHED"   # MATCHED / AMBIGUOUS / UNMATCHED / ORPHAN


@dataclass
class StructuralObject:
    """
    Classe de base de tout objet STRUCTCALC.

    Garantit l'identifiant permanent et la liste des références externes.
    """
    sc_id: str
    name: str = ""
    external_refs: List[ExternalRef] = field(default_factory=list)
    notes: str = ""

    def add_external_ref(self, ref: ExternalRef) -> None:
        self.external_refs.append(ref)

    def ref_for(self, software: str) -> Optional[ExternalRef]:
        for r in self.external_refs:
            if r.software == software:
                return r
        return None


# ---------------------------------------------------------------------------
# Matériau et section
# ---------------------------------------------------------------------------

@dataclass
class Material(StructuralObject):
    """
    Matériau. Propriétés en TrackedValue : certaines peuvent être MANQUANTES
    ou des HYPOTHÈSES — jamais inventées silencieusement.
    """
    kind: str = ""                       # "concrete" | "steel" | ...
    concrete_class: str = ""             # ex. "C30/37" (EC2) ou classe BAEL
    steel_grade: str = ""                # ex. "S500"
    E: TrackedValue = field(default_factory=lambda: TrackedValue.missing("MPa"))
    fck: TrackedValue = field(default_factory=lambda: TrackedValue.missing("MPa"))
    fyd: TrackedValue = field(default_factory=lambda: TrackedValue.missing("MPa"))
    gamma_c: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    gamma_s: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))

    def is_complete(self) -> bool:
        """Vrai si toutes les propriétés requises sont fournies/validées."""
        required = (self.E, self.fck, self.fyd, self.gamma_c, self.gamma_s)
        return all(v is not None and not v.is_missing for v in required)

    def missing_properties(self) -> List[str]:
        out = []
        for attr in ("E", "fck", "fyd", "gamma_c", "gamma_s"):
            v = getattr(self, attr)
            if v is None or v.is_missing:
                out.append(attr)
        return out


@dataclass
class CrossSection(StructuralObject):
    """
    Section. Dimensions en unités cohérentes (à contrôler). Propriétés
    géométriques calculables (aires, inerties) — calculées par le SOLVER.
    """
    kind: str = ""                       # "rectangular" | "circular" | profile name
    b: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm"))
    h: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm"))
    # Propriétés dérivées (CALCULATED par le solver, pas saisies à la main)
    area: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm2"))
    Iz: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm4"))
    Iy: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm4"))

    def is_defined(self) -> bool:
        return not self.b.is_missing and not self.h.is_missing


# ---------------------------------------------------------------------------
# Géométrie : nœud, appui
# ---------------------------------------------------------------------------

@dataclass
class Node(StructuralObject):
    x: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    y: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    z: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    support: Optional["Support"] = None

    def coordinates(self) -> Optional[tuple]:
        if any(v.is_missing for v in (self.x, self.y, self.z)):
            return None
        return (float(self.x.value), float(self.y.value), float(self.z.value))


@dataclass
class Support(StructuralObject):
    """
    Appui. Conditions aux limites. Toute rigidité non fournie = MISSING,
    jamais supposée nulle silencieusement sans statut ASSUMED.
    """
    kind: str = ""                        # "pinned" | "fixed" | "roller" ...
    dx: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    dy: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    dz: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    rx: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    ry: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))
    rz: TrackedValue = field(default_factory=lambda: TrackedValue.missing("-"))


# ---------------------------------------------------------------------------
# Éléments de barre : poteau, poutre
# ---------------------------------------------------------------------------

@dataclass
class StructuralMember(StructuralObject):
    """Classe de base poteau/poutre : deux nœuds + section + matériau."""
    start_node: Optional[str] = None      # SC-NODE-*
    end_node: Optional[str] = None        # SC-NODE-*
    material: Optional[str] = None         # SC-MATERIAL-*
    section: Optional[str] = None          # SC-SECTION-*
    length: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))

    def is_complete_geometry(self) -> bool:
        return (self.start_node is not None and self.end_node is not None
                and self.section is not None)


@dataclass
class Column(StructuralObject):
    """Poteau (objet prioritaire du module de dimensionnement, spec §10)."""
    start_node: Optional[str] = None
    end_node: Optional[str] = None
    material: Optional[str] = None
    section: Optional[str] = None
    storey: Optional[str] = None           # SC-STOREY-*
    height: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    # Longueur de flambement justifiée (différente de la hauteur si appuis intermédiaires)
    buckling_length_y: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    buckling_length_z: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    # Liaisons (encastrement/rotule aux extrémités) — justifiées
    fixity_top: str = ""
    fixity_bottom: str = ""

    def geometry_ready(self) -> bool:
        return (self.start_node is not None and self.end_node is not None
                and not self.height.is_missing)


@dataclass
class Beam(StructuralObject):
    start_node: Optional[str] = None
    end_node: Optional[str] = None
    material: Optional[str] = None
    section: Optional[str] = None
    span: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))


@dataclass
class Slab(StructuralObject):
    """Dalle / panneau. Géométrie par contour de nœuds."""
    node_ids: List[str] = field(default_factory=list)
    thickness: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm"))
    material: Optional[str] = None


@dataclass
class Wall(StructuralObject):
    node_ids: List[str] = field(default_factory=list)
    thickness: TrackedValue = field(default_factory=lambda: TrackedValue.missing("cm"))
    material: Optional[str] = None


@dataclass
class Foundation(StructuralObject):
    kind: str = ""                        # "strip" | "pad" | "raft" ...
    node_ids: List[str] = field(default_factory=list)
    material: Optional[str] = None


# ---------------------------------------------------------------------------
# Niveaux et bâtiment
# ---------------------------------------------------------------------------

@dataclass
class Storey(StructuralObject):
    level: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    height_above: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    node_ids: List[str] = field(default_factory=list)


@dataclass
class Building(StructuralObject):
    storeys: List[str] = field(default_factory=list)     # SC-STOREY-*
    grid: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Charges
# ---------------------------------------------------------------------------

@dataclass
class LoadCase(StructuralObject):
    kind: str = ""                        # "dead" | "live" | "wind" | "snow" | "seismic"
    nature: str = ""                      # libellé réglementaire
    # Les charges proprement dites (valeurs) sont portées par le SOLVER /
    # la couche d'échange ; ici on garde la définition du cas.


@dataclass
class LoadCombination(StructuralObject):
    """
    Combinaison d'actions. La définition EXACTE (coefficients) est conservée
    (spec §9.2) : le moteur ne codage pas les coefficients universellement.
    """
    expression: str = ""                  # ex. "1.35 G + 1.5 Q"
    factors: Dict[str, float] = field(default_factory=dict)   # case_sc_id -> coefficient
    source_code: str = ""                 # ex. "BAEL 91 r99" / "Eurocode"


@dataclass
class Load(StructuralObject):
    """
    Charge lue dans un logiciel (valeur RÉELLE, jamais inventée).

    `value` : valeur lue (MISSING si le logiciel n'expose pas l'index de
    valeur vérifié pour ce type de charge — spec §19 : pas de devinette).
    `ref`   : description exacte renvoyée par le logiciel (ex. description
    Robot du record) — preuve traçable de la donnée.
    """
    case_sc_id: str = ""                   # SC-LOADCASE-* du cas porteur
    kind: str = ""                         # type de charge (enum logiciel, réel)
    value: TrackedValue = field(default_factory=lambda: TrackedValue.missing(""))
    unit: str = ""                         # unité déclarée par le logiciel
    target: str = ""                       # "robot" | "autocad" | ...
    ref: str = ""                          # description exacte du logiciel


# ---------------------------------------------------------------------------
# Projet
# ---------------------------------------------------------------------------

@dataclass
class Project(StructuralObject):
    """
    Racine du modèle interne. Contient l'allocateur d'identifiants pour
    garantir l'unicité et la stabilité sur toute la durée du projet.
    """
    buildings: List[str] = field(default_factory=list)      # SC-BUILDING-*
    materials: Dict[str, Material] = field(default_factory=dict)
    sections: Dict[str, CrossSection] = field(default_factory=dict)
    nodes: Dict[str, Node] = field(default_factory=dict)
    columns: Dict[str, Column] = field(default_factory=dict)
    beams: Dict[str, Beam] = field(default_factory=dict)
    slabs: Dict[str, Slab] = field(default_factory=dict)
    walls: Dict[str, Wall] = field(default_factory=dict)
    supports: Dict[str, Support] = field(default_factory=dict)
    storeys: Dict[str, Storey] = field(default_factory=dict)
    load_cases: Dict[str, LoadCase] = field(default_factory=dict)
    load_combinations: Dict[str, LoadCombination] = field(default_factory=dict)
    loads: Dict[str, Load] = field(default_factory=dict)
    allocator: IdAllocator = field(default_factory=IdAllocator)
    # Fichier d'origine du pivot (ex. plan DWG) — porté pour la coordination
    # (conversion NWD Navisworks, rapports). Renseigné par le chargeur ; vide
    # si inconnu (jamais inventé).
    source_file: str = ""

    # -- Fabriques d'objets (garantissent l'ID permanent) -----------------

    def new_node(self, x=None, y=None, z=None, name="") -> Node:
        nid = self.allocator.new("NODE")
        def tv(v):
            if v is None:
                return TrackedValue.missing("m")
            return TrackedValue.of(float(v), "m", DataStatus.PROVIDED,
                                   Provenance.provided_by("modélisation"))
        node = Node(sc_id=nid, name=name, x=tv(x), y=tv(y), z=tv(z))
        self.nodes[nid] = node
        return node

    def new_column(self, start_node, end_node, name="") -> Column:
        cid = self.allocator.new("COLUMN")
        col = Column(sc_id=cid, name=name, start_node=start_node,
                     end_node=end_node)
        self.columns[cid] = col
        return col

    def new_material(self, kind="", name="") -> Material:
        mid = self.allocator.new("MATERIAL")
        mat = Material(sc_id=mid, name=name, kind=kind)
        self.materials[mid] = mat
        return mat

    def new_section(self, kind="", name="") -> CrossSection:
        sid = self.allocator.new("SECTION")
        sec = CrossSection(sc_id=sid, name=name, kind=kind)
        self.sections[sid] = sec
        return sec

    # -- Sauvegarde/chargement des compteurs (stabilité des IDs) ----------

    def collect_all_ids(self) -> List[str]:
        """Tous les identifiants utilisés (pour restaurer les compteurs)."""
        ids: List[str] = []
        for d in (self.buildings,):
            ids.extend(d)
        for dct in (self.materials, self.sections, self.nodes, self.columns,
                    self.beams, self.slabs, self.walls, self.supports,
                    self.storeys, self.load_cases, self.load_combinations):
            ids.extend(dct.keys())
        return ids

    def restore_allocator(self) -> None:
        """Rejoue les compteurs au-delà des IDs existants (appelé au chargement)."""
        self.allocator.restore(self.collect_all_ids())

    # -- Compteurs de cohérence -------------------------------------------

    def counts(self) -> Dict[str, int]:
        return {
            "nodes": len(self.nodes),
            "columns": len(self.columns),
            "beams": len(self.beams),
            "slabs": len(self.slabs),
            "walls": len(self.walls),
            "supports": len(self.supports),
            "materials": len(self.materials),
            "sections": len(self.sections),
            "storeys": len(self.storeys),
            "load_cases": len(self.load_cases),
            "combinations": len(self.load_combinations),
            "loads": len(self.loads),
        }

    def data_gaps(self) -> Dict[str, List[str]]:
        """
        Rapport des données manquantes (spec §4.2 MISSING).

        Une donnée manquante n'est JAMAIS inventée : elle est signalée.
        """
        gaps: Dict[str, List[str]] = {}
        for mid, mat in self.materials.items():
            miss = mat.missing_properties()
            if miss:
                gaps[mid] = miss
        for sid, sec in self.sections.items():
            if not sec.is_defined():
                gaps[sid] = [a for a in ("b", "h")
                             if getattr(sec, a).is_missing]
        return gaps
