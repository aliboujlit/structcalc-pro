# -*- coding: utf-8 -*-
"""
tools/exec_workflow_live_v2.py — Exécution LIVE d'une démarche (workflow)
sur un projet de test réel, en utilisant EXCLUSIVEMENT les connecteurs du hub.

Workflow testé : etude_sans_bim (autocad -> robot -> autocad)
Projet : Villa Robot (.rtd) + Plan DWG AutoCAD
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
from structcalc.integration.interop.combinaisons import workflow as get_workflow
from structcalc.integration.interop.loop import (
    exchange_plan,
    _phase_label, MISSION_LABELS, PROFILES, LABELS,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = TEST_DIR / "Projet-Villa-avec-sous-sol" / "Projet Villa avec sous sol.rtd"
DWG_PLAN = TEST_DIR / "_structcalc_sortie" / "echange_robot_autocad.dwg"


# ---------------------------------------------------------------------------
# Classes utilitaires simples pour le plan
# ---------------------------------------------------------------------------

class _Step:
    def __init__(self, order, source, target, phase, source_label, target_label, target_mission):
        self.order = order
        self.source = source
        self.target = target
        self.phase = phase
        self.source_label = source_label
        self.target_label = target_label
        self.target_mission = target_mission
        self.sense = f"{source} -> pivot -> {target}"


class _Plan:
    def __init__(self, order, steps):
        self.ok = True
        self.order = order
        self.steps = steps
        self.error = ""


def build_workflow_plan() -> _Plan:
    """Construit le plan pour 'etude_sans_bim' : autocad -> robot -> autocad."""
    chain = ["autocad", "robot", "autocad"]
    steps = [
        _Step(
            order=1, source="autocad", target="robot",
            phase="Conception -> Étude",
            source_label="AutoCAD 2027", target_label="Robot Structural Analysis 2027",
            target_mission="Étude structurelle (charges + calcul + résultats)"
        ),
        _Step(
            order=2, source="robot", target="autocad",
            phase="Étude -> Plans",
            source_label="Robot Structural Analysis 2027", target_label="AutoCAD 2027",
            target_mission="Plans (DWG)"
        ),
        _Step(
            order=3, source="autocad", target="autocad",
            phase="Plans (retour boucle)",
            source_label="AutoCAD 2027", target_label="AutoCAD 2027",
            target_mission="Plans (DWG)"
        ),
    ]
    return _Plan(order=["autocad", "robot"], steps=steps)


# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("STRUCTCALC PRO — EXECUTION LIVE DEMARCHE (workflow) - HUB ONLY")
    print("=" * 72)

    # 1. Hub UNIQUE
    hub = default_hub()
    print(f"\nConnecteurs disponibles : {hub.names}")

    # 2. Projet pivot
    project = Project(sc_id="SC-WORKFLOW-LIVE", name="Villa-Workflow")
    project.source_file = str(DWG_PLAN)

    # 3. Récupérer les connecteurs DU HUB
    autocad = hub.get("autocad")
    robot = hub.get("robot")

    # 4. Connexions + ouverture fichiers
    print("\n" + "=" * 72)
    print("CONNEXIONS + OUVERTURE FICHIERS (connecteurs du hub)")
    print("=" * 72)

    # AutoCAD
    print("\n--- AutoCAD : connexion + ouverture DWG ---")
    autocad = hub.get("autocad")
    autocad.attach_only = True
    try:
        autocad.connect()
        print("  AutoCAD connecté (instance existante)")
    except Exception as exc:
        print(f"  [ERREUR] AutoCAD connect : {exc}")
        return 1

    # Ouvrir le DWG Plan-villa
    try:
        if hasattr(autocad, '_app') and autocad._app:
            docs = autocad._app.Documents
            if docs.Count == 0:
                print(f"  Ouverture {DWG_PLAN.name}...")
                autocad.open_document(str(DWG_PLAN))
                print(f"  OK : {DWG_PLAN.name}")
            else:
                print(f"  Document déjà ouvert : {autocad._app.Documents.Item(0).Name}")
    except Exception as exc:
        print(f"  [AVERTISSEMENT] Ouverture DWG : {exc}")

    # Robot
    print("\n--- Robot : connexion + ouverture projet ---")
    robot = hub.get("robot")
    robot.attach_only = True
    try:
        robot.connect()
        print("  Robot connecté (instance existante)")
    except Exception as exc:
        print(f"  [INFO] Robot attach_only échoué : {exc}")
        robot.attach_only = False
        try:
            robot.connect()
            print("  Robot lancé")
        except Exception as exc2:
            print(f"  [ERREUR] Robot : {exc2}")
            return 1

    # Ouvrir le projet Robot Villa
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

    # 5. Plan de workflow
    wf = get_workflow("etude_sans_bim")
    print(f"\nWorkflow : {wf.name}")
    print(f"  Chaîne : {wf.chain_labels}")

    # Plan simple : 3 étapes autocad -> robot -> autocad
    class _Step:
        def __init__(self, order, source, target, phase, source_label, target_label, target_mission):
            self.order = order
            self.source = source
            self.target = target
            self.phase = phase
            self.source_label = source_label
            self.target_label = target_label
            self.target_mission = target_mission
            self.sense = f"{source} -> pivot -> {target}"

    class _Plan:
        def __init__(self, order, steps):
            self.ok = True
            self.order = order
            self.steps = steps
            self.error = ""

    chain = ["autocad", "robot", "autocad"]
    steps = [
        _Step(
            order=1, source="autocad", target="robot",
            phase="Conception -> Étude",
            source_label="AutoCAD 2027", target_label="Robot Structural Analysis 2027",
            target_mission="Étude structurelle (charges + calcul + résultats)"
        ),
        _Step(
            order=2, source="robot", target="autocad",
            phase="Étude -> Plans",
            source_label="Robot Structural Analysis 2027", target_label="AutoCAD 2027",
            target_mission="Plans (DWG)"
        ),
        _Step(
            order=3, source="autocad", target="autocad",
            phase="Plans (retour boucle)",
            source_label="AutoCAD 2027", target_label="AutoCAD 2027",
            target_mission="Plans (DWG)"
        ),
    ]
    plan = _Plan(order=["autocad", "robot"], steps=steps)

    # 6. Exécution du plan via le hub (connect=False = déjà connectés)
    print("\n" + "=" * 72)
    print("EXECUTION DU PLAN (exchange_plan via hub, connecteurs partagés)")
    print("=" * 72)

    results = exchange_plan(plan, project, connect=False, hub=hub)

    # 7. Résultats
    print("\n" + "=" * 72)
    print("RÉSULTATS D'EXECUTION")
    print("=" * 72)
    for r in results:
        status = "OK" if r["success"] else "ÉCHEC/REFUS"
        print(f"  [{r['order']:2d}] {r['source']:>8} -> {r['target']:<8} | {r['phase']:<25} | {status}")
        print(f"       Action : {r['action']}")
        print(f"       Msg    : {r['message'][:150]}")
        if r.get("step_failed"):
            print(f"       Étape en échec : {r['step_failed']}")
        print()

    ok_count = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"Bilan : {ok_count}/{total} étapes réussies")

    # 8. Fermeture S5.4
    print("\n--- Fermeture (S5.4 sans sauvegarde) ---")
    try:
        robot.disconnect()
        print("  Robot déconnecté")
    except Exception:
        pass
    try:
        autocad.disconnect()
        print("  AutoCAD déconnecté")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())