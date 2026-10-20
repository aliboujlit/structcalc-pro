# -*- coding: utf-8 -*-
"""
tools/probe_reactions_shape_live.py — SONDAGE CIBLÉ : forme RÉELLE de
Results.Nodes.Reactions.Value(node, case) sur la villa (v1.3.1, 20/10).

Constat live (verify_bureau_etudes) : import_reactions retourne Fz=None
(getattr(rv, "Fx", None) -> AttributeError avalée) alors que l'appel Value()
ne lève RIEN. Ce sondeur imprime :
  - type/répr de rv, _prop_map_get_/_prop_map_put_ (dynamic Dispatch)
  - essais SANS default ( AttributeError complète )
  - formes alternatives : séquence rv[i], GetValue, .Fx via _attr_to_id
  - essai comtypes typé via GetModule(robotom.tlb) si dispo
Fermeture SANS sauvegarde (S5.4).
    chcp 65001 ; $env:PYTHONIOENCODING="utf-8" ; python -u tools\\probe_reactions_shape_live.py
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
TLB = Path(r"C:\Program Files\Autodesk\Robot Structural Analysis "
           r"Professional 2027\Exe\robotom.tlb")


def banner(t: str) -> None:
    print()
    print("=" * 74)
    print(t)
    print("=" * 74, flush=True)


def main() -> int:
    from structcalc.integration.interop import default_hub
    from structcalc.integration.robot import loads
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
            print("[REFUS] un projet est deja ouvert")
            return 1
        rc.open_project(str(RTD_VILLA))
        opened = True
        rcalc = loads.calculate(rc)
        print(f"CALCUL : {rcalc}")
        S = rc.structure
        reac = S.Results.Nodes.Reactions

        banner("A — rv = Reactions.Value(2, 1) : forme de l'objet retour")
        rv = reac.Value(2, 1)
        print(f"type(rv) = {type(rv)!r}")
        print(f"repr     = {repr(rv)[:300]}")
        d = [x for x in dir(rv) if not x.startswith("__")]
        print(f"dir()    = {d[:50]}")
        pmg = getattr(rv, "_prop_map_get_", None)
        print(f"_prop_map_get_ = {dict(pmg) if pmg else pmg}")
        pmp = getattr(rv, "_prop_map_put_", None)
        print(f"_prop_map_put_ = {list(pmp)[:20] if pmp else pmp}")
        print(f"hasattr _oleobj_ = {hasattr(rv, '_oleobj_')}")

        banner("B — essais SANS default (erreur exacte)")
        for name in ("Fx", "Fy", "Fz", "Mx", "My", "Mz"):
            try:
                v = getattr(rv, name)
                print(f"  rv.{name} = {v!r}")
            except Exception as exc:
                print(f"  rv.{name} -> {type(exc).__name__}: {str(exc)[:150]}")

        banner("C — formes alternatives")
        for i in range(6):
            try:
                print(f"  rv[{i}] = {rv[i]!r}")
            except Exception as exc:
                print(f"  rv[{i}] -> {type(exc).__name__}: {str(exc)[:80]}")
                break
        for meth in ("GetValue", "Item"):
            try:
                print(f"  rv.{meth}() -> {getattr(rv, meth)()!r}")
            except Exception as exc:
                print(f"  rv.{meth}() -> {type(exc).__name__}: {str(exc)[:80]}")
        # dispatch typed via _oleobj_
        try:
            import win32com.client as w
            td = w.dynamic.Dispatch(rv._oleobj_)
            print(f"  re-Dispatch dyn : dir = "
                  f"{[x for x in dir(td) if not x.startswith('_')][:30]}")
        except Exception as exc:
            print(f"  re-Dispatch dyn -> {type(exc).__name__}: {str(exc)[:120]}")
        # typeinfo brute force : Invoke par DISPID inconnu -> non teste

        banner("D — comtypes GetModule(robotom.tlb) -> interface typée")
        try:
            import comtypes.client  # noqa
            mod = comtypes.client.GetModule(str(TLB))
            print(f"  module = {mod!r}")
            print(f"  noms IRobotNodeReaction ? "
                  f"{[n for n in dir(mod) if 'Reaction' in n][:10]}")
        except Exception as exc:
            print(f"  comtypes -> {type(exc).__name__}: {str(exc)[:200]}")

        banner("E — meme test sur un AUTRE cas + nœud supporte 10")
        for (n, c) in ((2, 4), (10, 1), (10, 4)):
            try:
                r2 = reac.Value(n, c)
                fx = getattr(r2, "Fx", "PAS-DE-MEMBRE")
                print(f"  Value({n},{c}): type={type(r2).__name__} "
                      f"Fx={fx!r} (dir taille {len(dir(r2))})")
            except Exception as exc:
                print(f"  Value({n},{c}) -> {type(exc).__name__}: "
                      f"{str(exc)[:100]}")
        return 0
    finally:
        try:
            if opened:
                rc.close_project(save=False)
                print("\nVilla fermee SANS sauvegarde (S5.4).")
        except Exception as exc:
            print(f"[ERREUR] fermeture : {exc}")
        try:
            rconn.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
