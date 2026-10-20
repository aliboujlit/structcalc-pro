# -*- coding: utf-8 -*-
"""
regulation/bael91r99/interaction.py — Diagramme d'interaction N/M + 2ᵉ ordre.

Cœur du dimensionnement des poteaux (spec §10.3, §11.3), auparavant NON
implémenté. On implémente la MÉTHODOLOGIE (section analysis par compatibilité
des déformations) de façon traçable et testable, en PARAMÉTRANT chaque
coefficient (spec §3.4 : aucune valeur n'est codée en dur comme seule vérité).

RÈGLE ABSOLUE (§0) : l'implémentation de la méthode ne PRÉSUMÉ JAMAIS de la
conformité réglementaire. Le verdict « Conforme » reste GATE sur `verified` de
l'article (statut par défaut A_VALIDER) tant que les coefficients ne sont pas
confrontés au fascicule officiel BAEL 91 r99. Ici on valide la COHÉRENCE
interne du calcul par des cas de référence (spec §17.2), pas la conformité.

Méthode (section rectangulaire b×h, armatures discrètes) :
  - béton : bloc de contrainte rectangulaire de profondeur a = λ·x (λ=0,8) et
    contrainte η·fcd (η=0,85), x = profondeur de l'axe neutre depuis la fibre
    comprimée extrême ;
  - acier : compatibilité des déformations, ε_i = ε_cu·(x − d_i)/x, contrainte
    σ_i = Es·ε_i bornée à ±fyd ;
  - on fait varier x pour tracer la courbe (N, M) ; contrôle par enveloppe.

Hypothèses (documentées, à confronter au fascicule) :
  - sections planes (Bernoulli), retrait négligé, adhérence parfaite ;
  - résistance à la traction du béton NULLE (règle de non-fragilité BAEL) ;
  - ε_cu déform ultime béton en compression (paramètre, ex. 0,0035).

Coefficients PARAMÉTRÉS (§3.4) : η, λ, ε_cu, αcc (facteur 0,85 de fcd sous
charges longues — confirmé exister par revue, forme exacte À CONFIRMER).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# CONTRÔLE DES UNITÉS (spec §5.3) — conversion MPa·cm² -> kN / kN.m
# ---------------------------------------------------------------------------
# fcd/fyd sont en MPa (= N/mm²) et les aires en cm².  Le produit
# MPa · cm² vaut (N/mm²)·(100 mm²) = 100 N.  Convertir en kN impose donc
# ×100 /1000 = /10.  Cette constante REND la conversion EXPLICITE et évite
# l'erreur classique « /1000 » qui sous-estimerait les efforts d'un facteur 100.
K_MPA_CM2_TO_KN = 10.0   # 1 kN = 10 MPa·cm²


# ---------------------------------------------------------------------------
# Paramètres de méthode (PARAMÉTRÉS, jamais seule vérité — spec §3.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionModel:
    """Hypothèses de méthode du diagramme d'interaction (paramétrables)."""
    lam_block: float = 0.8      # λ : profondeur du bloc de contrainte (·x)
    eta_block: float = 0.85     # η : contrainte du bloc (·fcd)
    eps_cu: float = 0.0035      # ε_cu : déform. ultime béton compression
    alpha_cc: float = 1.0       # αcc : facteur fcd longue durée (1,0 / 0,85)


# ---------------------------------------------------------------------------
# Entrées
# ---------------------------------------------------------------------------

@dataclass
class RectSection:
    """Section rectangulaire + armatures discrètes (cm)."""
    b: float                   # largeur (cm)
    h: float                   # hauteur (cm)
    bars: List[Tuple[float, float]] = field(default_factory=list)
    # chaque barre : (d = profondeur depuis fibre comprimée en cm, As en cm2)

    @property
    def Ac(self) -> float:
        return self.b * self.h

    @property
    def As_total(self) -> float:
        return sum(as_ for _, as_ in self.bars)


@dataclass
class DesignMaterials:
    """Résistances de calcul (MPa) déjà réduites par γ (couche MAT)."""
    fcd: float     # béton compression de calcul (MPa)
    fyd: float     # acier élasticité de calcul (MPa)
    Es: float = 200000.0


