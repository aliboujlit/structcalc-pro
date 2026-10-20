# -*- coding: utf-8 -*-
"""
tests/unit/test_module71_pipeline.py — Module 71 : pipeline complet
§11.3 (tests de calcul) + §11.4 (tests documentaires) + §16 (acceptation).
"""

import pytest

from structcalc.core.model import Project
from structcalc.core.status import DataStatus, RegulatoryStatus
from structcalc.architectural_structural import (
    ArchitecturalModel, import_architectural_source, build_grid,
    propose_layout, create_variants, build_structural_model,
    build_analysis_model, VariantManager, LoadEntry, link_loads,
    detect_column_vs_opening, detect_documentary_conflict, conflict_register,
    preflight_send, receive_results, generate_formwork_drawing,
    generate_drawing_set, drawing_content, dispatch_change, stale_results,
    ValidationGate, check_model_drawing_consistency, Drawing, DeliveryStatus,
    detect_structural_discontinuity, CHANGE_MOVE_COLUMN,
)

REF_SOURCE = {
    "unit": "m",
    "levels": [
        {"name": "RDC", "elevation": 0.0, "height": 3.5},
        {"name": "R+1", "elevation": 3.5, "height": 3.0},
        {"name": "R+2", "elevation": 6.5, "height": 3.0},
        {"name": "R+3", "elevation": 9.5, "height": 3.0},
    ],
    "axes_x": [0.0, 5.0, 10.0],
    "axes_y": [0.0, 5.0, 10.0],
    "openings": [],
    "elements": [],
}


def build_pipeline():
    """Import -> grille -> layout -> modèle -> modèle analytique."""
    proj = Project(sc_id="SC-TEST-R3-100M2", name="Référence R+3")
    am = ArchitecturalModel(project=proj)
    assert import_architectural_source(am, "raw", REF_SOURCE).ok()
    grid = build_grid(am)
    layout = propose_layout(am, level_ref=None, grid=grid)
    build_structural_model(am, layout, level_ref=None,
                           material_ref=None, section_ref=None)
    am_mod = build_analysis_model(am)
    return am, grid, layout, am_mod


# ---------------------------------------------------------------------------
# §11.3 — Tests de calcul
# ---------------------------------------------------------------------------

def test_every_load_has_origin():
    """Chaque charge possède une origine (§11.3)."""
    am, *_ = build_pipeline()
    entries = [
        LoadEntry(kind="dead", value=5.0, origin="auto: géométrie dalle",
                  target_ref="SC-SLAB-000001", automatic_dead=True),
        LoadEntry(kind="live", value=2.0, origin="Eurocode/BAEL usage bureaux",
                  target_ref="SC-SLAB-000001"),
    ]
    rep = link_loads(am, entries)
    assert rep.ok
    assert not rep.missing_origins
    assert all(t["origin"] for t in rep.traced)


def test_load_without_origin_rejected():
    """Une charge sans origine est REFUSÉE, pas acceptée (§11.3)."""
    am, *_ = build_pipeline()
    bad = LoadEntry(kind="live", value=2.0, origin="", target_ref="X")
    rep = link_loads(am, [bad])
    assert not rep.ok
    assert bad.origin == ""
    assert any("Origine" in e for e in rep.errors)


def test_units_coherent():
    """Les unités sont cohérentes (§11.3)."""
    am, *_ = build_pipeline()
    e = LoadEntry(kind="live", value=2.0, unit="kN/m2", origin="test",
                  target_ref="SC-SLAB-000001")
    rep = link_loads(am, [e])
    assert rep.entries[0].unit == "kN/m2"


