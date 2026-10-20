# -*- coding: utf-8 -*-
"""
tools/probe_bar_material_live.py — SONDAGE CIBLÉ : matériau PORTÉ par les
barres de la villa (v1.3, 20/10/2026).

Hypothèse à tester : bar.GetLabelName(I_LT_BAR_MATERIAL=8) renvoie le nom
du matériau RÉELLEMENT appliqué (même mécanique que GetLabelName(3) pour la
section, prouvé « C R30x30 »). Si oui -> matériaux utilisés dans le pivot
(ex. 'BETON25') au lieu des 136 labels disponibles ; si non -> honnête.

Fermeture SANS sauvegarde (S5.4).
    chcp 65001 ; $env:PYTHONIOENCODING="utf-8" ; python -u tools\\probe_bar_material_live.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = (TEST_DIR / "Projet-Villa-avec-sous-sol" /
             "Projet Villa avec sous sol.rtd")

LT_BAR_MATERIAL = 8


def main() -> int:
    from structcalc.integration.interop import default_hub
    hub = default_hub()
    rconn = hub.get("robot")
    try:
        rconn.connect(timeout=300.0)
    except Exception as exc:
        print(f"[REFUS] Robot : {exc}")
        return 1
    rc = rconn.rc
    opened = False
    try:
        if rc.is_project_open:
            live = ""
            try:
                live = str(rc.app.Project.FileName or "")
            except Exception:
                live = ""
            if Path(live).resolve() == RTD_VILLA.resolve():
                rc.adopt_live_project()
                print("Villa deja ouverte : ADOPTION (S5.4).")
            else:
                print(f"[REFUS] projet etranger ouvert (S5.4) : {live}")
                return 1
        else:
            print(f"Ouverture visible : {RTD_VILLA.name} ...")
            rc.open_project(str(RTD_VILLA))
            opened = True
        S = rc.structure
        coll = S.Bars.GetAll()
        n = int(coll.Count)
        counts: Counter[str] = Counter()
        errs: Counter[str] = Counter()
        by_type: dict[str, Counter[str]] = {"column": Counter(),
                                            "other": Counter()}
        for i in range(1, n + 1):
            br = coll.Get(i)
            bnum = int(br.Number)
            try:
                st = int(S.Bars.GetStructuralType(bnum))
            except Exception:
                st = -1
            try:
                mat = str(br.GetLabelName(LT_BAR_MATERIAL) or "")
            except Exception as exc:
                mat = ""
                errs[f"{type(exc).__name__}: {str(exc)[:80]}"] += 1
            counts[mat or "<vide>"] += 1
            key = "column" if st == 2 else "other"
            by_type[key][mat or "<vide>"] += 1
            if i <= 6 or (mat and i <= 12):
                print(f"  barre {bnum}: OST={st} material={mat!r}")
        print(f"\n  materiaux portes ({n} barres) : {dict(counts)}")
        print(f"  par type : poteaux={dict(by_type['column'])} |"
              f" autres={dict(by_type['other'])}")
        if errs:
            print(f"  exceptions GetLabelName(8) : {dict(errs)}")
        else:
            print("  GetLabelName(8) : aucune exception")
        return 0
    finally:
        try:
            if opened:
                rc.close_project(save=False)
                print("Villa fermee SANS sauvegarde (S5.4).")
        except Exception as exc:
            print(f"[ERREUR] fermeture : {exc}")
        try:
            rconn.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
