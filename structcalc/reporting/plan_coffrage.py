# -*- coding: utf-8 -*-
"""
reporting/plan_coffrage.py — Plans de coffrage PDF vectoriels (spec §15).

Source de vérité UNIQUE : le pivot chargé (nœuds/poteaux/poutres RÉELLEMENT
lus dans Robot/AutoCAD). Règles d'honnêteté absolues :

  - les dimensions de section sont DÉDUITES du nom de label Robot, convention
    « R<b>x<h> » en centimètres (ex. « C R30x30 » -> 30 x 30 cm). Cette
    déduction est TRACÉE sur le plan même (mention + avertissement) ;
  - un nom de section non interprétable -> poteau dessiné au point d'axe et
    marqué « section non cotée » — JAMAIS une dimension devinée ;
  - 0 poteau/exploitable = 0 plan (refus EXPLICITE, jamais un plan vide
    présenté comme un succès) ;
  - l'échelle affichée est l'échelle RÉELLE d'impression A3 calculée depuis
    les extents du dessin (pas un « 1:50 » décoratif).

PDF vectoriel (reportlab canvas) — A3 paysage, un niveau par page,
axes cotés + chaîne de cotes + cartouche.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Tolérance d'appariement de niveau (m)
LEVEL_TOL = 0.05
# Bornes de crédibilité d'une section déduite (cm) — au-delà : refus de
# l'interprétation (jamais une dimension farfelue sur un plan)
DIM_MIN_CM = 5.0
DIM_MAX_CM = 200.0

# Conventions de dessin (mm A3 paysage)
PAGE_W_MM, PAGE_H_MM = 420.0, 297.0
MARGIN_MM = 12.0
CARTOUCHE_H_MM = 26.0


# ---------------------------------------------------------------------------
# Parsing des noms de sections Robot (données RÉELLES, déduction tracée)
# ---------------------------------------------------------------------------

_SEC_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)",
                     re.IGNORECASE)


def parse_section_dims(name: str) -> Optional[Tuple[float, float]]:
    """
    Déduit (b_cm, h_cm) d'un nom de section Robot (convention « R<b>x<h> »).

    Retourne None si le nom n'est PAS interprétable dans la convention
    (jamais de dimension inventée). Les valeurs hors bornes [5; 200] cm sont
    rejetées (signal d'interprétation fausse).
    """
    if not name:
        return None
    m = _SEC_RE.search(str(name))
    if not m:
        return None
    try:
        b = float(m.group(1).replace(",", "."))
        h = float(m.group(2).replace(",", "."))
    except ValueError:
        return None
    if not (DIM_MIN_CM <= b <= DIM_MAX_CM and DIM_MIN_CM <= h <= DIM_MAX_CM):
        return None
    return (b, h)


# ---------------------------------------------------------------------------
# Géométrie du plan (m, indépendant de tout backend de rendu)
# ---------------------------------------------------------------------------

@dataclass
class PlanColumn:
    sc_id: str
    x: float                 # m
    y: float                 # m
    dims_cm: Optional[Tuple[float, float]]   # None = section non cotée
    section_name: str = ""


@dataclass
class PlanBeam:
    sc_id: str
    p1: Tuple[float, float]
    p2: Tuple[float, float]
    width_cm: Optional[float]               # None = largeur non déduite
    section_name: str = ""


@dataclass
class LevelPlan:
    """Plan de coffrage d'un niveau (données en m, source = pivot)."""
    z: float                              # niveau (m)
    label: str = ""                       # nom de storey si apparié
    columns: List[PlanColumn] = field(default_factory=list)
    beams: List[PlanBeam] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.columns and not self.beams


def _node_xyz(node) -> Optional[Tuple[float, float, float]]:
    try:
        if node.x.is_missing or node.y.is_missing or node.z.is_missing:
            return None
        return (float(node.x.value), float(node.y.value),
                float(node.z.value))
    except Exception:
        return None


def build_level_plans(project) -> List[LevelPlan]:
    """
    Découpe le pivot en plans de niveau : chaque niveau = plan horizontal
    au sommet des poteaux qui s'y terminent + poutres horizontales du
    niveau. Les storeys du pivot (si présents) nomment les niveaux.
    Aucune géométrie n'est inventée : seuls les objets avec nœuds lisibles
    et classification réelle (poteau/poutre) apparaissent.
    """
    nodes = getattr(project, "nodes", {}) or {}
    storeys = getattr(project, "storeys", {}) or {}

    # Niveaux = z distincts des extrémités de poteaux (regroupés à LEVEL_TOL)
    z_groups: List[List[float]] = []
    col_rows = []
    for cid, col in (getattr(project, "columns", {}) or {}).items():
        n1 = nodes.get(col.start_node)
        n2 = nodes.get(col.end_node)
        p1 = _node_xyz(n1) if n1 is not None else None
        p2 = _node_xyz(n2) if n2 is not None else None
        if p1 is None or p2 is None:
            continue                       # géométrie illisible -> non dessiné
        if abs(p1[2] - p2[2]) < 1e-9:
            continue                       # poteau horizontal : incohérent
        top = p1 if p1[2] > p2[2] else p2
        col_rows.append((top, col))
        z = top[2]
        for g in z_groups:
            if abs(z - g[0]) <= LEVEL_TOL:
                g.append(z)
                break
        else:
            z_groups.append([z])

    if not z_groups:
        return []
    z_groups.sort(key=lambda g: sum(g) / len(g))

    # Nommage des niveaux par storeys du pivot (appariement toléré)
    storey_by_z: Dict[float, str] = {}
    for st in storeys.values():
        try:
            if st.level.is_missing:
                continue
            storey_by_z[round(float(st.level.value), 2)] = \
                (st.name or st.sc_id)
        except Exception:
            continue

    plans: List[LevelPlan] = []
    for g in z_groups:
        zlev = sum(g) / len(g)
        label = ""
        for zs, nm in storey_by_z.items():
            if abs(zs - zlev) <= LEVEL_TOL:
                label = nm
                break
        plans.append(LevelPlan(z=zlev, label=label))

    # Poteaux affectés à leur niveau (sommet)
    for top, col in col_rows:
        lp = min(plans, key=lambda L: abs(L.z - top[2]))
        if abs(lp.z - top[2]) > LEVEL_TOL:
            continue
        sec_name = ""
        sec = (getattr(project, "sections", {}) or {}).get(col.section)
        if sec is not None:
            sec_name = str(sec.name or "")
        dims = parse_section_dims(sec_name)
        lp.columns.append(PlanColumn(
            sc_id=col.sc_id, x=top[0], y=top[1],
            dims_cm=dims, section_name=sec_name))
        if dims is None and sec_name:
            lp.notes.append(f"{col.sc_id} : section « {sec_name} » non "
                            f"interprétable (convention R<b>x<h>) — dessinée "
                            f"au point d'axe, NON cotée.")
        elif not sec_name:
            lp.notes.append(f"{col.sc_id} : aucune section liée — dessiné au "
                            f"point d'axe, NON coté.")

    # Poutres horizontales du niveau (extrémités au même z, appariées à un
    # niveau de plan)
    for bid, beam in (getattr(project, "beams", {}) or {}).items():
        n1 = nodes.get(beam.start_node)
        n2 = nodes.get(beam.end_node)
        p1 = _node_xyz(n1) if n1 is not None else None
        p2 = _node_xyz(n2) if n2 is not None else None
        if p1 is None or p2 is None:
            continue
        if abs(p1[2] - p2[2]) > LEVEL_TOL:
            continue                       # poutre non horizontale -> ignorée
        zlev = (p1[2] + p2[2]) / 2.0
        lp = min(plans, key=lambda L: abs(L.z - zlev))
        if abs(lp.z - zlev) > LEVEL_TOL:
            continue
        sec_name = ""
        sec = (getattr(project, "sections", {}) or {}).get(beam.section)
        if sec is not None:
            sec_name = str(sec.name or "")
        dims = parse_section_dims(sec_name)
        lp.beams.append(PlanBeam(
            sc_id=bid, p1=(p1[0], p1[1]), p2=(p2[0], p2[1]),
            width_cm=(dims[0] if dims else None), section_name=sec_name))

    return [lp for lp in plans if not lp.empty]


# ---------------------------------------------------------------------------
# Rendu PDF (reportlab canvas, vectoriel)
# ---------------------------------------------------------------------------

def _fmt_len(m: float) -> str:
    return f"{m:.2f}"


def coffrage_pdf(project, path: str, project_name: str = "") -> str:
    """
    Écrit le(s) plan(s) de coffrage PDF (un niveau par page, A3 paysage).
    Retourne le chemin écrit. Lève une erreur EXPLICITE si le pivot est
    vide ou si reportlab manque (jamais de faux succès, spec §0).
    """
    try:
        from reportlab.lib.colors import Color, HexColor, black, white
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.pdfgen import canvas as pdfcanvas
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Plan de coffrage impossible : 'reportlab' indisponible "
            f"({exc}).") from exc

    plans = build_level_plans(project)
    plans = [lp for lp in plans if lp.columns]     # page = niveau porteur
    if not plans:
        raise RuntimeError(
            "Aucun plan de coffrage produisible : le projet chargé ne "
            "contient AUCUN poteau avec géométrie lisible (0 objet = "
            "0 plan, rien n'est inventé).")

    name = project_name or str(getattr(project, "name", "") or "Projet")
    src = str(getattr(project, "source_file", "") or "pivot STRUCTCALC")
    from ..version import __version__
    today = datetime.now().strftime("%d/%m/%Y %H:%M")

    c = pdfcanvas.Canvas(path, pagesize=landscape(A3))
    pw, ph = PAGE_W_MM, PAGE_H_MM   # unités mm via setFont/e scaleFactor
    scale = 72.0 / 25.4             # mm -> points PDF

    def mm(v: float) -> float:
        return v * scale

    for idx, lp in enumerate(plans, start=1):
        _draw_level_page(c, lp, idx, len(plans), name, src, today,
                         __version__, mm, pw, ph)
        c.showPage()
    c.save()
    return path


