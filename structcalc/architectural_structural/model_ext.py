# -*- coding: utf-8 -*-
"""
architectural_structural/model_ext.py — Objets étendus Module 71 (spec §6.1).

Étend le modèle CORE SANS le modifier : réutilise `StructuralObject`,
`TrackedValue`, `DataStatus`, `Provenance` et l'allocateur `SC-*` de CORE.
Aucun doublon de définition => aucun conflit de code avec core/model.py.

Objets ajoutés (spec Module 71 §6.1) qui n'existaient pas dans CORE :
    Axis, ArchitecturalElement, Opening, Stair,
    AnalysisModel, AnalysisResult, Conflict, DesignVariant,
    Drawing, Approval, Revision

Objets déjà présents dans CORE et RÉUTILISÉS (non redéfinis) :
    Project, Building, Storey(=Level), Column, Beam, Slab, Wall, Foundation,
    Material, LoadCase, LoadCombination

Règles (spec Module 71 §6.1/§6.2) :
  - chaque objet porte un identifiant stable `SC-*`, indépendant de Revit/Robot ;
  - les représentations (architecturale / physique / analytique / graphique /
    ferraillage) sont LIÉES mais NON interchangeables ;
  - une donnée non fournie reste MISSING, jamais inventée.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.model import StructuralObject
from ..core.status import DataStatus
from ..core.tracked import TrackedValue, Provenance


# ---------------------------------------------------------------------------
# Représentations (spécifiquement distinctes, spec §6.2)
# ---------------------------------------------------------------------------

class Representation(str, Enum):
    """Nature d'une représentation géométrique — non interchangeables (§6.2)."""
    ARCHITECTURAL = "ARCHITECTURAL"    # géométrie architecturale
    PHYSICAL = "PHYSICAL"              # géométrie physique du béton
    ANALYTICAL = "ANALYTICAL"          # modèle de calcul (axes, appuis)
    GRAPHICAL = "GRAPHICAL"            # géométrie des plans
    REINFORCEMENT = "REINFORCEMENT"    # détails de ferraillage


# ---------------------------------------------------------------------------
# Niveaux / axes (Phase A)
# ---------------------------------------------------------------------------

@dataclass
class Level(StructuralObject):
    """
    Niveau (alias Structurel du Storey CORE). Une altitude par niveau.

    `elevation` est TrackedValue : PROVIDED par l'architecte, ou ASSUMED si
    provisoire. Une altitude manquante reste MISSING (jamais 0 par défaut).
    """
    elevation: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    height_above: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    index: int = 0                        # ordre (RDC=0, R+1=1, ...)
    storey_ref: Optional[str] = None       # lien vers SC-STOREY-* CORE


@dataclass
class Axis(StructuralObject):
    """
    Axe de trame (Phase A/B). Direction X (verticale sur plan) ou Y.

    `position` = coordonnée de l'axe (m). Les entraxes sont CALCULÉS par
    axis_grid_engine, pas saisis.
    """
    direction: str = "X"                  # "X" | "Y"
    position: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    label: str = ""                       # repère graphique (1, 2, A, B...)


# ---------------------------------------------------------------------------
# Éléments architecturaux (Phase A)
# ---------------------------------------------------------------------------

@dataclass
class ArchitecturalElement(StructuralObject):
    """
    Élément architectural importé (mur, cloison, porte, fenêtre, ...).

    `structural_function` porte l'état de connaissance (spec §4.2) :
      - "UNKNOWN"  -> fonction structurelle inconnue (à confirmer) ;
      - "BEARING" / "NON_BEARING" / "OPENS" -> confirmée.
    Une fonction UNKNOWN n'est jamais promue silencieusement.
    """
    kind: str = ""                        # wall|partition|door|window|stair|shaft|slab_outline
    level_ref: Optional[str] = None       # SC-LEVEL-* / SC-STOREY-*
    structural_function: str = "UNKNOWN"  # UNKNOWN|BEARING|NON_BEARING|OPENS
    # Contour simplifié : liste de points (x, y) en m, sur le plan du niveau
    outline: List[tuple] = field(default_factory=list)
    height: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))