def test_dead_load_not_double_counted():
    """Le poids propre n'est pas compté deux fois (§7.2, §11.3)."""
    am, *_ = build_pipeline()
    slab = "SC-SLAB-000001"
    entries = [
        LoadEntry(kind="dead", value=5.0, origin="auto: peso propio",
                  target_ref=slab, automatic_dead=True),
        LoadEntry(kind="dead", value=5.0, origin="saisie manuelle",
                  target_ref=slab, automatic_dead=False),
        LoadEntry(kind="live", value=2.0, origin="test", target_ref=slab),
    ]
    rep = link_loads(am, entries)
    assert rep.double_counting, "double comptage non détecté"
    assert not rep.ok


def test_cases_and_combinations_identified():
    """Les cas et combinaisons sont identifiés (§11.3)."""
    am, *_ = build_pipeline()
    e = LoadEntry(kind="live", value=2.0, origin="test",
                  target_ref="SC-SLAB-000001",
                  combination="1.35 G + 1.5 Q")
    rep = link_loads(am, [e])
    assert rep.traced[0]["combination"] == "1.35 G + 1.5 Q"


def test_robot_results_match_sent_model():
    """Les résultats Robot correspondent au modèle envoyé (§8.3)."""
    am, grid, layout, am_mod = build_pipeline()
    pre = preflight_send(am, am_mod.sc_id)
    # Le modèle de référence n'a pas d'appuis -> export signalé non prêt
    # (aucun faux succès). On vérifie que les 7 contrôles existent.
    good = {
        "model_version": am_mod.version,
        "member_ids": list(am_mod.member_ids),
        "reactions": {}, "bar_forces": {}, "displacements": {},
        "combinations": ["1.35G+1.5Q"],
        "calc_error": "",
    }
    rep = receive_results(am, am_mod.sc_id, good,
                          units={"force": "kN", "length": "m"})
    assert [c.index for c in rep.checks] == list(range(1, 8))
    # Contrôle 1 (version) passe
    assert rep.checks[0].passed is True
    assert rep.accepted, f"non accepté : {rep.to_dict()}"
    # Un résultat est stocké et traçable
    assert len(am.analysis_results) == 1
    res = list(am.analysis_results.values())[0]
    assert res.model_version == am_mod.version
    assert res.software == "Robot"


def test_robot_version_mismatch_rejected():
    """Une version de modèle divergente est REJETÉE (§8.3.1)."""
    am, *_ , am_mod = build_pipeline()
    bad = {"model_version": am_mod.version + 99, "member_ids": [],
           "reactions": {}, "combinations": ["x"], "calc_error": ""}
    rep = receive_results(am, am_mod.sc_id, bad,
                          units={"force": "kN", "length": "m"})
    assert not rep.accepted
    assert rep.checks[0].passed is False
    # Aucun résultat stocké si refusé
    assert len(am.analysis_results) == 0


def test_calc_error_signalé():
    """Les erreurs de calcul bloquantes sont signalées (§11.3)."""
    am, *_, am_mod = build_pipeline()
    err = {"model_version": am_mod.version,
           "member_ids": list(am_mod.member_ids),
           "reactions": {}, "combinations": ["x"],
           "calc_error": "matrice singulière"}
    rep = receive_results(am, am_mod.sc_id, err,
                          units={"force": "kN", "length": "m"})
    assert not rep.accepted
    assert rep.checks[4].passed is False      # contrôle 5
    assert any("matrice singulière" in e for e in rep.errors)


def test_results_outdated_after_modification():
    """Les résultats périmés sont invalidés après modification (§11.3, §12)."""
    am, *_, am_mod = build_pipeline()
    good = {"model_version": am_mod.version,
            "member_ids": list(am_mod.member_ids),
            "reactions": {"SC-NODE-000001": {"Fx": 0.0}},
            "combinations": ["x"], "calc_error": ""}
    receive_results(am, am_mod.sc_id, good,
                    units={"force": "kN", "length": "m"})
    assert not stale_results(am)
    # Modification -> résultats périmés
    dispatch_change(am, CHANGE_MOVE_COLUMN, "SC-COLUMN-000001",
                    reason="déplacement poteau P-B2", actor="ingé")
    assert stale_results(am), "résultats non invalidés après modif"
    for r in stale_results(am):
        assert r.outdated is True
        assert r.model_version == am_mod.version   # trace de la version


