# -*- coding: utf-8 -*-
"""
tools/verify_interop_hub.py — Vérifie l'architecture d'interconnexion
RÉCIPROQUE Autodesk (hub en étoile par pivot SC-*).

Montre, SANS lancer aucun logiciel :
  1. inventaire honnête des connecteurs (installé / transport / pilotable) ;
  2. matrice des routes A -> pivot -> B (avec motifs si non faisables) ;
  3. paires RÉCIPROQUES (A<->B dans les deux sens) ;
  4. refus explicite Revit (aucun COM modèle), objets Civil 3D, et
     géométrie Navisworks (COM limité à OpenFile/SaveAs).

Usage : python tools/verify_interop_hub.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structcalc.integration.interop import default_hub  # noqa: E402


def main() -> int:
    hub = default_hub()

    print("=" * 72)
    print("HUB INTEROP AUTODESK — architecture en étoile par pivot SC-*")
    print("=" * 72)

    print("\n[1] INVENTAIRE HONNÊTE (registre, aucun logiciel lancé)")
    for name, info in hub.status().items():
        flag = "OK  " if info["automatable"] else "----"
        ver = info["version"] or "?"
        print(f"    [{flag}] {info['label']} ({ver}) "
              f"transport={info['transport']} "
              f"installe={info['installed']} "
              f"pilotable={info['automatable']}")
        if info["usable_capabilities"]:
            print(f"           utiles : "
                  f"{', '.join(info['usable_capabilities'])}")
        blocked = {k: v for k, v in info["blocked_capabilities"].items()
                   if v not in ("SUPPORTED", "PARTIAL")}
        for cap, st in blocked.items():
            print(f"           bloque : {cap}={st}")

    print("\n[2] MATRICE DES ROUTES (A -> pivot -> B)")
    matrix = hub.routes()
    for s, row in matrix.items():
        for t, info in row.items():
            if s == t:
                continue
            mark = "OK " if info["feasible"] else "NON"
            line = f"    [{mark}] {s:8} -> {t:8} : {info['reason']}"
            if info["missing"]:
                line += " | " + ", ".join(info["missing"])
            print(line)

    print("\n[3] PAIRES RÉCIPROQUES (échange dans les deux sens)")
    pairs = hub.reciprocal_pairs()
    for a, b in pairs:
        print(f"    {a} <==> {b}")
    if not pairs:
        print("    (aucune)")

    print("\n[4] REFUS EXPLICITES (§19 : jamais de faux succès)")
    from structcalc.integration.interop import RevitConnector, \
        Civil3DConnector, NavisworksConnector
    rev = RevitConnector()
    print(f"    revit.read_model  -> {rev.read_model(None).status}")
    print(f"      motif : {rev.read_model(None).message}")
    print(f"    revit.write_model -> {rev.write_model(None).status}")
    c3d = Civil3DConnector()
    print(f"    civil3d.read_civil_objects -> "
          f"{c3d.read_civil_objects().status}")
    print(f"      motif : {c3d.read_civil_objects().message}")
    nw = NavisworksConnector()
    print(f"    navisworks.read_model  -> {nw.read_model(None).status}")
    print(f"      motif : {nw.read_model(None).message}")
    print(f"    navisworks.write_model -> {nw.write_model(None).status}")

    print("\n" + "=" * 72)
    print(f"SYNTHÈSE :\n{hub.summary()}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
