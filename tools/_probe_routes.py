# -*- coding: utf-8 -*-
"""Sonde lecture seule : matrice de routes du hub (aucun COM, aucun lancement)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structcalc.integration.interop import default_hub

hub = default_hub()
routes = hub.routes()

print("=== ROUTES ROUGES (non faissables) ===")
for src, row in routes.items():
    for tgt, info in row.items():
        if info.get("feasible"):
            continue
        miss = ",".join(info.get("missing") or []) or "-"
        reason = info.get("reason", "")
        print(f"ROUGE {src:11s} -> {tgt:11s} | {reason} | {miss}")

print()
print("=== ROUTES VERT (faissables) ===")
for src, row in routes.items():
    for tgt, info in row.items():
        if info.get("feasible"):
            print(f"VERT  {src:11s} -> {tgt:11s} | {info.get('reason','')}")
