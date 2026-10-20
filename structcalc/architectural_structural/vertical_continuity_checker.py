# -*- coding: utf-8 -*-
"""
architectural_structural/vertical_continuity_checker.py — Phase D (Module 71 §7.1).

Contrôle de la continuité des éléments porteurs entre les niveaux : poteaux
alignés / décalés / interrompus, changements de section, poutres de transfert,
éléments sans appui cohérent, éléments ne rejoignant pas les fondations.

Règle absolue (§7.1) : « Une discontinuité géométrique déclenche une analyse.
Elle ne doit pas être déclarée dangereuse ou acceptable sur la seule base de
la géométrie. » → ce module ne conclut PAS ; il produit des constats à analyser.

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .model_ext import ArchitecturalModel
from .geometry_normalization import dist2d as _dist


# Types de constat (aucun n'est une conclusion de sûreté)
ALIGN_ALIGNED = "ALIGNED"
ALIGN_OFFSET = "OFFSET"
ALIGN_INTERRUPTED = "INTERRUPTED"
ALIGN_SECTION_CHANGE = "SECTION_CHANGE"
ALIGN_NO_SUPPORT = "NO_SUPPORT"
ALIGN_NO_FOUNDATION = "NO_FOUNDATION"
ALIGN_TRANSFER = "TRANSFER_POSSIBLE"


@dataclass
class ContinuityFinding:
    """Constat de continuité — à ANALYSER, pas une conclusion (§7.1)."""
    element_kind: str               # column | wall
    lower_ref: Optional[str]        # SC-* niveau inférieur
    upper_ref: Optional[str]        # SC-* niveau supérieur (None si interrompu)
    position: Tuple[float, float]
    code: str                       # ALIGN_*
    detail: str
    requires_analysis: bool = True  # toujours True : jamais concluant seul

    def to_dict(self) -> dict:
        return {
            "kind": self.element_kind,
            "lower": self.lower_ref, "upper": self.upper_ref,
            "x": self.position[0], "y": self.position[1],
            "code": self.code, "detail": self.detail,
            "requires_analysis": self.requires_analysis,
        }


@dataclass
class ContinuityReport:
    findings: List[ContinuityFinding] = field(default_factory=list)

    @property
    def aligned(self) -> List[ContinuityFinding]:
        return [f for f in self.findings if f.code == ALIGN_ALIGNED]

    @property
    def needs_analysis(self) -> List[ContinuityFinding]:
        """Tout sauf ALIGN_ALIGNED — et même ALIGN est informatif (§7.1)."""
        return [f for f in self.findings if f.code != ALIGN_ALIGNED]

    def by_code(self, code: str) -> List[ContinuityFinding]:
        return [f for f in self.findings if f.code == code]

    @property
    def summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.code] = out.get(f.code, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {"summary": self.summary,
                "findings": [f.to_dict() for f in self.findings]}


TOL = 0.05   # tolérance d'alignement (m) — donnée, pas vérité


def check_vertical_continuity(
        model: ArchitecturalModel,
        level_order: Sequence[str],
        level_columns: Dict[str, List[dict]],
        sections_by_pos: Optional[Dict[Tuple[int, int, float, float], str]] = None
        ) -> ContinuityReport:
    """
    Compare les poteaux entre niveaux consécutifs.

    `level_order` : refs de niveaux du plus bas au plus haut.
    `level_columns` : {level_ref: [{"ref": SC-*, "x":, "y":, "section":}]}.
    `sections_by_pos` optionnel pour détecter les changements de section.

    Détecte (§7.1) : alignés, décalés, interrompus, changements de section.
    Aucun constat n'est déclaré dangereux ou acceptable — seulement signalé.
    """
    rep = ContinuityReport()
    if len(level_order) < 2:
        return rep

    for lower, upper in zip(level_order, level_order[1:]):
        low_cols = level_columns.get(lower, [])
        up_cols = level_columns.get(upper, [])

        for lc in low_cols:
            pos = (lc["x"], lc["y"])
            match = _nearest_column(pos, up_cols)
            if match is None:
                rep.findings.append(ContinuityFinding(
                    element_kind="column", lower_ref=lc.get("ref"),
                    upper_ref=None, position=pos, code=ALIGN_INTERRUPTED,
                    detail="Poteau interrompu : aucune continuation au niveau "
                           "supérieur. Analyse requise (transfert ? rupture ?)."))
                continue
            d = _dist(pos, (match["x"], match["y"]))
            if d > TOL:
                rep.findings.append(ContinuityFinding(
                    element_kind="column", lower_ref=lc.get("ref"),
                    upper_ref=match.get("ref"), position=pos,
                    code=ALIGN_OFFSET,
                    detail=f"Décalage {d:.3f} m entre étages. Analyse requise "
                           "(excentricité / poutre de transfert)."))
            else:
                # Changement de section ?
                sl = lc.get("section")
                su = match.get("section")
                if sl and su and sl != su:
                    rep.findings.append(ContinuityFinding(
                        element_kind="column", lower_ref=lc.get("ref"),
                        upper_ref=match.get("ref"), position=pos,
                        code=ALIGN_SECTION_CHANGE,
                        detail=f"Changement de section {sl} -> {su}. "
                               "Analyse requise."))
                else:
                    rep.findings.append(ContinuityFinding(
                        element_kind="column", lower_ref=lc.get("ref"),
                        upper_ref=match.get("ref"), position=pos,
                        code=ALIGN_ALIGNED,
                        detail="Poteau aligné entre étages (constat "
                               "géométrie, non validation)."))

        # Poteaux du niveau supérieur sans origine
        for uc in up_cols:
            pos = (uc["x"], uc["y"])
            if _nearest_column(pos, low_cols) is None:
                rep.findings.append(ContinuityFinding(
                    element_kind="column", lower_ref=None,
                    upper_ref=uc.get("ref"), position=pos,
                    code=ALIGN_NO_SUPPORT,
                    detail="Poteau sans origine au niveau inférieur : appui "
                           "à clarifier. Analyse requise."))

    return rep


def check_foundation_link(model: ArchitecturalModel,
                          bottom_columns: List[dict],
                          foundation_positions: Sequence[Tuple[float, float]]
                          ) -> ContinuityReport:
    """
    Contrôle que les poteaux du bas rejoignent des fondations (§7.1 dernier
    point). Les fondations doivent venir de la géotechnique (§10.1) — ici on
    ne fait que constater l'absence d'appui.
    """
    rep = ContinuityReport()
    for bc in bottom_columns:
        pos = (bc["x"], bc["y"])
        if not foundation_positions:
            rep.findings.append(ContinuityFinding(
                element_kind="column", lower_ref=bc.get("ref"), upper_ref=None,
                position=pos, code=ALIGN_NO_FOUNDATION,
                detail="Aucune fondation définie. NE PAS déduire la "
                       "fondation d'une trame seule (§10.1) : étude "
                       "géotechnique requise."))
            continue
        if _nearest_point(pos, foundation_positions) is None:
            rep.findings.append(ContinuityFinding(
                element_kind="column", lower_ref=bc.get("ref"), upper_ref=None,
                position=pos, code=ALIGN_NO_FOUNDATION,
                detail="Poteau sans fondation associée. Analyse requise."))
    return rep


def detect_transfer_possible(findings: ContinuityReport) -> List[ContinuityFinding]:
    """
    Signale les décalages/interruptions qui pourraient nécessiter une poutre
    de transfert (§5.1, §7.1). NE valide PAS le transfert — seulement signale.
    """
    out = []
    for f in findings.by_code(ALIGN_OFFSET) + findings.by_code(ALIGN_INTERRUPTED):
        f.code = ALIGN_TRANSFER
        f.detail += " | Poutre de transfert éventuelle à vérifier (§5.1)."
        out.append(f)
    return out


# Helpers -------------------------------------------------------------------

def _nearest_column(pos, cols):
    if not cols:
        return None
    return min(cols, key=lambda c: _dist(pos, (c["x"], c["y"])))


def _nearest_point(pos, pts):
    if not pts:
        return None
    return min(pts, key=lambda p: _dist(pos, p))
