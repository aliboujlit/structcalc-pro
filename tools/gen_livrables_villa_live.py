# -*- coding: utf-8 -*-
"""
tools/gen_livrables_villa_live.py — Génération LIVE des livrables v1.4
sur la villa réelle (preuve que les modules marchent avec les vraies
données Robot, pas seulement des fakes).

Chaîne (sessions COM séquentielles, une seule à la fois) :
  1. Robot : connect -> open villa -> read_model -> CALCUL
  2. Réactions réelles au pied -> combinaison 1.35G+1.5Q -> N ELU
  3. Dimensionnement BAEL (fck dérivé du label BETON25)
  4. Plans de coffrage PDF (cotes issues des labels R<b>x<h>)
  5. Plans de ferraillage PDF (proposition A_VALIDER) + nomenclature
  6. Dossier de contrôle BCT (référentiel MA : BAEL 91 r99 + RPS 2011)
  7. Fermeture S5.4 (SANS sauvegarde)

Sortie : C:\\...\\_structcalc_sortie\\livrables_villa
    chcp 65001 ; python -u tools\\gen_livrables_villa_live.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = (TEST_DIR / "Projet-Villa-avec-sous-sol" /
             "Projet Villa avec sous sol.rtd")
OUT_DIR = TEST_DIR / "_structcalc_sortie" / "livrables_villa"


def step(t: str) -> None:
    print()
    print("-" * 74)
    print(f"  {t}")
    print("-" * 74, flush=True)


def _node_num(sc_id):
    m = re.search(r"R(\d+)", sc_id or "")
    return int(m.group(1)) if m else None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print("STRUCTCALC PRO v1.4 — GENERATION LIVE DES LIVRABLES (villa)")
    print(f"Sortie : {OUT_DIR}")
    print("=" * 74)

    from structcalc.integration.interop import default_hub
    from structcalc.integration.robot import loads

    hub = default_hub()
    rconn = hub.get("robot")
    opened = False
    try:
        rconn.connect(timeout=300.0)
    except Exception as exc:
        print(f"[REFUS] Robot : {exc}")
        return 1
    rc = rconn.rc
    study = None
    try:
        # -- Robot : ouverture + modèle + calcul --------------------------
        step("ETAPE 1 — Robot : ouverture villa + modele + calcul")
        if rc.is_project_open:
            live = ""
            try:
                live = str(rc.app.Project.FileName or "")
            except Exception:
                live = ""
            if Path(live).resolve() == RTD_VILLA.resolve():
                rc.adopt_live_project()
                print("  Villa deja ouverte : ADOPTION (S5.4).")
            elif live.lower().endswith((".rtd", ".rsm", ".rtdbak")):
                # VRAI fichier projet étranger ouvert -> jamais fermé (§5.4)
                print(f"  [REFUS] projet etranger ouvert (S5.4) : {live}")
                return 1
            else:
                # projet vierge par défaut de Robot (FileName = fond temp
                # ou vide, aucune donnée structurelle) -> safe à remplacer
                print(f"  Projet vierge Robot (FileName={live or 'vide'}) :"
                      " ouverture villa par-dessus (S5.4 — rien perdu).")
                rc.open_project(str(RTD_VILLA))
                opened = True
        else:
            print("  Ouverture visible : villa ...")
            rc.open_project(str(RTD_VILLA))
            opened = True
        rconn2 = hub.get("robot")
        rep = rconn2.read_model(study := _new_project())
        print(f"  read_model : {rep.status} — {rep.message}")
        if not rep.ok:
            print("[STOP] modele illisible — aucun livrable produit.")
            return 1
        rcalc = loads.calculate(rc)
        print(f"  CALCUL : {rcalc}")
        if not rcalc.get("results_available"):
            print("[STOP] pas de resultat — dimensionnement/ferraillage "
                  "non produibles (aucune donnee inventee).")
            return 1

        # -- Réactions réelles + combinaison -> N ------------------------
        step("ETAPE 2 — reactions reelles -> N ELU (1.35G+1.5Q)")
        from structcalc.integration.robot import results as rresults
        from structcalc.solver.loads import apply_combination
        cases = _cases(rc)
        by_name = {c["name"]: c["number"] for c in cases}
        dead_lc = next((lc for lc in study.load_cases.values()
                        if lc.kind == "dead"), None)
        live_lc = next((lc for lc in study.load_cases.values()
                        if lc.kind == "live"), None)
        numG = by_name.get(dead_lc.name) if dead_lc else None
        numQ = by_name.get(live_lc.name) if live_lc else None
        sup_nums = {_node_num(s.sc_id) for s in study.supports.values()}
        col = pied = None
        for c in study.columns.values():
            for end in (c.start_node, c.end_node):
                if _node_num(end) in sup_nums:
                    col, pied = c, _node_num(end)
                    break
            if col:
                break
        N = fck = d_h = None
        outcomes = []
        mat_label = ""
        if col is None or numG is None or numQ is None:
            print("[REFUS] poteau sur appui ou cas G/Q absents — "
                  "dimensionnement/ferraillage non produits.")
        else:
            rG = rresults.import_reactions(rc, case_number=numG,
                                           node_numbers=[pied])[0]
            rQ = rresults.import_reactions(rc, case_number=numQ,
                                           node_numbers=[pied])[0]
            res = apply_combination(
                {dead_lc.sc_id: rG["Fz"], live_lc.sc_id: rQ["Fz"]},
                {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
                expression="1.35 G + 1.5 Q")
            N = abs(res.value)
            print(f"  Poteau {col.sc_id} (pied nœud {pied}) : "
                  f"Fz G={rG['Fz']:.1f}, Fz Q={rQ['Fz']:.1f} -> "
                  f"N ELU = {N:.1f} {rG['units']['force']}")
            try:
                n1, n2 = study.nodes[col.start_node], study.nodes[col.end_node]
                d_h = abs(float(n2.z.value) - float(n1.z.value))
            except Exception:
                d_h = None
            if col.material and col.material in study.materials:
                mat_label = study.materials[col.material].name
                m = re.match(r"BETON(\d+)", mat_label or "", re.IGNORECASE)
                if m:
                    fck = float(m.group(1))

        # -- Dimensionnement BAEL ----------------------------------------
        if N and d_h and fck:
            step("ETAPE 3 — dimensionnement BAEL (fck derive BETON25)")
            from structcalc.solver.column_design import (
                ColumnDesigner, ColumnMaterials, ColumnActions)
            d = ColumnDesigner()
            outcomes = d.search(
                height=d_h, buckling_y=d_h, buckling_z=d_h,
                materials=ColumnMaterials(fck=fck, fyk=500, E=200000),
                actions=ColumnActions(N=N, combination="1.35G+1.5Q"))
            cands = [o for o in outcomes if o.is_candidate and o.rank]
            if cands:
                b = min(cands, key=lambda o: o.rank)
                print(f"  {len(outcomes)} variantes ; rang 1 : "
                      f"{b.variant.designation} "
                      f"(As={b.variant.As_provided_cm2:.1f} cm2)")

        # -- Livrables ----------------------------------------------------
        step("ETAPE 4 — plans de coffrage PDF (labels R<b>x<h> reels)")
        from structcalc.reporting.plan_coffrage import coffrage_pdf
        f_coff = OUT_DIR / "plans_coffrage_villa.pdf"
        try:
            coffrage_pdf(study, str(f_coff), project_name="Villa")
            print(f"  OK : {f_coff.name} ({f_coff.stat().st_size} o)")
        except RuntimeError as exc:
            print(f"  [REFUS] {exc}")

        step("ETAPE 5 — plans de ferraillage PDF (proposition A_VALIDER)")
        from structcalc.reporting.plan_ferraillage import (
            plan_reinforcement, reinforcement_pdf)
        n_ok = 0
        if outcomes and col is not None:
            rep_f = plan_reinforcement(col, study, outcomes=outcomes)
            if rep_f:
                f_ferr = (OUT_DIR /
                          f"plan_ferraillage_{col.sc_id}.pdf")
                reinforcement_pdf(rep_f, str(f_ferr),
                                  project_name="Villa")
                print(f"  OK : {f_ferr.name} — {rep_f.bar_count} "
                      f"Ø{rep_f.bar_d_mm:.0f} (As={rep_f.as_provided_cm2:.1f}"
                      f" cm2, rho={rep_f.ratio*100:.2f}%) — "
                      f"{rep_f.total_mass_kg:.1f} kg acier")
                n_ok += 1
            else:
                print("  [REFUS] donnee manquante (hauteur/section/As).")
        else:
            print("  [REFUS] pas de dimensionnement -> pas de ferraillage"
                  " (aucune armature inventee).")

        step("ETAPE 6 — dossier de controle BCT (BAEL 91 r99 + RPS 2011)")
        from structcalc.reporting.dossier_bct import (
            build_dossier_bct, dossier_bct_md)
        from structcalc.reporting.exports import export_pdf, export_xlsx
        files = [str(f_coff)] + ([str(OUT_DIR /
                 f"plan_ferraillage_{col.sc_id}.pdf")]
                if (outcomes and col) else [])
        d_bct = build_dossier_bct(study, files_written=files,
                                  design_done=bool(outcomes))
        md = dossier_bct_md(d_bct, project_name="Villa")
        f_md = OUT_DIR / "dossier_bct.md"
        f_md.write_text(md, encoding="utf-8")
        try:
            export_pdf(md, str(OUT_DIR / "dossier_bct.pdf"),
                       title="Dossier de controle")
        except RuntimeError as exc:
            print(f"  PDF BCT : {exc}")
        try:
            export_xlsx(md, str(OUT_DIR / "dossier_bct.xlsx"))
        except RuntimeError as exc:
            print(f"  XLSX BCT : {exc}")
        print(f"  Synthese : {len(d_bct.generated)} GENERE / "
              f"{len(d_bct.to_validate)} A VALIDER / "
              f"{len(d_bct.incomplete)} A COMPLETER")

        step("ETAPE 7 — bilan")
        print(f"  Livrables dans {OUT_DIR} :")
        for f in sorted(OUT_DIR.iterdir()):
            print(f"    - {f.name} ({f.stat().st_size} o)")
        return 0
    finally:
        try:
            if opened:
                rc.close_project(save=False)
                print("\nVilla fermee SANS sauvegarde (S5.4).")
        except Exception as exc:
            print(f"[ERREUR] fermeture : {exc}")
        try:
            rconn.disconnect()
        except Exception:
            pass


def _new_project():
    from structcalc.core.model import Project
    return Project(sc_id="SC-VILLA-LIVE", name="Villa")


def _cases(rc):
    S = rc.structure
    cs = S.LoadCases
    out = []
    for i in range(1, cs.Count + 1):
        c = cs.Item(i)
        out.append({"number": int(c.Number), "name": str(c.Name)})
    return out


if __name__ == "__main__":
    raise SystemExit(main())
