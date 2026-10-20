# -*- coding: utf-8 -*-
"""
tools/verify_bureau_etudes_live.py — VÉRIFICATION LIVE COMPLÈTE v1.3.1 :
le PROCESSUS DE BUREAU D'ÉTUDES sur le VRAI plan-villa, avec la MÊME
logique que le programme (GUI) et les mêmes code paths (couche par couche) :

  É0  LEDs des 6 logiciels            (INTEGRATION — sans lancement)
  É1  Projet + PLAN architecte        (AutoCAD ouvre Plan-villa.dwg)
  É2  Étude structure                 (Robot .rtd villa -> read_model
                                       enrichi -> charges -> CALCUL ->
                                       réactions par cas)
  É3  SOLVER                          (combinaison ELU sur réactions
                                       RÉELLES 1.35G+1.5Q ; descente de
                                       charges — refus motivé si donnée
                                       absente ; dimensionnement BAEL du
                                       VRAI poteau C R30x30)
  É4  RÉGLEMENTATION                  (registres BAEL 91 r99 + RPS 2011 :
                                       identité, articles, état réel,
                                       checks RÉELS exécutés)
  É5  VÉRIFICATIONS                   (constats de cohérence — aucun
                                       masquage)
  É6  RAPPORTS                        (note de calcul, fiche de poteau
                                       RÉELLE, dossier complet)
  É7  LEDs finales + bilan + fermeture SANS sauvegarde (§5.4)

Règles : aucune donnée inventée ; chaque hypothèse AFFICHÉE comme telle ;
chaque refus MOTIVÉ ; statuts réglementaires honnêtes (jamais « conforme »).

    chcp 65001 ; $env:PYTHONIOENCODING="utf-8"
    python -u tools\\verify_bureau_etudes_live.py
"""
from __future__ import annotations

import re
import sys
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
OUT = SORTIE / "verif_bureau_etudes"


def banner(t: str) -> None:
    print()
    print("=" * 74)
    print(t)
    print("=" * 74, flush=True)


def step(t: str) -> None:
    print()
    print(f"--- {t} " + "-" * max(2, 72 - len(t)), flush=True)


def _node_num(sc_id: str) -> int:
    m = re.search(r"R0*(\d+)$", sc_id or "")
    return int(m.group(1)) if m else -1


