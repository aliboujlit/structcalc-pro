# -*- coding: utf-8 -*-
"""
tools/probe_autocad_fix.py — Valide les correctifs des 4 échecs du round-trip.

Hypothèses à confirmer :
  1. AddLine/AddText marchent avec point en VARIANT(VT_ARRAY|VT_R8)
  2. Item(0) fonctionne une fois ModelSpace peuplé
  3. SaveAs marche avec AcSaveAsType = 23 (acSaveAs2018)
  4. lecture géométrique (StartPoint/EndPoint) après écriture

Usage : python tools/probe_autocad_fix.py
"""
from __future__ import annotations

import os
import tempfile

R: dict = {}


def rec(op, fn):
    try:
        v = fn()
        R[op] = True
        print(f"  [OK  ] {op} -> {repr(v)[:80]}")
        return v
    except Exception as exc:
        R[op] = False
        print(f"  [FAIL] {op} -> {type(exc).__name__}: {exc}")
        return None


def v6(vals):
    """Variante VT_ARRAY|VT_R8 pour un/des point(s) 3D."""
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)


def v24(vals):
    """Variante VT_ARRAY|VT_R8 de 24 éléments : 4 points XY (polyline)."""
    return v6(vals)


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("VALIDATION CORRECTIFS AUTOCAD (VARIANT + SaveAs=23)")
    print("=" * 68)
    pythoncom.CoInitialize()

    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")
    rec("attach", lambda: app.Name)

    docs = app.Documents
    doc = docs.Add()
    rec("doc.Name", lambda: doc.Name)
    ms = doc.ModelSpace

    # --- 1) AddLine avec point VARIANT ---
    p1 = v6([0.0, 0.0, 0.0])
    p2 = v6([5.0, 3.0, 0.0])
    line = rec("AddLine(VARIANT p1, p2)",
               lambda: ms.AddLine(p1, p2))

    # --- 1b) variante ligne : AddLine avec tuple float explicites ---
    if line is None:
        line = rec("AddLine(tuple 3 float)",
                   lambda: ms.AddLine((0.0, 0.0, 0.0), (5.0, 3.0, 0.0)))

    # --- 1c) polyligne (déjà OK) pour peupler ---
    pts = v24([0.0, 0.0, 5.0, 0.0, 5.0, 5.0, 0.0, 5.0])
    rec("AddLightWeightPolyline(VARIANT)",
        lambda: ms.AddLightWeightPolyline(pts))

    # --- 2) Count + Item(0) ---
    n = rec("ModelSpace.Count", lambda: ms.Count)
    ent = rec("ModelSpace.Item(0)", lambda: ms.Item(0))
    if ent is not None:
        rec("ent.ObjectName", lambda: ent.ObjectName)
        # Lecture géométrique selon le type
        rec("ent.StartPoint/EndPoint",
            lambda: (tuple(getattr(ent, "StartPoint")),
                     tuple(getattr(ent, "EndPoint"))))

    # --- 1d) AddText avec point VARIANT ---
    rec("AddText(txt,h,VARIANT pt)",
        lambda: ms.AddText("SC-PROBE", 0.25, v6([1.0, 1.0, 0.0])))

    # --- 3) SaveAs avec AcSaveAsType corrects ---
    tmp = os.path.join(tempfile.gettempdir(), "sc_fix_probe.dwg")
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    for code in (23, 24, 1, 5, 6):
        r = rec(f"SaveAs(code={code})",
                lambda c=code: doc.SaveAs(tmp, c))
        if r is not None and os.path.exists(tmp):
            break
    rec("fichier .dwg créé", lambda: os.path.exists(tmp))

    # --- 4) Regen + Close ---
    rec("doc.Regen(1)", lambda: doc.Regen(1))
    rec("doc.Close(False)", lambda: doc.Close(False))

    ok = sum(1 for v in R.values() if v)
    bad = sum(1 for v in R.values() if not v)
    print("\n" + "=" * 68)
    print(f"CONFIRMÉS : {ok} | ÉCHOUÉS : {bad}")
    print("=" * 68)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
