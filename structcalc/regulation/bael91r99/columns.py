# -*- coding: utf-8 -*-
"""
regulation/bael91r99/columns.py — Dimensionnement des poteaux BAEL 91 r99 (spec §10, §11.1).

STATUT DE VÉRIFICATION (règle absolue §0, §11.1)
-----------------------------------------------
Les formules sont transcrites selon l'usage courant du BAEL 91 révisé 99
(équations en texte, coefficients documentés). Chaque vérification retourne
un `VerificationResult` dont le statut n'est JAMAIS « CONFORME » par défaut :
  - NON_CONFORME / CONFORME calculés si l'article est marqué `verified=True`
  - sinon A_VALIDER ou VERIFICATION_NON_IMPLEMENTE

Les cas de référence (`REFERENCE_CASES`) servent à la vérification
indépendante (spec §17.2) : calcul manuel comparé au calcul du logiciel.

Coefficient de sécurité béton/acier : BAEL impose γc et γs. Valeurs par
défaut usuelles (à CONFIRMER sur l'édition officielle) : γc=1.5, γs=1.15
(ou 1.15/1.5 selon convention). Elles sont PARAMÈTRES, jamais codées en dur
comme seule vérité (spec §3.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..base import Regulation, Article, VerificationResult
from ...core.status import RegulatoryStatus
from .interaction import (
    K_MPA_CM2_TO_KN,
    RectSection,
    DesignMaterials,
    SectionModel,
    SecondOrderInput,
    capacity_at_normal,
    interaction_diagram,
    second_order_moment,
)


# ---------------------------------------------------------------------------
# Données d'entrée (geometry, materials, actions)
# ---------------------------------------------------------------------------

@dataclass
class ColumnGeometry:
    """Géométrie d'un poteau (unités : m pour longueurs, cm pour section)."""
    b: float                 # largeur de section (cm)
    h: float                 # hauteur de section (cm)
    height: float            # hauteur d'étage (m)
    buckling_length_y: float # longueur de flambement axe y (m)
    buckling_length_z: float # longueur de flambement axe z (m)
    node_count: int = 2      # nb de nœuds retenus (contrôle de stabilité)


@dataclass
class ColumnMaterials:
    """Caractéristiques des matériaux (valeurs caractéristiques + γ)."""
    fck: float       # résistance caractéristique béton (MPa)
    fyk: float       # limite élastique acier caractéristique (MPa)
    E: float         # module acier (MPa)
    gamma_c: float = 1.5   # coefficient de sécurité béton (à confirmer)
    gamma_s: float = 1.15  # coefficient de sécurité acier (à confirmer)


@dataclass
class ColumnActions:
    """
    Sollicitations concomitantes d'une combinaison (unités : kN, kN.m).
    Signe convention : compression positive pour N.
    """
    N: float                 # effort normal (kN, compression +)
    My: float = 0.0          # moment autour de y (kN.m)
    Mz: float = 0.0          # moment autour de z (kN.m)
    combination: str = ""    # combinaison déterminante (traçabilité)


# ---------------------------------------------------------------------------
# Référentiel
# ---------------------------------------------------------------------------

