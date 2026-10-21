# -*- coding: utf-8 -*-
"""
tools/test_all_projects.py — Test complet de TOUS les projets de test.

Valide :
  1. Projets Robot (.rtd) : read_model, CALCUL, réactions, dimensionnement
  2. Projets AutoCAD (.dwg) : read_model, write_model, échange
  3. Advance Steel (via AutoCAD COM) : détection, lecture DWG acier
  4. Navisworks : conversion DWG → NWD
  5. Workflows complets selon type de projet
  6. Génération livrables (plans, ferraillage, dossier BCT)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")

# Projets à tester
PROJECTS = {
    "robot": {
        "villa": TEST_DIR / "Projet-Villa-avec-sous-sol" / "Projet Villa avec sous sol.rtd",
        "batiment_r2": TEST_DIR / "Projet-Batiment-R2-" / "Projet Bâtiment R+2 .rtd",
    },
    "autocad": {
        "villa": TEST_DIR / "Plan-villa" / "Plan-villa.dwg",
        "appartement": TEST_DIR / "Plan-Appartement" / "Plan-Appartement.dwg",
        "charpente_trad": TEST_DIR / "plan-charpente-traditionnelle" / "plan-charpente-traditionnelle.dwg",
        "charpente_3d": TEST_DIR / "plan-charpente-tridimensionnelle" / "plan-charpente-tridimensionnelle.dwg",
        "plateau_bureau": TEST_DIR / "plan-plateau-bureau" / "plan-plateau-bureau.dwg",
    },
    "navisworks": {
        "villa_nwc": TEST_DIR / "Plan-villa" / "Plan-villa.nwc",
        "villa_nwd": TEST_DIR / "Plan-villa" / "Plan-villa.nwd",
    }
}

OUT_DIR = Path(r"C:\Users\Admin\Desktop\projets de test\_structcalc_sortie\test_all_projects")


def step(msg: str) -> None:
    print()
    print("=" * 72)
    print(f"  {msg}")
    print("=" * 72, flush=True)


def test_robot_project(name: str, rtd_path: Path) -> Dict[str, Any]:
    """Test complet d'un projet Robot."""
    result = {"name": name, "path": str(rtd_path), "steps": {}}
    
    from structcalc.integration.interop import default_hub
    from structcalc.integration.robot import loads, results as rresults
    from structcalc.core.model import Project
    from structcalc.solver.column_design import ColumnDesigner, ColumnMaterials, ColumnActions
    from structcalc.solver.loads import apply_combination
    
    hub = default_hub()
    rconn = hub.get("robot")
    
    try:
        step(f"ROBOT : {name} - {rtd_path.name}")
        
        # Connexion
        rconn.connect(timeout=300)
        rc = rconn.rc
        
        if rc.is_project_open:
            rc.adopt_live_project()
        else:
            rc.open_project(str(rtd_path))
        
        # Read model
        project = Project(sc_id=f"SC-TEST-{name.upper()}", name=name)
        rep = rconn.read_model(project)
        result["steps"]["read_model"] = {"ok": rep.ok, "msg": rep.message, "counts": rep.objects}
        print(f"  read_model: {rep.status} - {rep.message}")
        if not rep.ok:
            return result
        
        # Calculate
        rcalc = loads.calculate(rc)
        result["steps"]["calculate"] = {"ok": rcalc.get("results_available", False), "msg": str(rcalc)}
        print(f"  calculate: {rcalc}")
        if not rcalc.get("results_available"):
            return result
        
        # Réactions + dimensionnement
        cases = loads.list_cases(rc)
        by_name = {c["name"]: c["number"] for c in cases}
        dead_lc = next((lc for lc in project.load_cases.values() if lc.kind == "dead"), None)
        live_lc = next((lc for lc in project.load_cases.values() if lc.kind == "live"), None)
        numG = by_name.get(dead_lc.name) if dead_lc else None
        numQ = by_name.get(live_lc.name) if live_lc else None
        
        sup_nums = {int(s.sc_id.split("-")[-1]) for s in project.supports.values()}
        col = pied = None
        for c in project.columns.values():
            for end in (c.start_node, c.end_node):
                if int(end.split("-")[-1]) in sup_nums:
                    col, pied = c, int(end.split("-")[-1])
                    break
            if col:
                break
        
        if col and numG and numQ:
            rG = rresults.import_reactions(rc, case_number=numG, node_numbers=[pied])[0]
            rQ = rresults.import_reactions(rc, case_number=numQ, node_numbers=[pied])[0]
            
            from structcalc.solver.loads import apply_combination
            res = apply_combination(
                {dead_lc.sc_id: rG["Fz"], live_lc.sc_id: rQ["Fz"]},
                {dead_lc.sc_id: 1.35, live_lc.sc_id: 1.5},
                expression="1.35 G + 1.5 Q")
            N = abs(res.value)
            
            n1, n2 = project.nodes[col.start_node], project.nodes[col.end_node]
            h = abs(float(n2.z.value) - float(n1.z.value))
            
            fck = 25
            if col.material and col.material in project.materials:
                mat = project.materials[col.material]
                import re
                m = re.match(r"BETON(\d+)", mat.name or "", re.IGNORECASE)
                if m:
                    fck = float(m.group(1))
            
            d = ColumnDesigner()
            outcomes = d.search(
                height=h, buckling_y=h, buckling_z=h,
                materials=ColumnMaterials(fck=fck, fyk=500, E=200000),
                actions=ColumnActions(N=N, combination="1.35G+1.5Q"))
            cands = [o for o in outcomes if o.is_candidate and o.rank]
            best = min(cands, key=lambda o: o.rank) if cands else None
            
            result["steps"]["design"] = {
                "ok": best is not None,
                "N_kN": round(N, 1),
                "height_m": round(h, 2),
                "fck": fck,
                "best_variant": best.variant.designation if best else None,
                "As_cm2": best.variant.As_provided_cm2 if best else None
            }
            print(f"  design: N={N:.1f} kN, best={best.variant.designation if best else 'None'}")
        
        # Plans ferraillage
        from structcalc.reporting.plan_ferraillage import plan_reinforcement, reinforcement_pdf
        from structcalc.reporting.plan_coffrage import coffrage_pdf
        from structcalc.reporting.dossier_bct import build_dossier_bct, dossier_bct_md
        from structcalc.reporting.exports import export_pdf, export_xlsx
        
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        project_out = OUT_DIR / name
        project_out.mkdir(parents=True, exist_ok=True)
        
        # Plans coffrage
        try:
            f_coff = project_out / f"plans_coffrage_{name}.pdf"
            coffrage_pdf(project, str(f_coff), project_name=name)
            result["steps"]["plan_coffrage"] = {"ok": True, "file": str(f_coff)}
            print(f"  plan_coffrage: OK")
        except Exception as e:
            result["steps"]["plan_coffrage"] = {"ok": False, "error": str(e)}
            print(f"  plan_coffrage: ERREUR - {e}")
        
        # Ferraillage
        reinforcement_plans = {}
        if 'best' in locals() and best:
            from structcalc.reporting.plan_ferraillage import plan_reinforcement, reinforcement_pdf
            rep_f = plan_reinforcement(col, project, outcomes=[best])
            if rep_f:
                f_ferr = project_out / f"plan_ferraillage_{col.sc_id}.pdf"
                reinforcement_pdf(rep_f, str(f_ferr), project_name=name)
                result["steps"]["plan_ferraillage"] = {"ok": True, "file": str(f_ferr)}
                print(f"  plan_ferraillage: OK")
        
        # Dossier BCT
        try:
            from structcalc.reporting.dossier_bct import build_dossier_bct, dossier_bct_md
            files = [str(project_out / f"plans_coffrage_{name}.pdf")]
            if 'col' in locals() and col:
                files.append(str(project_out / f"plan_ferraillage_{col.sc_id}.pdf"))
            
            d_bct = build_dossier_bct(project, files_written=files, design_done=bool('best' in locals() and best))
            md = dossier_bct_md(d_bct, project_name=name)
            (project_out / "dossier_bct.md").write_text(md, encoding="utf-8")
            export_pdf(md, str(project_out / "dossier_bct.pdf"), title="Dossier de controle")
            export_xlsx(md, str(project_out / "dossier_bct.xlsx"))
            result["steps"]["dossier_bct"] = {"ok": True, "file": str(project_out / "dossier_bct.md")}
            print(f"  dossier_bct: OK")
        except Exception as e:
            result["steps"]["dossier_bct"] = {"ok": False, "error": str(e)}
            print(f"  dossier_bct: ERREUR - {e}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"  ERREUR: {e}")
    finally:
        try:
            if 'rconn' in locals() and rconn.connected:
                rconn.disconnect()
        except:
            pass
    
    return result


def test_autocad_project(name: str, dwg_path: Path) -> Dict[str, Any]:
    """Test d'un projet AutoCAD."""
    result = {"name": name, "path": str(dwg_path), "steps": {}}
    
    from structcalc.integration.interop import default_hub
    from structcalc.core.model import Project
    
    hub = default_hub()
    acad = hub.get("autocad")
    acad.attach_only = True
    
    try:
        step(f"AUTOCAD : {name} - {dwg_path.name}")
        
        acad.connect()
        result["steps"]["connect"] = {"ok": True, "msg": "Connected"}
        print(f"  connect: OK")
        
        # Ouvrir le DWG
        try:
            doc = acad.open_document(str(dwg_path))
            result["steps"]["open"] = {"ok": True, "msg": f"Opened {dwg_path.name}"}
            print(f"  open: OK")
        except Exception as e:
            result["steps"]["open"] = {"ok": False, "error": str(e)}
            print(f"  open: ERREUR - {e}")
            return result
        
        # Read model
        project = Project(sc_id=f"SC-ACAD-{name.upper()}", name=name)
        rep = acad.read_model(project, document=doc)
        result["steps"]["read_model"] = {"ok": rep.ok, "msg": rep.message, "counts": rep.objects}
        print(f"  read_model: {rep.status} - {rep.message}")
        
        # Write model (test round-trip)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_dwg = OUT_DIR / f"roundtrip_{name}.dwg"
        rep_write = acad.write_model(project)
        result["steps"]["write_model"] = {"ok": rep_write.ok, "msg": rep_write.message, "objects": rep_write.objects}
        print(f"  write_model: {rep_write.status} - {rep_write.message}")
        
        # Sauvegarder
        try:
            acad.save_document(doc, str(out_dwg))
            result["steps"]["save"] = {"ok": True, "file": str(out_dwg)}
            print(f"  save: OK -> {out_dwg}")
        except Exception as e:
            result["steps"]["save"] = {"ok": False, "error": str(e)}
            print(f"  save: ERREUR - {e}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"  ERREUR: {e}")
    finally:
        try:
            acad.disconnect()
        except:
            pass
    
    return result


def test_navisworks_conversion(name: str, dwg_path: Path) -> Dict[str, Any]:
    """Test conversion Navisworks DWG -> NWD."""
    result = {"name": name, "path": str(dwg_path), "steps": {}}
    
    from structcalc.integration.interop import default_hub
    
    hub = default_hub()
    nw = hub.get("navisworks")
    
    try:
        step(f"NAVISWORKS : {name} - {dwg_path.name}")
        
        nw.connect()
        result["steps"]["connect"] = {"ok": True}
        print(f"  connect: OK")
        
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_nwd = OUT_DIR / f"{name}.nwd"
        
        rep = nw.convert(str(dwg_path), str(out_nwd))
        result["steps"]["convert"] = {"ok": rep.ok, "msg": rep.message}
        print(f"  convert: {rep.status} - {rep.message}")
        
        if rep.ok and out_nwd.exists():
            result["steps"]["output"] = {"ok": True, "file": str(out_nwd), "size": out_nwd.stat().st_size}
            print(f"  output: OK -> {out_nwd} ({out_nwd.stat().st_size} bytes)")
        else:
            result["steps"]["output"] = {"ok": False, "error": "NWD not created"}
            print(f"  output: ERREUR - NWD not created")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"  ERREUR: {e}")
    finally:
        try:
            nw.disconnect()
        except:
            pass
    
    return result


def test_advance_steel_detection() -> Dict[str, Any]:
    """Test détection Advance Steel."""
    result = {"name": "advance_steel_detection", "steps": {}}
    
    from structcalc.integration.interop import default_hub
    
    hub = default_hub()
    adv = hub.get("advsteel")
    
    try:
        step("ADVANCE STEEL : Détection")
        
        det = adv.detect()
        result["steps"]["detect"] = {"installed": det.installed, "version": det.version, "automatable": det.automatable, "detail": det.detail}
        print(f"  detect: installed={det.installed}, version={det.version}, automatable={det.automatable}")
        
        if det.automatable:
            adv.connect()
            result["steps"]["connect"] = {"ok": True}
            print(f"  connect: OK")
            
            # Test read_model (DWG niveau dessin)
            from structcalc.core.model import Project
            project = Project(sc_id="SC-ADV-TEST", name="AdvSteel Test")
            rep = adv.read_model(project)
            result["steps"]["read_model"] = {"ok": rep.ok, "msg": rep.message, "counts": rep.objects}
            print(f"  read_model: {rep.status} - {rep.message}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"  ERREUR: {e}")
    finally:
        try:
            adv.disconnect()
        except:
            pass
    
    return result


def main():
    print("=" * 72)
    print("TEST COMPLET DE TOUS LES PROJETS")
    print("=" * 72)
    
    all_results = {}
    
    # 1. Projets Robot
    print("\n" + "=" * 72)
    print("PHASE 1 : PROJETS ROBOT (.rtd)")
    print("=" * 72)
    for name, path in PROJECTS["robot"].items():
        if path.exists():
            all_results[f"robot_{name}"] = test_robot_project(name, path)
        else:
            print(f"IGNORÉ (manquant) : {path}")
    
    # 2. Projets AutoCAD
    print("\n" + "=" * 72)
    print("PHASE 2 : PROJETS AUTOCAD (.dwg)")
    print("=" * 72)
    for name, path in PROJECTS["autocad"].items():
        if path.exists():
            all_results[f"autocad_{name}"] = test_autocad_project(name, path)
        else:
            print(f"IGNORÉ (manquant) : {path}")
    
    # 3. Navisworks
    print("\n" + "=" * 72)
    print("PHASE 3 : NAVISWORKS (conversion DWG -> NWD)")
    print("=" * 72)
    for name, path in PROJECTS["navisworks"].items():
        if path.exists():
            all_results[f"navisworks_{name}"] = test_navisworks_conversion(name, path)
        else:
            print(f"IGNORÉ (manquant) : {path}")
    
    # 4. Advance Steel Detection
    print("\n" + "=" * 72)
    print("PHASE 4 : ADVANCE STEEL (Détection)")
    print("=" * 72)
    all_results["advance_steel"] = test_advance_steel_detection()
    
    # 5. Bilan
    print("\n" + "=" * 72)
    print("BILAN FINAL")
    print("=" * 72)
    
    for key, result in all_results.items():
        steps_ok = sum(1 for s in result.get("steps", {}).values() if isinstance(s, dict) and s.get("ok"))
        steps_total = len(result.get("steps", {}))
        status = "✅" if result.get("error") is None and steps_ok == steps_total and steps_total > 0 else "❌"
        print(f"  {status} {key} : {steps_ok}/{steps_total} étapes OK")
        if "error" in result:
            print(f"      ERREUR: {result['error']}")
    
    # Sauvegarder rapport
    import json
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "test_report.json").write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nRapport sauvegardé : {OUT_DIR / 'test_report.json'}")
    
    return all_results


if __name__ == "__main__":
    results = main()
    sys.exit(0 if all(r.get("error") is None for r in results.values()) else 1)