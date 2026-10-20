# -*- coding: utf-8 -*-
"""
probe_createsimple_typed.py — Phase 2 : signature exacte CreateSimple (binding typé).

Le binding dynamique coerce mal les paramètres. On utilise ici le module
comtypes généré (RobotOM) qui connaît les vrais types. On lit aussi la
définition _methods_ de IRobotCaseServer pour extraire la signature exacte.
"""

import os
import json
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_createsimple_typed.json")
R = {}


def dump_methods(iface):
    """Liste les méthodes COM d'une interface comtypes (nom + argtypes)."""
    out = []
    for m in getattr(iface, "_methods_", []):
        try:
            name = m[2]
            argtypes = [str(a) for a in m[3]]
            out.append({"name": name, "argtypes": argtypes})
        except Exception:
            pass
    return out


def main():
    comtypes.client.GetModule(TLB)
    import comtypes.gen.RobotOM as RobotOM

    # 1) Signature brute de IRobotCaseServer.CreateSimple
    print("=== IRobotCaseServer._methods_ (CreateSimple) ===")
    srv_methods = dump_methods(RobotOM.IRobotCaseServer)
    for m in srv_methods:
        if "Create" in m["name"] or "Combo" in m["name"]:
            print(f"  {m['name']}({', '.join(m['argtypes'])})")
    R["case_server_methods"] = srv_methods

    # 2) Enums de type de cas (IRobotCaseType)
    print("\n=== Enums IRobotCaseType ===")
    for sym in dir(RobotOM):
        if "CaseType" in sym or sym.startswith("I_CT"):
            print(f"  {sym}")
    # Chercher l'enum réel
    ct = getattr(RobotOM, "IRobotCaseType", None)
    if ct is not None:
        vals = {k: int(getattr(ct, k)) for k in dir(ct)
                if k.startswith("I_CT") or k.startswith("IR_CT")}
        print(f"  IRobotCaseType : {vals}")
        R["case_type_enum"] = vals

    # 3) Tenter CreateSimple avec le BON type via binding typé
    app = comtypes.client.CreateObject("Robot.Application",
                                       interface=RobotOM.IRobotApplication)
    proj = app.Project
    proj.New(1)
    S = proj.Structure
    cases = S.Cases
    print(f"\nCases (typed) = {type(cases).__name__}")

    # Test avec différents types (1 = mort probablement)
    for ctype in (1, 2, 3, 4):
        try:
            r = cases.CreateSimple(1, ctype, "Cas test")
            print(f"  CreateSimple(1, {ctype}, 'Cas test') OK -> {repr(r)[:40]}")
            R["create_simple_success"] = {"number": 1, "type": ctype,
                                          "name": "Cas test"}
            break
        except Exception as exc:
            print(f"  CreateSimple(1, {ctype}, 'Cas test') : {str(exc)[:70]}")

    try:
        R["cases_count"] = int(cases.GetAll().Count)
        print(f"  Cases.GetAll().Count = {R['cases_count']}")
    except Exception as exc:
        print(f"  count : {exc}")

    proj.Close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nRapport : {OUT}")


if __name__ == "__main__":
    main()
