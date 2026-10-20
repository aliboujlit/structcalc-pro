# -*- coding: utf-8 -*-
"""
architectural_structural — MODULE 71 : Architectural-to-Structural Formwork
Engine (spec Module 71).

Transformation d'un dossier architectural en proposition de modèle structurel,
puis en plans de coffrage cohérents avec les hypothèses, calculs et décisions
validés par le BET.

Chaîne (§17) :
  IMPORT -> MODÈLE INTERNE -> PROPOSITION -> CHARGES -> ROBOT ->
  RÉSULTATS -> VÉRIFICATIONS -> COORDINATION -> CORRECTIONS ->
  RECALCUL -> PLANS DE COFFRAGE -> CONTRÔLE QUALITÉ -> VALIDATION -> DIFFUSION

Sous-modules (§14) — interfaces abstraites, moteurs séparés (§14) :
  - architectural_import_service : adaptateurs Revit/IFC/DWG/PDF (§4.1)
  - geometry_normalization       : unités/échelles/doublons (§4.4)
  - axis_grid_engine             : trame d'axes, alignements (§3, §5.2)
  - structural_layout_proposal   : proposition système porteur + variantes (§5)
  - vertical_continuity_checker  : continuité verticale (§7.1)
  - opening_reservation_checker  : ouvertures/trémies/gaines (§9.1)
  - structural_model_builder     : modèle canonique SC-* + analytique (§6)
  - load_transfer_linker         : liaison charges, anti-double-comptage (§7.2)
  - conflict_detection_engine    : conflits archi–structure (§9)
  - design_variant_manager       : variantes A/B/C/D versionnées (§5.3)
  - robot_exchange_coordinator   : échange Robot + 7 contrôles (§8.3)
  - drawing_generation_coordinator : plans de coffrage (§10)
  - change_impact_dispatcher     : impact des modifications (§12)
  - model_drawing_consistency_checker : cohérence modèle/documents (§13)
  - validation_gate              : portes de validation avant diffusion (§13)
  - model_ext                    : objets étendus (§6.1)

Règles fondamentales encodées (§16, §17) :
  - un plan n'est JAMAIS validé parce qu'il a été généré automatiquement ;
  - aucune conformité sans vérification (ingénieur) ;
  - les résultats affectés par une modification sont PÉRIMÉS (OUTDATED) ;
  - aucune donnée manquante n'est inventée.
"""

from .model_ext import (
    ArchitecturalModel, Level, Axis, ArchitecturalElement, Opening, Stair,
    AnalysisModel, AnalysisResult, Conflict, ConflictKind, DesignVariant,
    Drawing, Approval, Revision, Representation, DeliveryStatus,
    CONFLICT_TRANSITIONS, DELIVERY_TRANSITIONS,
)
from .architectural_import_service import (
    ArchitecturalImporter, RawGeometryImporter, RevitImporter, IfcImporter,
    DwgImporter, PdfImporter, get_importer, available_formats,
    import_architectural_source,
)
from .geometry_normalization import (
    ImportReport, ImportIssue, detect_scale, normalize_levels, normalize_axes,
    normalize_openings, spacing_between, flag_unknown_function,
)
from .axis_grid_engine import (
    GridProposal, build_grid, aligned_across_levels,
)
from .structural_layout_proposal import (
    LayoutProposal, ProposedMember, propose_layout, create_variants,
    move_column_documented,
)
from .vertical_continuity_checker import (
    ContinuityReport, ContinuityFinding, check_vertical_continuity,
    check_foundation_link, detect_transfer_possible,
)
from .opening_reservation_checker import (
    OpeningReport, OpeningCheck, check_openings_against_members,
    check_shaft_near_member,
)
from .structural_model_builder import (
    BuildReport, build_structural_model, build_analysis_model,
    next_analysis_version,
)
from .load_transfer_linker import (
    LoadEntry, LoadTransferReport, link_loads, SlabRepartition,
    check_slab_repartition,
)
from .conflict_detection_engine import (
    Rect, detect_column_vs_opening, detect_beam_vs_clear_height,
    detect_stairwell_vs_beam, detect_structural_discontinuity,
    detect_documentary_conflict, conflict_register,
)
from .design_variant_manager import (
    VariantManager, VariantComparison,
)
from .robot_exchange_coordinator import (
    ExchangeReport, ExchangeCheck, preflight_send, receive_results,
    receive_and_validate, CHECK_LABELS,
)
from .drawing_generation_coordinator import (
    DrawingContent, generate_formwork_drawing, generate_drawing_set,
    drawing_content, is_formwork_vs_rebar, R3_DRAWING_SET,
)
from .change_impact_dispatcher import (
    ImpactReport, dispatch_change, stale_results,
    CHANGE_MOVE_COLUMN, CHANGE_REMOVE_COLUMN, CHANGE_CHANGE_SECTION,
    CHANGE_CHANGE_SPAN, CHANGE_MOVE_SUPPORT, CHANGE_ARCH_OPENING,
)
from .model_drawing_consistency_checker import (
    ConsistencyReport, ConsistencyFinding,
    check_model_drawing_consistency, reports_and_drawings_match,
)
from .validation_gate import (
    ValidationGate, ValidationState, GateResult,
    CONTROL_GEOMETRIC, CONTROL_ANALYTIC, CONTROL_REGULATORY,
    CONTROL_DOCUMENTARY, ALL_CONTROLS,
)

