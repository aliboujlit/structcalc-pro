# -*- coding: utf-8 -*-
"""
architectural_structural/geometry_normalization.py — Phase A (Module 71 §4).

Normalisation géométrique de l'import architectural : unités, échelles,
doublons, niveaux incohérents, axes manquants/contradictoires, ouvertures
chevauchantes, éléments à fonction ambiguë.

Règle (§4.4) : les erreurs BLOQUANTES doivent être résolues avant toute
création d'un modèle structurel exploitable. Ce module ne corrige jamais
silencieusement : il signale (DataStatus.CONFLICT / MISSING).

100 % pur (aucune dépendance COM/Qt) — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .model_ext import ArchitecturalModel, Level, Axis, Opening


# Unités de longueur reconnues -> facteur vers les mètres
LENGTH_UNITS = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "in": 0.0254,
}


def dist2d(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance euclidienne 2D (m). Helper partagé — évite la duplication."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def dist3d(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance euclidienne 3D (m). Helper partagé — évite la duplication."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


@dataclass
class ImportIssue:
    """Un problème d'import. `blocking=True` => empêche le modèle structurel."""
    code: str
    message: str
    blocking: bool = False
    object_id: str = ""
    severity: str = "ERROR"      # ERROR | WARNING

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "blocking": self.blocking, "object": self.object_id,
                "severity": self.severity}


@dataclass
class ImportReport:
    """Rapport d'import/normalisation (§4.4)."""
    issues: List[ImportIssue] = field(default_factory=list)
    units_detected: str = ""
    scale_factor: float = 1.0
    levels_found: int = 0
    axes_found: int = 0
    elements_found: int = 0

    # -- Accès ------------------------------------------------------------
    @property
    def blocking_issues(self) -> List[ImportIssue]:
        return [i for i in self.issues if i.blocking]

    @property
    def has_blocking(self) -> bool:
        return bool(self.blocking_issues)

    def ok(self) -> bool:
        """Aucune erreur bloquante => modèle structurel autorisé (§4.4)."""
        return not self.has_blocking

    def to_dict(self) -> dict:
        return {
            "units": self.units_detected,
            "scale_factor": self.scale_factor,
            "levels": self.levels_found,
            "axes": self.axes_found,
            "elements": self.elements_found,
            "issues": [i.to_dict() for i in self.issues],
            "blocking": len(self.blocking_issues),
            "ok": self.ok(),
        }


# ---------------------------------------------------------------------------
# Unités et échelles
# ---------------------------------------------------------------------------

def detect_scale(unit: str, report: ImportReport) -> float:
    """
    Détermine le facteur vers les mètres. Unité inconnue => BLOQUANT
    (§4.4 « contrôler les unités »), jamais supposée = mètre.
    """
    key = str(unit or "").strip().lower()
    if key in LENGTH_UNITS:
        report.units_detected = key
        report.scale_factor = LENGTH_UNITS[key]
        return report.scale_factor
    report.issues.append(ImportIssue(
        code="UNIT_UNKNOWN",
        message=f"Unité de longueur non reconnue : {unit!r}. "
                "Conversion impossible sans hypothèse — résoudre avant import.",
        blocking=True, severity="ERROR"))
    report.scale_factor = 1.0
    return 1.0


def to_meters(value: float, scale: float) -> float:
    return float(value) * float(scale)


# ---------------------------------------------------------------------------
# Niveaux
# ---------------------------------------------------------------------------

def normalize_levels(model: ArchitecturalModel,
                     raw_levels: Sequence[dict],
                     report: ImportReport,
                     scale: float = 1.0) -> List[Level]:
    """
    Construit les niveaux depuis des données brutes [{name, elevation, height}].

    Contrôles §4.4 :
      - altitudes DOUBLONS (2 niveaux même altitude) -> CONFLICT ;
      - altitude MANQUANTE -> bloquant ;
      - ordre croissant des altitudes (sinon WARNING).
    """
    levels: List[Level] = []
    seen_elev: Dict[float, str] = {}
    for i, raw in enumerate(raw_levels):
        name = raw.get("name", f"N{i}")
        elev = raw.get("elevation")
        height = raw.get("height")
        if elev is None:
            report.issues.append(ImportIssue(
                code="LEVEL_ELEVATION_MISSING",
                message=f"Niveau {name!r} sans altitude — donnée manquante "
                        "(jamais inventée).",
                blocking=True))
            lv = model.new_level(name=name, index=i)
            levels.append(lv)
            continue
        elev_m = to_meters(elev, scale)
        height_m = to_meters(height, scale) if height is not None else None
        # Doublon d'altitude ?
        if any(abs(elev_m - e) < 1e-6 for e in seen_elev):
            report.issues.append(ImportIssue(
                code="LEVEL_DUPLICATE_ELEVATION",
                message=f"Niveau {name!r} partage l'altitude {elev_m:.3f} m "
                        f"avec {seen_elev.get(elev_m, '?')!r}.",
                blocking=True))
        seen_elev[elev_m] = name
        lv = model.new_level(name=name, elevation=elev_m, index=i,
                             height_above=height_m)
        levels.append(lv)

    # Ordre croissant ?
    elevs = [float(lv.elevation.value) for lv in levels
             if not lv.elevation.is_missing]
    if elevs != sorted(elevs):
        report.issues.append(ImportIssue(
            code="LEVEL_ORDER",
            message="Altitudes non croissantes — vérifier l'ordre des niveaux.",
            blocking=False, severity="WARNING"))

    report.levels_found = len(levels)
    return levels


# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------

