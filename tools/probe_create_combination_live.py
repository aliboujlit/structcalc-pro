# -*- coding: utf-8 -*-
"""
tools/probe_create_combination_live.py — PREUVE PAR EXÉCUTION (spec §0, §19)
de `Cases.CreateCombination` sur Robot 2027.

Signature statiquement établie (robotom.tlb, IRobotCaseServer) :
    CreateCombination(int, str, enum, enum, enum)  — 5 params [in], tous requis.
Ordre de référence (wrapper qui fonctionne) :
    (comb_number, comb_name, comb_type, case_nature, case_analize_type)

Ce probe, en lançant Robot, PRÉUVE par lecture de retour :
  1. la création effective d'une combinaison ;
  2. l'ORDRE exact des 3 enums (valeurs distinctives -> propriétaire identifié) ;
  3. l'ajout de membres via CaseFactors.New(case, coeff).

Usage : python tools/probe_create_combination_live.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from structcalc.integration.robot.connection import RobotConnection  # noqa: E402


def main() -> int:
    rc = RobotConnection(visible=True)
    rc.connect(timeout=90)
    print("[1] connecté à Robot")
    rc.new_project()
    print("[2] projet vierge créé")

    Cases = rc.structure.Cases

    # -- Cas simples (signature CONFIRMÉE : CreateSimple(int, str, nature, analize))
    try:
        Cases.CreateSimple(1, "G", 0, 1)    # PERMANENT=0, STATIC_LINEAR=1
        Cases.CreateSimple(2, "Q", 1, 1)    # EXPLOITATION=1, STATIC_LINEAR=1
        print("[3] cas simples 1 (G) et 2 (Q) créés")
    except Exception as exc:
        print(f"[3] CreateSimple a échoué (non bloquant pour l'ordre) : {exc}")

    # -- Combinaison de base (valeurs sûres : ULS=0, PERMANENT=0, COMB=0)
    results = {}
    try:
        comb = Cases.CreateCombination(10, "ULS 1", 0, 0, 0)
        results["created"] = True
        print(f"[4] CreateCombination(10,...,0,0,0) OK -> type={int(comb.Type)}")
    except Exception as exc:
        results["created"] = False
        print(f"[4] CreateCombination a ÉCHOUÉ : {exc}")

    # -- Ordre des enums : valeurs DISTINCTIVES
    #    comb_type=2 (ALS), case_nature=3 (SNOW), case_analize_type=0 (COMB)
    order = {}
    try:
        c2 = Cases.CreateCombination(11, "ORDRE", 2, 3, 0)
        ct = int(c2.CombinationType)
        na = int(c2.Nature)
        an = int(c2.AnalizeType)
        order = {"CombinationType": ct, "Nature": na, "AnalizeType": an}
        print(f"[5] ordre par lecture de retour : CombinationType={ct}, "
              f"Nature={na}, AnalizeType={an}")
        # Interprétation : quels valeurs entrées (2,3,0) ont atterri où ?
        print(f"    entrée param2=2 -> CombType={ct} | param3=3 -> Nature={na} "
              f"| param4=0 -> AnalizeType={an}")
        results["order"] = order
        # attendu si ordre (comb_type, case_nature, case_analize_type) :
        if ct == 2 and na == 3 and an == 0:
            results["order_confirmed"] = True
            print("[5] ORDRE CONFIRMÉ : (number, name, comb_type, case_nature, "
                  "case_analize_type)")
        else:
            results["order_confirmed"] = False
            print("[5] ORDRE DIFFÉRENT de la référence — analyser la sortie.")
    except Exception as exc:
        print(f"[5] test d'ordre a échoué : {exc}")
        results["order_confirmed"] = None

    # -- Ajout de membres (CaseFactors.New) sur la combinaison 10
    try:
        comb = Cases.Get(10)
        cf = comb.CaseFactors
        cf.New(1, 1.35)
        cf.New(2, 1.5)
        results["factors_added"] = True
        print("[6] membres ajoutés : 1*1.35 + 2*1.5")
    except Exception as exc:
        results["factors_added"] = False
        print(f"[6] CaseFactors.New a échoué : {exc}")

    print("\n=== RÉSUMÉ ===")
    for k, v in results.items():
        print(f"  {k}: {v}")

    # Fermeture sans sauvegarde (§5.4)
    rc.close_project(save=False)
    print("projet fermé (sans sauvegarde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