# ---------------------------------------------------------------------------
# §11.4 — Tests documentaires
# ---------------------------------------------------------------------------

def test_drawings_match_validated_version():
    """Les plans correspondent à la version validée (§11.4)."""
    am, *_, am_mod = build_pipeline()
    drawings = generate_drawing_set(am, model_ref=am_mod.sc_id,
                                    model_version=am_mod.version)
    assert len(drawings) >= 8
    for d in drawings:
        assert d.model_version == am_mod.version


def test_marks_identical_in_model_and_drawings():
    """Les repères sont identiques dans modèle et dessins (§11.4)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="Test",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    known = set(am.project.columns) | set(am.project.beams)
    assert set(dr.element_ids) <= known
    rep = check_model_drawing_consistency(am, current_model_version=am_mod.version)
    mark_errors = [f for f in rep.errors if f.code == "MARK_MISMATCH"]
    assert not mark_errors


def test_provisional_sections_identified():
    """Les sections provisoires sont identifiées (§11.4, §10.2)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="Test",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    # Aucune section assignée -> toutes provisoires
    assert dr.sections_provisional
    content = drawing_content(am, dr.sc_id)
    assert content.is_provisional
    assert any("provisoire" in w.lower() for w in content.warnings)


def test_section_drawings_carry_visible_provisional_note():
    """Régression : les plans coupes/détails doivent porter la MENTION
    provisoire visible (§10.2), sinon le contrôle documentaire signale
    PROVISIONAL_HIDDEN. Le générateur pose la mention, pas seulement le
    contrôle."""
    am, *_, am_mod = build_pipeline()
    drawings = generate_drawing_set(am, model_ref=am_mod.sc_id,
                                    model_version=am_mod.version)
    section_dr = [d for d in drawings if d.kind in ("section", "detail")]
    assert section_dr, "aucun plan coupe/détails généré"
    for d in section_dr:
        if d.sections_provisional:
            assert d.notes, (f"Plan {d.sc_id} : sections provisoires sans "
                             f"mention visible (§10.2)")
    # Aucune erreur PROVISIONAL_HIDDEN dans le contrôle documentaire
    rep = check_model_drawing_consistency(am, current_model_version=am_mod.version)
    hidden = [f for f in rep.errors if f.code == "PROVISIONAL_HIDDEN"]
    assert not hidden, [f.detail for f in hidden]


def test_open_conflicts_visible():
    """Les conflits non résolus sont visibles (§11.4)."""
    am, *_ = build_pipeline()
    # Ouvrir un conflit
    cf = am.new_conflict(kind="GEOMETRIC", description="poteau devant porte",
                         source="test")
    open_ids = [c.sc_id for c in am.open_conflicts()]
    assert cf.sc_id in open_ids
    reg = conflict_register(am)
    assert cf.sc_id in reg["open"]
    assert cf.sc_id in reg["blocking_delivery"]


def test_revisions_historized():
    """Les révisions sont historisées (§11.4, §15)."""
    am, *_, am_mod = build_pipeline()
    dispatch_change(am, CHANGE_MOVE_COLUMN, "SC-COLUMN-000001",
                    reason="adaptation architecturale", actor="architecte")
    assert am.revisions, "aucune révision historisée"
    rev = list(am.revisions.values())[0]
    assert rev.actor == "architecte"
    assert rev.reason == "adaptation architecturale"