@dataclass
class Opening(StructuralObject):
    """
    Ouverture / trémie / réservation (portes, fenêtres, escalier, gaine).

    `blocked` est piloté par opening_reservation_checker : une ouverture qui
    entre en conflit avec un élément structurel est signalée, pas supprimée.
    """
    kind: str = ""                        # door|window|stairwell|shaft|reserved
    level_ref: Optional[str] = None
    # Rectangulaire simplifié : centre + dimensions (m) dans le plan du niveau
    cx: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    cy: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    width: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    depth: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))
    conflicts_with: List[str] = field(default_factory=list)   # SC-* en conflit


@dataclass
class Stair(StructuralObject):
    """Escalier : emprise + niveau desservi + trémie associée."""
    level_ref: Optional[str] = None
    opening_ref: Optional[str] = None      # SC-OPENING-* (trémie)
    outline: List[tuple] = field(default_factory=list)
    rise: TrackedValue = field(default_factory=lambda: TrackedValue.missing("m"))


# ---------------------------------------------------------------------------
# Modèle analytique et résultats (Phase C/E)
# ---------------------------------------------------------------------------

@dataclass
class AnalysisModel(StructuralObject):
    """
    Modèle analytique destiné au solveur (§6.2) : axes de calcul, appuis,
    liaisons, excentricités, sections. VERSIONNÉ : une modification produit
    une nouvelle version et rend les résultats antérieurs OBSOLÈTES.
    """
    version: int = 1
    node_ids: List[str] = field(default_factory=list)
    member_ids: List[str] = field(default_factory=list)   # columns + beams
    support_ids: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)   # hypothèses de liaison
    source_variant: Optional[str] = None                   # SC-VARIANT-*
    created_from: str = ""                                 # provenance (§4.3)


@dataclass
class AnalysisResult(StructuralObject):
    """
    Résultats d'un calcul, associés à un AnalysisModel VERSIONNÉ (Phase E).

    `outdated` est mis à True par change_impact_dispatcher quand le modèle
    source change. Un résultat périmé n'est jamais présenté comme valable.
    """
    model_ref: Optional[str] = None        # SC-ANALYSISMODEL-*
    model_version: int = 0
    software: str = ""                     # "Robot" ...
    available: bool = False
    outdated: bool = False
    reactions: Dict[str, Any] = field(default_factory=dict)     # node -> {Fx,Fy,...}
    bar_forces: Dict[str, Any] = field(default_factory=dict)    # member -> {...}
    displacements: Dict[str, Any] = field(default_factory=dict)
    calc_error: str = ""                   # erreur bloquante éventuelle
    imported_at: str = ""


# ---------------------------------------------------------------------------
# Conflits (Phase F)
# ---------------------------------------------------------------------------

class ConflictKind(str, Enum):
    GEOMETRIC = "GEOMETRIC"        # porte, hauteur libre, trémie, gaine
    STRUCTURAL = "STRUCTURAL"      # porteur interrompu, appui absent, portée
    DOCUMENTARY = "DOCUMENTARY"    # versions divergentes, plan != calcul


# Cycle de traitement (spec Module 71 §9.3)
CONFLICT_TRANSITIONS = {
    "DETECTED": {"CLASSIFIED", "SUSPENDED", "REJECTED"},
    "CLASSIFIED": {"ANALYZED", "SUSPENDED", "REJECTED"},
    "ANALYZED": {"SOLUTIONS_PROPOSED", "SUSPENDED", "REJECTED"},
    "SOLUTIONS_PROPOSED": {"UNDER_REVIEW", "SUSPENDED", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED_FOR_CALCULATION", "REJECTED", "SUSPENDED",
                     "UNRESOLVED"},
    "APPROVED_FOR_CALCULATION": {"RECALCULATED", "SUSPENDED", "REJECTED"},
    "RECALCULATED": {"VERIFIED", "UNRESOLVED"},
    "VERIFIED": {"VALIDATED_FOR_DELIVERY", "UNRESOLVED"},
    "VALIDATED_FOR_DELIVERY": set(),
    # États complémentaires
    "REJECTED": set(),
    "SUSPENDED": {"DETECTED", "REJECTED"},
    "UNRESOLVED": {"DETECTED", "SUSPENDED", "REJECTED"},
}


