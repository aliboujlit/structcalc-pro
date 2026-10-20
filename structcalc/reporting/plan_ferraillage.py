# -*- coding: utf-8 -*-
"""
reporting/plan_ferraillage.py — Plans de ferraillage poteau PDF (spec §15).

Le ferraillage produit ici est une PROPOSITION déduite du dimensionnement
(SOLVER : `As_provided_cm2` de la variante retenue) et des dimensions de
section (convention R<b>x<h> des labels Robot, cf. plan_coffrage).
Règles absolues :

  - le document est marqué PROPOSITION — À VALIDER (statut A_VALIDER) sur
    CHAQUE page : aucune barre n'est « conforme » sans validation ingénieur
    (§10.4, §15.3) ;
  - les diamètres proposés viennent de la gamme usuelle HA (Ø12…Ø32) — le
    dénombrement (nb de barres) est un ARITHMÉTIQUE As >= As_requis, sans
    prétention réglementaire (le contrôle des espacements/longueurs reste
    un check BAEL non implémenté ici -> affiché tel quel) ;
  - enrobage, longueurs d'attente et recouvrements ne sont PAS lus dans le
    modèle : ce sont des HYPOTHÈSES déclarées (paramètres d'entrée), jamais
    présentées comme lues ;
  - 0 poteau dimensionné = 0 plan (refus explicite).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

# Gamme d'acier longitudinale usuelle (mm) — gamme STANDARD déclarée,
# pas une lecture de projet (aucun label acier n'est lu dans Robot).
BAR_DIAMS_MM = (12.0, 16.0, 20.0, 25.0, 32.0)
# Cadres (mm) — gamme usuelle déclarée.
STIRRUP_DIAMS_MM = (6.0, 8.0, 10.0)
# Masse volumique acier (kg/m3) — constante physique documentée.
STEEL_DENSITY = 7850.0
# Nombre de barres MAXIMUM d'un arrangement (plafond constructif déclaré :
# au-delà, gamme supérieure exigée — 24 barres dans un poteau n'est pas
# une solution d'exécution).
MAX_BARS = 12

# HYPOTHÈSES par défaut (déclarées, ajustables par l'ingénieur) :
COVER_MM = 25.0          # enrobage béton (mm) — HYPOTHÈSE
ATTENTE_MM = 400.0       # longueur d'attente (mm) — HYPOTHÈSE


def bar_area_cm2(d_mm: float) -> float:
    """Aire d'une barre (cm²) — d en mm."""
    return math.pi * (d_mm / 10.0) ** 2 / 4.0


def propose_bars(as_required_cm2: float,
                 b_cm: float, h_cm: float,
                 cover_mm: float = COVER_MM
                 ) -> Optional[Tuple[float, int]]:
    """
    Décompose `as_required_cm2` en (Ø_mm, nb) sur la plus petite gamme
    satisfaisant As >= requis avec un espacement constructif minimal
    (barres réparties sur les 4 faces d'une section rectangulaire).

    Retourne None si aucun arrangement de la gamme n'atteint l'aire
    requise (jamais d'armature insuffisante présentée comme proposition).
    """
    avail_mm = min(b_cm, h_cm) * 10.0 - 2.0 * cover_mm
    if avail_mm <= 0:
        return None
    best = None
    for d_mm in BAR_DIAMS_MM:
        if d_mm > avail_mm:
            continue
        n_min = max(4, math.ceil(as_required_cm2 / bar_area_cm2(d_mm)))
        if n_min % 2:
            n_min += 1                    # nb de barres PAIR (symétrie)
        if n_min > MAX_BARS:
            continue                      # arrangement non constructible
        # espacement constructif minimal ~ d_mm entre axes (déclaré)
        if n_min * d_mm > avail_mm:
            continue                      # trop serré : gamme supérieure
        as_prov = n_min * bar_area_cm2(d_mm)
        cand = (d_mm, n_min, as_prov)
        if best is None or cand[2] < best[2]:
            best = cand
    if best is None:
        return None
    return (best[0], best[1])


