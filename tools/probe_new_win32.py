# -*- coding: utf-8 -*-
"""
probe_new_win32.py — Phase 0 : résolution de Project.New via win32com.

win32com.client.Dispatch('Robot.Application') est PROUVÉ fonctionnel
(premier sondage). comtypes.CreateObject échouait. On teste ici les
variantes New() avec win32com. Aucun fichier enregistré.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_new_win32.json")
report = {}


def try_variant(label, fn):
    try:
        r = fn()
        report[label] = {"ok": True, "result": repr(r)[:150]}
        print(f"  [OK]   {label} -> {repr(r)[:70]}")
        return True
    except Exception as exc:
        report[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:250]}
        print(f"  [FAIL] {label} -> {type(exc).__name__}: {str(exc)[:80]}")
        return False


def main():
    print("Connexion win32com...")
    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    print(f"Robot {app.ProgramVersion}, IsActive={proj.IsActive}")
    report["program_version"] = str(app.ProgramVersion)
    report["is_active_initial"] = int(proj.IsActive)

    # Robot ouvre-t-il un projet par défaut ?
    try_variant("initial_active_model", lambda: proj.ActiveModel)

    print("\n=== Variantes New ===")
    try_variant("New_0args", lambda: proj.New())
    try_variant("New_1arg_0", lambda: proj.New(0))
    try_variant("New_1arg_1", lambda: proj.New(1))
    try_variant("New_1arg_2", lambda: proj.New(2))
    try_variant("NewFromTemplate_empty", lambda: proj.NewFromTemplate(""))
    try_variant("NewFromTemplate_space", lambda: proj.NewFromTemplate(" "))

    print(f"\n=== État final : IsActive={proj.IsActive} ===")
    report["is_active_final"] = int(proj.IsActive)
    if proj.IsActive:
        try:
            model = proj.ActiveModel
            print(f"  ActiveModel accessible ! Bars={model.Bars.Count}, "
                  f"Nodes={model.Nodes.Count}")
            report["bars"] = int(model.Bars.Count)
            report["nodes"] = int(model.Nodes.Count)
        except Exception as exc:
            print(f"  ActiveModel échec : {exc}")

    # Fermer sans sauvegarder
    try:
        proj.Close(False)
        print("  Projet fermé sans sauvegarde.")
    except Exception as exc:
        print(f"  Fermeture : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nRapport : {OUT}")
    ok = [k for k, v in report.items() if isinstance(v, dict) and v.get("ok")]
    print(f">>> Variantes OK : {ok if ok else 'AUCUNE'}")


if __name__ == "__main__":
    main()
