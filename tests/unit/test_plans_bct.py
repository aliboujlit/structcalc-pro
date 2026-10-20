# -*- coding: utf-8 -*-
"""
tests/unit/test_plans_bct.py — Plans de coffrage/ferraillage + dossier BCT.

Teste les modules de livrables v1.4 avec des pivots FAUX — AUCUNE
connexion Robot/COM/AutoCAD. Honnêteté vérifiée :
  - parsing des labels section (convention R<b>x<h>) ;
  - plans = seuls objets RÉELLEMENT présents (0 = 0) ;
  - ferraillage = PROPOSITION A_VALIDER (jamais conforme) ;
  - dossier BCT : aucun statut « CONFORME » décerné.
"""

import math
import os
import tempfile

import pytest

from structcalc.core.model import (
    Project, Node, Column, Beam, CrossSection, TrackedValue,
)
from structcalc.core.status import DataStatus
from structcalc.core.tracked import Provenance
from structcalc.reporting.plan_coffrage import (
    parse_section_dims, build_level_plans, coffrage_pdf,
)
from structcalc.reporting.plan_ferraillage import (
    bar_area_cm2, propose_bars, stirrup_proposal, plan_reinforcement,
    reinforcement_pdf, ReinforcementPlan,
)
from structcalc.reporting.dossier_bct import (
    build_dossier_bct, dossier_bct_md,
)
from structcalc.solver.column_design import ColumnVariant, DesignOutcome


def _tv(v, unit="m"):
    return TrackedValue.of(float(v), unit, DataStatus.IMPORTED,
                           Provenance.imported_from("Robot"))


def _villa_fake() -> Project:
    """Mini-villa fake : 4 poteaux 30x30, 2 poutres, 1 niveau."""
    p = Project(sc_id="SC-P", name="Villa-test")
    for i, (x, y) in enumerate([(0, 0), (6, 0), (6, 4), (0, 4)]):
        p.nodes[f"N{i}"] = Node(sc_id=f"N{i}", x=_tv(x), y=_tv(y), z=_tv(0.0))
        p.nodes[f"N{i}b"] = Node(sc_id=f"N{i}b", x=_tv(x), y=_tv(y),
                                 z=_tv(2.8))
    p.sections["S1"] = CrossSection(sc_id="S1", name="C R30x30")
    for i in range(4):
        p.columns[f"C{i}"] = Column(sc_id=f"C{i}", start_node=f"N{i}",
                                    end_node=f"N{i}b", section="S1")
    p.beams["B0"] = Beam(sc_id="B0", start_node="N0b", end_node="N1b",
                         section="S1")
    p.beams["B1"] = Beam(sc_id="B1", start_node="N1b", end_node="N2b",
                         section="S1")
    return p


# ---------------------------------------------------------------------------
# Parsing des labels de section (convention Robot R<b>x<h>)
# ---------------------------------------------------------------------------

def test_parse_section_dims_basic():
    assert parse_section_dims("C R30x30") == (30.0, 30.0)
    assert parse_section_dims("B R20x35") == (20.0, 35.0)
    assert parse_section_dims("R15x60") == (15.0, 60.0)


def test_parse_section_dims_rejects_garbage():
    assert parse_section_dims("IPE200") is None
    assert parse_section_dims("HEB300") is None
    assert parse_section_dims("") is None
    assert parse_section_dims("R300x400") is None   # hors bornes [5;200] cm


def test_parse_section_dims_accepts_decimal():
    d = parse_section_dims("R22.5x45")
    assert d is not None and d[0] == 22.5


# ---------------------------------------------------------------------------
# Plans de coffrage : géométrie
# ---------------------------------------------------------------------------

def test_build_level_plans_real_objects_only():
    p = _villa_fake()
    plans = build_level_plans(p)
    assert len(plans) == 1
    lp = plans[0]
    assert lp.z == pytest.approx(2.8)
    assert len(lp.columns) == 4          # seuls objets présents
    assert len(lp.beams) == 2
    # toutes les sections interprétées -> aucune note de refus
    assert all(c.dims_cm == (30.0, 30.0) for c in lp.columns)


def test_build_level_plans_empty_project():
    p = Project(sc_id="SC-P")
    assert build_level_plans(p) == []