def stirrup_proposal(b_cm: float, h_cm: float,
                     d_bar_mm: float
                     ) -> Tuple[float, float, float]:
    """
    Cadre : (Ø_mm, espacement_zone_attente_mm, espacement_zone_corps_mm).
    Espacements = propositions déclarées (règle usuelle e≈b/2 en zone de
    flexion, e=min(b,h) ailleurs) — statut A_VALIDER, jamais conforme.
    """
    d_min = min(b_cm, h_cm) * 10.0
    # Gamme : le plus petit cadre >= 6 mm et constructif
    d_st = next(d for d in STIRRUP_DIAMS_MM
                if d_min - 2 * COVER_MM > d * 2)
    e_zone = max(100.0, min(d_min, 200.0))     # zone d'attente (déclarée)
    e_corps = max(e_zone, min(d_min, 400.0))   # corps (déclarée)
    return (d_st, e_zone, e_corps)


@dataclass
class ReinforcementPlan:
    """Proposition d'armature d'un poteau (statut : À VALIDER)."""
    column_id: str
    b_cm: float
    h_cm: float
    height_m: float
    as_required_cm2: float
    bar_d_mm: float
    bar_count: int
    stirrup_d_mm: float
    stirrup_e_zone_mm: float
    stirrup_e_corps_mm: float
    cover_mm: float = COVER_MM
    attente_mm: float = ATTENTE_MM
    hypotheses: List[str] = field(default_factory=list)

    @property
    def as_provided_cm2(self) -> float:
        return self.bar_count * bar_area_cm2(self.bar_d_mm)

    @property
    def ratio(self) -> float:
        return self.as_provided_cm2 / (self.b_cm * self.h_cm)

    def nomenclature(self) -> List[dict]:
        """
        Nomenclature d'acier (barres + cadres) : longueurs en m, masses en
        kg (rho = 7850 kg/m3, constante). Longueurs = hauteur + attentes
        (hypothèses déclarées), cadres = périmètre de la cage.
        """
        rows = []
        lbar = self.height_m + 2 * (self.attente_mm / 1000.0)
        a_bar = bar_area_cm2(self.bar_d_mm) / 1e4          # m2
        rows.append({
            "repère": f"P{self.bar_d_mm:.0f}-{self.bar_count}",
            "type": "Barre longitudinale",
            "diametre_mm": self.bar_d_mm, "nombre": self.bar_count,
            "longueur_m": round(lbar, 2),
            "masse_kg": round(lbar * self.bar_count * a_bar
                              * STEEL_DENSITY, 1),
        })
        per = 2 * ((self.b_cm - 2 * self.cover_mm / 10.0)
                   + (self.h_cm - 2 * self.cover_mm / 10.0)) / 100.0
        n_zone = max(2, math.ceil(self.attente_mm / self.stirrup_e_zone_mm))
        n_corps = max(1, math.ceil(
            (self.height_m * 1000 - 2 * self.attente_mm)
            / self.stirrup_e_corps_mm) - 1)
        n_st = 2 * n_zone + max(0, n_corps)
        a_st = bar_area_cm2(self.stirrup_d_mm) / 1e4
        rows.append({
            "repère": f"C{self.stirrup_d_mm:.0f}",
            "type": "Cadre",
            "diametre_mm": self.stirrup_d_mm, "nombre": n_st,
            "longueur_m": round(per + 0.30, 2),   # +crochets (hyp. 0.30)
            "masse_kg": round((per + 0.30) * n_st * a_st
                              * STEEL_DENSITY, 1),
        })
        return rows

    @property
    def total_mass_kg(self) -> float:
        return sum(r["masse_kg"] for r in self.nomenclature())


