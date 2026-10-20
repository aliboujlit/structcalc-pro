# -*- coding: utf-8 -*-
"""
tools/probe_units_live.py — PROBE LIVE des UNITÉS Robot (spec §5.3).

Découverte statique (robotom.tlb) :
  - IRobotUnitType : I_UT_FORCE=7, I_UT_MOMENT=8, I_UT_DISPLACEMENT=10, ...
  - IRobotProjectPreferences.Units -> gestionnaire d'unités
  - IRobotUnitEditionServer.Get/Set -> IRobotUnitEditionData (.Unit/.Coefficient/.Type)

Ce probe, en lançant Robot, PRÉUVE par lecture :
  1. l'accès aux unités courantes (Preferences.Units) ;
  2. la lecture effective de la FORCE / MOMENT / DÉPLACEMENT / LONGUEUR ;
  3. la forme de `.Unit` (chaîne ou entier) et `.Coefficient`.

Read-only : ne modifie AUCUNE unité Robot (pas de .Set).

Usage : python tools/probe_units_live.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from structcalc.integration.robot.connection import RobotConnection  # noqa: E402


def _describe(obj):
    """Décrit un objet IDispatch : propriétés lisibles communes."""
    out = {}
    for attr in ("Unit", "Coefficient", "Type", "Name"):
        try:
            out[attr] = getattr(obj, attr)
        except Exception:
            pass
    return out


def main() -> int:
    rc = RobotConnection(visible=True)
    rc.connect(timeout=90)
    print("[1] connecté")
    rc.new_project()
    print("[2] projet vierge")

    # -- accès au gestionnaire d'unités via les préférences du projet
    prefs = rc.project.Preferences
    print(f"[3] Preferences = {type(prefs)}")
    units = prefs.Units
    print(f"[4] Preferences.Units = {units}")

    # le gestionnaire peut être IRobotUnitMngr (→ .UnitEdition) ou directement
    # le serveur d'édition (→ .Get). On tente les deux, sans deviner.
    server = units
    try:
        server.Get  # noqa: B018  (vérifie la présence de Get)
        print("[5] Preferences.Units a .Get -> utilisé directement")
    except Exception:
        try:
            server = units.UnitEdition
            print("[5] descendu via .UnitEdition")
        except Exception as exc:
            print(f"[5] accès au serveur d'unités impossible : {exc}")
            server = None

    # -- lire Count
    if server is not None:
        try:
            cnt = server.Count()
            print(f"[6] server.Count() = {cnt}")
        except Exception as exc:
            print(f"[6] Count() a échoué : {exc}")

        # -- lire les unités FORCE(7), MOMENT(8), DISPLACEMENT(10),
        #    STRUCTURE_DIMENSION(1) via Get(type)
        for label, utype in [("FORCE", 7), ("MOMENT", 8),
                             ("DISPLACEMENT", 10), ("LENGTH", 1),
                             ("STRESS", 9)]:
            try:
                data = server.Get(utype)
                info = _describe(data)
                print(f"[7] Get({utype}={label}) -> {info}")
            except Exception as exc:
                print(f"[7] Get({utype}={label}) a échoué : {exc}")

    rc.close_project(save=False)
    print("projet fermé (sans sauvegarde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