def test_documents_associated_with_validation():
    """Les documents diffusés sont associés à leur validation (§11.4, §77)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="Test",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    # Enregistrer une approval
    from structcalc.architectural_structural import Approval
    aid = am.new_id("APPROVAL")
    ap = Approval(sc_id=aid, subject_ref=dr.sc_id, subject_kind="DRAWING",
                  role="BET", actor="ingé bet", decision="APPROVED")
    am.approvals[aid] = ap
    dr.validations.append(aid)
    assert dr.validations == [aid]
    assert am.approvals[aid].decision == "APPROVED"


# ---------------------------------------------------------------------------
# Portes de validation (§13, §16.12)
# ---------------------------------------------------------------------------

def test_gate_blocks_final_without_controls():
    """Un document dont les contrôles restent ouverts NE PEUT PAS être
    présenté comme définitif (§16.12)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="Test",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    gate = ValidationGate(am)
    # Tentative de saut direct DRAFT -> VALIDATED : transition interdite
    res = gate.advance(dr.sc_id, DeliveryStatus.VALIDATED_FOR_DELIVERY)
    assert not res.allowed
    assert dr.status == DeliveryStatus.DRAFT     # inchangé

    # Progression valide jusqu'à VERIFIED mais SANS marquer les contrôles
    for status in (DeliveryStatus.PRELIMINARY, DeliveryStatus.UNDER_REVIEW,
                   DeliveryStatus.APPROVED_FOR_CALCULATION,
                   DeliveryStatus.CALCULATED, DeliveryStatus.VERIFIED):
        r = gate.advance(dr.sc_id, status, actor="a", reason="étape")
        assert r.allowed, f"refus {status}: {r.message}"
    # Le passage final échoue : contrôles manquants
    res = gate.advance(dr.sc_id, DeliveryStatus.VALIDATED_FOR_DELIVERY)
    assert not res.allowed
    assert res.missing_controls
    assert dr.status == DeliveryStatus.VERIFIED   # bloqué avant diffusion


def test_gate_allows_after_all_controls_and_no_conflicts():
    """Après les 4 contrôles + conflits traités, la validation passe (§13)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="Test",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    gate = ValidationGate(am)
    for c in ("geometric", "analytic", "regulatory", "documentary"):
        gate.mark_control(dr.sc_id, c, True, "exécuté")
    # Progression normale étape par étape
    for status in (DeliveryStatus.PRELIMINARY, DeliveryStatus.UNDER_REVIEW,
                   DeliveryStatus.APPROVED_FOR_CALCULATION,
                   DeliveryStatus.CALCULATED, DeliveryStatus.VERIFIED):
        r = gate.advance(dr.sc_id, status, actor="ingé", reason="étape")
        assert r.allowed, f"refus {status}: {r.message}"
    r = gate.advance(dr.sc_id, DeliveryStatus.VALIDATED_FOR_DELIVERY,
                     actor="bet", reason="contrôles ok")
    assert r.allowed, r.message
    assert dr.status == DeliveryStatus.VALIDATED_FOR_DELIVERY
    readiness = gate.delivery_readiness()
    assert readiness[dr.sc_id]["can_be_presented_as_final"] is True


def test_calculated_does_not_imply_conformity():
    """CALCULATED ne préjuge JAMAIS de la conformité (§13)."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="T",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    gate = ValidationGate(am)
    gate.advance(dr.sc_id, DeliveryStatus.PRELIMINARY, actor="a", reason="r")
    gate.advance(dr.sc_id, DeliveryStatus.UNDER_REVIEW, actor="a", reason="r")
    gate.advance(dr.sc_id, DeliveryStatus.APPROVED_FOR_CALCULATION,
                 actor="a", reason="r")
    res = gate.advance(dr.sc_id, DeliveryStatus.CALCULATED, actor="a",
                       reason="calcul fait")
    assert res.allowed
    assert dr.status == DeliveryStatus.CALCULATED
    # Ce n'est PAS VALIDATED_FOR_DELIVERY
    assert dr.status != DeliveryStatus.VALIDATED_FOR_DELIVERY
    readiness = gate.delivery_readiness()[dr.sc_id]
    assert readiness["is_final"] is False


