# -*- coding: utf-8 -*-
"""
probe_calc_pipeline.py — Phase 2 : pipeline complet charge -> calcul -> résultats.

Vérifie :
  1. signature exacte de Cases.CreateSimple (ordre des arguments)
  2. création d'une charge sur une barre (Records.Create)
  3. calcul (CalcEngine.Calculate)
  4. lecture des résultats (Results.Nodes.Reactions, Results.Bars.Forces)

Poutre isostatique de 4 m, charge uniforme connue -> reaction théorique
comparable. Projet jetable, fermé SANS sauvegarde.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_calc_pipeline.json")
R = {}


def main():
    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    proj.New(1)  # FRAME_2D
    S = proj.Structure
    print(f"Robot {app.ProgramVersion}, projet 2D")

    # --- Modèle : poutre isostatique 4 m, 2 appuis ---
    S.Nodes.Create(1, 0.0, 0.0, 0.0)
    S.Nodes.Create(2, 4.0, 0.0, 0.0)
    S.Bars.Create(1, 1, 2)
    print("Poutre 4 m créée (2 nœuds, 1 barre)")

    # --- Appuis : node 1 rotule, node 2 roulement ---
    #    SetLabel sur le nœud avec un type d'appui
    supports_names = S.Labels.GetAvailableNames(2)  # I_LT_SUPPORT ~ 2 ? on tente
    print(f"Appuis disponibles (type {2}) : {supports_names.Count}")
    for i in range(1, min(supports_names.Count, 5) + 1):
        print(f"   appui {i}: {supports_names.Get(i)}")
    R["support_labels"] = [supports_names.Get(i)
                           for i in range(1, supports_names.Count + 1)]

    # Tenter d'appliquer un appui au nœud 1
    try:
        S.Nodes.SetLabel(1, 2, supports_names.Get(1))  # signature à confirmer
        print("Appui appliqué au nœud 1")
        R["support_applied"] = True
    except Exception as exc:
        print(f"SetLabel nœud : {str(exc)[:100]}")
        R["support_error"] = str(exc)[:150]

    # --- Cas de charge : tester les ordres d'arguments de CreateSimple ---
    print("\n=== Test CreateSimple ===")
    case_ok = None
    for args in ((1, "Poids propre", 1), (1, 1, "PP"), (1, "PP")):
        try:
            r = S.Cases.CreateSimple(*args)
            print(f"  CreateSimple{args} OK -> {repr(r)[:50]}")
            R["create_simple_ok"] = list(args)
            case_ok = args
            break
        except Exception as exc:
            print(f"  CreateSimple{args} : {str(exc)[:70]}")
    R["cases_count"] = int(S.Cases.GetAll().Count)
    print(f"  Cases.GetAll().Count = {R['cases_count']}")

    # --- Charge barre uniforme sur la barre 1 ---
    if case_ok:
        try:
            case1 = S.Cases.Get(1)
            recs = case1.Records
            # I_LRT_BAR_UNIFORM : type d'enregistrement charge uniforme barre
            for tval in (3, 4, 5, 6, 2):
                try:
                    rec = recs.Create(tval)
                    R["bar_load_rectype"] = tval
                    print(f"  Records.Create({tval}) OK -> {type(rec).__name__}")
                    # Appliquer Fz = -10 (kN/m) sur barre 1
                    try:
                        rec.Objects = "1"
                        rec.Fz = -10.0
                        print(f"    Charge uniforme Fz=-10 sur barre 1 appliquée")
                        R["bar_load"] = {"type": tval, "Fz": -10.0, "bar": 1}
                    except Exception as exc:
                        print(f"    réglage charge : {str(exc)[:70]}")
                    break
                except Exception:
                    continue
        except Exception as exc:
            print(f"  Charge barre : {str(exc)[:100]}")
            R["bar_load_error"] = str(exc)[:150]

    # --- Calcul ---
    print("\n=== Calcul ===")
    try:
        proj.CalcEngine.Calculate()
        print("  CalcEngine.Calculate() lancé")
        R["calc_called"] = True
    except Exception as exc:
        print(f"  Calculate : {str(exc)[:100]}")
        R["calc_error"] = str(exc)[:150]

    # --- Résultats ---
    try:
        avail = int(S.Results.Available)
        R["results_available"] = avail
        print(f"  Results.Available = {avail}")
    except Exception as exc:
        print(f"  Available : {exc}")

    # Réactions aux appuis
    try:
        nodes_res = S.Results.Nodes
        reac = nodes_res.Reactions
        print(f"  [Results.Nodes.Reactions] membres : "
              f"{[m for m in dir(reac) if not m.startswith('_')][:12]}")
        # Value(node, case) -> objet avec Fx,Fy,Fz,Mx,My,Mz
        for n in (1, 2):
            try:
                rv = reac.Value(n, 1)
                print(f"    Nœud {n}: Fy={getattr(rv,'Fy',None)} Fx={getattr(rv,'Fx',None)}")
                R[f"reaction_node{n}"] = {"Fx": getattr(rv, "Fx", None),
                                          "Fy": getattr(rv, "Fy", None),
                                          "Fz": getattr(rv, "Fz", None)}
            except Exception as exc:
                print(f"    réaction nœud {n} : {str(exc)[:70]}")
    except Exception as exc:
        print(f"  Réactions : {str(exc)[:100]}")
        R["reaction_error"] = str(exc)[:150]

    # Efforts barre
    try:
        bars_res = S.Results.Bars
        forces = bars_res.Forces
        print(f"  [Results.Bars.Forces] membres : "
              f"{[m for m in dir(forces) if not m.startswith('_')][:12]}")
        for case in (1,):
            try:
                fv = forces.Value(1, case)   # barre 1, cas 1
                attrs = {a: getattr(fv, a, None) for a in
                         ("Fx", "Fy", "Fz", "Mx", "My", "Mz")}
                print(f"    Barre 1 cas {case} (extrémité A) : {attrs}")
                R[f"bar_force_c{case}"] = {k: (float(v) if isinstance(v, (int, float)) else str(v))
                                           for k, v in attrs.items()}
            except Exception as exc:
                print(f"    force barre cas {case} : {str(exc)[:80]}")
    except Exception as exc:
        print(f"  Forces barre : {str(exc)[:100]}")

    proj.Close()
    print("\nProjet fermé SANS sauvegarde.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False, default=str)
    print(f"Rapport : {OUT}")


if __name__ == "__main__":
    main()
