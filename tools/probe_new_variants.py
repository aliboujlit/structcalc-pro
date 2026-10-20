# -*- coding: utf-8 -*-
"""
probe_new_variants.py — Phase 0 : résolution empirique de l'ouverture de projet.

Le call proj.New() échoue ("nombre de paramètres non valide"). On teste ici,
de façon contrôlée, les variantes documentées/plausibles de l'API Robot,
ainsi que la question : un projet est-il créé automatiquement à la connexion ?

Chaque variante est indépendante (try/except) pour isoler celle qui fonctionne.
Aucun fichier n'est enregistré sur disque.
"""

import os
import json
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_new_variants.json")

report = {}


def nature_of(obj, name):
    info = {
        "python_type": type(obj).__name__,
        "module": type(obj).__module__,
    }
    try:
        info["has_methods_"] = hasattr(obj, "_methods_")
    except Exception:
        pass
    return info


def try_variant(label, fn):
    """Exécute une variante, capture succès/échec."""
    try:
        r = fn()
        report[label] = {"ok": True, "result": repr(r)[:200]}
        print(f"  [OK]   {label}  -> {repr(r)[:80]}")
        return True
    except Exception as exc:
        report[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(f"  [FAIL] {label}  -> {type(exc).__name__}: {str(exc)[:90]}")
        return False


def main():
    print("Chargement RobotOM...")
    comtypes.client.GetModule(TLB)
    import comtypes.gen.RobotOM as RobotOM

    # 1) Nature de quelques symboles clés
    print("\n=== Nature des symboles RobotOM ===")
    for sym in ("IRobotProject", "RobotProject", "IRobotApplication"):
        obj = getattr(RobotOM, sym, None)
        if obj is None:
            print(f"  {sym}: absent")
            continue
        info = nature_of(obj, sym)
        print(f"  {sym}: {info['python_type']} (module={info['module']}, "
              f"_methods_={info.get('has_methods_')})")
        report[f"symbol_{sym}"] = info

    # 2) Connexion
    print("\n=== Connexion Robot ===")
    app = comtypes.client.CreateObject("Robot.Application", dynamic=True)
    proj = app.Project
    print(f"  Version: {app.ProgramVersion}")
    report["program_version"] = str(app.ProgramVersion)
    report["is_active_initial"] = int(proj.IsActive)

    # 3) Un projet est-il déjà là ? (Robot peut en ouvrir un par défaut)
    print("\n=== Projet initial ===")
    try_variant("initial_active_model", lambda: proj.ActiveModel)
    print(f"  Project.IsActive initial = {proj.IsActive}")

    # 4) Variantes d'ouverture de projet
    print("\n=== Variantes Project.New ===")
    try_variant("New_0args", lambda: proj.New())
    try_variant("New_1arg_0", lambda: proj.New(0))
    try_variant("New_1arg_1", lambda: proj.New(1))
    try_variant("NewFromTemplate_empty", lambda: proj.NewFromTemplate(""))
    try_variant("NewFromTemplate_none", lambda: proj.NewFromTemplate(None))

    # Re-vérifier l'accès au modèle après chaque tentative réussie
    print("\n=== État après tentatives ===")
    report["is_active_final"] = int(proj.IsActive)
    print(f"  Project.IsActive final = {proj.IsActive}")
    if proj.IsActive:
        try_variant("final_active_model", lambda: proj.ActiveModel)
        try:
            model = proj.ActiveModel
            print(f"  ActiveModel.Bars.Count = {model.Bars.Count}")
            print(f"  ActiveModel.Nodes.Count = {model.Nodes.Count}")
            report["bars_count"] = int(model.Bars.Count)
            report["nodes_count"] = int(model.Nodes.Count)
        except Exception as exc:
            print(f"  lecture modèle échec : {exc}")

    # 5) Fermeture sans sauvegarde
    try:
        proj.Close(False)
        print("\n  Projet fermé sans sauvegarde.")
    except Exception as exc:
        print(f"\n  Fermeture : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nRapport : {OUT}")

    # Résumé des variantes fonctionnelles
    ok = [k for k, v in report.items()
          if isinstance(v, dict) and v.get("ok")]
    print(f"\n>>> Variantes fonctionnelles : {ok if ok else 'AUCUNE'}")


if __name__ == "__main__":
    main()
