# -*- coding: utf-8 -*-
"""
probe_cs_minimal.py — Phase 2 : test décisif CreateSimple (binding typé, minimal).

Teste les deux ordres d'arguments plausibles avec le binding typé comtypes :
  A) CreateSimple(number, case_type_int, name_str)
  B) CreateSimple(number, name_str, case_type_int)

N'imprime que le verdict. Projet jetable, fermé sans sauvegarde.
"""

import os
import json
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_cs_minimal.json")
R = {}


def try_order(cases, label, args):
    try:
        cases.CreateSimple(*args)
        print(f"  [OK]   {label} {args}")
        return True
    except Exception as exc:
        msg = str(exc)[:70]
        print(f"  [FAIL] {label} {args} -> {msg}")
        return False


def main():
    comtypes.client.GetModule(TLB)
    import comtypes.gen.RobotOM as RobotOM

    app = comtypes.client.CreateObject("Robot.Application",
                                       interface=RobotOM.IRobotApplication)
    proj = app.Project
    proj.New(1)
    cases = proj.Structure.Cases

    print("Ordre A : (num, type_int, nom)")
    okA = None
    for ctype in (1, 2, 3, 4, 5):
        if try_order(cases, "A", (1, ctype, "PP")):
            okA = ("A", ctype)
            break

    print("Ordre B : (num, nom, type_int)")
    okB = None
    for ctype in (1, 2, 3, 4, 5):
        if try_order(cases, "B", (2, "Exploitation", ctype)):
            okB = ("B", ctype)
            break

    try:
        cnt = int(cases.GetAll().Count)
    except Exception:
        cnt = None
    print(f"Cases.GetAll().Count = {cnt}")

    R["order_A_success"] = okA
    R["order_B_success"] = okB
    R["cases_count"] = cnt

    proj.Close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nVerdict -> A={okA}  B={okB}")


if __name__ == "__main__":
    main()
