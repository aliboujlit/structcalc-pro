# -*- coding: utf-8 -*-
"""
probe_robot.py — Phase 0 : sonde de compatibilité Robot Structural Analysis 2027.

Ne modifie AUCUN fichier. Se contente de :
  1. Charger le TypeLib robotom.tlb
  2. Lister les coclasses / interfaces disponibles
  3. Tenter une instantiation COM de Robot.Application
  4. Lire la version réelle

Sortie : rapport texte + dictionnaire de résultats.
"""

import os
import sys
import json
import traceback

ROBOT_EXE_DIR = (r"C:\Program Files\Autodesk\Robot Structural Analysis "
                 r"Professional 2027\Exe")
ROBOTOM_TLB = os.path.join(ROBOT_EXE_DIR, "robotom.tlb")
ROBOTOM_DLL = os.path.join(ROBOT_EXE_DIR, "Interop.RobotOM.dll")

results = {
    "tlb_exists": os.path.isfile(ROBOTOM_TLB),
    "dll_exists": os.path.isfile(ROBOTOM_DLL),
    "tlb_path": ROBOTOM_TLB,
    "coclasses": [],
    "interfaces": [],
    "dispatch_success": False,
    "version": None,
    "error": None,
}


def step1_load_tlb():
    """Charger le TypeLib via comtypes et inventorier les types."""
    import comtypes
    import comtypes.client

    print(f"[1] Chargement du TypeLib : {ROBOTOM_TLB}")
    # Regenerate le module Python depuis le tlb (écrit dans un cache)
    tlb = comtypes.client.GetModule(ROBOTOM_TLB)
    print(f"    -> module généré : {tlb}")

    # Inventorier les coclasses exposées
    import comtypes.typeinfo as ti
    ti_lib = ti.GetTypeAttrOfTypelibEx if hasattr(ti, "GetTypeAttrOfTypelibEx") else None

    # Explorer via les symboles du module généré
    coclasses = []
    interfaces = []
    for name in dir(tlb):
        obj = getattr(tlb, name)
        kind = type(obj).__name__
        # Les coclasses généré par comtypes sont des classes avec _reg_clsid_
        if hasattr(obj, "_reg_clsid_"):
            coclasses.append(str(name))
        elif hasattr(obj, "_com_interface_"):
            interfaces.append(str(name))

    results["coclasses"] = sorted(set(coclasses))
    results["interfaces"] = sorted(set(interfaces))
    print(f"    -> {len(coclasses)} coclasses, {len(interfaces)} interfaces")
    return tlb


def step2_dispatch():
    """Tenter une instantiation COM réelle de Robot.Application."""
    import win32com.client

    print("[2] Tentative d'instanciation COM (peut lancer Robot)...")
    app = None
    progids = ["Robot.Application", "Robot.Application.27", "Robot.Application.26"]

    last_err = None
    for pid in progids:
        try:
            app = win32com.client.Dispatch(pid)
            results["dispatch_prog_id"] = pid
            print(f"    -> Dispatch('{pid}') RÉUSSI")
            break
        except Exception as exc:
            last_err = exc
            print(f"    -> Dispatch('{pid}') échec : {exc}")

    if app is None:
        results["error"] = f"Dispatch impossible : {last_err}"
        return None

    # Lire des propriétés basiques
    try:
        results["version"] = str(app.Version) if hasattr(app, "Version") else None
        print(f"    -> Version : {results['version']}")
    except Exception as exc:
        print(f"    -> Version illisible : {exc}")

    # Inventorier les propriétés/methodes de premier niveau
    try:
        public = [m for m in dir(app) if not m.startswith("_")]
        results["app_members"] = public[:60]
        print(f"    -> {len(public)} membres publics sur l'objet Application")
        print(f"       Exemples : {public[:15]}")
    except Exception as exc:
        print(f"    -> Membres illisibles : {exc}")

    results["dispatch_success"] = True
    return app


def step3_probe_project(app):
    """Explorer l'objet Project et Model (cœur de l'API)."""
    print("[3] Exploration Project / Model...")
    for attr in ("Project", "Script"):
        try:
            sub = getattr(app, attr)
            members = [m for m in dir(sub) if not m.startswith("_")]
            results[f"members_{attr.lower()}"] = members[:40]
            print(f"    -> app.{attr} : {len(members)} membres")
            print(f"       {members[:20]}")
        except Exception as exc:
            print(f"    -> app.{attr} inaccessible : {exc}")


def main():
    print("=" * 64)
    print("SONDE COMPATIBILITE ROBOT STRUCTURAL ANALYSIS 2027")
    print("=" * 64)

    if not results["tlb_exists"]:
        results["error"] = "robotom.tlb introuvable"
        print("ERREUR : tlb introuvable")
        return 2

    tlb = None
    try:
        tlb = step1_load_tlb()
    except Exception:
        results["error"] = "Chargement TypeLib échoué :\n" + traceback.format_exc()
        print(results["error"])
        return 1

    app = None
    try:
        app = step2_dispatch()
    except Exception:
        print("ERREUR dispatch :\n" + traceback.format_exc())

    if app is not None:
        try:
            step3_probe_project(app)
        except Exception:
            print("ERREUR exploration :\n" + traceback.format_exc())

    print("=" * 64)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "robot_probe_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Résultats écrits : {out_path}")

    # Fermeture si on a lancé nous-mêmes l'application
    if app is not None:
        try:
            if results.get("dispatch_prog_id"):
                # Ne ferme QUE si Robot n'était pas déjà ouvert avant
                pass
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
