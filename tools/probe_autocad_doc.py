# -*- coding: utf-8 -*-
"""
tools/probe_autocad_doc.py — Round-trip Document COM AutoCAD (écriture+lecture).

Vérifie au niveau DOCUMENT : Documents.Add, ModelSpace.AddLine, relecture
géométrique, Layers, Regen, SaveAs, Close sans sauvegarde. Utilise la
liaison TYPÉE (TLB fra) quand possible, sinon la liaison dynamique.

Seules les opérations CONFIRMÉES alimentent la matrice de capacités (§19).

Usage : python tools/probe_autocad_doc.py [--json]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

R: dict = {}


def rec(op: str, fn, expect_fail: bool = False):
    """Exécute `fn`, enregistre le résultat, retourne la valeur ou None."""
    try:
        v = fn()
        R[op] = {"ok": True, "value": repr(v)[:120]}
        print(f"  [OK  ] {op} -> {repr(v)[:90]}")
        return v
    except Exception as exc:
        R[op] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
        print(f"  [FAIL] {op} -> {type(exc).__name__}: {exc}")
        return None


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("ROUND-TRIP DOCUMENT AUTOCAD (liaison typée si possible)")
    print("=" * 68)
    pythoncom.CoInitialize()

    app = None
    doc = None
    mode = "dynamic"

    # --- Essai liaison typée (TLB fr) ---
    try:
        import comtypes.client
        import glob
        base = r"C:\Program Files\Autodesk\AutoCAD 2027"
        tlbs = glob.glob(os.path.join(base, "**", "acax26fra.tlb"),
                         recursive=True)
        if tlbs:
            comtypes.client.GetModule(tlbs[0])
            from comtypes.gen import Acax26  # noqa: F401
            mode = "typed(fra)"
            print(f"TLB chargée : {os.path.basename(tlbs[0])}")
    except Exception as exc:
        print(f"(liaison typée indisponible : {type(exc).__name__})")

    # --- Attachement ---
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        rec("attach.GetActiveObject", lambda: app.Name)
    except Exception:
        try:
            app = win32com.client.Dispatch("AutoCAD.Application")
            rec("attach.Dispatch", lambda: app.Name)
        except Exception as exc:
            print(f"attach FAIL {exc}")
            return 1

    rec("app.Version", lambda: app.Version)
    rec("app.Caption", lambda: app.Caption)
    rec("app.Visible=get/set", lambda: (setattr(app, "Visible", True),
                                        app.Visible)[1])

    # --- Documents ---
    docs = rec("app.Documents", lambda: app.Documents)
    if docs is None:
        return finish()

    cnt0 = rec("Documents.Count", lambda: docs.Count)
    doc = rec("Documents.Add()", lambda: docs.Add())
    if doc is None:
        return finish()

    rec("doc.Name", lambda: doc.Name)
    rec("doc.FullName", lambda: doc.FullName)

    # --- ModelSpace (sur le DOCUMENT) ---
    ms = rec("doc.ModelSpace", lambda: doc.ModelSpace)
    if ms is not None:
        rec("ModelSpace.Count(init)", lambda: ms.Count)
        line = rec("ModelSpace.AddLine(p1,p2)",
                   lambda: ms.AddLine((0.0, 0.0, 0.0), (5.0, 3.0, 0.0)))
        rec("ModelSpace.Count(after)", lambda: ms.Count)

        ent = rec("ModelSpace.Item(0)", lambda: ms.Item(0))
        if ent is not None:
            rec("ent.ObjectName", lambda: ent.ObjectName)
            rec("ent.StartPoint", lambda: tuple(ent.StartPoint))
            rec("ent.EndPoint", lambda: tuple(ent.EndPoint))

        # Écriture polygone (fermeture dalle) — utile coffrage
        try:
            pts = win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_R8,
                [0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 5.0, 5.0, 0.0, 0.0, 5.0, 0.0])
            pl = rec("ModelSpace.AddLightWeightPolyline(pts)",
                     lambda: ms.AddLightWeightPolyline(pts))
        except Exception as exc:
            R["ModelSpace.AddLightWeightPolyline(pts)"] = {
                "ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
            print(f"  [FAIL] AddLightWeightPolyline -> {type(exc).__name__}")

        # Texte (repère/étiquette)
        rec("ModelSpace.AddText(txt,h,pt)",
            lambda: ms.AddText("SC-PROBE", 0.25, (1.0, 1.0, 0.0)))

    # --- Couches (sur le DOCUMENT) ---
    lay = rec("doc.Layers", lambda: doc.Layers)
    if lay is not None:
        rec("Layers.Count", lambda: lay.Count)
        rec("Layers.Add(name)", lambda: lay.Add("SC_INTEROP"))

    # --- Regen / Save / Close ---
    rec("doc.Regen(1)", lambda: doc.Regen(1))
    tmp = os.path.join(tempfile.gettempdir(), "sc_probe_doc.dwg")
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    rec("doc.SaveAs(path,0)", lambda: doc.SaveAs(tmp, 0))
    rec("fichier écrit", lambda: os.path.exists(tmp))

    rec("doc.Close(False) [sans sauvegarde]", lambda: doc.Close(False))
    rec("Documents.Count(après fermeture)", lambda: docs.Count)

    return finish()


def finish() -> int:
    ok = [k for k, v in R.items() if v["ok"]]
    bad = [k for k, v in R.items() if not v["ok"]]
    print("\n" + "=" * 68)
    print(f"CONFIRMÉS : {len(ok)} | ÉCHOUÉS : {len(bad)}")
    for k in bad:
        print(f"  FAIL {k}: {R[k].get('error','')}")
    print("=" * 68)
    if "--json" in sys.argv:
        print("JSON:\n" + json.dumps(R, indent=2, ensure_ascii=False))
    try:
        import pythoncom
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