@dataclass
class Conflict(StructuralObject):
    """Un conflit architecture–structure (spec Module 71 §9.2)."""
    kind: ConflictKind = ConflictKind.GEOMETRIC
    level_ref: Optional[str] = None
    element_ids: List[str] = field(default_factory=list)   # SC-* concernés
    source: str = ""                          # qui a signalé
    description: str = ""
    severity: str = "PROVISIONAL"             # gravité provisoire
    rule_ref: str = ""                        # règle / vérification concernée
    variants_proposed: List[str] = field(default_factory=list)
    assignee: str = ""                        # responsable de traitement
    evidence: List[str] = field(default_factory=list)      # documents de preuve
    status: str = "DETECTED"
    history: List[dict] = field(default_factory=list)      # décisions

    def can_transition(self, new_status: str) -> bool:
        allowed = CONFLICT_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    def transition(self, new_status: str, actor: str = "", reason: str = "") -> bool:
        """
        Passe à un nouveau statut SI la transition est autorisée (§9.3).
        Une solution proposée n'est JAMAIS une solution approuvée sans
        validation. Retourne False si transition interdite (sans effet).
        """
        if not self.can_transition(new_status):
            return False
        self.history.append({
            "from": self.status, "to": new_status,
            "actor": actor, "reason": reason,
        })
        self.status = new_status
        return True


# ---------------------------------------------------------------------------
# Variantes de conception (Phase B)
# ---------------------------------------------------------------------------

@dataclass
class DesignVariant(StructuralObject):
    """
    Variante de conception (spec Module 71 §5.3).

    Chaque variante possède identifiant, VERSION, hypothèses, conflits et
    résultats. Le déplacement automatique d'un poteau est INTERDIT sans
    documenter la modification (contrôlé par design_variant_manager).
    """
    version: int = 1
    description: str = ""
    assumptions: List[str] = field(default_factory=list)
    conflict_ids: List[str] = field(default_factory=list)
    analysis_model_ref: Optional[str] = None
    result_refs: List[str] = field(default_factory=list)
    is_reference: bool = False               # variante de référence ?
    change_log: List[dict] = field(default_factory=list)   # modifications tracées


# ---------------------------------------------------------------------------
# Documents graphiques (Phase G)
# ---------------------------------------------------------------------------

class DeliveryStatus(str, Enum):
    """États de diffusion (spec Module 71 §13)."""
    DRAFT = "DRAFT"
    PRELIMINARY = "PRELIMINARY"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED_FOR_CALCULATION = "APPROVED_FOR_CALCULATION"
    CALCULATED = "CALCULATED"
    VERIFIED = "VERIFIED"
    VALIDATED_FOR_DELIVERY = "VALIDATED_FOR_DELIVERY"
    SUPERSEDED = "SUPERSEDED"


# Portes : quel état exige quel contrôle (validation_gate)
DELIVERY_TRANSITIONS = {
    "DRAFT": {"PRELIMINARY", "SUPERSEDED"},
    "PRELIMINARY": {"UNDER_REVIEW", "DRAFT", "SUPERSEDED"},
    "UNDER_REVIEW": {"APPROVED_FOR_CALCULATION", "PRELIMINARY", "DRAFT"},
    "APPROVED_FOR_CALCULATION": {"CALCULATED", "UNDER_REVIEW"},
    "CALCULATED": {"VERIFIED", "APPROVED_FOR_CALCULATION"},
    "VERIFIED": {"VALIDATED_FOR_DELIVERY", "CALCULATED"},
    "VALIDATED_FOR_DELIVERY": {"SUPERSEDED"},
    "SUPERSEDED": {"APPROVED_FOR_CALCULATION"},   # recalcul après modif
}


