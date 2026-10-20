# -*- coding: utf-8 -*-
"""
probe_cs_analize.py — Phase 2 : CreateSimple avec le 4e param 'analize'.

Le binding typé a révélé un paramètre requis 'analize'. On teste :
  CreateSimple(number, type, name, analize_bool)
et les variantes d'ordre. 'analize' = calcul automatique du cas probablement.
Projet jetable, fermé sans sauvegarde.
"""

import os
import json
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_cs_analize.json")
R = {}


def attempt(cases, args, label):
    try:
        cases.CreateSimple(*args)
        print(f"  [OK]   {label} {args}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {label} {args} -> {str(exc)[:65]}")
        return False


def main():
    comtypes.client.GetModule(TLB)
    import comtypes.gen.RobotOM as RobotOM

    app = comtypes.client.CreateObject("Robot.Application",
                                       interface=RobotOM.IRobotApplication)
    proj = app.Project
    proj.New(1)
    cases = proj.Structure.Cases

    ok = None
    # Hypothèse : (number, type, name, analize_bool)
    for ctype in (1, 2, 3, 4, 5):
        if attempt(cases, (1, ctype, "Poids propre", False), "A"):
            ok = ("num,type,name,analize", ctype)
            break
    # Variante : (number, name, type, analize)
    if not ok:
        for ctype in (1, 2, 3, 4, 5):
            if attempt(cases, (2, "Exploitation", ctype, False), "B"):
                ok = ("num,name,type,analize", ctype)
                break
    # Variante True
    if not ok:
        for ctype in (1, 2, 3):
            if attempt(cases, (1, ctype, "Poids propre", True), "A-true"):
                ok = ("num,type,name,analize=True", ctype)
                break

    try:
        cnt = int(cases.GetAll().Count)
    except Exception:
        cnt = None
    print(f"Cases.GetAll().Count = {cnt}")

    # Si un cas existe, lire son nom/type pour confirmer
    if cnt and cnt > 0:
        try:
            c1 = cases.Get(1)
            print(f"  Cas 1 : Name={getattr(c1,'Name','?')} "
                  f"Type={getattr(c1,'Type','?')} Number={getattr(c1,'Number','?')}")
            R["case1"] = {"name": str(getattr(c1, "Name", "?")),
                          "type": str(getattr(c1, "Type", "?"))}
        except Exception as exc:
            print(f"  lecture cas 1 : {str(exc)[:60]}")

    R["signature_success"] = ok
    R["cases_count"] = cnt

    proj.Close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nVerdict -> {ok}")


if __name__ == "__main__":
    main()