__all__ = [
    # modèle
    "ArchitecturalModel", "Level", "Axis", "ArchitecturalElement", "Opening",
    "Stair", "AnalysisModel", "AnalysisResult", "Conflict", "ConflictKind",
    "DesignVariant", "Drawing", "Approval", "Revision", "Representation",
    "DeliveryStatus", "CONFLICT_TRANSITIONS", "DELIVERY_TRANSITIONS",
    # import
    "ArchitecturalImporter", "RawGeometryImporter", "RevitImporter",
    "IfcImporter", "DwgImporter", "PdfImporter", "get_importer",
    "available_formats", "import_architectural_source",
    # géométrie / trame
    "ImportReport", "ImportIssue", "detect_scale", "normalize_levels",
    "normalize_axes", "normalize_openings", "spacing_between",
    "flag_unknown_function", "GridProposal", "build_grid",
    "aligned_across_levels",
    # proposition / continuité / ouvertures
    "LayoutProposal", "ProposedMember", "propose_layout", "create_variants",
    "move_column_documented", "ContinuityReport", "ContinuityFinding",
    "check_vertical_continuity", "check_foundation_link",
    "detect_transfer_possible", "OpeningReport", "OpeningCheck",
    "check_openings_against_members", "check_shaft_near_member",
    # modèle / charges
    "BuildReport", "build_structural_model", "build_analysis_model",
    "next_analysis_version", "LoadEntry", "LoadTransferReport", "link_loads",
    "SlabRepartition", "check_slab_repartition",
    # conflits / variantes
    "Rect", "detect_column_vs_opening", "detect_beam_vs_clear_height",
    "detect_stairwell_vs_beam", "detect_structural_discontinuity",
    "detect_documentary_conflict", "conflict_register",
    "VariantManager", "VariantComparison",
    # robot / plans / impact / cohérence / validation
    "ExchangeReport", "ExchangeCheck", "preflight_send", "receive_results",
    "receive_and_validate", "CHECK_LABELS", "DrawingContent",
    "generate_formwork_drawing", "generate_drawing_set", "drawing_content",
    "is_formwork_vs_rebar", "R3_DRAWING_SET", "ImpactReport",
    "dispatch_change", "stale_results", "CHANGE_MOVE_COLUMN",
    "CHANGE_REMOVE_COLUMN", "CHANGE_CHANGE_SECTION", "CHANGE_CHANGE_SPAN",
    "CHANGE_MOVE_SUPPORT", "CHANGE_ARCH_OPENING", "ConsistencyReport",
    "ConsistencyFinding", "check_model_drawing_consistency",
    "reports_and_drawings_match", "ValidationGate", "ValidationState",
    "GateResult", "CONTROL_GEOMETRIC", "CONTROL_ANALYTIC",
    "CONTROL_REGULATORY", "CONTROL_DOCUMENTARY", "ALL_CONTROLS",
]