def normalize_axes(model: ArchitecturalModel,
                   raw_axes_x: Sequence[float],
                   raw_axes_y: Sequence[float],
                   report: ImportReport,
                   scale: float = 1.0) -> List[Axis]:
    """
    Construit les axes X et Y depuis les positions brutes.

    Contrôles §4.4 :
      - axes MANQUANTS (une direction vide) -> bloquant (pas de trame) ;
      - axes DOUBLONS / trop proches (< 0.01 m) -> bloquant (contradictoire) ;
      - labellisation automatique (1..n pour X, A.. pour Y).
    """
    axes: List[Axis] = []
    if not raw_axes_x or not raw_axes_y:
        report.issues.append(ImportIssue(
            code="AXIS_MISSING_DIRECTION",
            message="Direction d'axe vide : trame incomplète "
                    "(X et Y requis).",
            blocking=True))
    for direction, raws, labels in (
            ("X", raw_axes_x, None),
            ("Y", raw_axes_y, None)):
        positions: List[float] = []
        for i, r in enumerate(raws):
            pos = to_meters(r, scale)
            # Doublon / proximité
            if any(abs(pos - p) < 0.01 for p in positions):
                report.issues.append(ImportIssue(
                    code="AXIS_DUPLICATE",
                    message=f"Axe {direction}#{i+1} à {pos:.3f} m en "
                            "doublon ou quasi confondu.",
                    blocking=True))
                continue
            positions.append(pos)
        # Tri pour labellisation stable
        order = sorted(range(len(positions)), key=lambda i: positions[i])
        for n, idx in enumerate(order, start=1):
            label = str(n) if direction == "X" else _col_label(n)
            ax = model.new_axis(direction=direction,
                                position=positions[idx], label=label)
            axes.append(ax)
        positions.clear()
    report.axes_found = len(axes)
    return axes


def _col_label(n: int) -> str:
    """1 -> 'A', 2 -> 'B', ... 27 -> 'AA'."""
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


# ---------------------------------------------------------------------------
# Entraxes / cotations
# ---------------------------------------------------------------------------

def spacing_between(axes: Sequence[Axis], direction: str) -> List[Tuple[str, str, float]]:
    """
    Entraxes (spécification Module 71 §3 : 5,00 m) CALCULÉES entre axes
    consécutifs d'une même direction. Retourne [(label_avant, label_après, d)].
    """
    sel = [a for a in axes if a.direction == direction and not a.position.is_missing]
    sel.sort(key=lambda a: float(a.position.value))
    out = []
    for a, b in zip(sel, sel[1:]):
        d = float(b.position.value) - float(a.position.value)
        out.append((a.label, b.label, round(d, 6)))
    return out


# ---------------------------------------------------------------------------
# Ouvertures
# ---------------------------------------------------------------------------

def normalize_openings(model: ArchitecturalModel,
                       raw_openings: Sequence[dict],
                       report: ImportReport,
                       scale: float = 1.0) -> List[Opening]:
    """
    Construit les ouvertures [{kind, level, cx, cy, w, d}].

    Contrôle §4.4 : ouvertures SE CHEVAUCHANT -> CONFLICT (signalé, jamais
    fusionnées silencieusement).
    """
    openings: List[Opening] = []
    for raw in raw_openings:
        w = raw.get("width")
        d = raw.get("depth", w)
        if w is None:
            report.issues.append(ImportIssue(
                code="OPENING_DIM_MISSING",
                message=f"Ouverture {raw.get('kind','?')} sans largeur.",
                blocking=True))
            continue
        op = model.new_opening(
            kind=raw.get("kind", ""),
            level_ref=raw.get("level_ref"),
            cx=raw.get("cx"), cy=raw.get("cy"),
            width=to_meters(w, scale),
            depth=to_meters(d, scale) if d is not None else None)
        openings.append(op)

    # Chevauchements (même niveau)
    for i in range(len(openings)):
        for j in range(i + 1, len(openings)):
            a, b = openings[i], openings[j]
            if a.level_ref != b.level_ref:
                continue
            if _rect_overlap(a, b):
                report.issues.append(ImportIssue(
                    code="OPENING_OVERLAP",
                    message=f"Ouvertures {a.sc_id} et {b.sc_id} se chevauchent.",
                    blocking=False, severity="WARNING",
                    object_id=a.sc_id))
    return openings


def _rect_overlap(a: Opening, b: Opening) -> bool:
    if any(v.is_missing for v in (a.cx, a.cy, a.width, a.depth,
                                  b.cx, b.cy, b.width, b.depth)):
        return False
    ax, ay = float(a.cx.value), float(a.cy.value)
    bx, by = float(b.cx.value), float(b.cy.value)
    aw, ad = float(a.width.value), float(a.depth.value)
    bw, bd = float(b.width.value), float(b.depth.value)
    return (abs(ax - bx) < (aw + bw) / 2.0 and
            abs(ay - by) < (ad + bd) / 2.0)


# ---------------------------------------------------------------------------
# Fonction structurelle ambiguë
# ---------------------------------------------------------------------------

def flag_unknown_function(model: ArchitecturalModel,
                          report: ImportReport) -> int:
    """
    Signale les éléments architecturaux dont la fonction est INCONNUE (§4.2).
    N'attribue jamais une fonction — retourne juste le nombre à confirmer.
    """
    n = 0
    for el in model.arch_elements.values():
        if el.structural_function == "UNKNOWN":
            n += 1
            report.issues.append(ImportIssue(
                code="FUNCTION_UNKNOWN",
                message=f"Élément {el.sc_id} ({el.kind}) : fonction "
                        "structurelle inconnue — confirmation requise.",
                blocking=False, severity="WARNING", object_id=el.sc_id))
    return n