def _draw_level_page(c, lp: LevelPlan, page_no: int, page_total: int,
                     name: str, src: str, today: str, version: str,
                     mm, pw: float, ph: float) -> None:
    from reportlab.lib.colors import HexColor, black, white

    # -- Zone de dessin (mm) --
    x0 = MARGIN_MM
    y0 = MARGIN_MM + CARTOUCHE_H_MM + 14.0     # bandeau titre
    x1 = pw - MARGIN_MM
    y1 = ph - MARGIN_MM - 10.0
    dw, dh = x1 - x0, y1 - y0

    # -- Extents du contenu (m) --
    xs: List[float] = []
    ys: List[float] = []
    for col in lp.columns:
        xs.append(col.x)
        ys.append(col.y)
    for bm in lp.beams:
        xs += [bm.p1[0], bm.p2[0]]
        ys += [bm.p1[1], bm.p2[1]]
    cx0, cx1 = min(xs), max(xs)
    cy0, cy1 = min(ys), max(ys)
    span_x = max(cx1 - cx0, 0.5)
    span_y = max(cy1 - cy0, 0.5)
    # échelle RÉELLE d'impression (mm de page / m de terrain), marge 8%
    scale_mm_per_m = min(dw * 0.92 / span_x, dh * 0.92 / span_y)
    ratio = dw / dh
    # bbox carrée de dessin centrée
    draw_w_m = dw / scale_mm_per_m
    draw_h_m = dh / scale_mm_per_m
    if span_x / span_y > ratio:
        draw_h_m = draw_w_m * span_y / span_x
    else:
        draw_w_m = draw_h_m * span_x / span_y
    offx = x0 + (dw - draw_w_m * scale_mm_per_m) / 2
    offy = y0 + (dh - draw_h_m * scale_mm_per_m) / 2

    def px(xm: float) -> float:
        return mm(offx + (xm - cx0) * scale_mm_per_m)

    def px_y(ym: float) -> float:
        return mm(offy + (ym - cy0) * scale_mm_per_m)

    # -- Cadre --
    c.setLineWidth(1.0)
    c.setStrokeColor(black)
    c.rect(mm(x0 - 4), mm(y0 - 4), mm(dw + 8), mm(dh + 8))

    # -- Axes (abscisses numérotées / ordonnées lettered) --
    ax_x = sorted({round(v, 2) for v in xs})
    ax_y = sorted({round(v, 2) for v in ys})
    letters = "ABCDEFGHIJKLMNOP"
    c.setDash(1, 3)
    c.setLineWidth(0.3)
    c.setStrokeColor(HexColor("#888888"))
    for i, xv in enumerate(ax_x):
        c.line(mm(x0 - 2), px_y(cy0), mm(x0 - 2), mm(y1))
        c.setDash()
        c.circle(mm(x0 - 2), mm(y1 + 4), mm(3.0), stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(mm(x0 - 2), mm(y1 + 2.6), str(i + 1))
        c.setDash(1, 3)
    for j, yv in enumerate(ax_y):
        c.line(px(cx0), mm(y0 - 2), mm(x1), mm(y0 - 2))
        c.setDash()
        c.circle(mm(x1 + 4), mm(y0 - 2), mm(3.0), stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(mm(x1 + 4), mm(y0 - 2 - 1.4),
                            letters[j] if j < len(letters) else f"Z{j+1}")
        c.setDash(1, 3)
    c.setDash()

    # -- Poutres : double ligne (largeur déduite) ou axe (largeur inconnue) --
    for bm in lp.beams:
        xA, yA = px(bm.p1[0]), px_y(bm.p1[1])
        xB, yB = px(bm.p2[0]), px_y(bm.p2[1])
        if bm.width_cm:
            w_m = (bm.width_cm / 100.0) * scale_mm_per_m / 2.0
            dx, dy = xB - xA, yB - yA
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * w_m, dx / L * w_m
            c.setStrokeColor(HexColor("#1a4f8b"))
            c.setLineWidth(0.6)
            c.line(mm(x0) + xA + nx, mm(y0) + yA + ny,
                   mm(x0) + xB + nx, mm(y0) + yB + ny)
            c.line(mm(x0) + xA - nx, mm(y0) + yA - ny,
                   mm(x0) + xB - nx, mm(y0) + yB - ny)
        else:
            c.setStrokeColor(HexColor("#1a4f8b"))
            c.setLineWidth(0.3)
            c.setDash(3, 2)
            c.line(mm(x0) + xA, mm(y0) + yA, mm(x0) + xB, mm(y0) + yB)
            c.setDash()

    # -- Poteaux : rectangles cotés (ou croix au point d'axe) --
    c.setLineWidth(0.8)
    for col in lp.columns:
        X, Y = px(col.x), px_y(col.y)
        if col.dims_cm:
            b_m = (col.dims_cm[0] / 100.0) * scale_mm_per_m / 2.0
            h_m = (col.dims_cm[1] / 100.0) * scale_mm_per_m / 2.0
            c.setFillColor(HexColor("#D9E2F3"))
            c.setStrokeColor(black)
            c.rect(mm(x0) + X - b_m, mm(y0) + Y - h_m,
                   2 * b_m, 2 * h_m, stroke=1, fill=1)
        else:
            c.setStrokeColor(HexColor("#C00000"))
            c.setLineWidth(0.5)
            c.line(mm(x0) + X - 2, mm(y0) + Y - 2,
                   mm(x0) + X + 2, mm(y0) + Y + 2)
            c.line(mm(x0) + X - 2, mm(y0) + Y + 2,
                   mm(x0) + X + 2, mm(y0) + Y - 2)

    # -- Chaîne de cotes horizontale (sous le dessin) --
    c.setStrokeColor(black)
    c.setLineWidth(0.3)
    c.setFont("Helvetica", 6)
    if len(ax_x) >= 2:
        ychain = y0 - 1.0
        for i in range(len(ax_x) - 1):
            xa, xb = px(ax_x[i]), px(ax_x[i + 1])
            c.line(mm(x0) + xa, mm(ychain), mm(x0) + xb, mm(ychain))
            c.drawCentredString(mm(x0) + (xa + xb) / 2, mm(ychain - 2.6),
                                _fmt_len(ax_x[i + 1] - ax_x[i]))
        c.line(mm(x0) + px(ax_x[0]), mm(ychain - 1.4),
               mm(x0) + px(ax_x[-1]), mm(ychain - 1.4))
        c.drawCentredString(mm(x0) + (px(ax_x[0]) + px(ax_x[-1])) / 2,
                            mm(ychain - 4.4), _fmt_len(ax_x[-1] - ax_x[0]))

    # -- Bandeau titre --
    lvl = lp.label or f"niveau z = {lp.z:+.2f} m"
    c.setFont("Helvetica-Bold", 12)
    c.drawString(mm(x0), mm(ph - MARGIN_MM - 4),
                 f"PLAN DE COFFRAGE — {lvl}")
    c.setFont("Helvetica", 8)
    c.drawRightString(mm(x1), mm(ph - MARGIN_MM - 4),
                      f"{name} — page {page_no}/{page_total} — échelle "
                      f"approx. 1:{max(1, round(1000.0 / scale_mm_per_m / 5) * 5)}")

    # -- Cartouche --
    c.setLineWidth(0.5)
    c.rect(mm(MARGIN_MM), mm(MARGIN_MM), mm(pw - 2 * MARGIN_MM),
           mm(CARTOUCHE_H_MM), stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(mm(MARGIN_MM + 3), mm(MARGIN_MM + CARTOUCHE_H_MM - 5),
                 f"STRUCTCALC PRO v{version} — plan de coffrage « {lvl} »")
    c.setFont("Helvetica", 6.5)
    lines = [
        f"Projet : {name}    Source : {src}    Généré le {today}",
        f"Contenu : {len(lp.columns)} poteau(x), {len(lp.beams)} poutre(s) "
        f"RÉELLEMENT lus (0 objet inventé). Cotes en mètres.",
        "Dimensions de section DÉDUITES du nom de label Robot "
        "(convention R<b>x<h> cm) — déduction à CONFIRMER par l'ingénieur ; "
        "plan NON coté en mm, NON validé pour exécution.",
    ]
    for k, t in enumerate(lines):
        c.drawString(mm(MARGIN_MM + 3),
                     mm(MARGIN_MM + CARTOUCHE_H_MM - 10 - 4 * k), t)
    # notes de refus/limites du niveau
    ny = MARGIN_MM + 4
    c.setFillColor(HexColor("#C00000"))
    for note in lp.notes[:4]:
        c.setFont("Helvetica-Oblique", 6)
        c.drawRightString(mm(pw - MARGIN_MM - 3), mm(ny), note[:120])
        ny -= 3.5
    c.setFillColor(black)
