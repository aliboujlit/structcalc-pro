# -*- coding: utf-8 -*-
"""
probe_robot_deep.py — Phase 0 : exploration ciblée de l'arbre Project/Model.

Inventorie précisément les membres de :
  app.Project, app.Project.Model, et serveurs clés (Bar, Node, Case...)

Objectif : documenter l'API RÉELLEMENT disponible avant d'écrire le connecteur.
Aucune modification de modèle n'est effectuée.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_api_tree.json")


def members(obj, limit=400):
    try:
        return sorted(m for m in dir(obj) if not m.startswith("_"))[:limit]
    except Exception as exc:
        return [f"<erreur: {exc}>"]


def main():
    tree = {}
    app = win32com.client.Dispatch("Robot.Application")
    print(f"Robot connecté, version = {app.ProgramVersion}")

    # --- Project ---
    proj = app.Project
    tree["Project"] = members(proj)

    # --- Project.Model (le serveur de modèle central) ---
    try:
        model = proj.Model
        tree["Project.Model"] = members(model)
        print(f"Project.Model : {len(tree['Project.Model'])} membres")

        # Serveurs d'objets principaux
        for srv in ("Bars", "Nodes", "Cases", "Combos", "Materials",
                    "Sections", "Stories", "Helpers", "AnalysisResults",
                    "ObjectTypes", "Texts", "Sets"):
            try:
                s = getattr(model, srv)
                tree[f"Project.Model.{srv}"] = members(s)
                print(f"  model.{srv} : {len(tree[f'Project.Model.{srv}'])} membres")
            except Exception as exc:
                tree[f"Project.Model.{srv}"] = [f"<inaccessible: {exc}>"]
    except Exception as exc:
        tree["Project.Model"] = [f"<inaccessible: {exc}>"]
        print(f"Project.Model inaccessible : {exc}")

    # --- AnalysisResults (pour l'import des résultats, priorité spec) ---
    try:
        res = proj.Model.AnalysisResults
        tree["AnalysisResults"] = members(res)
        print(f"AnalysisResults : {len(tree['AnalysisResults'])} membres")
    except Exception as exc:
        print(f"AnalysisResults inaccessible : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    print(f"\nArbre API écrit : {OUT}")

    # Afficher les membres métier clés de Project.Model
    print("\n=== Membres Project.Model (pertinents) ===")
    for m in tree.get("Project.Model", []):
        if any(k in m for k in ("Bar", "Node", "Case", "Section", "Material",
                                "Combo", "Story", "Result", "Support",
                                "Calc", "Shell", "Wall")):
            print(f"  - {m}")


if __name__ == "__main__":
    main()