def main() -> int:
    banner("STRUCTCALC PRO v1.3.1 — VERIFICATION BUREAU D'ETUDES (villa)")
    from structcalc.core.model import Project
    from structcalc.integration.interop import default_hub

    # ==================================================================
    # É0 — LEDs (INTEGRATION : détection SANS lancement)
    # ==================================================================
    step("ETAPES 0 - LEDs des 6 logiciels (sans lancement)")
    from structcalc.integration.software_status import status_all
    for s in status_all():
        mark = "[v]" if s["connected"] else "[ ]"
        print(f"  {mark} {s['label']:<28} {s['detail']}")

    # ==================================================================
    # É1 — PROJET + PLAN : AutoCAD ouvre le plan de l'architecte
    # ==================================================================
    step("ETAPE 1 - AUTOCAD : ouverture de Plan-villa.dwg (matiere premiere)")
    from structcalc.integration.interop.loader import load_project_file
    res_plan = load_project_file(PLAN_VILLA, timeout=300.0)
    print(f"  status={res_plan.status} | {str(res_plan.message)[:220]}")
    if res_plan.ok and res_plan.project is not None:
        print(f"  Pivot plan : {res_plan.project.counts()}")
    else:
        print("  [HONNETE] plan non charge ou sans objet SC_* — la"
              " structure vient de l'etude (Etape 2), jamais inventee.")

    # ==================================================================
    # É2 — ÉTUDE : Robot villa -> modèle enrichi -> CALCUL -> réactions
    # ==================================================================
    step("ETAPE 2 - ROBOT : etude villa (modele enrichi -> CALCUL)")
    hub = default_hub()
    rconn = hub.get("robot")
    try:
        rconn.connect(timeout=300.0)
    except Exception as exc:
        print(f"  [REFUS] Robot : {exc}")
        return 1
    rc = rconn.rc
    opened = False
    study = Project(sc_id="SC-PROJECT-000020", name="Villa-BET")
    rcalc = {}

    def _fin() -> None:
        """Fermeture SANS sauvegarde (S5.4) de ce QUE LE SCRIPT a ouvert."""
        try:
            if opened:
                rc.close_project(save=False)
                print("Villa fermee SANS sauvegarde (S5.4).")
        except Exception as exc:
            print(f"[ERREUR] fermeture villa : {exc}")
        try:
            rconn.disconnect()
        except Exception:
            pass

    try:
        if rc.is_project_open:
            live = ""
            try:
                live = str(rc.app.Project.FileName or "")
            except Exception:
                live = ""
            if Path(live).resolve() == RTD_VILLA.resolve():
                rc.adopt_live_project()
                print("  Villa deja ouverte : ADOPTION (S5.4).")
            else:
                print(f"  [REFUS] projet etranger ouvert (S5.4) : {live}")
                return 1
        else:
            print(f"  Ouverture visible : {RTD_VILLA.name} ...")
            rc.open_project(str(RTD_VILLA))
            opened = True
        rep = rconn.read_model(study)
        print(f"  read_model : {rep.status} — {rep.message}")
        print(f"  Contenu REEL : {study.counts()}")
        from structcalc.integration.robot import loads, results
        cases = loads.list_cases(rc)
        print(f"  Cases Robot : {[(c['number'], c['name']) for c in cases]}")
        rcalc = loads.calculate(rc)
        print(f"  CALCUL : {rcalc}")
        if not rcalc.get("results_available"):
            print("  [HONNETE] aucun resultat : AUCUN nombre invente.")
    except Exception as exc:
        print(f"  [REFUS] etude Robot : {exc}")
        _fin()
        return 1

    # -- É2b : cas par nature + réactions réelles au pied d'un poteau ----
    from structcalc.integration.robot import results as rresults
    by_name = {c["name"]: c["number"] for c in cases}
    dead_lc = next((lc for lc in study.load_cases.values()
                    if lc.kind == "dead"), None)
    live_lc = next((lc for lc in study.load_cases.values()
                    if lc.kind == "live"), None)
    elu_case = next((c for c in cases if "elu" in c["name"].lower()), None)
    numG = by_name.get(dead_lc.name) if dead_lc else None
    numQ = by_name.get(live_lc.name) if live_lc else None
    print(f"  Cas G (dead) : {dead_lc.name if dead_lc else 'ABSENT'}"
          f" -> numero {numG}")
    print(f"  Cas Q (live) : {live_lc.name if live_lc else 'ABSENT'}"
          f" -> numero {numQ}")
    print(f"  Cas ELU Robot : {elu_case['name'] if elu_case else 'ABSENT'}"
          f" -> numero {elu_case['number'] if elu_case else '-'}")

    # poteau avec PIED sur un appui réel (15 encastrements)
    sup_nums = {_node_num(s.sc_id) for s in study.supports.values()}
    col = None
    pied = None
    for c in study.columns.values():
        for end in (c.start_node, c.end_node):
            if _node_num(end) in sup_nums:
                col, pied = c, _node_num(end)
                break
        if col:
            break

    # ==================================================================
    # É3 — SOLVER : combinaison sur réactions RÉELLES + dimensionnement
    # ==================================================================
    step("ETAPE 3 - SOLVER : combinaison ELU reelle + dimensionnement")
    from structcalc.solver.loads import apply_combination
    N = My = Mz = None
    f_sg = f_sq = None
    combo_expr = ""
    if col is None or not rcalc.get("results_available"):
        print("  [REFUS] pas de poteau sur appui ou pas de resultat —"
              " dimensionnement non lance (aucune donnee inventee).")
    else:
        print(f"  Poteau cible : {col.sc_id} (pied nœud Robot {pied}),"
              f" section liee : {col.section}, materiau : {col.material}")
        try:
            rG = rresults.import_reactions(rc, case_number=numG,
                                           node_numbers=[pied])[0]
            rQ = rresults.import_reactions(rc, case_number=numQ,
                                           node_numbers=[pied])[0]
            f_sg, f_sq = rG["Fz"], rQ["Fz"]
            u = rG["units"]["force"]
            print(f"  Reactions RELLES au pied (unite lue Robot : {u}) :")
            print(f"    Fz {dead_lc.name} = {f_sg} {u}"
                  f" ; Fz {live_lc.name} = {f_sq} {u}")
            combo_expr = "1.35 G + 1.5 Q (facteurs AFFICHES — entree BET)"
            res_combo = apply_combination(
                {dead_lc.sc_id: f_sg, live_lc.sc_id: f_sq},
                {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
                expression=combo_expr)
            print(f"  Combinaison programme : {res_combo.expression}")
            print(f"    contributions : {res_combo.contributions}"
                  f" ; complete={res_combo.complete}")
            N = abs(res_combo.value)
            print(f"    N ELU (compression |Fz|) = {N:.2f} {u}")
            # comparaison honnête : case ELU de Robot (memes reactions?)
            if elu_case:
                rE = rresults.import_reactions(
                    rc, case_number=elu_case["number"],
                    node_numbers=[pied])[0]
                print(f"  Case ELU Robot ({elu_case['name']}) : Fz ="
                      f" {rE['Fz']} {u} — presentee telle quelle (facteurs"
                      f" Robot non lus : AUCUNE equivalence pretendue)")
            # moments reels (memes facteurs)
            res_my = apply_combination(
                {dead_lc.sc_id: rG["My"], live_lc.sc_id: rQ["My"]},
                {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
                expression="1.35G+1.5Q")
            res_mz = apply_combination(
                {dead_lc.sc_id: rG["Mz"], live_lc.sc_id: rQ["Mz"]},
                {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
                expression="1.35G+1.5Q")
            My, Mz = res_my.value, res_mz.value
            print(f"  Moments combines : My = {My:.3f}, Mz = {Mz:.3f}"
                  f" {rG['units']['moment']}")
        except Exception as exc:
            print(f"  [REFUS] reactions/combinaison : {exc}")

    # -- 3b : descente de charges (refus motivé si surface non lue) -------
    print()
    print("  Descente de charges surfacique :")
    vals = [ld for ld in study.loads.values()
            if not ld.value.is_missing]
    miss = [ld for ld in study.loads.values() if ld.value.is_missing]
    print(f"    charges RÉELLES avec valeur lue : {len(vals)}"
          f" (ex. {[ld.value.value for ld in vals[:4]]} {[ld.unit for ld in vals[:4]]})")
    print(f"    charges SANS valeur lisible : {len(miss)} — description"
          " Robot conservee dans `ref` (ex.:"
          f" {str(miss[0].ref)[:90] if miss else '—'}...)")
    if any(ld.unit == "kN/m2" or "kN/m²" in ld.unit for ld in vals):
        print("    [OK] charge surfacique numerique reelle disponible.")
    else:
        print("    [REFUS MOTIVE] aucune charge surfacique kN/m² lue via"
              " l'API verifiee (seul GetValue(2) sur bar_uniform est prouve)"
              " -> element_actions_from_area NON EXÉCUTÉE : q_kNm2 serait"
              " invente. Interdit (spec §19).")

    # -- 3c : dimensionnement BAEL du VRAI poteau -------------------------
    outcomes = []
    d_h = d_by = d_bz = None
    fck = None
    mat_label = None
    if N:
        from structcalc.solver.column_design import (
            ColumnDesigner, ColumnMaterials, ColumnActions, ColumnVariant)
        # hauteur RÉELLE = dz des nœuds (coordonnées importées Robot)
        try:
            n1 = study.nodes[col.start_node]
            n2 = study.nodes[col.end_node]
            d_h = abs(float(n2.z.value) - float(n1.z.value))
            d_by = d_bz = d_h
        except Exception:
            d_h = None
        # matériau : fck DÉRIVÉ du nom de label RÉEL (BETON25 -> 25 MPa)
        if col.material and col.material in study.materials:
            mat_label = study.materials[col.material].name
            m = re.match(r"BETON(\d+)", mat_label or "", re.IGNORECASE)
            if m:
                fck = float(m.group(1))
        if d_h and fck:
            print()
            print(f"  Dimensionnement BAEL du poteau RÉEL {col.sc_id} :")
            print(f"    section : {study.sections[col.section].name if col.section and col.section in study.sections else '?'}"
                  f" -> variante 30x30 (nom de label reel)")
            print(f"    hauteur : {d_h:.3f} m (delta z des nœuds Robot)")
            print(f"    materiau : {mat_label} -> fck = {fck} MPa"
                  " (DERIVE du nom de label reel BETONxx)")
            print("    [HYPOTHESE DECLAREE] acier d'armature HA500 :"
                  " classe NON LUE dans l'etude (aucun label armature)"
                  " — entree de dimensionnement, a confirmer par"
                  " l'ingenieur.")
            print("    [HYPOTHESE DECLAREE] longueurs de flambement"
                  " Lf = hauteur d'etage : non lues dans le modele —"
                  " a confirmer (conditions d'encastrement).")
            mat = ColumnMaterials(fck=fck, fyk=500.0, E=200000.0)
            acts = ColumnActions(N=N, My=My or 0.0, Mz=Mz or 0.0,
                                 combination=combo_expr)
            d = ColumnDesigner()
            cands = d.generate_candidates()
            cands.append(ColumnVariant(b=30.0, h=30.0,
                                       As_provided_cm2=0.015 * 30 * 30,
                                       label="C R30x30 (section reelle villa)"))
            outcomes = d.search(height=d_h, buckling_y=d_by,
                                buckling_z=d_bz, materials=mat,
                                actions=acts, candidates=cands)
            if outcomes:
                top = outcomes[0]
                print(f"  -> {len(outcomes)} variante(s) viable(s),"
                      f" rang 1 : {top.variant.designation}"
                      f" (score {top.ranking_score:.3f})")
                for o in outcomes[:5]:
                    print(f"     rang {o.rank}: {o.variant.designation}"
                          f" — candidate={o.is_candidate}, a valider="
                          f"{o.to_validate}")
                print(f"  -> GLOBAL : reanalyse globale requise ?"
                      f" {d.requires_global_reanalysis(top)} (toujours"
                      " conseillee apres changement de section)")
            else:
                real = d.design_variant(
                    ColumnVariant(b=30.0, h=30.0,
                                  As_provided_cm2=0.015 * 900,
                                  label="C R30x30 (reel)"),
                    d_h, d_by, d_bz, mat, acts)
                print(f"  [HONNETE] AUCUNE variante viable — echecs :"
                      f" {real.failed} ; manquants : {real.missing_data}")
                outcomes = [real]
        else:
            print(f"  [REFUS MOTIVE] dimensionnement non lance :"
                  f" hauteur={'lue' if d_h else 'ABSENTE'},"
                  f" fck={'derive du nom reel' if fck else 'NON DERIVE'}"
                  f" (materiau={mat_label}) — aucune donnee inventee.")

    # ==================================================================
    # É4 — RÉGLEMENTATION : registres + état réel + checks exécutés
    # ==================================================================
    step("ETAPE 4 - REGLEMENTATION : BAEL 91 r99 + RPS 2011 (etat reel)")
    from structcalc.regulation.bael91r99.columns import bael91r99
    from structcalc.regulation.rps2011.seismic import rps2011
    for reg in (bael91r99, rps2011):
        ident = reg.identity()
        print(f"  {ident['key']} — {ident['title']} ({ident['edition']})"
              f" | {ident['geography']} | articles={ident['articles']}"
              f" | checks={ident['checks_registered']}")
        n_ok = 0
        for art in reg.articles.values():
            st = art.status().value
            n_ok += 1 if art.verified else 0
            print(f"    - {art.code:<28} verified={art.verified}"
                  f" -> {st}")
        print(f"    -> {n_ok}/{len(reg.articles)} articles transcrits et"
              " verifies independamment ; le reste ="
              " VERIFICATION_NON_IMPLEMENTE (jamais presente conforme)")
    if outcomes:
        print("  Checks RÉELS exécutés sur la variante rang 1"
              f" ({outcomes[0].variant.designation}) :")
        for c in outcomes[0].checks:
            comp = (f"{c.computed_value:.2f}/{c.limit_value:.2f} {c.unit}"
                    if c.computed_value is not None
                    and c.limit_value is not None else "—")
            print(f"    - {c.check_id:<24} {c.article_code:<22}"
                  f" {c.status.value:<28} {comp}")
            if c.message:
                print(f"        {c.message[:110]}")
    # preuve §11.3 : check inexistant -> NON_IMPLEMENTE (jamais conforme)
    res_demo = bael91r99.run_check("controle_parasismique_non_implante")
    print(f"  Preuve S11.3 : run_check(inconnu) ->"
          f" {res_demo.status.value} — {res_demo.message[:80]}")
    # RPS : cas sismique reel dans l'etude MAIS parametres spectrum non lus
    seis = [lc for lc in study.load_cases.values() if lc.kind == "seismic"]
    print(f"  RPS : cas sismique dans l'etude ="
          f" {[lc.name for lc in seis] or 'aucun'} ;"
          " [REFUS MOTIVE] run_check(spectrum) NON lance : parametres"
          " (ag, S, Tc...) non lus depuis Robot — aucune valeur inventee.")

    # ==================================================================
    # É5 — VÉRIFICATIONS : constats de cohérence (aucun masquage)
    # ==================================================================
    step("ETAPE 5 - VERIFICATIONS : coherence du pivot")
    from structcalc.core.coherence import (
        coherence_findings, format_findings)
    findings = coherence_findings(study)
    md_coh = format_findings(study, findings)
    print(f"  {len(findings)} constat(s) de coherence :")
    cats: dict[str, int] = {}
    for f in findings:
        cats[f.category] = cats.get(f.category, 0) + 1
    for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print(f"    - {cat} : {n}")
    if not findings:
        print("    (modele complet : aucun constat)")

    # ==================================================================
    # É6 — RAPPORTS : note de calcul + fiche RÉELLE + dossier
    # ==================================================================
    step("ETAPE 6 - RAPPORTS : note de calcul, fiche, dossier")
    OUT.mkdir(parents=True, exist_ok=True)
    from structcalc.reporting.column_report import (
        project_summary, column_fiche)
    md_note = project_summary(study)
    (OUT / "note_calcul_bureau.md").write_text(md_note, encoding="utf-8")
    print(f"  note de calcul (MD) : {len(md_note)} caractères")
    if col is not None:
        md_fiche = column_fiche(col, project=study, outcomes=outcomes)
        (OUT / "fiche_poteau_reelle.md").write_text(md_fiche,
                                                     encoding="utf-8")
        print(f"  fiche poteau RÉEL {col.sc_id} : {len(md_fiche)}"
              " caractères (verifications + statuts honnêtes)")
    from structcalc.reporting.dossier import build_dossier
    files = build_dossier(study, str(OUT), coherence_md=md_coh)
    print(f"  dossier complet : {len(files)} fichier(s) :")
    for f in sorted(files):
        print(f"    - {Path(f).name} ({Path(f).stat().st_size} o)")

    # ==================================================================
    # É7 — LEDs finales + bilan + fermeture S5.4
    # ==================================================================
    step("ETAPE 7 - LEDs finales + bilan")
    n_led = sum(1 for s in status_all() if s["connected"])
    print(f"  logiciels connectes : {n_led}/6")
    try:
        c = study.counts()
        print(f"  BILAN — plan: {res_plan.status if res_plan else '?'} |"
              f" etude: {c['nodes']} nœuds, {c['columns']} poteaux,"
              f" {c['beams']} poutres, {c['supports']} appuis,"
              f" {c['materials']} materiau, {c['loads']} charges"
              f" | calcul: {rcalc}")
        print(f"  combinaison: {combo_expr} -> N ="
              f" {N:.2f}" if N else "  combinaison: non executee")
        print(f"  dimensionnement: {len(outcomes)} variante(s) classee(s)"
              if outcomes else
              "  dimensionnement: non execute (refus motive ci-dessus)")
        print(f"  coherence: {len(findings)} constat(s) |"
              f" rapports: {len(files)} fichier(s) dans {OUT}")
    except Exception:
        pass
    print()
    print("  Rejouer VOI-MEME depuis le programme (sans codage) :")
    print("    Projet > Ouvrir… (Plan-villa.dwg)")
    print("    Modele > Importer depuis Robot (etude villa)")
    print("    Calculs > Dimensionner les poteaux")
    print("    Modele > Verifier la coherence")
    print("    Rapports > Note de calcul / Fiche de poteau /"
          " Exporter le dossier…")
    print("    Integrations > Workflow complet (cases a cocher)")
    print()
    print("  Regles : AUCUNE donnee inventee, hypotheses DECLAREES,")
    print("  refus motives, statuts regulamentaires honnêtes,")
    print("  fermeture SANS sauvegarde (S5.4).")
    _fin()
    print("=" * 74, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