def test_build_level_plans_unreadable_nodes_skipped():
    p = Project(sc_id="SC-P")
    p.nodes["N1"] = Node(sc_id="N1")          # coordonnées MISSING
    p.nodes["N2"] = Node(sc_id="N2")
    p.columns["C1"] = Column(sc_id="C1", start_node="N1",
                             end_node="N2")
    assert build_level_plans(p) == []


def test_coffrage_pdf_writes_file():
    p = _villa_fake()
    out = os.path.join(tempfile.gettempdir(), "test_coffrage.pdf")
    coffrage_pdf(p, out, "Villa-test")
    assert os.path.getsize(out) > 1000


def test_coffrage_pdf_refuses_empty_project():
    p = Project(sc_id="SC-P")
    out = os.path.join(tempfile.gettempdir(), "test_coffrage_vide.pdf")
    with pytest.raises(RuntimeError, match="Aucun plan"):
        coffrage_pdf(p, out)


# ---------------------------------------------------------------------------
# Ferraillage : arithmétique des barres
# ---------------------------------------------------------------------------

def test_bar_area_cm2():
    # Ø20 mm = 2 cm -> A = pi * (2 cm)^2 / 4 = pi cm2
    assert bar_area_cm2(20.0) == pytest.approx(math.pi, rel=1e-6)


def test_propose_bars_meets_required_area():
    d, n = propose_bars(75.0, 50, 50)
    assert n * bar_area_cm2(d) >= 75.0


def test_propose_bars_min_four_bars():
    d, n = propose_bars(1.0, 30, 30)
    assert n >= 4


def test_propose_bars_even_count_symmetry():
    d, n = propose_bars(12.0, 30, 30)
    assert n % 2 == 0


def test_propose_bars_refuses_impossible():
    # 200 cm2 dans 50x50 : >4% ou arrangement non constructible -> refus
    assert propose_bars(200.0, 50, 50) is None


def test_stirrup_proposal_zones():
    d_st, e_z, e_c = stirrup_proposal(50.0, 50.0, 20.0)
    assert d_st >= 6.0
    assert e_z <= e_c          # zone d'attente plus dense que le corps


# ---------------------------------------------------------------------------
# Ferraillage : proposition à partir du pivot + dimensionnement
# ---------------------------------------------------------------------------

def test_plan_reinforcement_uses_variant_dims():
    p = _villa_fake()
    col = p.columns["C0"]
    v = ColumnVariant(b=50, h=50, As_provided_cm2=75.0, label="50x50 r3%")
    out = DesignOutcome(variant=v)
    out.rank = 1
    plan = plan_reinforcement(col, p, outcomes=[out])
    assert plan is not None
    # dimensions de la VARIANTE retenue (50x50), pas de la section (30x30)
    assert (plan.b_cm, plan.h_cm) == (50.0, 50.0)
    assert plan.as_provided_cm2 >= 75.0
    assert plan.height_m == pytest.approx(2.8)


def test_plan_reinforcement_refuses_without_design():
    p = _villa_fake()
    col = p.columns["C0"]
    assert plan_reinforcement(col, p, outcomes=None) is None


def test_plan_reinforcement_refuses_missing_height():
    p = _villa_fake()
    # nœud sans z -> hauteur inconnue
    p.nodes["N0"] = Node(sc_id="N0", x=_tv(0), y=_tv(0))
    col = p.columns["C0"]
    v = ColumnVariant(b=40, h=40, As_provided_cm2=40.0, label="40x40 r2%")
    out = DesignOutcome(variant=v)
    out.rank = 1
    assert plan_reinforcement(col, p, outcomes=[out]) is None


def test_nomenclature_masses():
    plan = ReinforcementPlan(
        column_id="C0", b_cm=50, h_cm=50, height_m=3.0,
        as_required_cm2=75.0, bar_d_mm=32.0, bar_count=10,
        stirrup_d_mm=8.0, stirrup_e_zone_mm=200.0,
        stirrup_e_corps_mm=400.0)
    rows = plan.nomenclature()
    assert len(rows) == 2
    # barre : 10 Ø32 sur 3.8 m (3.0 + 2*0.40 attente, ATTENTE_MM=400)
    lbar = 3.0 + 2 * 0.400
    assert rows[0]["longueur_m"] == pytest.approx(lbar, rel=1e-6)
    assert rows[0]["masse_kg"] == pytest.approx(
        lbar * 10 * bar_area_cm2(32.0) / 1e4 * 7850.0, rel=1e-3)
    assert plan.total_mass_kg == pytest.approx(
        sum(r["masse_kg"] for r in rows), rel=1e-6)


