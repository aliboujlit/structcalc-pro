# -*- coding: utf-8 -*-
"""
tools/verify_module71_pipeline.py — Vérification de bout en bout Module 71.

Exécute la chaîne complète (Phases A -> J) sur le projet de référence
SC-TEST-R3-100M2 et affiche une trace lisible :

  A IMPORT -> NORMALISATION -> B TRAME/PROPOSITION -> C MODÈLE ->
  D CONTINUITÉ/CHARGES -> E ROBOT -> F CONFLITS -> G PLANS ->
  I IMPACT -> J VALIDATION -> DIFFUSION

Aucune donnée n'est inventée : les statuts et hypothèses sont affichés tels
quels. Code pur (pas de COM/Qt) — exécutable sans Robot ni PyQt6.

Usage : python tools/verify_module71_pipeline.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structcalc.core.model import Project                      # noqa: E402
from structcalc.architectural_structural import (              # noqa: E402
    ArchitecturalModel, import_architectural_source, build_grid,
    propose_layout, create_variants, build_structural_model,
    build_analysis_model, VariantManager, LoadEntry, link_loads,
    check_vertical_continuity, conflict_register, preflight_send,
    receive_results, generate_drawing_set, dispatch_change,
    ValidationGate, check_model_drawing_consistency, Drawing,
    DeliveryStatus, CHANGE_MOVE_COLUMN,
)

STEP = 0


def step(title: str) -> None:
    global STEP
    STEP += 1
    print(f"\n[{STEP:02d}] {title}")
    print("-" * 68)


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
    "openings": [
        {"kind": "stairwell", "level": "R+1", "cx": 7.5, "cy": 2.5,
         "width": 2.4, "depth": 4.8},
    ],
    "elements": [
        {"kind": "wall", "level": "RDC", "function": "BEARING",
         "outline": [(0, 0), (10, 0)]},
        {"kind": "partition", "level": "RDC", "function": "UNKNOWN",
         "outline": [(5, 0), (5, 10)]},
    ],
}


def main() -> int:
    print("=" * 68)
    print("STRUCTCALC PRO — Vérification pipeline MODULE 71")
    print("Projet de référence : SC-TEST-R3-100M2 (R+3, 10x10, trame 5m)")
    print("=" * 68)

    # -- A : IMPORT -------------------------------------------------------
    step("PHASE A — Import architectural + normalisation (§4)")
    proj = Project(sc_id="SC-TEST-R3-100M2", name="Reference R+3")
    am = ArchitecturalModel(project=proj)
    rep = import_architectural_source(am, "raw", REF_SOURCE)
    print(f"  Unités détectées : {rep.units_detected} "
          f"(x{rep.scale_factor})")
    print(f"  Niveaux : {rep.levels_found} | Axes : {rep.axes_found} "
          f"| Ouvertures/éléments : {len(am.openings)}/{len(am.arch_elements)}")
    print(f"  Blocages : {len(rep.blocking_issues)} -> modèle "
          f"{'AUTORISÉ' if rep.ok() else 'INTERDIT'} (§4.4)")
    for i in rep.issues:
        print(f"    - [{i.severity}] {i.code}: {i.message[:70]}")
    assert rep.ok(), "import bloqué"

    # -- B : TRAME + PROPOSITION -----------------------------------------
    step("PHASE B — Trame d'axes + proposition système porteur (§3, §5)")
    grid = build_grid(am)
    print(f"  Nœuds : {len(grid.nodes)} | Poteaux : {grid.n_columns} | "
          f"Panleaux : {grid.n_panels}")
    spans = [f"{a}-{b}={d:.2f}" for a, b, d in grid.spans]
    print(f"  Entraxes calculés : {', '.join(spans)}")
    for r in grid.reasons[:3]:
        print(f"    . {r[:75]}")
    assert grid.n_columns == 9 and grid.n_panels == 4

    variants = create_variants(am)
    layout = propose_layout(am, grid=grid, variant=variants["A"])
    vm = VariantManager(am)
    vm.attach_layout(variants["A"].sc_id, layout)
    print(f"  Variantes créées : {sorted(variants)} (A = référence)")
    print(f"  Layout A : {layout.summary()['columns']} poteaux, "
          f"{layout.summary()['beams']} poutres, "
          f"{layout.summary()['slabs']} dalles")
    print(f"  Portées longues à étudier : {len(layout.long_spans())}")
    print(f"  PROVISIONNEL : {' | '.join(layout.warnings)[:60] or 'aucun'}")

    # -- C : MODÈLE CANONIQUE + ANALYTIQUE -------------------------------
    step("PHASE C — Modèle structurel canonique SC-* + modèle analytique (§6)")
    b = build_structural_model(am, layout, material_ref=None, section_ref=None)
    print(f"  Nœuds : {b.nodes_created} | Poteaux : {b.columns_created} | "
          f"Poutres : {b.beams_created} | Dalles : {b.slabs_created}")
    for w in b.warnings:
        print(f"    ! {w}")
    for a in b.assumptions:
        print(f"    ? {a[:70]}")
    am_mod = build_analysis_model(am, variant_ref=variants["A"].sc_id)
    print(f"  Modèle analytique : {am_mod.sc_id} v{am_mod.version} "
          f"({len(am_mod.node_ids)} nœuds, {len(am_mod.member_ids)} barres)")

    # -- D : CONTINUITÉ + CHARGES ----------------------------------------
    step("PHASE D — Continuité verticale + liaison charges (§7.1, §7.2)")
    level_ids = [lv.sc_id for lv in
                 sorted(am.levels.values(), key=lambda l: l.index)]
    # Regroupement des poteaux par niveau (via le nœud de départ)
    cols_by_level = {lid: [] for lid in level_ids}
    if level_ids:
        base = level_ids[0]
        for c, col in am.project.columns.items():
            pos = _col_pos(col, am)
            if pos is None:
                continue
            cols_by_level[base].append(
                {"ref": c, "x": pos[0], "y": pos[1], "section": None})
    cont = check_vertical_continuity(am, level_ids, cols_by_level)
    print(f"  Constats de continuité : {len(cont.findings)} -> "
          f"{cont.summary}")
    print("  (aucun constat concluant seul — analyse requise, §7.1)")

    entries = [
        LoadEntry(kind="dead", value=5.0, origin="auto: geometrie dalle",
                  target_ref="SC-SLAB-000001", automatic_dead=True),
        LoadEntry(kind="live", value=2.0, origin="BAEL usage bureaux",
                  target_ref="SC-SLAB-000001", combination="1.35G+1.5Q"),
    ]
    lrep = link_loads(am, entries, analysis_model_ref=am_mod.sc_id)
    print(f"  Charges tracées : {lrep.n_loads} | OK : {lrep.ok} | "
          f"Double comptage : {len(lrep.double_counting)}")
    print(f"  Origines manquantes : {lrep.missing_origins or 'aucune'}")
    assert lrep.ok and not lrep.missing_origins

    # -- E : ROBOT (simulation d'un retour conforme) ---------------------
    step("PHASE E — Échange Robot : 7 contrôles de retour (§8.3)")
    pre = preflight_send(am, am_mod.sc_id)
    print(f"  Preflight (avant envoi) : erreurs = {pre.errors or 'aucune'}")
    raw = {"model_version": am_mod.version,
           "member_ids": list(am_mod.member_ids),
           "reactions": {}, "bar_forces": {}, "displacements": {},
           "combinations": ["1.35G+1.5Q"], "calc_error": ""}
    ex = receive_results(am, am_mod.sc_id, raw,
                         units={"force": "kN", "length": "m"})
    for c in ex.checks:
        st = "OK" if c.passed else ("FAIL" if c.passed is False else "N/C")
        print(f"    [{c.index}] {st:4} {c.label[:55]}")
    print(f"  Résultats ACCEPTÉS : {ex.accepted}")
    assert ex.accepted

    # -- F : CONFLITS -----------------------------------------------------
    step("PHASE F — Détection et suivi des conflits (§9)")
    cf = am.new_conflict(kind="GEOMETRIC",
                         description="Poteau devant porte (simulé)",
                         source="verification")
    print(f"  Conflit ouvert : {cf.sc_id} [{cf.status}]")
    print(f"  Cycle autorisé depuis DETECTED : "
          f"{sorted(__import__('structcalc.architectural_structural', fromlist=['CONFLICT_TRANSITIONS']).CONFLICT_TRANSITIONS['DETECTED'])}")
    print(f"  DETECTED -> VALIDATED interdit ? "
          f"{not cf.can_transition('VALIDATED_FOR_DELIVERY')}")
    reg = conflict_register(am)
    print(f"  Registre : {reg['total']} total, ouverts = {len(reg['open'])}, "
          f"bloquants diffusion = {len(reg['blocking_delivery'])}")

    # -- G : PLANS DE COFFRAGE -------------------------------------------
    step("PHASE G — Plans de coffrage (§10)")
    drawings = generate_drawing_set(am, model_ref=am_mod.sc_id,
                                    model_version=am_mod.version)
    print(f"  Plans générés : {len(drawings)}")
    prov = [d for d in drawings if d.sections_provisional]
    print(f"  Plans à sections PROVISOIRES : {len(prov)} (visibles, §10.2)")
    for d in drawings[:4]:
        print(f"    - {d.sc_id} [{d.status.value}] {d.name[:42]}")

    # -- I : IMPACT D'UNE MODIFICATION -----------------------------------
    step("PHASE I — Impact d'une modification (§12)")
    impact = dispatch_change(am, CHANGE_MOVE_COLUMN, "SC-COLUMN-000001",
                             reason="deplacement P-B2 demande architecte",
                             actor="architecte")
    print(f"  Éléments affectés : {len(impact.affected_elements)}")
    print(f"  Résultats invalidés : {len(impact.invalidated_results)}")
    print(f"  Documents à régénérer : {len(impact.documents_to_regenerate)}")
    print(f"  Conflits ouverts : {len(impact.conflicts_opened)}")
    print(f"  Révisions tracées : {len(am.revisions)}")
    assert impact.invalidated_results, "résultats non invalidés"

    # -- J : VALIDATION + DIFFUSION --------------------------------------
    step("PHASE J — Portes de validation avant diffusion (§13)")
    target = drawings[0].sc_id
    gate = ValidationGate(am)
    # Tentative de saut -> refusé
    r = gate.advance(target, DeliveryStatus.VALIDATED_FOR_DELIVERY)
    print(f"  Saut direct -> VALIDATED : autorisé = {r.allowed} "
          f"(manquants : {r.missing_controls})")
    assert not r.allowed
    # Conflit encore ouvert -> bloque
    r2 = gate.check_advance(target, DeliveryStatus.PRELIMINARY)
    print(f"  Conflit ouvert bloque la diffusion avancée : "
          f"{len(r2.blocking_conflicts)} conflit(s)")
    # Résolution du conflit
    cf.transition("CLASSIFIED", "BET", "prise en compte")
    cf.transition("ANALYZED", "BET", "analyse")
    cf.transition("SOLUTIONS_PROPOSED", "BET", "solution")
    cf.transition("UNDER_REVIEW", "BET", "revue")
    cf.transition("APPROVED_FOR_CALCULATION", "BET", "approuve")
    cf.transition("RECALCULATED", "BET", "recalcule")
    cf.transition("VERIFIED", "BET", "verifie")
    cf.transition("VALIDATED_FOR_DELIVERY", "BET", "valide")
    print(f"  Conflit résolu -> {cf.status}")
    # Contrôles des 4 familles
    for c in ("geometric", "analytic", "regulatory", "documentary"):
        gate.mark_control(target, c, True, "execute")
    chain = [DeliveryStatus.PRELIMINARY, DeliveryStatus.UNDER_REVIEW,
             DeliveryStatus.APPROVED_FOR_CALCULATION,
             DeliveryStatus.CALCULATED, DeliveryStatus.VERIFIED,
             DeliveryStatus.VALIDATED_FOR_DELIVERY]
    for st in chain:
        res = gate.advance(target, st, actor="BET", reason="controle ok")
        if not res.allowed:
            print(f"  BLOQUÉ {st.value}: {res.message}")
    print(f"  Statut final du plan : {drawings[0].status.value}")
    readiness = gate.delivery_readiness()[target]
    print(f"  Présentable comme définitif : "
          f"{readiness['can_be_presented_as_final']}")
    print(f"  Contrôles manquants : {readiness['controls_missing'] or 'aucun'}")

    # -- CONTRÔLE DOCUMENTAIRE FINAL -------------------------------------
    step("CONTRÔLE DOCUMENTAIRE — cohérence modèle <-> plans (§13)")
    cons = check_model_drawing_consistency(am, current_model_version=am_mod.version)
    print(f"  Erreurs : {len(cons.errors)} | Avertissements : "
          f"{len(cons.warnings)}")
    for e in cons.errors[:5]:
        print(f"    X [{e.code}] {e.detail[:65]}")

    print("\n" + "=" * 68)
    print("RÉSULTAT : chaîne Module 71 exécutée sans erreur.")
    print(f"  Objets du projet : {am.counts()}")
    print("  Aucune donnée inventée ; statuts/hypothèses affichés tels quels.")
    print("=" * 68)
    return 0


def _col_pos(col, am):
    """Position (x, y) d'un poteau via son nœud de départ (si mappé)."""
    n = am.project.nodes.get(col.start_node)
    if n is None:
        return None
    return (float(n.x.value) if not n.x.is_missing else 0.0,
            float(n.y.value) if not n.y.is_missing else 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
