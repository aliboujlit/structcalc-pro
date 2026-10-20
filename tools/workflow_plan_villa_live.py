# -*- coding: utf-8 -*-
"""
tools/workflow_plan_villa_live.py — VOTRE CHAINE COMPLITE EN LIVE (v1.2).

  1. AUTOCAD : ouverture VISIBLE de Plan-villa.dwg (votre plan) + lecture
  2. ROBOT   : ouverture VISIBLE du .rtd VILLA -> modele reel -> charges ->
               CALCUL -> reactions (etudes et calcul — resultats REELS)
  3. REVIT   : add-in .NET (pipe) -> lecture du document ouvert -> ecriture
               du modele etudie (UPDATE-ONLY — jamais de creation inventee)
  4. BOUCLE  : les 6 logiciels en boucle fermee (hub partage)
  5. DOSSIER : resume MD/PDF/XLSX + plan DWG + NWD + rapport (architecte)

Ordre des donnees : le PLAN (AutoCAD) est la reference de l'architecte ;
l'ETUDE (Robot) fournit la structure reelle ; REVIT recoit le modele
etudie (mise a jour seulement) ; la BOUCLE fait voyager le tout.

Aucun fichier de production modifie : fermetures SANS sauvegarde (S5.4).

Lance (console visible) :
    chcp 65001
    $env:PYTHONIOENCODING="utf-8"
    python tools\\workflow_plan_villa_live.py
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
PLAN_VILLA = TEST_DIR / "Plan-villa" / "Plan-villa.dwg"
RTD_VILLA = (TEST_DIR / "Projet-Villa-avec-sous-sol" /
             "Projet Villa avec sous sol.rtd")
SORTIE = TEST_DIR / "_structcalc_sortie"
OUT = SORTIE / "dossier_architecte"


def banner(t: str) -> None:
    print()
    print("=" * 74)
    print(t)
    print("=" * 74, flush=True)


def step(t: str) -> None:
    print()
    print(f"--- {t} " + "-" * max(2, 72 - len(t)), flush=True)


def _start_revit() -> bool:
    """Lance Revit normalement (visible) — l'add-in se charge au demarrage."""
    import subprocess
    root = Path(r"C:\Program Files\Autodesk")
    cands = sorted(root.glob("Revit */Revit.exe"), reverse=True)
    for exe in cands:
        try:
            subprocess.Popen([str(exe)])
            print(f"  Revit lance : {exe}")
            return True
        except Exception:
            continue
    return False


