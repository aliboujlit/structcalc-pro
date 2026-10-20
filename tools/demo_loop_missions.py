# -*- coding: utf-8 -*-
"""
tools/demo_loop_missions.py — Demonstration BOUCLE + MISSIONS (sans GUI).

Montre, pour l'exemple utilisateur (Revit conception + Robot etude) :
  1) le plan de boucle fermee avec les missions de chaque maillon ;
  2) l'execution honnete des lignes (transport + missions) SANS ouvrir
     aucun logiciel (connect=False) : chaque refus porte son motif.

Usage : python tools/demo_loop_missions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structcalc.integration.interop.loop import (  # noqa: E402
    Selection, ROLE_CONCEPTION, ROLE_ETUDE, plan_loop, describe_plan,
    exchange_plan,
)


def main() -> int:
    plan = plan_loop([
        Selection("revit", ROLE_CONCEPTION),
        Selection("robot", ROLE_ETUDE),
    ])
    print(describe_plan(plan))
    print()
    print("=== Execution honnete : AUCUN logiciel ouvert (connect=False) ===")
    for r in exchange_plan(plan, None, connect=False):
        etat = "OK  " if r["success"] else "REFUS"
        action = r.get("action", "")
        print(f"[{etat}] {r['source']} -> {r['target']} | {action}")
        msg = r["message"]
        print(f"       {msg[:150]}")
    print()
    print("Les refus ci-dessus sont ATTENDUS : aucun logiciel ouvert.")
    print("Avec les logiciels ouverts (bouton « Lancer la boucle »),")
    print("chaque maillon accomplit alors sa mission propre.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
