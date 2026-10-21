# -*- coding: utf-8 -*-
"""
Test complet workflow Robot : Villa -> CALCUL -> Dimensionnement -> Plans -> Dossier BCT
"""

import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\geni  civil\structcalc_pro")

from structcalc.integration.interop import default_hub
from structcalc.core.model import Project
from structcalc.integration.robot import loads, results as rresults
from structcalc.solver.column_design import ColumnDesigner, ColumnMaterials, ColumnActions
from structcalc.solver.loads import apply_combination
from structcalc.reporting.plan_ferraillage import plan_reinforcement, reinforcement_pdf
from structcalc.reporting.plan_coffrage import coffrage_pdf
from structcalc.reporting.dossier_bct import build_dossier_bct, dossier_bct_md
from structcalc.reporting.exports import export_pdf, export_xlsx
from pathlib import Path
import re

def main():
    OUT_DIR = Path(r"C:\Users\Admin\Desktop\projets de test\_structcalc_sortie\bim_revit_demo")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    hub = default_hub()
    r = hub.get("robot")
    r.connect(timeout=60)
    rc = r.rc

    villa_path = r"C:\Users\Admin\Desktop\projets de test\Projet-Villa-avec-sous-sol\Projet Villa avec sous sol.rtd"
    rc.open_project(villa_path)

    p = Project(sc_id="SC-VILLA-BIM", name="Villa")
    rep = r.read_model(p)
    print(f"read_model: {rep.status} - {rep.message}")
    print(f"  nodes: {len(p.nodes)}, beams: {len(p.beams)}, columns: {len(p.columns)}, supports: {len(p.supports)}")

    # Load cases
    cases = loads.list_cases(rc)
    by_name = {c["name"]: c["number"] for c in cases}
    dead_lc = next((lc for lc in p.load_cases.values() if lc.kind == "dead"), None)
    live_lc = next((lc for lc in p.load_cases.values() if lc.kind == "live"), None)
    numG = by_name.get(dead_lc.name) if dead_lc else None
    numQ = by_name.get(live_lc.name) if live_lc else None
    print(f"Dead LC: {dead_lc.name if dead_lc else None} (#{numG}), Live LC: {live_lc.name if live_lc else None} (#{numQ})")

    # Find first column on support
    sup_nums = set()
    for s in p.supports.values():
        # Extract numeric part from SC_ID like "SC-SUP-R2" -> "2"
        import re
        m = re.search(r"(\d+)$", s.sc_id)
        if m:
            sup_nums.add(int(m.group(1)))
    
    col = pied = None
    for c in p.columns.values():
        for end in (c.start_node, c.end_node):
            if end:
                m = re.search(r"(\d+)$", end)
                if m and int(m.group(1)) in sup_nums:
                    col, pied = c, int(m.group(1))
                    break
        if col:
            break

    if col and numG and numQ:
        rG = rresults.import_reactions(rc, case_number=numG, node_numbers=[pied])[0]
        rQ = rresults.import_reactions(rc, case_number=numQ, node_numbers=[pied])[0]
        res = apply_combination(
            {dead_lc.sc_id: rG["Fz"], live_lc.sc_id: rQ["Fz"]},
            {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
            expression="1.35 G + 1.5 Q")
        N = abs(res.value)
        print(f"Poteau {col.sc_id} (pied nœud {pied}) : N ELU = {N:.1f} kN")

        n1, n2 = p.nodes[col.start_node], p.nodes[col.end_node]
        h = abs(float(n2.z.value) - float(n1.z.value))
        print(f"  Hauteur: {h:.2f} m")

        fck = 25
        if col.material and col.material in p.materials:
            mat = p.materials[col.material]
            m = re.match(r"BETON(\d+)", mat.name or "", re.IGNORECASE)
            if m:
                fck = float(m.group(1))
        print(f"  fck: {fck} MPa")

        d = ColumnDesigner()
        outcomes = d.search(
            height=h, buckling_y=h, buckling_z=h,
            materials=ColumnMaterials(fck=fck, fyk=500, E=200000),
            actions=ColumnActions(N=N, combination="1.35G+1.5Q"))
        cands = [o for o in outcomes if o.is_candidate and o.rank]
        if cands:
            best = min(cands, key=lambda o: o.rank)
            print(f"  {len(outcomes)} variantes, rang 1: {best.variant.designation} (As={best.variant.As_provided_cm2:.1f} cm²)")

            # Plans ferraillage
            rep_f = plan_reinforcement(col, p, outcomes=[best])
            if rep_f:
                f_ferr = OUT_DIR / f"plan_ferraillage_{col.sc_id}.pdf"
                reinforcement_pdf(rep_f, str(f_ferr), project_name="Villa")
                print(f"  Plan ferraillage: {f_ferr}")
            
            # Plans coffrage
            f_coff = OUT_DIR / "plans_coffrage_villa.pdf"
            coffrage_pdf(p, str(f_coff), project_name="Villa")
            print(f"  Plans coffrage: {f_coff}")

            # Dossier BCT
            files = [str(f_coff), str(f_ferr)]
            d_bct = build_dossier_bct(p, files_written=files, design_done=True)
            md = dossier_bct_md(d_bct, project_name="Villa")
            (OUT_DIR / "dossier_bct.md").write_text(md, encoding="utf-8")
            export_pdf(md, str(OUT_DIR / "dossier_bct.pdf"), title="Dossier de controle")
            export_xlsx(md, str(OUT_DIR / "dossier_bct.xlsx"))
            print(f"  Dossier BCT: {OUT_DIR / 'dossier_bct.md'}")

    r.disconnect()
    print("SUCCESS - All Robot workflows complete")

if __name__ == "__main__":
    main()