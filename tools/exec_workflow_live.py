# -*- coding: utf-8 -*-
"""
tools/exec_workflow_live.py — Exécution LIVE d'une démarche (workflow)
sur un projet de test réel.

Usage :
  python tools/exec_workflow_live.py

Teste : etude_sans_bim (autocad -> robot -> autocad)
sur le projet Villa Robot (.rtd).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from structcalc.core.model import Project
from structcalc.integration.interop import default_hub
from structcalc.integration.interop.loop import (
    plan_loop, exchange_plan, Selection, ROLE_CONCEPTION, ROLE_ETUDE,
    ROLE_BOTH, describe_plan, LoopPlan, LoopStep, _phase_label, MISSION_LABELS,
    PROFILES, LABELS,
)
from structcalc.integration.interop.combinaisons import workflow as get_workflow

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = TEST_DIR / "Projet-Villa-avec-sous-sol" / "Projet Villa avec sous sol.rtd"
DWG_PLAN = TEST_DIR / "Plan-villa" / "Plan-villa.dwg"  # pour AutoCAD source

# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("STRUCTCALC PRO — EXECUTION LIVE DEMARCHE (workflow)")
    print("=" * 72)

    # 1. Projet pivot (vide au début, sera rempli par la lecture)
    project = Project(sc_id="SC-WORKFLOW-LIVE", name="Villa-Workflow")

    # 2. Hub avec connecteurs
    hub = default_hub()
    print(f"\nConnecteurs disponibles : {hub.names}")

    # 3. Workflow prédéfini : etude_sans_bim (autocad -> robot -> autocad)
    wf = get_workflow("etude_sans_bim")
    print(f"\nWorkflow : {wf.name}")
    print(f"  Chaîne : {wf.chain_labels}")

    # Construire LoopPlan depuis la chaîne du workflow (autorise doublons en boucle)
    def workflow_to_loopplan(wf) -> LoopPlan:
        if len(wf.chain) < 2:
            return LoopPlan(ok=False, error="Chaîne trop courte")
        # Rôles : premier = conception, dernier = étude, retour = conception
        role_of = {}
        for i, name in enumerate(wf.chain):
            if i == 0:
                role_of[name] = ROLE_CONCEPTION
            elif i == len(wf.chain) - 1:
                role_of[name] = ROLE_ETUDE
            else:
                role_of[name] = ROLE_BOTH
        # Étapes : chaîne + retour fermant
        steps = []
        for i in range(len(wf.chain) - 1):
            src, tgt = wf.chain[i], wf.chain[i + 1]
            steps.append(LoopStep(
                order=i + 1, source=src, target=tgt,
                phase=_phase_label(role_of[src], role_of[tgt]),
                source_label=LABELS[src], target_label=LABELS[tgt],
                target_mission=MISSION_LABELS[PROFILES[tgt].mission]))
        # Retour (dernier -> premier)
        steps.append(LoopStep(
            order=len(wf.chain), source=wf.chain[-1], target=wf.chain[0],
            phase=_phase_label(role_of[wf.chain[-1]], role_of[wf.chain[0]]),
            source_label=LABELS[wf.chain[-1]], target_label=LABELS[wf.chain[0]],
            target_mission=MISSION_LABELS[PROFILES[wf.chain[0]].mission]))
        return LoopPlan(ok=True, order=list(wf.chain), steps=steps)

    plan = workflow_to_loopplan(wf)
    print(describe_plan(plan))

    if not plan.ok:
        print(f"\n[ERREUR] Plan invalide : {plan.error}")
        return 1

    # 4. Connexions séquentielles + ouverture fichiers source
    print("\n--- Connexions + ouverture fichiers ---")

    # AutoCAD - attach_only + ouvrir DWG source si aucun doc
    autocad = hub.get("autocad")
    autocad.attach_only = True
    print("Connexion AutoCAD (instance existante)...")
    try:
        autocad.connect()
        print("  OK")
    except Exception as exc:
        print(f"  [ERREUR] AutoCAD : {exc}")
        return 1

    # S'assurer qu'un document DWG est ouvert (ouvrir Plan-villa.dwg si nécessaire)
    print("Vérification document DWG ouvert...")
    try:
        # Le connecteur AutoCAD a une méthode pour ouvrir un document
        if hasattr(autocad, '_app') and autocad._app:
            docs = autocad._app.Documents
            if docs.Count == 0:
                print(f"  Ouverture {DWG_PLAN.name}...")
                doc = autocad.open_document(str(DWG_PLAN))
                print(f"  OK : {doc.Name}")
            else:
                print(f"  Document déjà ouvert : {autocad._app.Documents.Item(0).Name}")
    except Exception as exc:
        print(f"  [AVERTISSEMENT] Ouverture DWG : {exc}")

    # Robot - attach_only ou lancement
    robot = hub.get("robot")
    robot.attach_only = True
    print("\nConnexion Robot (instance existante ou lancement)...")
    try:
        robot.connect()
        print("  OK")
    except Exception as exc:
        print(f"  [ERREUR] Robot : {exc}")
        # Tentative sans attach_only (lancement)
        robot.attach_only = False
        try:
            robot.connect()
            print("  OK (lancé)")
        except Exception as exc2:
            print(f"  [ERREUR] Robot lancement : {exc2}")
            return 1

    # Ouvrir le projet Robot Villa si pas déjà ouvert
    print("Vérification projet Robot ouvert...")
    try:
        rc = robot.rc
        if rc and not rc.is_project_open:
            print(f"  Ouverture {RTD_VILLA.name}...")
            rc.open_project(str(RTD_VILLA))
            print("  OK")
        else:
            print("  Projet déjà ouvert")
    except Exception as exc:
        print(f"  [AVERTISSEMENT] Projet Robot : {exc}")

    # 5. Exécuter le plan (hub gère les échanges)
    print("\n--- EXECUTION DU PLAN (exchange_plan) ---")
    results = exchange_plan(plan, project, connect=True, hub=hub)

    # 6. Afficher résultats
    print("\n" + "=" * 72)
    print("RÉSULTATS D'EXECUTION")
    print("=" * 72)
    for r in results:
        status = "OK" if r["success"] else "ÉCHEC/REFUS"
        print(f"  [{r['order']:2d}] {r['source']:>8} -> {r['target']:<8} "
              f"| {r['phase']:<30} | {status}")
        print(f"       Action : {r['action']}")
        print(f"       Msg    : {r['message'][:120]}")
        if r["step_failed"]:
            print(f"       Étape en échec : {r['step_failed']}")
        print()

    # 7. Bilan
    ok_count = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"Bilan : {ok_count}/{total} étapes réussies")

    # 8. Fermeture (S5.4 : sans sauvegarde)
    print("\n--- Fermeture (S5.4 sans sauvegarde) ---")
    try:
        if robot.connected:
            robot.disconnect()
            print("  Robot déconnecté")
    except Exception:
        pass
    try:
        if autocad.connected:
            autocad.disconnect()
            print("  AutoCAD déconnecté")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())