def test_gate_blocks_final_when_open_conflict():
    """Un conflit ouvert empêche la validation finale (§13) — il bloque
    déjà la progression au-delà de UNDER_REVIEW."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, level_ref=None, title="T",
                                   model_ref=am_mod.sc_id,
                                   model_version=am_mod.version)
    gate = ValidationGate(am)
    for c in ("geometric", "analytic", "regulatory", "documentary"):
        gate.mark_control(dr.sc_id, c, True)
    # Ouvrir un conflit AVANT la progression
    am.new_conflict(kind="STRUCTURAL", description="porteur interrompu")
    # Jusqu'à UNDER_REVIEW : autorisé
    for status in (DeliveryStatus.PRELIMINARY, DeliveryStatus.UNDER_REVIEW):
        r = gate.advance(dr.sc_id, status, actor="a", reason="r")
        assert r.allowed, f"refus inattendu {status}: {r.message}"
    # Au-delà : BLOQUÉ par le conflit ouvert
    res = gate.check_advance(dr.sc_id,
                             DeliveryStatus.APPROVED_FOR_CALCULATION)
    assert not res.allowed
    assert res.blocking_conflicts
    assert dr.status == DeliveryStatus.UNDER_REVIEW   # non avancé


# ---------------------------------------------------------------------------
# §16 — Critères d'acceptation
# ---------------------------------------------------------------------------

def test_acceptance_stable_ids_and_structure():
    """§16.2 : représentation interne à identifiants stables."""
    am, grid, layout, am_mod = build_pipeline()
    for sc_id in list(am.project.nodes)[:5]:
        assert sc_id.startswith("SC-NODE-")
    assert am_mod.sc_id.startswith("SC-ANALYSISMODEL-")
    assert am_mod.version == 1


def test_acceptance_detects_incoherence():
    """§16.4 : détecte incohérences géométriques et discontinuités."""
    am, *_ = build_pipeline()
    findings = check_model_drawing_consistency(am, current_model_version=1)
    assert isinstance(findings.ok, bool)
    # Continuité : discontinuité détectée
    disc = [{"code": "INTERRUPTED", "lower": "SC-COLUMN-000001",
             "upper": None, "detail": "test"}]
    dc = detect_structural_discontinuity(am, disc)
    assert dc and dc[0].kind.value == "STRUCTURAL"


def test_acceptance_variants_comparable():
    """§16.8 : identifie conflits et permet de comparer les variantes."""
    am, grid, layout, am_mod = build_pipeline()
    variants = create_variants(am)
    assert set(variants) == {"A", "B", "C", "D"}
    vm = VariantManager(am)
    for v in variants.values():
        vm.attach_layout(v.sc_id, layout)
    comps = vm.compare()
    assert len(comps) == 4
    assert any(c.is_reference for c in comps)
    assert vm.best_by_conflicts() is not None


def test_acceptance_invalidates_affected_documents():
    """§16.10 : invalide résultats et documents affectés par une modif."""
    am, *_, am_mod = build_pipeline()
    generate_formwork_drawing(am, None, "T", am_mod.sc_id, am_mod.version)
    rep = dispatch_change(am, CHANGE_MOVE_COLUMN, "SC-COLUMN-000001",
                          reason="test", actor="a")
    assert rep.documents_to_regenerate
    assert rep.conflicts_opened
    # Chaque document à régénérer a un conflit documentaire ouvert
    reg = conflict_register(am)
    assert reg["by_kind"].get("DOCUMENTARY", 0) >= 1


def test_acceptance_never_final_when_controls_open():
    """§16.12 : interdit de présenter définitif un document à contrôles
    obligatoires ouverts."""
    am, *_, am_mod = build_pipeline()
    dr = generate_formwork_drawing(am, None, "T", am_mod.sc_id, am_mod.version)
    gate = ValidationGate(am)
    # Même avec conflits résolus, sans contrôles -> pas définitif
    readiness = gate.delivery_readiness()[dr.sc_id]
    assert readiness["can_be_presented_as_final"] is False
    assert readiness["controls_missing"]
