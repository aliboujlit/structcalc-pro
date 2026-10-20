# -*- coding: utf-8 -*-
"""
tools/check_fix_v131_live.py — VÉRIFICATION LIVE du correctif v1.3.1 :
read_model enrichi sur la villa -> matériaux portés (BETON25), appuis par
label (15 Encastrement), 108 barres / 45 poteaux (collection typée).
Fermeture SANS sauvegarde (S5.4).
    chcp 65001 ; $env:PYTHONIOENCODING="utf-8" ; python -u tools\\check_fix_v131_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = (TEST_DIR / "Projet-Villa-avec-sous-sol" /
             "Projet Villa avec sous sol.rtd")


def main() -> int:
    from structcalc.core.model import Project
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
            else:
                print(f"[REFUS] projet etranger ouvert (S5.4) : {live}")
                return 1
        else:
            rc.open_project(str(RTD_VILLA))
            opened = True
        study = Project(sc_id="SC-PROJECT-000011", name="Villa-fix-check")
        rep = rconn.read_model(study)
        print(f"read_model : {rep.status} — {rep.message}")
        c = study.counts()
        print(f"counts : {c}")
        mats = {m.name for m in study.materials.values()}
        sups = {s.name for s in study.supports.values()}
        cols = list(study.columns.values())
        linked = sum(1 for col in cols if col.material)
        print(f"materiaux ({len(mats)}) : {sorted(mats)[:10]}"
              f"{' ...' if len(mats) > 10 else ''}")
        print(f"appuis ({len(study.supports)}) : noms={sorted(sups)}")
        print(f"poteaux : {len(cols)} ; avec materiau lie : {linked}")
        ok = (c.get("columns") == 45 and c.get("beams") == 63
              and c.get("materials", 0) >= 1 and c.get("supports") == 15)
        print(f"VERDICT correctif v1.3.1 : {'OK' if ok else 'ECART'}")
        return 0 if ok else 2
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