# ---------------------------------------------------------------------------
# Calcul des efforts (N compression +, M kN.m) pour un axe neutre donné
# ---------------------------------------------------------------------------

def _forces_at_neutral_axis(sec: RectSection, mat: DesignMaterials,
                            x: float, m: SectionModel
                            ) -> Optional[Tuple[float, float]]:
    """
    Efforts (N en kN compression +, M en kN.m) pour axe neutre en prof. x (cm).

    Retourne None si x hors domaine utilisable (x→0 sans acier, mal défini).
    x est mesuré depuis la fibre COMPRIMÉE extrême (d_i croît vers l'autre fibre).
    """
    if x <= 1e-9:
        return None
    h = sec.h

    # --- Béton : bloc rectangulaire de profondeur a = λ·x (borné à h) --------
    a = m.lam_block * x
    if a <= 0.0:
        Cc_N = 0.0
        arm_c = 0.0
    else:
        a_eff = min(a, h)                      # le bloc ne dépasse pas la fibre
        Cc_N = m.eta_block * mat.fcd * sec.b * a_eff       # N (MPa*cm2=N)
        arm_c = (h / 2.0 - a_eff / 2.0) / 100.0            # bras vers centroid (m)

    # --- Acier : compatibilité des déformations ------------------------------
    N_steel_N = 0.0
    M_steel_kNm = 0.0
    for d_i, as_i in sec.bars:
        eps_i = m.eps_cu * (x - d_i) / x       # + compression (d_i<x), − traction
        sig_i = mat.Es * eps_i                 # MPa
        sig_i = max(-mat.fyd, min(mat.fyd, sig_i))   # borné à ±fyd
        F_i = sig_i * as_i                     # MPa·cm² (compression +)
        N_steel_N += F_i
        arm_i = (d_i - h / 2.0) / 100.0        # bras depuis centroid (m)
        M_steel_kNm += (F_i / K_MPA_CM2_TO_KN) * arm_i   # kN·m

    # MPa·cm² -> kN via la constante de conversion explicite (§5.3)
    N_kN = (Cc_N + N_steel_N) / K_MPA_CM2_TO_KN
    # Moment au centre plastique (centroid) : béton + acier
    M_kNm = (Cc_N / K_MPA_CM2_TO_KN) * arm_c + M_steel_kNm
    return N_kN, M_kNm


# ---------------------------------------------------------------------------
# Diagramme d'interaction
# ---------------------------------------------------------------------------

def interaction_diagram(sec: RectSection, mat: DesignMaterials,
                        n_points: int = 120,
                        model: Optional[SectionModel] = None
                        ) -> List[Tuple[float, float]]:
    """
    Trace le domaine (N, M) en faisant varier l'axe neutre x.

    x varie de x_max (~ profondeur donnant compression maximale) à une valeur
    faible (traction). Retourne des points triés par N décroissant (compression
    → traction). Les bornes de x sont PARAMÉTRÉES par la géométrie.
    """
    m = model or SectionModel()
    h = sec.h
    # Bornes d'axe neutre : de (compression forte, x>h) à (traction, x<0 gérée
    # via un x petit mais on s'arrête avant les artefacts numériques).
    x_max = 3.0 * h
    x_min = 0.05 * h
    pts: List[Tuple[float, float]] = []

    for i in range(n_points):
        # répartition non linéaire : plus dense près de l'axe équilibré
        frac = i / (n_points - 1)
        x = x_max * (x_min / x_max) ** frac          # géométrique (log)
        res = _forces_at_neutral_axis(sec, mat, x, m)
        if res is not None:
            pts.append(res)

    # Bornes explicites : traction pure (tout acier à −fyd) et compression
    # pure (bloc + acier à +fyd) pour fermer la courbe proprement.
    as_t = sec.As_total
    if as_t > 0:
        N_tension_kN = -(mat.fyd * as_t)  / K_MPA_CM2_TO_KN    # traction (−)
        pts.append((N_tension_kN, 0.0))
    # compression maximale approchée (bloc plein + acier comprimé)
    N_comp_kN = (m.eta_block * mat.fcd * sec.Ac + mat.fyd * as_t)  / K_MPA_CM2_TO_KN
    pts.append((N_comp_kN, 0.0))

    # tri par N décroissant (compression en tête)
    pts.sort(key=lambda p: -p[0])
    return pts