@dataclass
class Drawing(StructuralObject):
    """
    Plan / document graphique (Phase G).

    `model_version` = version du modèle SOURCE ; `sections_provisional` signale
    les sections non calculées (à afficher, jamais présentées comme finales).
    """
    kind: str = ""                          # formwork|rebar|section|detail
    level_ref: Optional[str] = None
    model_ref: Optional[str] = None         # SC-* modèle source
    model_version: int = 0
    source_variant: Optional[str] = None    # SC-VARIANT-*
    status: DeliveryStatus = DeliveryStatus.DRAFT
    sections_provisional: List[str] = field(default_factory=list)   # SC-* provisoires
    element_ids: List[str] = field(default_factory=list)            # repères tracés
    format: str = "PDF"                     # PDF|DWG|DXF|RVT
    revision: int = 0
    validations: List[str] = field(default_factory=list)            # SC-APPROVAL-*

    def can_transition(self, new_status: DeliveryStatus) -> bool:
        return new_status.value in DELIVERY_TRANSITIONS.get(
            self.status.value, set())

    def transition(self, new_status: DeliveryStatus, actor: str = "",
                   reason: str = "") -> bool:
        if not self.can_transition(new_status):
            return False
        self.revision += 1
        self.status = new_status
        self.notes = (f"{self.notes} | {new_status.value}"
                      f"({actor}: {reason})").strip(" |")
        return True


@dataclass
class Approval(StructuralObject):
    """Validation par un acteur autorisé (spec Module 71 §15, §77)."""
    subject_ref: str = ""                   # SC-* approuvé (Drawing, Conflict...)
    subject_kind: str = ""
    role: str = ""                          # BET|ARCHITECT|BUREAU_CONTROLE
    actor: str = ""                         # identité de l'acteur
    decision: str = ""                      # APPROVED|REJECTED|CONDITIONAL
    timestamp: str = ""
    note: str = ""


@dataclass
class Revision(StructuralObject):
    """Historique de révision (spec Module 71 §15)."""
    subject_ref: str = ""
    subject_kind: str = ""
    version_from: int = 0
    version_to: int = 0
    actor: str = ""
    reason: str = ""
    timestamp: str = ""
    invalidated_results: List[str] = field(default_factory=list)   # SC-* périmés
    regenerated_docs: List[str] = field(default_factory=list)      # SC-* à régénérer


# ---------------------------------------------------------------------------
# Conteneur Module 71 : Agrège CORE + objets étendus
# ---------------------------------------------------------------------------