def plan_reinforcement(column, project, outcomes=None,
                       height_m: Optional[float] = None
                       ) -> Optional[ReinforcementPlan]:
    """
    Construit la proposition d'armature d'UN poteau du pivot, à partir :
      - des dimensions de section de la VARIANTE retenue au dimensionnement
        (b, h de `ColumnVariant`) — le ferraillage propose un
        redimensionnement, il ne déclare pas la section existante conforme ;
      - de `As_requis` pris sur la variante classée 1 du dimensionnement
        (`outcomes` : liste DesignOutcome, fournie par le SOLVER) ;
      - de la hauteur (TrackedValue du poteau, ou delta-z des nœuds).
    Retourne None si une donnée RÉELLE manque (jamais de proposition
    surdonnée).
    """
    nodes = getattr(project, "nodes", {}) or {}

    # As requis ET dimensions de la SECTION RETENUE au dimensionnement :
    # le ferraillage porte sur la variante classée 1 (redimensionnement
    # proposé), pas sur la section existante du modèle (qui peut être
    # insuffisante — cf. villa : C R30x30 vs variante 50x50).
    as_req = None
    b_cm = h_cm = None
    if outcomes:
        cands = [o for o in outcomes if o.is_candidate and o.rank]
        if cands:
            best = min(cands, key=lambda o: o.rank)
            as_req = best.variant.As_provided_cm2
            b_cm, h_cm = float(best.variant.b), float(best.variant.h)
    if as_req is None or b_cm is None:
        return None                       # pas de dimensionnement -> refus

    # Hauteur : TrackedValue, sinon delta-z des nœuds (réel)
    h_m = None
    try:
        if not column.height.is_missing:
            h_m = float(column.height.value)
    except Exception:
        h_m = None
    if h_m is None:
        n1 = nodes.get(column.start_node)
        n2 = nodes.get(column.end_node)
        try:
            z1, z2 = float(n1.z.value), float(n2.z.value)
            h_m = abs(z1 - z2)
        except Exception:
            return None                   # hauteur inconnue -> pas de plan
    if height_m is not None:
        h_m = float(height_m)

    bars = propose_bars(as_req, b_cm, h_cm)
    if bars is None:
        return None
    d_mm, n = bars
    d_st, e_z, e_c = stirrup_proposal(b_cm, h_cm, d_mm)

    hyp = [
        f"Enrobage {COVER_MM:.0f} mm — HYPOTHÈSE (non lu dans le modèle).",
        f"Longueurs d'attente {ATTENTE_MM:.0f} mm — HYPOTHÈSE (non lues).",
        "Gamme d'acier Ø12–Ø32 HA — gamme déclarée (aucun label acier lu).",
        "Espacements de cadres — propositions (contrôle BAEL des "
        "espacements NON implémenté ici).",
    ]
    return ReinforcementPlan(
        column_id=column.sc_id, b_cm=b_cm, h_cm=h_cm, height_m=h_m,
        as_required_cm2=as_req, bar_d_mm=d_mm, bar_count=n,
        stirrup_d_mm=d_st, stirrup_e_zone_mm=e_z, stirrup_e_corps_mm=e_c,
        hypotheses=hyp)


# ---------------------------------------------------------------------------
# Rendu PDF (élévation + coupe + nomenclature)
# ---------------------------------------------------------------------------