def capacity_at_normal(sec: RectSection, mat: DesignMaterials, N_kN: float,
                       model: Optional[SectionModel] = None
                       ) -> Optional[float]:
    """
    Moment résistant M_r (kN.m) pour un effort normal N donné, par lecture du
    diagramme (interpolation linéaire sur l'enveloppe |M| maximale du côté
    correspondant). Retourne None si N hors domaine.
    """
    diag = interaction_diagram(sec, mat, n_points=200, model=model)
    # enveloppe |M| la plus grande pour chaque N : on garde le max |M| par point
    # (le diagramme est en N décroissant ; on interpole autour de N_kN).
    best: List[Tuple[float, float]] = []
    for n, mm in diag:
        best.append((n, abs(mm)))
    # Pour N donnée, trouver les segments qui l'encadrent et interpoler |M|
    Ns = [n for n, _ in best]
    # s'assurer que N est dans l'étendue
    if not (min(Ns) <= N_kN <= max(Ns)):
        return None
    # parcourir les points, interpoler le |M| max autour de N_kN
    m_vals: List[float] = []
    for i in range(len(best) - 1):
        n1, m1 = best[i]
        n2, m2 = best[i + 1]
        lo, hi = min(n1, n2), max(n1, n2)
        if lo <= N_kN <= hi:
            if abs(n2 - n1) < 1e-12:
                m_vals.append(max(m1, m2))
            else:
                t = (N_kN - n1) / (n2 - n1)
                m_vals.append(m1 + t * (m2 - m1))
    if not m_vals:
        return None
    return max(m_vals)


# ---------------------------------------------------------------------------
# Effets du second ordre (amplification de moments, spec §10.3)
# ---------------------------------------------------------------------------

@dataclass
class SecondOrderInput:
    """Données pour l'amplification des moments du 1er ordre."""
    N_ed_kN: float              # effort normal de calcul (compression +)
    M1_kNm: float               # moment du 1er ordre (axe y)
    l0_m: float                 # longueur de flambement (m)
    EI_kNm2: float              # rigidité nominale de la section (kN.m²)
    cracking_factor: float = 1.0  # facteur de fissuration/raideur (paramètre)


def critical_buckling_load(EI_kNm2: float, l0_m: float) -> float:
    """Charge critique de flambement Euler : N_cr = π²·EI / l0² (kN)."""
    if l0_m <= 0:
        return float("inf")
    return (math.pi ** 2) * EI_kNm2 / (l0_m ** 2)


def second_order_moment(inp: SecondOrderInput) -> dict:
    """
    Moment du 2ᵉ ordre par amplification nominale (M2 = M1 / (1 − N/N_cr)).

    Hypothèse (documentée, à confronter au fascicule) : amplification
    « nominale » ; si N ≥ N_cr ou facteur ≤ 1 -> instabilité (signalée, jamais
    un succès silencieux). EI est une ENTRÉE (rigidité fissurée) : ce module ne
    la détermine pas (couche SOLVER/ingénieur).
    """
    N_cr = critical_buckling_load(inp.EI_kNm2, inp.l0_m)
    denom = 1.0 - (inp.N_ed_kN / N_cr if N_cr else float("inf"))
    if denom <= 1e-6:
        return {"stable": False, "M2_kNm": None, "N_cr_kN": N_cr,
                "amplification": None,
                "reason": (f"N_ed ({inp.N_ed_kN:.1f} kN) ≥ N_cr "
                           f"({N_cr:.1f} kN) : instabilité — pas de M2 fini.")}
    amp = inp.cracking_factor / denom
    M2 = inp.M1_kNm * amp
    return {"stable": True, "M2_kNm": M2, "N_cr_kN": N_cr,
            "amplification": amp, "reason": ""}