class Bael91r99(Regulation):
    """
    Référentiel BAEL 91 révisé 99 — module poteaux.

    Articles transcrites. `verified=False` par défaut : l'ingénieur doit
    confronter chaque formule à l'exemple de référence ET au texte officiel.
    """

    def __init__(self):
        super().__init__(
            key="BAEL91R99",
            title="Règles de calcul et de dimensionnement des structures en béton armé",
            edition="BAEL 91 révisé 99",
            geography="France",
            applicability_date="1999",
            scope="Béton armé — poteaux (compression, flexion composée, élancement)",
        )
        self._register_articles()
        self._register_checks()

    # -- Articles ---------------------------------------------------------

    def _register_articles(self):
        # fcd / fyd (base des matériaux)
        self.register_article(Article(
            code="BAEL91r99-MAT",
            title="Résistances de calcul du béton et de l'acier",
            equation_text="fcd = fck / γc ;  fyd = fyk / γs",
            variables={"fck": "résistance caract. béton", "fyk": "limite élast. acier",
                       "γc": "coéf. sécurité béton", "γs": "coéf. sécurité acier"},
            units={"fcd": "MPa", "fyd": "MPa"},
            coefficients={"gamma_c_defaut": 1.5, "gamma_s_defaut": 1.15},
            validity_limits="Béton normal, acier HA",
            source_doc="BAEL 91 révisé 99 — résistances de calcul",
            verified=False,
            verification_note=("γc=1.5 / γs=1.15 CONFIRMÉS (recherche web + doctrine). "
                               "fcd = fck/γc ; fyd = fyk/γs. Formules CONFIRMÉES. "
                               "À confronter au fascicule officiel pour vérification formelle."),
        ))
        # Compression centrale (simplifiée)
        self.register_article(Article(
            code="BAEL91r99-COMPR",
            title="Résistance à la compression centrale (formule simplifiée)",
            equation_text=("Nr = 0.6 * fcd * Ac + fyd * As_total  (hyp. compression "
                           "centrale, hors effets du second ordre)"),
            variables={"Ac": "aire de béton", "As_total": "aire totale d'acier"},
            units={"Nr": "kN", "Ac": "cm2", "As_total": "cm2"},
            validity_limits="Compression centrale ; NE PAS utiliser seul si moments "
                            "ou effets du second ordre non négligeables (spec §10.3).",
            source_doc="BAEL 91 révisé 99 — poteaux comprimés",
            verified=False,
            verification_note=("γc=1.5 / γs=1.15 CONFIRMÉS (recherche web + doctrine). "
                               "Coefficient 0.6 et formule Nr = 0.6·fcd·Ac + fyd·As CANDIDATS "
                               "— à confronter au fascicule officiel. fcd = fck/γc ; fyd = fyk/γs."),
        ))
        # Élancement
        self.register_article(Article(
            code="BAEL91r99-ELAM",
            title="Élancement et flambement",
            equation_text="λ = l0 / i ;  i = sqrt(I / A) ;  λ1 = 200 (limite courante à confirmer)",
            variables={"l0": "longueur de flambement", "i": "rayon de gyration"},
            units={"λ": "-", "l0": "m", "i": "cm"},
            validity_limits="Poteaux isolés ; tenir compte des liaisons.",
            source_doc="BAEL 91 révisé 99 — stabilité, élancement",
            verified=False,
            verification_note=("Formule λ = l0/i CONFIRMÉE (statique). λ_lim = 20/(1+0.5·As'/As) CANDIDATE "
                               "— à confronter au fascicule (article III.2.3.2). "
                               "Limite simplifiée sans acier double : λ_lim ≈ 20 à valider."),
        ))
        # Flexion composée
        self.register_article(Article(
            code="BAEL91r99-FLEXCOMP",
            title="Résistance en flexion composée (compression + moments)",
            equation_text=("Interaction N/M selon méthode des contraintes ; "
                           "vérifier N ≤ Nr(M) et M ≤ Mr(N) par diagramme "
                           "d'interaction ou méthode équivalente."),
            variables={"N": "effort normal", "M": "moment", "Nr": "résistance sous M"},
            units={"N": "kN", "M": "kN.m"},
            validity_limits="Toute section ; méthode à préciser selon le cas.",
            source_doc="BAEL 91 révisé 99 — flexion composée",
            verified=False,
            verification_note=("Diagramme d'interaction N/M IMPLÉMENTÉ "
                               "(interaction.py, sec. rectangulaire, bloc "
                               "λ=0,8/η=0,85, ε_cu paramétrés). Méthode testée "
                               "par cas de référence interne (§17.2). "
                               "Coefficients confirmés : η=0.85, λ=0.8, ε_cu=0.0035 (doctrine BAEL). "
                               "αcc (0.85 long terme) CANDIDAT — à confronter au fascicule officiel "
                               "avant verdict Conforme."),
        ))
        # Second ordre (amplification des moments du 1er ordre)
        self.register_article(Article(
            code="BAEL91r99-2ORD",
            title="Effets du second ordre (amplification des moments)",
            equation_text=("M2 = M1 / (1 − N/N_cr) ;  N_cr = π²·EI / l0² "
                           "(amplification nominale)"),
            variables={"M1": "moment 1er ordre", "N": "effort normal",
                       "N_cr": "charge critique de flambement", "EI": "rigidité"},
            units={"M": "kN.m", "N": "kN", "EI": "kN.m²"},
            validity_limits="Poteaux élancés (λ > λ_lim) ; EI fissurée = entrée "
                            "ingénieur, non déterminée ici.",
            source_doc="BAEL 91 révisé 99 — stabilité, second ordre",
            verified=False,
            verification_note=("Amplification nominale implémentée "
                               "(interaction.second_order_moment). M2 = M1/(1−N/N_cr) "
                               "CONFIRMÉE (formule nominale BAEL). N_cr = π²EI/l0² CONFIRMÉE. "
                               "Modèle EI fissurée et facteur de brassage CANDIDATS — "
                               "à confronter au fascicule officiel."),
        ))

    # -- Vérifications ----------------------------------------------------

    def _register_checks(self):
        self.register_check("material_strengths", self.check_material_strengths)
        self.register_check("compression_central", self.check_compression_central)
        self.register_check("slenderness", self.check_slenderness)
        self.register_check("min_reinforcement", self.check_min_reinforcement)
        # Flexion composée / second ordre : IMPLÉMENTÉS (spec §10.3, §11.3).
        # Statut reste A_VALIDER tant que l'article est verified=False.
        self.register_check("flexion_composed", self.check_flexion_composed)
        self.register_check("second_order", self.check_second_order)

    # fcd / fyd
    def check_material_strengths(self, mat: ColumnMaterials) -> VerificationResult:
        fcd = mat.fck / mat.gamma_c
        fyd = mat.fyk / mat.gamma_s
        art = self.article("BAEL91r99-MAT")
        return VerificationResult(
            check_id="material_strengths", article_code=art.code,
            computed_value=fcd, limit_value=fyd, unit="MPa",
            status=(RegulatoryStatus.A_VALIDER if not art.verified
                    else RegulatoryStatus.CONFORME),
            message=f"fcd={fcd:.2f} MPa, fyd={fyd:.2f} MPa "
                    f"(γc={mat.gamma_c}, γs={mat.gamma_s}).",
        )

    # Compression centrale simplifiée (filtre initial, spec §10.2)
    def check_compression_central(self, geo: ColumnGeometry,
                                  mat: ColumnMaterials,
                                  actions: ColumnActions,
                                  As_total_cm2: float = 0.0) -> VerificationResult:
        fcd = mat.fck / mat.gamma_c                 # MPa
        fyd = mat.fyk / mat.gamma_s                 # MPa
        Ac = geo.b * geo.h - As_total_cm2           # aire béton (cm2)
        # Nr en kN : 0.6*fcd[MPa]*Ac[cm2] est en MPa.cm2 = 100 N
        #  -> convertir en kN exige /K_MPA_CM2_TO_KN (= /10), PAS /1000
        #     (bug classique sous-estimant Nr d'un facteur 100, spec §5.3).
        Nr_concrete_MPaCm2 = 0.6 * fcd * Ac
        Nr_steel_MPaCm2 = fyd * As_total_cm2
        Nr_kN = (Nr_concrete_MPaCm2 + Nr_steel_MPaCm2) / K_MPA_CM2_TO_KN

        N_ed = actions.N                            # kN (compression +)
        ratio = N_ed / Nr_kN if Nr_kN > 0 else float("inf")
        art = self.article("BAEL91r99-COMPR")

        # Conforme/Non conforme SEULEMENT si l'article est vérifié (spec §11.3)
        if not art.verified:
            status = RegulatoryStatus.A_VALIDER
        else:
            status = (RegulatoryStatus.CONFORME if N_ed <= Nr_kN
                      else RegulatoryStatus.NON_CONFORME)

        return VerificationResult(
            check_id="compression_central", article_code=art.code,
            element_id="", combination=actions.combination,
            computed_value=N_ed, limit_value=Nr_kN, unit="kN",
            margin=Nr_kN - N_ed,
            status=status,
            message=(f"N_ed={N_ed:.1f} kN, Nr≈{Nr_kN:.1f} kN (ratio {ratio:.2f}). "
                     "Hypothèse compression centrale : filtre initial seulement, "
                     "pas preuve finale (spec §10.2)."),
            reference_example=self._ref_compression(geo, mat, As_total_cm2),
        )

    # Élancement
    def check_slenderness(self, geo: ColumnGeometry,
                          mat: ColumnMaterials) -> VerificationResult:
        # Rayon de gyration pour section rectangulaire (cm) : i = h/sqrt(12)
        i_y = geo.h / math.sqrt(12.0)   # autour de y (détend selon h)
        i_z = geo.b / math.sqrt(12.0)   # autour de z (détend selon b)
        lam_y = (geo.buckling_length_y * 100.0) / i_y
        lam_z = (geo.buckling_length_z * 100.0) / i_z
        lam_max = max(lam_y, lam_z)
        lam1 = 200.0   # limite courante — À CONFIRMER sur l'édition officielle

        art = self.article("BAEL91r99-ELAM")
        if not art.verified:
            status = RegulatoryStatus.A_VALIDER
        else:
            status = (RegulatoryStatus.CONFORME if lam_max <= lam1
                      else RegulatoryStatus.NON_CONFORME)

        return VerificationResult(
            check_id="slenderness", article_code=art.code,
            computed_value=lam_max, limit_value=lam1, unit="-",
            margin=lam1 - lam_max,
            status=status,
            message=(f"λy={lam_y:.1f}, λz={lam_z:.1f}, λmax={lam_max:.1f} "
                     f"(λ1={lam1:.0f}, à confirmer)."),
        )

    # Armatures minimales (dispositions constructives)
    def check_min_reinforcement(self, geo: ColumnGeometry,
                                mat: ColumnMaterials,
                                As_provided_cm2: float) -> VerificationResult:
        """
        Contrôle de l'armature minimale d'un poteau.
        As,min = max(ρ_min * Ac ; un seuil en % ). Valeurs à CONFIRMER.
        ρ_min usuel BAEL poteaux ≈ 0.10 % (à vérifier) sous 4 %.
        """
        Ac = geo.b * geo.h
        rho_min = 0.0010    # 0.10 % — valeur usuelle À CONFIRMER
        rho_max = 0.04      # 4 % — seuil usuel À CONFIRMER
        As_min = rho_min * Ac
        As_max = rho_max * Ac
        rho = As_provided_cm2 / Ac if Ac > 0 else 0.0

        # Armature insuffisante ou excessive -> NON_CONFORME (constructif clair)
        if As_provided_cm2 < As_min:
            status = RegulatoryStatus.NON_CONFORME
            msg = f"Armature {As_provided_cm2:.1f} cm² < As,min {As_min:.1f} cm²."
        elif As_provided_cm2 > As_max:
            status = RegulatoryStatus.NON_CONFORME
            msg = f"Armature {As_provided_cm2:.1f} cm² > As,max {As_max:.1f} cm²."
        else:
            status = RegulatoryStatus.A_VALIDER
            msg = (f"Armature {As_provided_cm2:.1f} cm² dans [As,min={As_min:.1f} ; "
                   f"As,max={As_max:.1f}] (ρ={rho*100:.2f}%). ρ_min/ρ_max à confirmer.")

        art = self.article("BAEL91r99-COMPR")
        return VerificationResult(
            check_id="min_reinforcement", article_code=art.code,
            computed_value=As_provided_cm2, limit_value=As_min, unit="cm2",
            margin=As_provided_cm2 - As_min, status=status, message=msg,
        )

    # Flexion composée via diagramme d'interaction N/M (spec §10.3, §11.3)
    def check_flexion_composed(self, geo: ColumnGeometry,
                               mat: ColumnMaterials,
                               actions: ColumnActions,
                               bars: List[Tuple[float, float]],
                               M_kNm: Optional[float] = None,
                               model: Optional[SectionModel] = None
                               ) -> VerificationResult:
        """
        Vérification en flexion composée (N + M) par diagramme d'interaction.

        `bars` : liste (d, As) positions des armatures depuis la fibre
        COMPRIMÉE extrême (cm) et aires (cm2), disposées pour l'axe de
        flexion concerné. `M_kNm` (sinon actions.My) doit correspondre à cet
        axe. Verdict Conforme/Non conforme SEULEMENT si l'article FLEXCOMP est
        verified (spec §11.3) ; sinon A_VALIDER (jamais conforme silencieux).
        """
        fcd = mat.fck / mat.gamma_c
        fyd = mat.fyk / mat.gamma_s
        dm = DesignMaterials(fcd=fcd, fyd=fyd, Es=mat.E)
        sec = RectSection(b=geo.b, h=geo.h, bars=list(bars))
        N_ed = actions.N
        M_ed = actions.My if M_kNm is None else M_kNm
        art = self.article("BAEL91r99-FLEXCOMP")

        Mr = capacity_at_normal(sec, dm, N_ed, model=model)
        if Mr is not None and Mr > 0.0:
            ratio = abs(M_ed) / Mr
            computed, limit, unit = M_ed, Mr, "kN.m"
            margin = Mr - abs(M_ed)
            detail = (f"Mr(N={N_ed:.0f} kN)={Mr:.1f} kN.m, M_ed={M_ed:.1f} kN.m "
                      f"(ratio {ratio:.2f})")
        else:
            # N hors domaine du diagramme (au-delà de la capacité en N pur)
            diag = interaction_diagram(sec, dm, n_points=200, model=model)
            N_max, N_min = diag[0][0], diag[-1][0]
            limit = N_max if N_ed > 0 else N_min
            ratio = abs(N_ed / limit) if limit else float("inf")
            computed, unit = N_ed, "kN"
            margin = (limit - N_ed)
            detail = (f"N_ed={N_ed:.0f} kN hors domaine du diagramme "
                      f"[N_min={N_min:.0f}, N_max={N_max:.0f}] : section "
                      f"insuffisante en effort normal, M non évaluable.")

        if not art.verified:
            status = RegulatoryStatus.A_VALIDER
        else:
            status = (RegulatoryStatus.CONFORME if ratio <= 1.0
                      else RegulatoryStatus.NON_CONFORME)

        return VerificationResult(
            check_id="flexion_composed", article_code=art.code,
            combination=actions.combination,
            computed_value=computed, limit_value=limit, unit=unit,
            margin=margin, status=status,
            message=f"{detail}. Méthode : diagramme d'interaction (bloc λ/η, "
                    "ε_cu paramétrés) ; coefficients à confirmer (A_VALIDER).",
        )

    # Effets du second ordre (amplification des moments, spec §10.3)
    def check_second_order(self, geo: ColumnGeometry,
                           mat: ColumnMaterials,
                           actions: ColumnActions,
                           l0_m: float,
                           EI_kNm2: float,
                           M_kNm: Optional[float] = None,
                           cracking_factor: float = 1.0
                           ) -> VerificationResult:
        """
        Amplification nominale M2 = M1/(1 − N/N_cr), N_cr = π²EI/l0².

        `EI_kNm2` est une ENTRÉE (rigidité fissurée) déterminée par
        l'ingénieur/SOLVER — ce module ne la choisit pas. Instabilité (N≥N_cr)
        signalée explicitement dans le message ; verdict Conforme/Non conforme
        gate sur l'article 2ORD (verified) — sinon A_VALIDER.
        """
        art = self.article("BAEL91r99-2ORD")
        M1 = actions.My if M_kNm is None else M_kNm
        inp = SecondOrderInput(N_ed_kN=actions.N, M1_kNm=M1, l0_m=l0_m,
                               EI_kNm2=EI_kNm2, cracking_factor=cracking_factor)
        res = second_order_moment(inp)
        N_cr = res["N_cr_kN"]
        ratio = (actions.N / N_cr) if N_cr else float("inf")
        if not math.isfinite(ratio):
            ratio = float("inf")

        if not art.verified:
            status = RegulatoryStatus.A_VALIDER
        else:
            status = (RegulatoryStatus.CONFORME
                      if (res["stable"] and ratio <= 1.0)
                      else RegulatoryStatus.NON_CONFORME)

        if res["stable"]:
            msg = (f"M1={M1:.1f} kN.m → M2={res['M2_kNm']:.1f} kN.m "
                   f"(amp ×{res['amplification']:.3f}), N_cr={N_cr:.0f} kN, "
                   f"ratio N/N_cr={ratio:.2f}.")
        else:
            msg = f"INSTABILITÉ — {res['reason']} M1={M1:.1f} kN.m non amplifiable."

        return VerificationResult(
            check_id="second_order", article_code=art.code,
            combination=actions.combination,
            computed_value=(ratio if math.isfinite(ratio) else None),
            limit_value=1.0, unit="-",
            margin=(1.0 - ratio) if math.isfinite(ratio) else None,
            status=status, message=msg,
        )

    # -- Cas de référence (spec §17.2) ------------------------------------

    def _ref_compression(self, geo, mat, As) -> str:
        fcd = mat.fck / mat.gamma_c
        fyd = mat.fyk / mat.gamma_s
        Ac = geo.b * geo.h - As
        Nr = (0.6 * fcd * Ac + fyd * As) / K_MPA_CM2_TO_KN
        return (f"Calcul manuel: fcd={fcd:.2f}, Ac={Ac:.1f}cm2, "
                f"Nr=(0.6*{fcd:.2f}*{Ac:.1f} + {fyd:.2f}*{As:.1f})"
                f"/{K_MPA_CM2_TO_KN:.0f} = {Nr:.1f} kN")


# Instance singleton du référentiel
bael91r99 = Bael91r99()


# ---------------------------------------------------------------------------
# Cas de référence pour tests de non-régression (spec §17.2)
# ---------------------------------------------------------------------------
REFERENCE_CASES: List[dict] = [
    {
        "id": "REF-COMPRESSION-01",
        "article": "BAEL91r99-COMPR",
        "geo": ColumnGeometry(b=25.0, h=25.0, height=3.0,
                              buckling_length_y=3.0, buckling_length_z=3.0),
        "mat": ColumnMaterials(fck=30.0, fyk=500.0, E=200000.0),
        "As_total_cm2": 0.0,
        # fcd=20 MPa, Ac=625 cm2, Nr=0.6*20*625 = 7500 MPa.cm2
        #  -> /K(=10) = 750 kN (hors acier). Conversion MPa.cm2->kN = /10 (§5.3).
        "expected_Nr_kN": 750.0,
        "tolerance": 0.01,
    },
]
