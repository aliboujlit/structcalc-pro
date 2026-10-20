# -*- coding: utf-8 -*-
"""
extract_param_names.py — Phase 2 : extraire les noms de paramètres exacts.

Lit le module RobotOM généré par comtypes et extrait, pour les méthodes
clés, la liste des noms de paramètres (depuis les COMMethod paramflags).
Plus besoin de deviner les signatures.
"""

import os
import re
import json

GEN = (r"C:\Users\Admin\AppData\Local\Programs\Python\Python312"
       r"\Lib\site-packages\comtypes\gen\RobotOM.py")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_param_names.json")

# Méthodes à documenter (interface -> méthodes voulues)
WANT = {
    "IRobotNodeServer": ["SetLabel", "Create"],
    "IRobotBarServer": ["Create", "SetLabel"],
    "IRobotCaseServer": ["CreateSimple", "CreateCombination", "Get", "GetAll"],
    "IRobotCase": ["Records"],
    "IRobotCaseRecordsServer": ["Create", "Get", "GetAll"],
    "IRobotBarForceServer": ["Value"],
    "IRobotNodeReactionServer": ["Value"],
    "IRobotNodeDisplacementServer": ["Value"],
    "IRobotLoadRecord": [],  # toutes
    "IRobotLoadRecord2": [],
}


def extract_class_body(src, classname):
    m = re.search(rf"^class {classname}\b.*?:", src, re.M)
    if not m:
        return None
    rest = src[m.start():]
    lines = rest.splitlines()
    body = []
    for i, line in enumerate(lines):
        if i > 0 and line.startswith("class "):
            break
        body.append(line)
    return "\n".join(body)


def methods_with_params(body):
    """
    Extrait COMMethod(...) et lit les paramflags pour les noms.
    Format comtypes :
        COMMethod(dispid, restype, 'Name', [argtypes], paramflags)
    paramflags : tuple de (flags, name, default) ou (flags, name)
    """
    out = []
    # On cherche chaque COMMethod(...) bloc équilibré
    for m in re.finditer(r"COMMethod\(", body):
        start = m.start()
        # équilibrer les parenthèses
        depth = 0
        i = start
        while i < len(body):
            if body[i] == "(":
                depth += 1
            elif body[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = body[start:i + 1]
        nm = re.search(r"'([^']+)'", block)
        if not nm:
            continue
        name = nm.group(1)
        # Noms de paramètres dans paramflags : 'name' après un int
        pnames = re.findall(r"\(\s*\d+\s*,\s*'([^']+)'", block)
        out.append({"method": name, "params": pnames})
    return out


def main():
    with open(GEN, encoding="utf-8", errors="replace") as f:
        src = f.read()

    result = {}
    for iface, methods in WANT.items():
        body = extract_class_body(src, iface)
        if body is None:
            result[iface] = "<classe absente>"
            continue
        meths = methods_with_params(body)
        if methods:
            meths = [x for x in meths if x["method"] in methods]
        result[iface] = meths

    # Affichage lisible
    for iface, meths in result.items():
        print(f"\n=== {iface} ===")
        if isinstance(meths, str):
            print(f"  {meths}")
            continue
        for m in meths:
            p = ", ".join(m["params"]) if m["params"] else "(voir doc)"
            print(f"  {m['method']}({p})")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nÉcrit : {OUT}")


if __name__ == "__main__":
    main()
