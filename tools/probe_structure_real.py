# -*- coding: utf-8 -*-
"""
probe_structure_real.py — Phase 0 : PREMIÈRE OPÉRATION RÉELLE VALIDÉE.

Chemin d'accès confirmé par le SDK officiel Autodesk (Robot.cs / Class1.cs) :
    app.Project.Structure.{Nodes,Bars,Cases,Results,Labels,Selections}
    app.Project.CalcEngine.Calculate()

Démonstration contrôlée et reproductible :
  1. Connexion + New(1)                      [projet 2D]
  2. Créer 2 nœuds + 1 barre                 [Structure.Nodes / Bars]
  3. Lire back nœuds + barre                 [vérification du transfert]
  4. Lister sections/blocs disponibles       [Labels.GetAvailableNames]
  5. Fermer SANS sauvegarde                  [Close()]

NE sauvegarde AUCUN fichier. Opération 100 % réversible.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_structure_real.json")
R = {}


def main():
    print("=" * 60)
    print("STRUCTCALC PRO — Phase 0 : démonstration opérationnelle Robot")
    print("=" * 60)

    # 1) Connexion
    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    print(f"[1] Connecté : Robot {app.ProgramVersion}")

    # 2) Nouveau projet 2D (I_PT_FRAME_2D = 1)
    proj.New(1)
    print(f"[2] Project.New(1) -> IsActive = {proj.IsActive}")

    # 3) Serveur de modèle = Project.Structure
    S = proj.Structure
    print(f"[3] proj.Structure = {type(S).__name__}")
    R["structure_type"] = type(S).__name__

    # Inventorier les serveurs d'objets réellement disponibles
    srvs = {}
    for name in ("Nodes", "Bars", "Cases", "Combos", "Materials",
                 "Sections", "Labels", "Selections", "Results", "Stories"):
        try:
            s = getattr(S, name)
            srvs[name] = type(s).__name__
        except Exception as exc:
            srvs[name] = f"INACCESSIBLE({exc})"
    print(f"[4] Serveurs sur Structure : {json.dumps(srvs, indent=2, ensure_ascii=False)}")
    R["servers"] = srvs

    # 5) Création 2 nœuds + 1 barre (poutre isostatique)
    nodes = S.Nodes
    bars = S.Bars
    print("[5] Création de la poutre test :")
    nodes.Create(1, 0.0, 0.0, 0.0)
    nodes.Create(2, 4.0, 0.0, 0.0)
    bars.Create(1, 1, 2)
    print(f"    Nodes.Count = {nodes.Count}  (attendu 2)")
    print(f"    Bars.Count  = {bars.Count}  (attendu 1)")
    R["nodes_created"] = int(nodes.Count)
    R["bars_created"] = int(bars.Count)

    # 6) Vérification du transfert : relecture du nœud et de la barre
    n1 = nodes.Item(1)
    b1 = bars.Item(1)
    n1_coords = (n1.X, n1.Y, n1.Z)
    print(f"[6] Relecture :")
    print(f"    Nœud 1  : X={n1.X}, Y={n1.Y}, Z={n1.Z}")
    print(f"    Barre 1 : Start={b1.StartNode}, End={b1.EndNode}")
    R["node1"] = {"x": float(n1.X), "y": float(n1.Y), "z": float(n1.Z)}
    R["bar1"] = {"start": int(b1.StartNode), "end": int(b1.EndNode)}

    # Contrôle de cohérence
    assert int(nodes.Count) == 2, "Nombre de nœuds inattendu"
    assert int(bars.Count) == 1, "Nombre de barres inattendu"
    assert int(b1.StartNode) == 1 and int(b1.EndNode) == 2, "Connexion barre fausse"
    print("[OK] Controles de coherence : TOUS OK")

    # 7) Sections / labels disponibles (pour le mapping materials/sections)
    try:
        inames = S.Labels.GetAvailableNames(21)   # 21 = I_LT_BAR_SECTION ? on tente
        print(f"[7] Sections disponibles : {inames.Count}")
        R["sections_available"] = int(inames.Count)
    except Exception as exc:
        print(f"[7] Labels sections : {exc}")
        R["labels_error"] = str(exc)[:200]

    R["success"] = True
    print("\n>>> OPERATION REELLE VALIDEE : noeuds + barre crees et lus dans Robot.")

    # 8) Fermeture sans sauvegarde
    try:
        proj.Close()
        print("[8] Projet fermé SANS sauvegarde. Aucun fichier touché.")
        R["closed_cleanly"] = True
    except Exception as exc:
        print(f"[8] Fermeture : {exc}")
        R["closed_cleanly"] = False

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nRapport : {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        R["fatal"] = traceback.format_exc()
        print(R["fatal"])
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(R, f, indent=2, ensure_ascii=False)
        raise SystemExit(1)
