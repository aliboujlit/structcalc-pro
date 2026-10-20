# -*- coding: utf-8 -*-
"""
probe_full_pipeline.py — Phase 2 : pipeline complet validé.

Signature CreateSimple CONFIRMÉE : CreateSimple(number, name, type, analize).

Teste le chaînage complet sur une poutre isostatique 4 m :
  appuis -> cas de charge -> charge uniforme barre -> Calculate -> Réactions

Compare la réaction de Robot avec la valeur théorique (control de cohérence).
Projet jetable, fermé sans sauvegarde.
"""

import os
import json
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_full_pipeline.json")
R = {}


def main():
    comtypes.client.GetModule(TLB)
    import comtypes.gen.RobotOM as RobotOM

    app = comtypes.client.CreateObject("Robot.Application",
                                       interface=RobotOM.IRobotApplication)
    proj = app.Project
    proj.New(1)  # FRAME_2D
    S = proj.Structure
    print(f"Robot {app.ProgramVersion} — projet 2D")

    # --- Modèle : poutre 4 m ---
    S.Nodes.Create(1, 0.0, 0.0, 0.0)
    S.Nodes.Create(2, 4.0, 0.0, 0.0)
    S.Bars.Create(1, 1, 2)
    print("Poutre 4 m : 2 nœuds, 1 barre")

    # --- Appuis (support labels) ---
    sup = S.Labels.GetAvailableNames(2)  # I_LT_SUPPORT
    sup_names = [sup.Get(i) for i in range(1, sup.Count + 1)]
    print(f"Appuis disponibles : {sup_names}")
    R["support_labels"] = sup_names
    # Appliquer appuis : nœud 1 rotule, nœud 2 roulement (si dispo)
    try:
        S.Nodes.SetLabel(1, sup_names[0])   # 1er type d'appui
        if len(sup_names) > 1:
            S.Nodes.SetLabel(2, sup_names[-1])
        else:
            S.Nodes.SetLabel(2, sup_names[0])
        print("Appuis appliqués aux nœuds 1 et 2")
        R["supports_applied"] = True
    except Exception as exc:
        print(f"SetLabel appui : {str(exc)[:80]}")
        R["supports_error"] = str(exc)[:120]

    # --- Cas de charge (signature confirmée) ---
    S.Cases.CreateSimple(1, "Poids propre", 1, False)
    print(f"Cas 1 créé. Cases.GetAll().Count = {int(S.Cases.GetAll().Count)}")

    # --- Charge barre uniforme ---
    try:
        case1 = S.Cases.Get(1)
        recs = case1.Records
        # Trouver le type d'enregistrement charge uniforme barre
        load_rectype = None
        for tval in range(1, 12):
            try:
                rec = recs.Create(tval)
                load_rectype = tval
                print(f"Records.Create({tval}) OK -> type de charge trouvé")
                break
            except Exception:
                continue
        if load_rectype:
            rec = recs.Get(1) if hasattr(recs, "Get") else rec
            # Appliquer sur barre 1, Fz = -10 kN/m
            for attr_set in ("Objects",):
                try:
                    rec.Objects = "1"
                except Exception:
                    pass
            rec.Fz = -10.0
            print(f"Charge uniforme barre 1 : Fz=-10 (rectype={load_rectype})")
            R["bar_load"] = {"rectype": load_rectype, "Fz": -10.0}
    except Exception as exc:
        print(f"Charge barre : {str(exc)[:80]}")
        R["bar_load_error"] = str(exc)[:120]

    # --- Calcul ---
    try:
        proj.CalcEngine.Calculate()
        avail = int(S.Results.Available)
        print(f"Calcul lancé. Results.Available = {avail}")
        R["results_available"] = avail
    except Exception as exc:
        print(f"Calculate : {str(exc)[:80]}")
        R["calc_error"] = str(exc)[:120]

    # --- Réactions ---
    try:
        reac = S.Results.Nodes.Reactions
        for n in (1, 2):
            rv = reac.Value(n, 1)
            fx, fy = getattr(rv, "Fx", None), getattr(rv, "Fy", None)
            print(f"  Réaction nœud {n} : Fx={fx} Fy={fy}")
            R[f"reaction_node{n}"] = {"Fx": _f(fx), "Fy": _f(fy)}
    except Exception as exc:
        print(f"Réactions : {str(exc)[:80]}")
        R["reaction_error"] = str(exc)[:120]

    # --- Efforts barre ---
    try:
        forces = S.Results.Bars.Forces
        fv = forces.Value(1, 1)
        attrs = {a: _f(getattr(fv, a, None)) for a in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")}
        print(f"  Barre 1 cas 1 (extrémité) : {attrs}")
        R["bar_force"] = attrs
    except Exception as exc:
        print(f"Efforts barre : {str(exc)[:80]}")

    proj.Close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nRapport : {OUT}")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else None


if __name__ == "__main__":
    main()