def reinforcement_pdf(plan: ReinforcementPlan, path: str,
                      project_name: str = "") -> str:
    """
    Écrit le plan de ferraillage PDF d'un poteau (A3, une page).
    Lève une erreur explicite si reportlab manque (jamais de faux succès).
    """
    try:
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.pdfgen import canvas as pdfcanvas
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Plan de ferraillage impossible : 'reportlab' indisponible "
            f"({exc}).") from exc

    from ..version import __version__
    scale = 72.0 / 25.4

    def mm(v: float) -> float:
        return v * scale

    c = pdfcanvas.Canvas(path, pagesize=landscape(A3))
    pw, ph = 420.0, 297.0

    # -- Bandeau « PROPOSITION » (rappel permanent, spec §15.3) --
    c.setFillColor(HexColor("#C00000"))
    c.rect(0, mm(ph - 10), mm(pw), mm(10), stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(mm(pw / 2), mm(ph - 7),
                        "PROPOSITION DE FERRAILLAGE — À VALIDER PAR "
                        "L'INGÉNIEUR (A_VALIDER) — PAS UN PLAN "
                        "D'EXÉCUTION")
    c.setFillColor(black)

    # -- Élévation (gauche) --
    elev_x, elev_y = 30.0, 30.0
    elev_w = 60.0
    # échelle élévation : hauteur -> 200 mm de page max
    h_mm = min(200.0, plan.height_m * 1000.0 * 0.5)   # 1:2 approx (déclaré)
    sc = h_mm / (plan.height_m * 1000.0)
    b_mm = plan.b_cm * 10.0 * sc
    c.setLineWidth(1.0)
    c.setStrokeColor(black)
    c.rect(mm(elev_x - b_mm / 2), mm(elev_y), mm(b_mm), mm(h_mm),
           stroke=1, fill=0)
    # barres longitudinales (traits pleins)
    n_side = max(2, plan.bar_count // 4)
    c.setLineWidth(0.8)
    c.setStrokeColor(HexColor("#C00000"))
    for i in range(n_side):
        xb = elev_x - b_mm / 2 + (i + 0.5) * b_mm / n_side
        c.line(mm(xb), mm(elev_y + COVER_MM * sc),
               mm(xb), mm(elev_y + h_mm - COVER_MM * sc))
    # cadres (traits horizontaux)
    c.setStrokeColor(HexColor("#1a4f8b"))
    c.setLineWidth(0.5)
    e_zone_mm_page = plan.stirrup_e_zone_mm * sc
    e_corps_mm_page = plan.stirrup_e_corps_mm * sc
    y = elev_y + COVER_MM * sc
    while y < elev_y + h_mm - COVER_MM * sc:
        c.line(mm(elev_x - b_mm / 2 - 2), mm(y),
               mm(elev_x + b_mm / 2 + 2), mm(y))
        zone = (y < elev_y + plan.attente_mm * sc
                or y > elev_y + h_mm - plan.attente_mm * sc)
        y += e_zone_mm_page if zone else e_corps_mm_page
    c.setLineWidth(0.8)
    c.setStrokeColor(black)
    c.setFont("Helvetica", 7)
    c.drawCentredString(mm(elev_x), mm(elev_y + h_mm + 4),
                        f"ÉLÉVATION H = {plan.height_m:.2f} m "
                        f"(échelle ≈1:{int(1 / sc)})")
    # cote hauteur
    c.line(mm(elev_x - b_mm / 2 - 8), mm(elev_y),
           mm(elev_x - b_mm / 2 - 8), mm(elev_y + h_mm))
    c.setFont("Helvetica", 6)
    c.drawString(mm(elev_x - b_mm / 2 - 16), mm(elev_y + h_mm / 2),
                 f"{plan.height_m:.2f}")

    # -- Coupe A-A (centre) --
    coup_x, coup_y = 150.0, 60.0
    coup_mm = min(plan.b_cm, plan.h_cm) * 10.0 * 1.0    # 1:1 mm réels -> page mm
    sc_c = coup_mm / (min(plan.b_cm, plan.h_cm) * 10.0)
    bw, hw = plan.b_cm * 10.0 * sc_c, plan.h_cm * 10.0 * sc_c
    c.setLineWidth(1.2)
    c.rect(mm(coup_x - bw / 2), mm(coup_y), mm(bw), mm(hw), stroke=1, fill=0)
    # cadre (rectangle intérieur)
    cov = COVER_MM * sc_c
    c.setLineWidth(0.6)
    c.setStrokeColor(HexColor("#1a4f8b"))
    c.rect(mm(coup_x - bw / 2 + cov), mm(coup_y + cov),
           mm(bw - 2 * cov), mm(hw - 2 * cov), stroke=1, fill=0)
    # barres (points)
    c.setFillColor(HexColor("#C00000"))
    r_pt = plan.bar_d_mm * sc_c / 2.0
    pos = _bar_positions(plan.b_cm, plan.h_cm, plan.bar_count,
                         plan.cover_mm)
    for (xx_cm, yy_cm) in pos:
        c.circle(mm(coup_x - bw / 2 + xx_cm * 10.0 * sc_c),
                 mm(coup_y + yy_cm * 10.0 * sc_c), mm(r_pt),
                 stroke=0, fill=1)
    c.setFillColor(black)
    c.setFont("Helvetica", 7)
    c.drawCentredString(mm(coup_x), mm(coup_y + hw + 4),
                        f"COUPE A-A  {plan.b_cm:.0f}x{plan.h_cm:.0f} cm "
                        f"(≈1:1)")
    c.setFont("Helvetica", 6)
    c.drawString(mm(coup_x - bw / 2), mm(coup_y - 6),
                 f"Enrobage (hyp.) {plan.cover_mm:.0f} mm")

    # -- Nomenclature (droite) --
    tx, ty = 240.0, ph - 40.0
    c.setFont("Helvetica-Bold", 9)
    c.drawString(mm(tx), mm(ty), "NOMENCLATURE D'ACIER (proposition)")
    ty -= 6
    c.setFont("Helvetica-Bold", 6.5)
    heads = ["Repère", "Type", "Ø mm", "Nb", "L (m)", "Masse (kg)"]
    colw = [22.0, 45.0, 14.0, 10.0, 16.0, 22.0]
    xx = tx
    for h_, w_ in zip(heads, colw):
        c.drawString(mm(xx), mm(ty), h_)
        xx += w_
    ty -= 2
    c.line(mm(tx), mm(ty), mm(tx + sum(colw)), mm(ty))
    ty -= 5
    c.setFont("Helvetica", 6.5)
    for row in plan.nomenclature():
        vals = [row["repère"], row["type"], f"{row['diametre_mm']:.0f}",
                str(row["nombre"]), f"{row['longueur_m']:.2f}",
                f"{row['masse_kg']:.1f}"]
        xx = tx
        for v_, w_ in zip(vals, colw):
            c.drawString(mm(xx), mm(ty), v_)
            xx += w_
        ty -= 5
    c.setFont("Helvetica-Bold", 7)
    c.drawString(mm(tx), mm(ty - 2),
                 f"Masse totale acier (ρ=7850 kg/m3) : "
                 f"{plan.total_mass_kg:.1f} kg")

    # -- Encadré dimensionnement / hypothèses --
    ty -= 16
    c.setFont("Helvetica-Bold", 8)
    c.drawString(mm(tx), mm(ty),
                 f"Poteau {plan.column_id} — dimensionnement d'origine")
    ty -= 5
    c.setFont("Helvetica", 6.5)
    info = [
        f"As requis (variante classée 1) : {plan.as_required_cm2:.1f} cm² "
        f"— As proposé : {plan.as_provided_cm2:.1f} cm² "
        f"(ρ = {plan.ratio * 100:.2f} %).",
        f"Barres : {plan.bar_count} Ø{plan.bar_d_mm:.0f} HA "
        f"(gamme usuelle Ø12–Ø32, déclarée).",
        f"Cadres : Ø{plan.stirrup_d_mm:.0f}, zones d'attente "
        f"e={plan.stirrup_e_zone_mm:.0f} mm / corps "
        f"e={plan.stirrup_e_corps_mm:.0f} mm (PROPOSITIONS).",
    ] + plan.hypotheses
    for t in info:
        c.drawString(mm(tx), mm(ty), f"- {t}")
        ty -= 4

    # -- Cartouche --
    c.setLineWidth(0.5)
    c.rect(mm(12), mm(12), mm(pw - 24), mm(14), stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(mm(15), mm(21),
                 f"STRUCTCALC PRO v{__version__} — ferraillage poteau "
                 f"{plan.column_id}"
                 + (f" — {project_name}" if project_name else ""))
    c.setFont("Helvetica", 6)
    c.drawString(mm(15), mm(16),
                 f"Généré le {datetime.now():%d/%m/%Y %H:%M} — "
                 f"PROPOSITION issues du dimensionnement BAEL (articles "
                 f"non vérifiés indépendamment -> A_VALIDER) — exécution "
                 f"sous responsabilité de l'ingénieur.")
    c.save()
    return path


def _bar_positions(b_cm: float, h_cm: float, n: int,
                   cover_mm: float) -> List[Tuple[float, float]]:
    """
    Positions (cm depuis le coin bas-gauche) des `n` barres sur le périmètre
    de la section (répartition symétrique sur les faces).
    """
    d = cover_mm / 10.0
    if n <= 4:
        pts = [(d, d), (b_cm - d, d), (b_cm - d, h_cm - d), (d, h_cm - d)]
        if n == 4:
            return pts
        return pts[:max(2, n)]
    pts = [(d, d), (b_cm - d, d), (b_cm - d, h_cm - d), (d, h_cm - d)]
    rest = n - 4
    per_side = rest // 4 + (1 if rest % 4 else 0)
    # répartition sur les faces horizontales puis verticales
    for i in range(1, per_side + 1):
        xx = d + (b_cm - 2 * d) * i / (per_side + 1)
        pts.append((xx, d))
        pts.append((xx, h_cm - d))
    k = rest - 2 * per_side
    for i in range(1, k + 1):
        yy = d + (h_cm - 2 * d) * i / (k + 1)
        pts.append((d, yy))
        pts.append((b_cm - d, yy))
    return pts[:n]