@dataclass
class ArchitecturalModel:
    """
    Conteneur Module 71 : agrège le Project CORE et les objets étendus.

    NE MUTUE PAS le dataclass Project (éviter tout conflit avec store.py) :
    les registres étendus vivent ici, les identifiants sont partagés via
    l'allocateur du Project (unicité SC-* garantie, spec §6.1).
    """
    project: Any                            # core.model.Project
    levels: Dict[str, Level] = field(default_factory=dict)
    axes: Dict[str, Axis] = field(default_factory=dict)
    arch_elements: Dict[str, ArchitecturalElement] = field(default_factory=dict)
    openings: Dict[str, Opening] = field(default_factory=dict)
    stairs: Dict[str, Stair] = field(default_factory=dict)
    analysis_models: Dict[str, AnalysisModel] = field(default_factory=dict)
    analysis_results: Dict[str, AnalysisResult] = field(default_factory=dict)
    conflicts: Dict[str, Conflict] = field(default_factory=dict)
    variants: Dict[str, DesignVariant] = field(default_factory=dict)
    drawings: Dict[str, Drawing] = field(default_factory=dict)
    approvals: Dict[str, Approval] = field(default_factory=dict)
    revisions: Dict[str, Revision] = field(default_factory=dict)

    # -- Allocation d'identifiants partagée avec CORE --------------------
    def new_id(self, kind: str) -> str:
        return self.project.allocator.new(kind)

    # -- Compteurs (complément de Project.counts()) ----------------------
    def counts(self) -> Dict[str, int]:
        c = dict(self.project.counts())
        c.update({
            "levels": len(self.levels),
            "axes": len(self.axes),
            "arch_elements": len(self.arch_elements),
            "openings": len(self.openings),
            "stairs": len(self.stairs),
            "analysis_models": len(self.analysis_models),
            "analysis_results": len(self.analysis_results),
            "conflicts": len(self.conflicts),
            "variants": len(self.variants),
            "drawings": len(self.drawings),
            "approvals": len(self.approvals),
            "revisions": len(self.revisions),
        })
        return c

    # -- Fabriques (IDs stables via allocateur partagé) ------------------
    def new_level(self, name="", elevation=None, index=0,
                  height_above=None) -> Level:
        lid = self.new_id("STOREY")
        lv = Level(sc_id=lid, name=name, index=index)
        if elevation is not None:
            lv.elevation = TrackedValue.of(
                float(elevation), "m", DataStatus.PROVIDED,
                Provenance.provided_by("architecture"))
        if height_above is not None:
            lv.height_above = TrackedValue.of(
                float(height_above), "m", DataStatus.PROVIDED,
                Provenance.provided_by("architecture"))
        self.levels[lid] = lv
        return lv

    def new_axis(self, direction="X", position=None, label="") -> Axis:
        aid = self.new_id("AXIS")
        ax = Axis(sc_id=aid, direction=direction, label=label)
        if position is not None:
            ax.position = TrackedValue.of(
                float(position), "m", DataStatus.PROVIDED,
                Provenance.provided_by("architecture"))
        self.axes[aid] = ax
        return ax

    def new_opening(self, kind="", level_ref=None, cx=None, cy=None,
                    width=None, depth=None) -> Opening:
        oid = self.new_id("OPENING")
        op = Opening(sc_id=oid, kind=kind, level_ref=level_ref)
        for attr, v in (("cx", cx), ("cy", cy),
                        ("width", width), ("depth", depth)):
            if v is not None:
                setattr(op, attr, TrackedValue.of(
                    float(v), "m", DataStatus.PROVIDED,
                    Provenance.provided_by("architecture")))
        self.openings[oid] = op
        return op

    def new_arch_element(self, kind="", level_ref=None, structural_function="UNKNOWN",
                         outline=None) -> ArchitecturalElement:
        eid = self.new_id("ARCHELEM")
        el = ArchitecturalElement(sc_id=eid, kind=kind, level_ref=level_ref,
                                  structural_function=structural_function,
                                  outline=list(outline or []))
        self.arch_elements[eid] = el
        return el

    def new_conflict(self, kind, description="", level_ref=None,
                     element_ids=None, source="") -> Conflict:
        cid = self.new_id("CONFLICT")
        # Coercition str -> enum : le modèle ne stocke que des ConflictKind
        if not isinstance(kind, ConflictKind):
            kind = ConflictKind(str(kind))
        cf = Conflict(sc_id=cid, kind=kind, description=description,
                      level_ref=level_ref,
                      element_ids=list(element_ids or []), source=source)
        self.conflicts[cid] = cf
        return cf

    def new_variant(self, description="", is_reference=False) -> DesignVariant:
        vid = self.new_id("VARIANT")
        var = DesignVariant(sc_id=vid, description=description,
                            is_reference=is_reference)
        self.variants[vid] = var
        return var

    def new_drawing(self, kind="", level_ref=None, model_ref=None,
                    model_version=0, source_variant=None) -> Drawing:
        did = self.new_id("DRAWING")
        dr = Drawing(sc_id=did, kind=kind, level_ref=level_ref,
                     model_ref=model_ref, model_version=model_version,
                     source_variant=source_variant)
        self.drawings[did] = dr
        return dr

    # -- Statuts agrégés --------------------------------------------------
    def open_conflicts(self) -> List[Conflict]:
        """Conflits NON résolus (visibles, jamais masqués, §9.3)."""
        terminal = {"VALIDATED_FOR_DELIVERY", "REJECTED"}
        return [c for c in self.conflicts.values() if c.status not in terminal]

    def provisional_drawings(self) -> List[Drawing]:
        """Plans encore provisoires (sections non calculées / statut ouvert)."""
        early = {DeliveryStatus.DRAFT, DeliveryStatus.PRELIMINARY,
                 DeliveryStatus.UNDER_REVIEW}
        return [d for d in self.drawings.values()
                if d.status in early or d.sections_provisional]

    def outdated_results(self) -> List[AnalysisResult]:
        """Résultats périmés après modification (spec Module 71 §12)."""
        return [r for r in self.analysis_results.values() if r.outdated]
