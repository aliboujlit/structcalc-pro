# -*- coding: utf-8 -*-
"""
tools/probe_bar_uniform_chain_live.py — PREUVE LIVE de la chaîne COMPLÈTE de
la charge uniforme barre (spec §0, §19) — tâche « rectype ».

Chaîne de référence (implémentation qui fonctionne) :
    idx = case.Records.New(5)          # I_LRT_BAR_UNIFORM -> index
    rec = case.Records.Get(idx)
    rec.Objects.FromText("1")          # OBJETS via FromText (pas rec.Objects=)
    rec.SetValue(2, fz)                # index 2 = Fz (local z)
    rec.GetValue(2)                    # lecture de retour

Ce probe PRÉUVE, sans avoir besoin d'une barre réelle pour la valeur :
  1. Records.New(5) -> index entier ;
  2. Records.Get(index) -> record ;
  3. SetValue(2, x) + GetValue(2) round-trip (index Fz=2) ;
  4. rec.Objects a la méthode FromText (nom confirmé).

Read-only, sans sauvegarde (§5.4).

Usage : python tools/probe_bar_uniform_chain_live.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from structcalc.integration.robot.connection import RobotConnection  # noqa: E402

I_LRT_BAR_UNIFORM = 5


def main() -> int:
    rc = RobotConnection(visible=True)
    rc.connect(timeout=90)
    print("[1] connecté")
    rc.new_project()
    S = rc.structure
    S.Cases.CreateSimple(1, "G", 0, 1)
    case = S.Cases.Get(1)
    print("[2] cas 1 (G) créé")

    # 1. New(5) -> index
    try:
        idx = case.Records.New(I_LRT_BAR_UNIFORM)
        print(f"[3] Records.New({I_LRT_BAR_UNIFORM}) -> index={idx!r} "
              f"(type {type(idx).__name__})")
    except Exception as exc:
        print(f"[3] Records.New({I_LRT_BAR_UNIFORM}) a ÉCHOUÉ : {exc}")
        rc.close_project(save=False)
        return 1

    # 2. Get(index) -> record
    try:
        rec = case.Records.Get(idx)
        print(f"[4] Records.Get({idx!r}) -> {rec}")
    except Exception as exc:
        print(f"[4] Records.Get a ÉCHOUÉ : {exc}")
        rc.close_project(save=False)
        return 1

    # 3. SetValue(2, -10.0) + GetValue(2) round-trip (index Fz)
    try:
        rec.SetValue(2, -10.0)
        back = rec.GetValue(2)
        ok = abs(float(back) - (-10.0)) < 1e-9
        print(f"[5] SetValue(2,-10.0) + GetValue(2)={back} -> "
              f"{'ROUND-TRIP OK' if ok else 'ÉCART'}")
    except Exception as exc:
        print(f"[5] SetValue/GetValue a ÉCHOUÉ : {exc}")

    # 4. rec.Objects a la méthode FromText
    try:
        objs = rec.Objects
        has_fromtext = hasattr(objs, "FromText")
        print(f"[6] rec.Objects existe ; FromText présent = {has_fromtext}")
        if has_fromtext:
            try:
                objs.FromText("1")   # peut échouer (pas de barre 1) — nom confirmé
                print("[6]   FromText('1') accepté")
            except Exception as exc:
                print(f"[6]   FromText('1') erreur (NOM confirmé, cause : {exc})")
    except Exception as exc:
        print(f"[6] rec.Objects inaccessible : {exc}")

    # bonus : rec.Type = 5 ?
    try:
        print(f"[7] rec.Type = {rec.Type}")
    except Exception as exc:
        print(f"[7] rec.Type lecture a échoué : {exc}")

    rc.close_project(save=False)
    print("projet fermé (sans sauvegarde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
