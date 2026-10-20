# -*- coding: utf-8 -*-
"""
probe_loads_results.py — Phase 2 : vérification API charges + résultats.

Avant d'écrire loads.py / results.py, on vérifie sur Robot 2027 :
  - création d'un cas de charge (Cases.CreateSimple)
  - type d'enregistrement de charge (IRobotLoadRecordType)
  - création d'une charge nodale / barre uniforme
  - combinaisons (Cases.CreateCombination)
  - lecture des résultats (Results.Nodes.Reactions/Displacements, BarForces)

Opération dans un projet jetable, fermé SANS sauvegarde.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_loads_results.json")
R = {}


def members(obj, limit=200):
    try:
        return sorted(m for m in dir(obj) if not m.startswith("_"))[:limit]
    except Exception as exc:
        return [f"<err:{exc}>"]


def main():
    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    proj.New(1)   # FRAME_2D
    S = proj.Structure
    print(f"Robot {app.ProgramVersion}, projet 2D ouvert")

    # 1) Serveur Cases : membres
    cases = S.Cases
    R["cases_members"] = members(cases)
    print(f"\n[Cases] {len(R['cases_members'])} membres")
    print("  ", [m for m in R["cases_members"]
                 if m.startswith(("Create", "Get", "Delete"))])

    # 2) Créer un cas de charge simple (type mort = 1 ?)
    #    CreateSimple(number, type, name) — on tente plusieurs signatures
    created = None
    for args in ((1, 1, "Poids propre"), (1, 1), (1,)):
        try:
            r = cases.CreateSimple(*args)
            created = (args, repr(r)[:60])
            print(f"\n[Cases.CreateSimple{args}] OK -> {created[1]}")
            R["create_simple"] = {"args": list(args), "result": created[1]}
            break
        except Exception as exc:
            print(f"\n[Cases.CreateSimple{args}] echec : {str(exc)[:80]}")

    # 3) Nombre de cas après création
    try:
        R["cases_count"] = int(cases.GetAll().Count)
        print(f"  Cases.GetAll().Count = {R['cases_count']}")
    except Exception as exc:
        print(f"  Cases count : {exc}")

    # 4) Accès aux records d'une charge (case 1)
    try:
        case1 = cases.Get(1)
        R["case1_members"] = members(case1)
        print(f"\n[Case 1] {len(R['case1_members'])} membres")
        print("  ", [m for m in R["case1_members"]
                     if m in ("Records", "Name", "Type", "Number")])
        # Records
        recs = case1.Records
        R["records_members"] = members(recs)
        print(f"  [Case1.Records] {len(R['records_members'])} membres")
    except Exception as exc:
        print(f"  Case1 : {exc}")
        R["case1_error"] = str(exc)[:150]

    # 5) Combinaisons
    try:
        R["cases_combomembers"] = [m for m in members(cases)
                                   if "ombin" in m or "CreateComb" in m]
        print(f"\n[Combinaisons] {R['cases_combomembers']}")
    except Exception:
        pass

    # 6) Résultats : membres de Results
    try:
        res = S.Results
        R["results_members"] = members(res)
        print(f"\n[Results] {R['results_members']}")
        # Sous-serveurs
        for sub in ("Nodes", "Bars"):
            try:
                s = getattr(res, sub)
                R[f"results_{sub}"] = members(s)
                print(f"  [Results.{sub}] {R[f'results_{sub}']}")
            except Exception as exc:
                print(f"  [Results.{sub}] {exc}")
        # Available
        try:
            R["results_available"] = int(res.Available)
            print(f"  Results.Available = {R['results_available']}")
        except Exception as exc:
            print(f"  Results.Available : {exc}")
    except Exception as exc:
        print(f"  Results : {exc}")

    # 7) CalcEngine
    try:
        ce = proj.CalcEngine
        R["calcmembers"] = members(ce)
        print(f"\n[CalcEngine] {R['calcmembers']}")
    except Exception as exc:
        print(f"  CalcEngine : {exc}")

    proj.Close()
    print("\nProjet ferme SANS sauvegarde.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"Rapport : {OUT}")


if __name__ == "__main__":
    main()
