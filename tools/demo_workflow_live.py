# -*- coding: utf-8 -*-
"""
tools/demo_workflow_live.py — DÉMONSTRATION LIVE DU WORKFLOW (v1.2).

À lancer dans une fenêtre CONSOLE VISIBLE : les logiciels Autodesks'
s'ouvrent en VISIBLE, chaque étape est racontée, et le DOSSIER DE RENDU
est produit à la fin. Aucun fichier de production n'est modifié : tout ce
que NOUS ouvrons est fermé SANS sauvegarde (§5.4) ; les documents créés
par la boucle sont laissés OUVERTS pour que vous les voyiez (fichiers
disque intacts — rien n'est enregistré sans VOUS).

Étapes :
  0. Inventaire des logiciels (détection registre — rien n'est lancé)
  1. Robot : ouverture du .rtd d'étude RÉEL (visible) -> lecture SC-*
  2. AutoCAD : le plan des 119 poutres APPARAÎT -> artefact DWG -> relecture
  3. RETOUR AutoCAD -> Robot : 119 poutres -> relecture IDENTIQUE
  4. Navisworks : Plan-villa.dwg -> NWD (Roamer visible)
  5. Revit : sonde add-in (pipe structcalc_revit) + lecture du document
  6. BOUCLE COMPLÈTE 6 logiciels (hub partagé, .rtd ouvert par le hub)
  7. ETUDE + DOSSIER : charges -> CALCUL -> reactions (resultats REELS)
     puis resume MD/PDF/XLSX + plan DWG + NWD + rapport de verification

Lance (fenetre console visible) :
    chcp 65001
    $env:PYTHONIOENCODING="utf-8"
    python tools\\demo_workflow_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))           # verify_test_projects
sys.path.insert(0, str(HERE.parent))    # structcalc


def banner(txt: str) -> None:
    print()
    print("=" * 74)
    print(txt)
    print("=" * 74, flush=True)


def step(label: str) -> None:
    print()
    print(f"--- {label} " + "-" * max(2, 72 - len(label)), flush=True)


def verdict(res, title: str) -> None:
    print(f"  -> [{res.status}] {title}", flush=True)
    for ln in str(res.detail).splitlines():
        print(f"     {ln}", flush=True)


def main() -> int:
    banner("STRUCTCALC PRO v1.2 — DEMONSTRATION LIVE DU WORKFLOW")
    print("Les logiciels Autodesk s'ouvrent en VISIBLE : regardez Robot,")
    print("AutoCAD, Navisworks travailler. Tout ce que le programme ouvre")
    print("est ferme SANS sauvegarde (S5.4) ; vos fichiers restent intacts.")
    print(f"Dossier de travail : {Path(r'C:\\Users\\Admin\\Desktop\\projets de test')}")

    import verify_test_projects as V

    # ------------------------------------------------------------------
    # ETAPE 0 — Inventaire (detection registre ; AUCUN logiciel lance)
    # ------------------------------------------------------------------
    step("ETAPE 0 — Inventaire des logiciels (detection, rien de lance)")
    from structcalc.integration.interop import default_hub
    hub = default_hub()
    for name, info in sorted(hub.status().items()):
        light = ", ".join(f"{k}={v}" for k, v in info.items()
                          if k != "capabilities")
        print(f"  [x] {name}: {light}")

    # ------------------------------------------------------------------
    # ETAPE 1 — Robot : le .rtd d'etude REEL, ouvert en visible
    # ------------------------------------------------------------------
    step("ETAPE 1 — Robot : ouverture du .rtd d'etude REEL (visible)")
    verdict(V.phase_robot_read_real(),
            "Robot — lecture du .rtd reel (bureau d'etude)")

    # ------------------------------------------------------------------
    # ETAPE 2 — AutoCAD : le plan APPARAIT (visible) + relecture
    # ------------------------------------------------------------------
    step("ETAPE 2 — AutoCAD : le plan des poutres APPARAIT a l'ecran")
    verdict(V.phase_exchange_robot_to_autocad(),
            "Echange Robot -> AutoCAD (doc SC_* + artefact DWG)")

    # ------------------------------------------------------------------
    # ETAPE 3 — Retour AutoCAD -> Robot
    # ------------------------------------------------------------------
    step("ETAPE 3 — RETOUR AutoCAD -> Robot (boucle reciproque)")
    verdict(V.phase_exchange_autocad_to_robot(),
            "Echange RETOUR AutoCAD -> Robot (nouveau projet)")

    # ------------------------------------------------------------------
    # ETAPE 4 — Navisworks : NWD (Roamer visible)
    # ------------------------------------------------------------------
    step("ETAPE 4 — Navisworks : conversion du plan en maquette NWD")
    verdict(V.phase_navisworks_convert(),
            "Navisworks — Plan-villa.dwg -> NWD")

    # ------------------------------------------------------------------
    # ETAPE 5 — Revit : sonde add-in + lecture du document ouvert
    # ------------------------------------------------------------------
    step("ETAPE 5 — Revit : sonde add-in (.NET, pipe structcalc_revit)")
    verdict(V.phase_revit_probe(),
            "Revit — sonde add-in + lecture")

    # ------------------------------------------------------------------
    # ETAPE 6 — BOUCLE COMPLÈTE (6 logiciels, hub partage)
    # ------------------------------------------------------------------
    step("ETAPE 6 — BOUCLE COMPLETE : 6 logiciels en boucle fermee")
    from structcalc.core.model import Project
    from structcalc.integration.interop.loop import (
        Selection, ROLE_BOTH, plan_loop, describe_plan, exchange_plan)

    selections = [Selection(n, ROLE_BOTH) for n in
                  ("revit", "robot", "autocad", "civil3d", "advsteel",
                   "navisworks")]
    plan = plan_loop(selections)
    if not plan.ok:
        print(f"  [REFUS] plan invalide : {plan.error}")
        return 1
    print(describe_plan(plan))

    # Le .rtd est ouvert PAR LA SESSION ROBOT DU HUB : Robot accepte alors
    # lecture et ecriture dans CE projet (opened_by_us), ferme sans save.
    rc_loop = hub.get("robot")
    opened_rtd = False
    try:
        rc_loop.connect(timeout=90.0)
        if rc_loop.rc.is_project_open and not rc_loop.rc.opened_by_us:
            print("  [REFUS] projet etranger ouvert dans Robot (S5.4) — "
                  "boucle lancee sans projet source.")
        else:
            rc_loop.rc.open_project(str(V.RTD_BATIMENT))
            opened_rtd = True
            print(f"  [boucle] .rtd REEL ouvert par la session du hub : "
                  f"{V.RTD_BATIMENT.name} (visible dans Robot)")
    except Exception as exc:
        print(f"  [boucle] ouverture .rtd impossible : {exc}")

    print("  Execution de la boucle (chaque logiciel fait sa mission) ...")
    rows = exchange_plan(plan, Project("SC-DEMO-LOOP-001"), connect=True,
                         hub=hub)
    ok = sum(1 for r in rows if r.get("success"))
    for r in rows:
        mark = "[x]" if r.get("success") else "[ ]"
        print(f"  {mark} [{r.get('order')}] {r.get('source')} -> "
              f"{r.get('target')} | {r.get('action')}")
        if not r.get("success"):
            print(f"       motif : {str(r.get('message', ''))[:150]}")
    print(f"  Boucle : {ok}/{len(rows)} etape(s) reussie(s) — chaque refus"
          " est MOTIVE (jamais masque en succes).")
    if opened_rtd:
        try:
            rc_loop.rc.close_project(save=False)
            print("  [boucle] .rtd ferme SANS sauvegarde (S5.4)")
        except Exception as exc:
            print(f"  [boucle] fermeture .rtd : {exc}")
    try:
        rc_loop.disconnect()          # Robot reste ouvert, session decrochee
    except Exception:
        pass
    print("  Documents crees par la boucle : laissés OUVERTS dans AutoCAD")
    print("  pour que vous les voyiez (fichiers disque intacts ; fermez-les")
    print("  sans enregistrer, ou enregistrez si VOUS le decidez).")

    # ------------------------------------------------------------------
    # ETAPE 7 — ETUDE (charges -> CALCUL -> reactions REELLES) + DOSSIER
    # ------------------------------------------------------------------
    step("ETAPE 7 — ETUDE + DOSSIER DE RENDU pour l'architecte")
    import build_architect_dossier as D
    rc_dossier = D.main()

    # ------------------------------------------------------------------
    # VERDICT FINAL + ou trouver tout
    # ------------------------------------------------------------------
    banner("FIN DE LA DEMONSTRATION — ou trouver chaque livrable")
    sortie = D.SORTIE
    dossier = D.OUT
    print(f"  Dossier de rendu (a remettre) : {dossier}")
    if dossier.exists():
        for p in sorted(dossier.rglob("*")):
            if p.is_file():
                print(f"    {p.relative_to(dossier)}  ({p.stat().st_size} o)")
    print()
    print(f"  Preuves et echanges : {sortie}")
    print("    echange_robot_autocad.dwg — le plan transfere (relecture")
    print("    IDENTIQUE prouvee) ; Plan-villa.nwd — maquette de")
    print("    coordination ; verification_report.txt — rapport live.")
    print()
    print("  Rejouer VOUS-MEME sans codage (STRUCTCALC PRO) :")
    print("    1) Projet > Ouvrir…      -> chargez le .rtd (ou un DWG)")
    print("    2) Modele > Verifier la coherence")
    print("    3) Integrations > Workflow complet (cases a cocher)")
    print("    4) Rapports > Exporter le dossier… (MD + PDF + XLSX)")
    print()
    print("  Regles appliquees partout : AUCUNE donnee inventee, chaque")
    print("  refus est motive, fermeture SANS sauvegarde de ce que le")
    print("  programme a ouvert (S5.4). Vos fichiers sont intacts.")
    print("=" * 74, flush=True)
    return 0 if rc_dossier == 0 else rc_dossier


if __name__ == "__main__":
    raise SystemExit(main())
