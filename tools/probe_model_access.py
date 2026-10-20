# -*- coding: utf-8 -*-
"""
probe_model_access.py — Phase 0 : accès au modèle après New(type).

Découverte : Project.ActiveModel est une méthode renvoyant une ENUM
(IRobotActiveModelType), PAS le serveur de modèle. Le vrai serveur est
probablement Project.Model, qui échouait car IsActive=0 (aucun projet).

Ici : New(1) ouvre un projet, puis on tente d'accéder au serveur de modèle
et de créer 2 nœuds + 1 barre. Fermeture sans sauvegarde.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_model_access.json")
R = {}


def main():
    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    print(f"Robot {app.ProgramVersion}, IsActive initial={proj.IsActive}")

    # Ouvrir un projet : type 1 = I_PT_FRAME_2D (ou 4 = FRAME_3D)
    print("Project.New(1)  [I_PT_FRAME_2D]...")
    proj.New(1)
    print(f"  IsActive après = {proj.IsActive}  (-1 = projet ouvert)")
    R["is_active"] = int(proj.IsActive)

    # ActiveModel = enum du type de modèle actif (pas le serveur)
    try:
        am = proj.ActiveModel
        print(f"  Project.ActiveModel (enum) = {am}  type={type(am).__name__}")
        R["active_model_enum"] = str(am)
    except Exception as exc:
        print(f"  ActiveModel : {exc}")

    # Le vrai serveur de modèle ?
    model = None
    for attr in ("Model",):
        try:
            model = getattr(proj, attr)
            print(f"  >>> proj.{attr} = {type(model).__name__}")
            R["model_accessor"] = attr
            break
        except Exception as exc:
            print(f"  proj.{attr} échec : {exc}")
            R[f"{attr}_error"] = str(exc)

    if model is None:
        print("Aucun serveur de modèle accessible. Abandon.")
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(R, f, indent=2, ensure_ascii=False)
        return 1

    # Inventorier les serveurs d'objets
    for srv in ("Bars", "Nodes", "Cases", "Sections", "Materials"):
        try:
            s = getattr(model, srv)
            cnt = getattr(s, "Count", None)
            print(f"  model.{srv}: type={type(s).__name__}, Count={cnt}")
            R[f"srv_{srv}"] = {"type": type(s).__name__, "count": int(cnt) if cnt is not None else None}
        except Exception as exc:
            print(f"  model.{srv} échec : {exc}")
            R[f"srv_{srv}_error"] = str(exc)

    # Démonstration : 2 nœuds + 1 barre
    try:
        nodes = model.Nodes
        bars = model.Bars
        print("\nCréation nœuds 1 (0,0,0) et 2 (4,0,0)...")
        nodes.Create(1, 0.0, 0.0, 0.0)
        nodes.Create(2, 4.0, 0.0, 0.0)
        print("Création barre 1 (n1->n2)...")
        bars.Create(1, 1, 2)
        print(f"  Nodes.Count = {nodes.Count}, Bars.Count = {bars.Count}")
        R["nodes_count"] = int(nodes.Count)
        R["bars_count"] = int(bars.Count)

        b1 = bars.Item(1)
        print(f"  barre1 StartNode={b1.StartNode}, EndNode={b1.EndNode}")
        R["bar1"] = {"start": int(b1.StartNode), "end": int(b1.EndNode)}
        R["success"] = True
        print("\n>>> OPÉRATION RÉELLE RÉUSSIE : nœuds + barre créés dans Robot.")
    except Exception as exc:
        print(f"\nCréation objets échec : {exc}")
        R["create_error"] = str(exc)
        R["success"] = False

    # Fermeture SANS sauvegarde (Close sans argument)
    try:
        proj.Close()
        print("Projet fermé (sans sauvegarde).")
        R["closed"] = True
    except Exception as exc:
        print(f"Fermeture : {exc}")
        R["closed"] = False

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"Rapport : {OUT}")
    return 0 if R.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