def test_reinforcement_pdf_writes_file():
    plan = ReinforcementPlan(
        column_id="C0", b_cm=50, h_cm=50, height_m=2.8,
        as_required_cm2=75.0, bar_d_mm=32.0, bar_count=10,
        stirrup_d_mm=8.0, stirrup_e_zone_mm=200.0,
        stirrup_e_corps_mm=400.0)
    out = os.path.join(tempfile.gettempdir(), "test_ferr.pdf")
    reinforcement_pdf(plan, out, "Villa")
    assert os.path.getsize(out) > 1000


# ---------------------------------------------------------------------------
# Dossier BCT (référentiel MA : BAEL 91 r99 + RPS 2011)
# ---------------------------------------------------------------------------

def test_dossier_bct_no_conforme_status():
    """Aucun statut « CONFORME » n'est décerné (spec §15.3)."""
    p = _villa_fake()
    d = build_dossier_bct(p)
    assert all(pc.etat != "CONFORME" for pc in d.pieces)


def test_dossier_bct_seismic_not_implemented():
    """RPS 2011 : spectre NON IMPLÉMENTÉ (motif exact, jamais conforme)."""
    p = _villa_fake()
    d = build_dossier_bct(p)
    rps = [pc for pc in d.pieces if pc.code == "BCT-05"]
    assert rps and rps[0].etat == "NON IMPLÉMENTÉ"
    assert "implémenté" in rps[0].motif or "IMPLÉMENTÉ" in rps[0].motif


def test_dossier_bct_admin_pieces_to_complete():
    p = _villa_fake()
    d = build_dossier_bct(p)
    # certificats matière, essais, géotech : TOUJOURS À COMPLÉTER
    codes = {pc.code: pc for pc in d.pieces}
    assert codes["BCT-06"].etat == "À COMPLÉTER"
    assert codes["BCT-07"].etat == "À COMPLÉTER"
    assert codes["BCT-08"].etat == "À COMPLÉTER"
    assert codes["BCT-11"].etat == "À COMPLÉTER"


def test_dossier_bct_empty_project_honest():
    """Projet vide : rien n'est GÉNÉRÉ, motifs exacts."""
    p = Project(sc_id="SC-P")
    d = build_dossier_bct(p)
    assert d.generated == []
    bct01 = [pc for pc in d.pieces if pc.code == "BCT-01"][0]
    assert bct01.etat == "À COMPLÉTER"


def test_dossier_bct_with_files_written():
    p = _villa_fake()
    files = [r"C:\x\resume_etude.pdf",
             r"C:\x\plans_coffrage.pdf",
             r"C:\x\plans_ferraillage.pdf",
             r"C:\x\fiche_poteau_C0.pdf"]
    d = build_dossier_bct(p, files_written=files, design_done=True)
    codes = {pc.code: pc for pc in d.pieces}
    assert codes["BCT-02"].etat == "GÉNÉRÉ"
    assert codes["BCT-03"].etat == "À VALIDER"    # ferraillage = proposition
    assert codes["BCT-01"].etat == "À VALIDER"    # BAEL non vérifié indép.
    assert codes["BCT-12"].etat == "GÉNÉRÉ"


def test_dossier_bct_md_rendu():
    p = _villa_fake()
    d = build_dossier_bct(p)
    md = dossier_bct_md(d, project_name="Villa")
    assert "# Dossier de contrôle" in md
    assert "BAEL 91 révisé 99" in md
    assert "RPS 2011" in md
    assert "CONFORME" in md          # dans l'avertissement (« pas une
    # attestation ») — mais JAMAIS comme statut de pièce
    # Vérifie que aucun tableau ne porte « CONFORME » comme état
    for line in md.splitlines():
        if line.startswith("| BCT-"):
            assert "| **CONFORME** |" not in line
