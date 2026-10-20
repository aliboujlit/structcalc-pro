# -*- coding: utf-8 -*-
"""
extract_robot_signature.py — Phase 0 : extraction propre de la signature IRobotProject.

Lit le module généré comtypes et extrait la liste des méthodes COM de
IRobotProject (nom + nombre de paramètres) pour documenter l'appel exact
de Project.New. Aucune instanciation Robot, aucune modification.
"""

import os
import re
import json

GEN = (r"C:\Users\Admin\AppData\Local\Programs\Python\Python312"
       r"\Lib\site-packages\comtypes\gen\RobotOM.py")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_project_api.json")


def extract_class_methods(src: str, classname: str) -> list[dict]:
    """
    Extrait les appels COM d'une classe donnée.
    Cherche : class <classname>(...): puis les COMMethod(...) qui suivent,
    jusqu'à la prochaine 'class ' de même indentation.
    """
    # Trouver le début de la classe
    pat = re.compile(rf"^class {re.escapeclassname(classname) if False else classname}"
                     r"\b.*?:", re.M)
    m = pat.search(src)
    if not m:
        return []
    start = m.start()
    # Fin = prochaine définition de classe au même niveau (colonne 0)
    rest = src[start:]
    lines = rest.splitlines()
    body = []
    for i, line in enumerate(lines):
        if i > 0 and line.startswith("class "):
            break
        body.append(line)
    body_txt = "\n".join(body)

    # Méthodes COM : COMMethod(dispid, restype, name, argtypes, paramflags)
    methods = []
    for cm in re.finditer(
        r"COMMethod\(\s*([-\wx]+)\s*,\s*([\w\.]+)\s*,\s*'([^']+)'\s*,\s*(\[[^\]]*\])",
        body_txt):
        dispid, restype, name, args = cm.groups()
        # Compter les arguments (séparés par virgule au niveau racine)
        inner = args.strip()[1:-1].strip()
        if not inner:
            nargs = 0
        else:
            nargs = inner.count(",") + 1
        methods.append({"name": name, "nargs": nargs, "dispid": dispid,
                        "restype": restype})
    return methods


def main():
    with open(GEN, encoding="utf-8", errors="replace") as f:
        src = f.read()

    out = {}
    for cls in ("IRobotProject", "IRobotBarServer", "IRobotNodeServer",
                "IRobotCaseServer", "IRobotAnalysisResults",
                "IRobotApplication"):
        methods = extract_class_methods(src, cls)
        out[cls] = methods
        print(f"\n=== {cls} : {len(methods)} méthodes COM ===")
        # Afficher les plus pertinentes
        wanted = ("New", "NewFromTemplate", "Open", "Save", "Close",
                  "IsActive", "ActiveModel", "Create", "Count", "Item",
                  "Name", "FileName")
        for mth in methods:
            if any(w.lower() in mth["name"].lower() for w in wanted):
                print(f"    {mth['name']:<28} nargs={mth['nargs']}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nÉcrit : {OUT}")


if __name__ == "__main__":
    main()