def main() -> int:
    banner("STRUCTCALC PRO v1.2 — VOTRE CHAINE : Plan-villa -> etude -> BIM -> boucle")
    print("1) AUTOCAD ouvre VOTRE plan Plan-villa (visible)")
    print("2) ROBOT etudie la villa (.rtd reel) : charges -> CALCUL -> reactions")
    print("3) REVIT recoit le modele etudie (mise a jour seulement, add-in .NET)")
    print("4) BOUCLE complete des 6 logiciels (hub partage)")
    print("5) DOSSIER de rendu ecrit pour l'architecte")

    from structcalc.core.model import Project
    from structcalc.integration.interop import default_hub
    hub = default_hub()

    # ==================================================================
    # ETAPE 1 — AUTOCAD : votre plan Plan-villa (visible)
    # ==================================================================
    step("ETAPE 1 - AUTOCAD : ouverture de VOTRE plan Plan-villa.dwg")
    from structcalc.integration.interop.loader import load_project_file
    res_plan = load_project_file(PLAN_VILLA, timeout=300.0)
    print(f"  status={res_plan.status} | {res_plan.message}")
    if res_plan.ok and res_plan.project is not None:
        c = res_plan.project.counts()
        print(f"  Pivot charge depuis le plan : {c}")
        if not any(c.get(k, 0) for k in
                   ("nodes", "beams", "columns", "slabs")):
            print("  [HONNETE] Plan architectural : AUCUN objet structurel")
            print("  SC_* (hors calques STRUCTCALC) — STRUCTCALC n'invente")
            print("  jamais de structure : c'est le plan de l'architecte,")
            print("  reference du projet. La structure vient de l'etude.")
    else:
        print("  [REFUS] plan non charge (motif ci-dessus) — suite de la"
              " chaine.")

    # ==================================================================
    # ETAPE 2 — ROBOT : etude REELLE de la villa + CALCUL
    # ==================================================================
    step("ETAPE 2 - ROBOT : etude de la villa (charges -> CALCUL -> reactions)")
    rconn = hub.get("robot")
    study = Project(sc_id="SC-PROJECT-000002", name="Villa-sous-sol")
    opened = False
    rcalc, n_reac = None, 0
    try:
        rconn.connect(timeout=300.0)
    except Exception as exc:
        print(f"  [REFUS] Robot : {exc}")
        return 1
    try:
        if rconn.rc.is_project_open and not rconn.rc.opened_by_us:
            # La villa est-elle DEJA ouverte (session existante, ex. ouverte
            # depuis le programme) ? -> ADOPTION (v1.2.4) : etude du projet
            # deja la, SANS fermeture ni sauvegarde (la session proprietaire
            # garde la main ; S5.4).
            live = ""
            try:
                live = str(rconn.rc.app.Project.FileName or "")
            except Exception:
                live = ""
            if live and Path(live).resolve() == RTD_VILLA.resolve():
                rconn.rc.adopt_live_project()
                opened = False     # pas notre ouverture -> pas notre ferme.
                print("  Villa DEJA OUVERTE (session existante) :")
                print("  ADOPTION — etude du projet deja ouvert, sans")
                print("  fermeture ni sauvegarde (S5.4 — la session")
                print("  proprietaire garde la main).")
            else:
                print("  [REFUS] projet etranger ouvert dans Robot (S5.4)"
                      f" ({live or 'inconnu'}) — fermez-le puis relancez.")
                return 1
        elif not rconn.rc.is_project_open:
            print(f"  Ouverture visible : {RTD_VILLA.name} ...")
            rconn.rc.open_project(str(RTD_VILLA))
            opened = True
        rep = rconn.read_model(study)
        print(f"  Lecture du modele : {rep.status} — {rep.message}")
        print(f"  Contenu REEL de l'etude : {study.counts()}")

        from structcalc.integration.robot import loads, results
        cases = loads.list_cases(rconn.rc)
        print(f"  Cases de charge dans l'etude : {len(cases)}")
        if not cases:
            r = loads.export_dead_load_case(rconn.rc, number=1,
                                            name="Poids propre",
                                            analyze=False)
            print(f"  Case creee : {r}")
        rcalc = loads.calculate(rconn.rc)
        print(f"  CALCUL : {rcalc}")
        avail = int((rcalc or {}).get("results_available", 0) or 0)
        if avail:
            try:
                reac = results.import_reactions(rconn.rc, case_number=1)
                n_reac = len(reac) if hasattr(reac, "__len__") else 0
                print(f"  RESULTATS RELS : {n_reac} reaction(s) lue(s)"
                      " (donnees Robot reelles)")
            except Exception as exc:
                print(f"  [REFUS] lecture des reactions : {exc}")
        else:
            print("  [HONNETE] aucun resultat disponible (le modele ne")
            print("  calcule rien de valide ici) — AUCUN nombre invente.")
    except Exception as exc:
        print(f"  [REFUS] etude Robot : {exc}")
        return 1

    # ==================================================================
    # ETAPE 3 — REVIT : reception du modele etudie (update-only)
    # ==================================================================
    step("ETAPE 3 - REVIT : add-in .NET + reception du modele etudie")
    from structcalc.detector_stub import revit_addin_alive
    if not revit_addin_alive():
        print("  Add-in non charge : demarrage de Revit (le manifeste")
        print("  StructCalcAddin.addin se charge au lancement) ...")
        if _start_revit():
            deadline = time.time() + 300.0
            while time.time() < deadline and not revit_addin_alive():
                time.sleep(3.0)
    alive = revit_addin_alive()
    print(f"  add-in STRUCTCALC (pipe structcalc_revit) :"
          f" {'VIVANT' if alive else 'ABSENT'}")
    if alive:
        vconn = hub.get("revit")
        try:
            vconn.connect(timeout=30.0)
            probe = Project(sc_id="SC-PROJECT-000003", name="Revit-lecture")
            rr = vconn.read_model(probe)
            print(f"  Lecture du document Revit : {rr.status} —"
                  f" {str(rr.message)[:180]}")
            wr = vconn.write_model(study)
            print(f"  Ecriture du modele etudie (UPDATE-ONLY) :"
                  f" {wr.status} — {str(wr.message)[:180]}")
            print("  (Regle : la boucle ne MET A JOUR que des elements")
            print("  existants dans votre modele — AUCUNE creation de")
            print("  structure inventee, S6.3.)")
        except Exception as exc:
            print(f"  [REFUS] echange Revit : {exc}")
    else:
        print("  [REFUS] add-in non charge — ouvrez Revit une fois et")
        print("  relancez : le maillon BIM sera actif (honnete, S6.3).")

    # ==================================================================
    # ETAPE 4 — BOUCLE COMPLETE (hub partage, .rtd villa deja ouvert)
    # ==================================================================
    step("ETAPE 4 - BOUCLE COMPLETE : 6 logiciels en boucle fermee")
    from structcalc.integration.interop.loop import (
        Selection, ROLE_BOTH, plan_loop, describe_plan, exchange_plan)
    selections = [Selection(n, ROLE_BOTH) for n in
                  ("revit", "robot", "autocad", "civil3d", "advsteel",
                   "navisworks")]
    plan = plan_loop(selections)
    if not plan.ok:
        print(f"  [REFUS] plan invalide : {plan.error}")
    else:
        print(describe_plan(plan))
        loop_pivot = Project(sc_id="SC-PROJECT-000004", name="Boucle")
        # Source de coordination RÉELLE : le plan de l'architecte (DWG) ->
        # la mission Navisworks le convertit en maquette .nwd (vérifié live).
        loop_pivot.source_file = str(PLAN_VILLA)
        print("  Execution de la boucle (Robot tient le .rtd villa ouvert"
              " par la session du hub) ...")
        rows = exchange_plan(plan, loop_pivot, connect=True, hub=hub)
        ok = sum(1 for r in rows if r.get("success"))
        for r in rows:
            mark = "[x]" if r.get("success") else "[ ]"
            print(f"  {mark} [{r.get('order')}] {r.get('source')} ->"
                  f" {r.get('target')} | {r.get('action')}")
            if not r.get("success"):
                print(f"       motif : {str(r.get('message', ''))[:150]}")
        print(f"  Boucle : {ok}/{len(rows)} etape(s) reussie(s) — chaque"
              " refus est MOTIVE (jamais masque).")
        print("  Documents crees par la boucle : laisses OUVERTS dans")
        print("  AutoCAD pour que vous les voyiez (disque intact).")

    # ==================================================================
    # ETAPE 5 — DOSSIER DE RENDU (resume + copies)
    # ==================================================================
    step("ETAPE 5 - DOSSIER DE RENDU pour l'architecte")
    if opened:
        try:
            rconn.rc.close_project(save=False)
            print("  .rtd villa ferme SANS sauvegarde (S5.4)")
            opened = False
        except Exception as exc:
            print(f"  [ERREUR] fermeture .rtd : {exc}")
    files = []
    try:
        from structcalc.core.coherence import (
            coherence_findings, format_findings)
        from structcalc.reporting.dossier import build_dossier
        OUT.mkdir(parents=True, exist_ok=True)
        findings = coherence_findings(study)
        files = build_dossier(study, str(OUT),
                              coherence_md=format_findings(study, findings))
        resume = OUT / "resume_etude.md"
        try:
            body = resume.read_text(encoding="utf-8")
            body += "\n\n## Etude villa (Robot 2027 - resultats reels)\n\n"
            body += f"- Modele lu : {study.counts()}\n"
            body += f"- Calcul : {rcalc}\n"
            body += f"- Reactions lues : {n_reac}\n"
            resume.write_text(body, encoding="utf-8")
        except OSError:
            pass
        print(f"  Reporting : {len(files)} fichier(s) ecrit(s)")
        for src, sub in [(SORTIE / "echange_robot_autocad.dwg", "plans"),
                         (TEST_DIR / "Plan-villa" / "Plan-villa.nwd",
                          "coordination"),
                         (SORTIE / "verification_report.txt", "")]:
            if src.exists():
                d = OUT / sub
                d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, d / src.name)
                print(f"  [OK] copie {src.name} -> {sub or '(racine)'}")
            else:
                print(f"  [absent] {src.name}")
    except Exception as exc:
        print(f"  [REFUS] dossier : {exc}")
    finally:
        try:
            rconn.disconnect()
        except Exception:
            pass

    # ==================================================================
    banner("FIN DE VOTRE CHAINE — livrables (dossier architecte)")
    if OUT.exists():
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                print(f"  {p.relative_to(OUT)}  ({p.stat().st_size} o)")
    print()
    print("  Rejouer VOI-MEME depuis le programme (sans codage) :")
    print("    Projet > Ouvrir… (Plan-villa.dwg ou le .rtd villa)")
    print("    Modele > Verifier la coherence")
    print("    Integrations > Workflow complet (cases a cocher)")
    print("    Rapports > Exporter le dossier… (MD + PDF + XLSX)")
    print()
    print("  Regles : AUCUNE donnee inventee, refus toujours motives,")
    print("  fermeture SANS sauvegarde de ce que le programme a ouvert")
    print("  (S5.4). Vos fichiers sont intacts.")
    print("=" * 74, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
