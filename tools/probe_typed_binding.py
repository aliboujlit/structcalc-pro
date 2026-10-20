# -*- coding: utf-8 -*-
"""
probe_typed_binding.py — Phase 0 : accès au modèle via binding anticipé typé.

Le binding dynamique (win32com) ne résout pas proj.Model. On instancie ici
Robot via comtypes avec l'interface IRobotApplication explicite, ce qui
résout les propriétés via le TypeLib. Puis New(1) + tentative Model/Bars.

Fermeture sans sauvegarde.
"""

import os
import json
import comtypes.client
import comtypes

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_typed_binding.json")
R = {}


def main():
    print("Chargement RobotOM (typed)...")
    RobotOM = comtypes.client.GetModule(TLB)

    print("Instanciation via IRobotApplication (interface typée)...")
    app = comtypes.client.CreateObject(
        "Robot.Application", interface=RobotOM.IRobotApplication)
    print(f"  app = {type(app).__name__}")

    proj = app.Project
    print(f"  proj = {type(proj).__name__}")
    R["proj_type"] = type(proj).__name__

    # Lister les membres exposés par le wrapper typé
    mem = [m for m in dir(proj) if not m.startswith("_")]
    print(f"  proj membres ({len(mem)}): {mem}")
    R["proj_members"] = mem

    print("Project.New(1)...")
    proj.New(1)
    print(f"  IsActive = {proj.IsActive}")
    R["is_active"] = int(proj.IsActive)

    # Tenter Model (peut résoudre en binding typé)
    model = None
    for attr in ("Model", "ActiveModel"):
        try:
            model = getattr(proj, attr)
            print(f"  proj.{attr} -> {type(model).__name__} = {repr(model)[:80]}")
            R[f"{attr}_type"] = type(model).__name__
            # Si c'est un objet serveur, on le garde
            if hasattr(model, "Bars") or hasattr(model, "Nodes"):
                R["model_accessor"] = attr
                break
        except Exception as exc:
            print(f"  proj.{attr} échec : {type(exc).__name__}: {exc}")
            R[f"{attr}_error"] = str(exc)[:200]

    # Inventorier les membres du modèle si obtenu
    if model is not None and hasattr(model, "Bars"):
        mmem = [m for m in dir(model) if not m.startswith("_")]
        print(f"  model membres ({len(mmem)}): {mmem[:40]}")
        R["model_members"] = mmem
        try:
            nodes, bars = model.Nodes, model.Bars
            nodes.Create(1, 0.0, 0.0, 0.0)
            nodes.Create(2, 4.0, 0.0, 0.0)
            bars.Create(1, 1, 2)
            print(f"  Nodes={nodes.Count}, Bars={bars.Count}")
            R["nodes"] = int(nodes.Count)
            R["bars"] = int(bars.Count)
            R["success"] = True
            print(">>> OPÉRATION RÉELLE RÉUSSIE (binding typé).")
        except Exception as exc:
            print(f"  création échec : {exc}")
            R["create_error"] = str(exc)[:200]

    try:
        proj.Close()
        print("Projet fermé sans sauvegarde.")
    except Exception as exc:
        print(f"Fermeture : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"Rapport : {OUT}")


if __name__ == "__main__":
    main()
