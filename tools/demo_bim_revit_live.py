# -*- coding: utf-8 -*-
"""
tools/demo_bim_revit_live.py — Démonstration LIVE workflow BIM complet.

Chaîne : Villa (.rtd) -> Robot (read_model + CALCUL) -> Dimensionnement
         -> Plans ferraillage -> Revit (FamilyInstance + Rebar + SC_Params)

Prérequis :
  - Robot 2027 ouvert avec "Projet Villa avec sous sol.rtd"
  - Revit 2027 ouvert avec add-in StructCalcRevitAddin chargé (LED verte)
  - families_map.json complété avec VOS familles Revit
  - shared_parameters.txt chargé dans Revit (Gérer > Paramètres partagés)

Usage :
  python tools/demo_bim_revit_live.py
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
from structcalc.integration.robot import loads
from structcalc.solver.column_design import ColumnDesigner, ColumnMaterials, ColumnActions
from structcalc.reporting.plan_ferraillage import plan_reinforcement
from structcalc.integration.revit.writer import (
    write_model_to_revit, build_apply_changes_request
)
from structcalc.integration.revit.families import write_default_mapping, FamiliesMap
from structcalc.integration.revit.protocol import RevitPipeClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = TEST_DIR / "Projet-Villa-avec-sous-sol" / "Projet Villa avec sous sol.rtd"
FAMILIES_MAP = ROOT / "families_map.json"  # À créer/compléter par l'utilisateur
SHARED_PARAMS = ROOT / "structcalc" / "integration" / "revit" / "shared_parameters.txt"

OUT_DIR = TEST_DIR / "_structcalc_sortie" / "bim_revit_demo"


def step(msg: str) -> None:
    print()
    print("=" * 72)
    print(f"  {msg}")
    print("=" * 72)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("STRUCTCALC PRO v1.5 — DEMO LIVE BIM REVIT COMPLET")
    print(f"Sortie : {OUT_DIR}")
    print("=" * 72)

    # 1. Vérifier families_map.json
    if not FAMILIES_MAP.exists():
        print(f"\n[INFO] Création families_map.json exemple : {FAMILIES_MAP}")
        write_default_mapping(str(FAMILIES_MAP))
        print("  -> ÉDITEZ ce fichier avec VOS familles Revit avant de continuer !")
        return 1

    # 2. Hub + connecteurs
    hub = default_hub()
    rconn = hub.get("robot")
    revit_conn = hub.get("revit")

    # 3. Robot : ouverture villa + modèle + calcul
    step("ÉTAPE 1 — Robot : ouverture villa + modèle + calcul")
    try:
        rconn.connect(timeout=300.0)
        print("  Robot connecté")
    except Exception as exc:
        print(f"[ERREUR] Robot connect : {exc}")
        return 1

    rc = rconn.rc
    if rc.is_project_open:
        print("  Projet déjà ouvert, adoption...")
        rc.adopt_live_project()
    else:
        rc.open_project(str(RTD_VILLA))
        print(f"  Villa ouverte : {RTD_VILLA.name}")

    project = Project(sc_id="SC-VILLA-BIM", name="Villa")
    rep = rconn.read_model(project)
    print(f"  read_model : {rep.status} — {rep.message}")
    if not rep.ok:
        print("[ERREUR] Modèle illisible")
        return 1

    rcalc = loads.calculate(rc)
    print(f"  CALCUL : {rcalc}")
    if not rcalc.get("results_available"):
        print("[ERREUR] Pas de résultats")
        return 1

    # 4. Réactions + dimensionnement
    step("ÉTAPE 2 — Réactions réelles + dimensionnement BAEL")
    from structcalc.integration.robot import results as rresults
    from structcalc.solver.loads import apply_combination

    cases = loads.list_cases(rc)
    by_name = {c["name"]: c["number"] for c in cases}
    dead_lc = next((lc for lc in project.load_cases.values() if lc.kind == "dead"), None)
    live_lc = next((lc for lc in project.load_cases.values() if lc.kind == "live"), None)
    numG = by_name.get(dead_lc.name) if dead_lc else None
    numQ = by_name.get(live_lc.name) if live_lc else None

    # Poteau représentatif (premier sur appui)
    sup_nums = {int(s.sc_id.split("-")[-1]) for s in project.supports.values()}
    col = pied = None
    for c in project.columns.values():
        for end in (c.start_node, c.end_node):
            nnum = int(end.split("-")[-1]) if end else 0
            if nnum in sup_nums:
                col, pied = c, nnum
                break
        if col:
            break

    N = None
    outcomes = []
    if col and numG and numQ:
        rG = rresults.import_reactions(rc, case_number=numG, node_numbers=[pied])[0]
        rQ = rresults.import_reactions(rc, case_number=numQ, node_numbers=[pied])[0]
        res = apply_combination(
            {dead_lc.sc_id: rG["Fz"], live_lc.sc_id: rQ["Fz"]},
            {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
            expression="1.35 G + 1.5 Q")
        N = abs(res.value)
        print(f"  Poteau {col.sc_id} (pied nœud {pied}) : N ELU = {N:.1f} kN")

        # Hauteur poteau
        n1, n2 = project.nodes[col.start_node], project.nodes[col.end_node]
        h = abs(float(n2.z.value) - float(n1.z.value))

        # fck depuis matériau
        fck = 25
        if col.material and col.material in project.materials:
            mat = project.materials[col.material]
            import re
            m = re.match(r"BETON(\d+)", mat.name or "", re.IGNORECASE)
            if m:
                fck = float(m.group(1))

        # Dimensionnement
        d = ColumnDesigner()
        outcomes = d.search(
            height=h, buckling_y=h, buckling_z=h,
            materials=ColumnMaterials(fck=fck, fyk=500, E=200000),
            actions=ColumnActions(N=N, combination="1.35G+1.5Q"))
        cands = [o for o in outcomes if o.is_candidate and o.rank]
        if cands:
            best = min(cands, key=lambda o: o.rank)
            print(f"  {len(outcomes)} variantes ; rang 1 : {best.variant.designation} (As={best.variant.As_provided_cm2:.1f} cm²)")

    # 5. Plans ferraillage (proposition A_VALIDER)
    step("ÉTAPE 3 — Plans ferraillage (proposition A_VALIDER)")
    from structcalc.reporting.plan_ferraillage import plan_reinforcement, reinforcement_pdf

    reinforcement_plans = {}
    if outcomes and col:
        rep = plan_reinforcement(col, project, outcomes=outcomes)
        if rep:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            fpdf = OUT_DIR / f"plan_ferraillage_{col.sc_id}.pdf"
            reinforcement_pdf(rep, str(fpdf), project_name="Villa")
            print(f"  PDF : {fpdf.name} — {rep.bar_count} Ø{rep.bar_d_mm:.0f} (As={rep.as_provided_cm2:.1f} cm²)")
            reinforcement_plans[col.sc_id] = rep

    # 6. Revit : connexion + écriture modèle complet
    step("ÉTAPE 4 — Revit : connexion + écriture BIM complet")
    revit_conn = hub.get("revit")
    try:
        revit_conn.connect()
        print("  Revit connecté (pipe OK)")
    except Exception as exc:
        print(f"[ERREUR] Revit connect : {exc}")
        return 1

    # 7. Écriture BIM complet
    step("ÉTAPE 5 — Écriture BIM (FamilyInstance + Rebar + SC_Params)")
    fmap_path = str(FAMILIES_MAP)
    report = write_model_to_revit(
        project, fmap_path, reinforcement_plans=reinforcement_plans,
        pipe_client=revit_conn._client if hasattr(revit_conn, '_client') else None
    )
    # Note: on utilise le connecteur hub qui a son propre client
    # Pour la demo, on utilise le client du hub
    from structcalc.integration.revit.writer import write_model_to_revit
    report = write_model_to_revit(
        project, fmap_path, reinforcement_plans=reinforcement_plans,
        pipe_client=revit_conn._client if hasattr(revit_conn, '_client') else None
    )
    # Le connecteur hub n'expose pas _client directement, on recrée
    client = RevitPipeClient()
    client.connect()
    report = write_model_to_revit(project, str(FAMILIES_MAP), reinforcement_plans, client)

    print(f"  {report.elements_created} éléments créés")
    print(f"  {report.rebars_created} armatures créées")
    print(f"  {report.sections_applied} sections appliquées")
    for note in report.notes:
        print(f"  - {note}")
    for err in report.errors:
        print(f"  [ERREUR] {err}")

    # 8. Nomenclature
    step("ÉTAPE 6 — Nomenclature acier (données pour planning Revit)")
    from structcalc.integration.revit.writer import export_nomenclature_to_revit
    nomenclature = export_nomenclature_to_revit(project, reinforcement_plans, client)
    print(f"  Masse totale acier : {nomenclature['total_mass_kg']:.1f} kg")
    print(f"  {len(nomenclature['rows'])} lignes de nomenclature")
    for row in nomenclature['rows'][:5]:
        print(f"  - {row['Repère']} : {row['Nombre']} Ø{row['Diamètre_mm']} L={row['Longueur_m']}m {row['Masse_kg']}kg")

    # 9. Fermeture (S5.4)
    step("FERMETURE (S5.4 sans sauvegarde)")
    try:
        rc.close_project(save=False)
        print("  Villa fermée sans sauvegarde")
    except Exception:
        pass
    try:
        client.close()
        print("  Pipe fermé")
    except Exception:
        pass
    try:
        rconn.disconnect()
        revit_conn.disconnect()
    except Exception:
        pass

    print("\n" + "=" * 72)
    print("DEMO BIM REVIT TERMINÉE")
    print("=" * 72)
    print(f"Prochaines étapes manuelles dans Revit :")
    print("  1. Vérifier les FamilyInstance créés (poteaux/poutres/semelles)")
    print("  2. Vérifier les Rebar créés (SC_Status = A_VALIDER)")
    print("  3. Ajuster positionnement barres (enrobage SC_Enrobage_mm)")
    print("  4. Créer planning nomenclatures depuis données exportées")
    print("  5. Valider par ingénieur -> changer SC_Status -> GÉNÉRÉE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())