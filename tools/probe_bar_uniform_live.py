# -*- coding: utf-8 -*-
"""
tools/probe_bar_uniform_live.py — PREUVE LIVE du type d'enregistrement de
charge barre uniforme (spec §0, §19) — tâche « rectype ».

Découverte statique (robotom.tlb, IRobotLoadRecordType) :
  I_LRT_BAR_UNIFORM = 5   (charge uniforme barre)

Ce probe, en lançant Robot, PRÉUVE :
  1. que Cases.Get(n).Records.Create(5) est ACCEPTÉ (type valide) ;
  2. que les propriétés `Fz` et `Objects` EXISTENT sur l'record (assignation
     sans AttributeError ; une erreur « barre introuvable » sur Objects
     confirmerait le NOM de propriété tout en signalant l'absence de barre).

Read-only sur le modèle : ne sauvegarde rien (§5.4).

Usage : python tools/probe_bar_uniform_live.py
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
    print("[2] projet vierge")

    S = rc.structure
    # cas simple de support
    try:
        S.Cases.CreateSimple(1, "G", 0, 1)   # PERMANENT, STATIC_LINEAR
        print("[3] cas 1 (G) créé")
    except Exception as exc:
        print(f"[3] CreateSimple a échoué : {exc}")

    case = S.Cases.Get(1)
    print(f"[4] Cases.Get(1) = {case}")

    # -- Records.Create(5) : type accepté ?
    try:
        rec = case.Records.Create(I_LRT_BAR_UNIFORM)
        print(f"[5] Records.Create({I_LRT_BAR_UNIFORM}=BAR_UNIFORM) OK -> {rec}")
    except Exception as exc:
        print(f"[5] Records.Create({I_LRT_BAR_UNIFORM}) a ÉCHOUÉ : {exc}")
        rec = None

    if rec is not None:
        # -- propriété Fz existe ?
        try:
            rec.Fz = -10.0
            readback = getattr(rec, "Fz", "<absent>")
            print(f"[6] rec.Fz = -10.0 OK (lecture de retour: {readback})")
        except AttributeError as exc:
            print(f"[6] rec.Fz : AttributeError (propriété absente) : {exc}")
        except Exception as exc:
            print(f"[6] rec.Fz : autre erreur (propriété présente ?) : {exc}")

        # -- propriété Objects existe ? (peut échouer si barre introuvable,
        #    ce qui confirme quand même le NOM de propriété)
        try:
            rec.Objects = "1"
            print("[7] rec.Objects = '1' OK")
        except AttributeError as exc:
            print(f"[7] rec.Objects : AttributeError (propriété absente) : {exc}")
        except Exception as exc:
            print(f"[7] rec.Objects : erreur (le NOM existe, cause : {exc})")

        # -- lire le type de l'record pour confirmer le round-trip
        try:
            print(f"[8] rec.Type (lecture) = {rec.Type}")
        except Exception as exc:
            print(f"[8] rec.Type lecture a échoué : {exc}")

    rc.close_project(save=False)
    print("projet fermé (sans sauvegarde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
