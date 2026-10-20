# -*- coding: utf-8 -*-
"""
probe_robot_model.py — Phase 0 : exploration du bon chemin vers le modèle.

Correctif après probe_robot_deep : l'objet s'appelle Project.ActiveModel
(et non Project.Model). Inventorie le serveur de modèle et ses serveurs
d'objets clés. Aucune modification de modèle.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_model_tree.json")


def members(obj, limit=500):
    try:
        return sorted(m for m in dir(obj) if not m.startswith("_"))[:limit]
    except Exception as exc:
        return [f"<erreur: {exc}>"]


def main():
    tree = {}
    app = win32com.client.Dispatch("Robot.Application")
    print(f"Robot {app.ProgramVersion} connecté")

    proj = app.Project
    model = proj.ActiveModel          # <-- bon chemin
    tree["ActiveModel"] = members(model)
    print(f"Project.ActiveModel : {len(tree['ActiveModel'])} membres")

    # Serveurs d'objets du modèle (cœur de l'API d'échange)
    servers = [
        "Bars", "Nodes", "Cases", "Combos", "Materials", "Sections",
        "Stories", "Helpers", "AnalysisResults", "ObjectTypes",
        "Supports", "Shells", "Walls", "Texts", "Sets", "ViewMngr",
        "CalcEngine", "AxisMngr", "ConcrReinfEngine", "ComponentMngr",
    ]
    for srv in servers:
        try:
            s = getattr(model, srv)
            mem = members(s)
            tree[f"ActiveModel.{srv}"] = mem
            print(f"  model.{srv:<20} : {len(mem):3} membres")
        except Exception as exc:
            tree[f"ActiveModel.{srv}"] = [f"<inaccessible: {exc}>"]
            print(f"  model.{srv:<20} : INACCESSIBLE ({exc})")

    # Détail des serveurs prioritaires pour la spec (Bar, Node, Case, Result)
    for srv in ("Bars", "Nodes", "Cases", "AnalysisResults", "Sections",
                "Materials", "Combos"):
        key = f"ActiveModel.{srv}"
        if key in tree and tree[key] and not tree[key][0].startswith("<"):
            print(f"\n=== {key} (méthodes métier) ===")
            for m in tree[key]:
                if not m.startswith(("AddRef", "Release", "QueryInterface",
                                     "GetIDsOfNames", "GetTypeInfo", "Invoke",
                                     "GetTypeInfoCount")):
                    print(f"    - {m}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    print(f"\nArbre API modèle écrit : {OUT}")


if __name__ == "__main__":
    main()
