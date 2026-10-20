# -*- coding: utf-8 -*-
"""
probe_structure_final.py — Phase 0 : validation finale + cartographie serveurs.

Corrections issues du SDK officiel Autodesk (Robot.cs) :
  - comptage : Structure.Bars.GetAll().Count  (PAS .Count sur le serveur)
  - sections/materiaux : via Structure.Labels.GetAvailableNames(I_LT_*)
  - cas de charges : Structure.Cases.GetAll()
  - resultats : Structure.Results.Nodes.Reactions/Displacements.Value(n,case)

Teste la creation 2 noeuds + 1 barre, la relecture, le comptage correct,
et cartographie les membres reels des serveurs. Fermeture sans sauvegarde.
"""

import os
import json
import win32com.client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_structure_final.json")
R = {}


def public_members(obj, limit=200):
    try:
        return sorted(m for m in dir(obj) if not m.startswith("_"))[:limit]
    except Exception as exc:
        return [f"<err:{exc}>"]


def main():
    print("=" * 60)
    print("STRUCTCALC PRO - Phase 0 : validation finale Robot")
    print("=" * 60)

    app = win32com.client.Dispatch("Robot.Application")
    proj = app.Project
    proj.New(1)   # I_PT_FRAME_2D
    print(f"[1] Connecte Robot {app.ProgramVersion}, projet 2D ouvert "
          f"(IsActive={proj.IsActive})")

    S = proj.Structure

    # Cartographie des membres reels des serveurs cles
    print("\n[2] Cartographie des serveurs Structure.*")
    carto = {}
    for name in ("Nodes", "Bars", "Cases", "Labels", "Selections", "Results"):
        try:
            srv = getattr(S, name)
            carto[name] = public_members(srv)
            print(f"    {name:<12}: {len(carto[name])} membres")
        except Exception as exc:
            carto[name] = [f"<inaccessible:{exc}>"]
            print(f"    {name:<12}: INACCESSIBLE")
    # Compter via GetAll().Count (motif SDK)
    print(f"    -> membres Bars : {carto.get('Bars')}")
    print(f"    -> membres Nodes : {carto.get('Nodes')}")
    print(f"    -> membres Cases : {carto.get('Cases')}")
    R["server_members"] = carto

    # Creation 2 noeuds + 1 barre
    nodes, bars = S.Nodes, S.Bars
    print("\n[3] Creation poutre test (2 noeuds, 1 barre)...")
    nodes.Create(1, 0.0, 0.0, 0.0)
    nodes.Create(2, 4.0, 0.0, 0.0)
    bars.Create(1, 1, 2)

    # Comptage correct via GetAll().Count
    try:
        nb_nodes = nodes.GetAll().Count
        nb_bars = bars.GetAll().Count
    except Exception:
        # fallback : item-max
        nb_nodes, nb_bars = None, None
    print(f"    Nodes.GetAll().Count = {nb_nodes} (attendu 2)")
    print(f"    Bars.GetAll().Count  = {nb_bars} (attendu 1)")
    R["nodes_count"] = int(nb_nodes) if nb_nodes is not None else None
    R["bars_count"] = int(nb_bars) if nb_bars is not None else None

    # Relecture nœud + barre (SDK : Get(id), PAS Item(id))
    n1 = nodes.Get(1)
    b1 = bars.Get(1)
    print(f"\n[4] Relecture :")
    print(f"    Noeud 1  : X={n1.X} Y={n1.Y} Z={n1.Z}")
    print(f"    Barre 1  : Start={b1.StartNode} End={b1.EndNode}")
    R["node1"] = {"x": float(n1.X), "y": float(n1.Y), "z": float(n1.Z)}
    R["bar1"] = {"start": int(b1.StartNode), "end": int(b1.EndNode)}

    # Contrôles de cohérence
    checks = {
        "2_noeuds": nb_nodes == 2,
        "1_barre": nb_bars == 1,
        "barre_connectee": int(b1.StartNode) == 1 and int(b1.EndNode) == 2,
        "noeud1_origine": abs(n1.X) < 1e-9 and abs(n1.Y) < 1e-9,
    }
    print(f"\n[5] Controles : {checks}")
    R["checks"] = checks
    R["success"] = all(checks.values())
    print(f"    -> {'VALIDE' if R['success'] else 'ECHEC'}")

    # Sections disponibles (mapping futur) via Labels
    try:
        from win32com.client import constants
        # I_LT_BAR_SECTION : valeur selon TypeLib ; on tente les plus courantes
        for val in (21, 1, 3, 5):
            try:
                names = S.Labels.GetAvailableNames(val)
                if names and names.Count > 0:
                    print(f"\n[6] Sections (type {val}) : {names.Count} dispo")
                    R["sections_type_used"] = val
                    R["sections_count"] = int(names.Count)
                    break
            except Exception:
                continue
    except Exception as exc:
        print(f"\n[6] Labels sections : {exc}")

    # Cas de charges
    try:
        cases = S.Cases.GetAll()
        print(f"[7] Cas de charges existants : {cases.Count}")
        R["cases_count"] = int(cases.Count)
    except Exception as exc:
        print(f"[7] Cases : {exc}")
        R["cases_error"] = str(exc)[:150]

    # Fermeture sans sauvegarde
    try:
        proj.Close()
        print("\n[8] Projet ferme SANS sauvegarde. Aucun fichier touche.")
        R["closed_cleanly"] = True
    except Exception as exc:
        print(f"\n[8] Fermeture : {exc}")
        R["closed_cleanly"] = False

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nRapport : {OUT}")
    return 0 if R.get("success") else 1


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
