# -*- coding: utf-8 -*-
"""
probe_robot_early.py — Phase 0 : test avec binding anticipé (comtypes généré).

Hypothèse à vérifier : ActiveModel n'est accessible qu'après ouverture
d'un projet (Project.New() ou Project.Open()). Utilise le module RobotOM
généré par comtypes pour un dispatch typé.

Opération démonstrée : créer un projet vierge, lire le serveur Bars.
N'enregistre AUCUN fichier sur disque.
"""

import os
import json
import comtypes.client
import comtypes

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_early_result.json")

result = {"steps": [], "success": False, "error": None}


def log(msg):
    print(msg)
    result["steps"].append(str(msg))


def main():
    log("Chargement du TypeLib RobotOM (binding anticipé)...")
    RobotOM = comtypes.client.GetModule(TLB)
    log(f"Module RobotOM chargé : {RobotOM}")

    log("Instanciation Robot.Application (typed dispatch)...")
    app = comtypes.client.CreateObject("Robot.Application",
                                       dynamic=True)
    log(f"Robot {app.ProgramVersion} connecté")

    proj = app.Project
    log(f"Project.IsActive avant = {proj.IsActive}")

    # Ouvrir un projet vierge (démonstration réelle)
    log("Project.New() — création d'un projet vierge...")
    proj.New()
    log(f"Project.IsActive après  = {proj.IsActive}")
    log(f"Project.Name = {proj.Name}")

    # Accès au modèle
    log("Accès à Project.ActiveModel...")
    model = proj.ActiveModel
    bars = model.Bars
    nodes = model.Nodes
    log(f"ActiveModel OK. Bars={type(bars).__name__}, Nodes={type(nodes).__name__}")

    # Inventorier les membres utiles du serveur Bars
    bar_methods = [m for m in dir(bars) if not m.startswith("_")]
    log(f"Serveur Bars : {len(bar_methods)} membres")

    # Démonstration : créer 2 nœuds + 1 barre (poutre simple)
    log("Création de 2 nœuds (0,0,0) et (4,0,0)...")
    nodes.Create(1, 0.0, 0.0, 0.0)
    nodes.Create(2, 4.0, 0.0, 0.0)

    log("Création de la barre n°1 (nœud 1 -> nœud 2)...")
    bars.Create(1, 1, 2)

    n_bars = bars.Count
    n_nodes = nodes.Count
    log(f"Vérification : {n_nodes} nœuds, {n_bars} barre(s)")

    # Lire la barre créée
    bar1 = bars.Item(1)
    log(f"Barre 1 : start={bar1.StartNode}, end={bar1.EndNode}")

    result.update({
        "success": True,
        "robot_program_version": str(app.ProgramVersion),
        "robot_app_version": str(app.Version) if hasattr(app, "Version") else None,
        "bars_count": int(n_bars),
        "nodes_count": int(n_nodes),
        "bars_methods_sample": bar_methods[:40],
    })

    log("Démonstration RÉUSSIE : modèle minimal créé en mémoire dans Robot.")

    # Fermer le projet sans sauvegarder (ne touche à aucun fichier)
    try:
        proj.Close(False)   # False = ne pas sauvegarder
        log("Projet fermé sans sauvegarde.")
    except Exception as exc:
        log(f"Fermeture sans sauvegarde : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nRésultats : {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        result["error"] = traceback.format_exc()
        print(result["error"])
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        raise SystemExit(1)
