# -*- coding: utf-8 -*-
"""
tools/probe_autocad_members.py — Découverte des membres COM réels d'AutoCAD.

`GetActiveObject` fonctionne mais la liaison dynamique échoue sur `.Version`.
Ce script ATTACHE et INTROSPECTIONNE : quels membres sont réellement
accessibles, et si une liaison typée (comtypes + robotom-like tlb) change
tout. Aucune API n'est supposée : on observe.

Usage : python tools/probe_autocad_members.py
"""
from __future__ import annotations

import sys

CANDIDATES_PROP = ("Version", "Caption", "Visible", "FullName", "Name")
CANDIDATES_METH = ("Quit", "Eval", "GetAcadWin")
CANDIDATES_DOC = ("Documents", "ActiveDocument", "ModelSpace", "Layers")


def try_late_binding() -> dict:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    out: dict = {}
    try:
        try:
            app = win32com.client.GetActiveObject("AutoCAD.Application")
            out["attach"] = "GetActiveObject OK"
        except Exception as exc:
            out["attach"] = f"GetActiveObject FAIL {type(exc).__name__}"
            try:
                app = win32com.client.Dispatch("AutoCAD.Application")
                out["attach"] += " | Dispatch OK"
            except Exception as exc2:
                out["attach"] += f" | Dispatch FAIL {type(exc2).__name__}"
                return out

        out["type"] = type(app).__name__

        # Membres exposés (dir + _prop_map_get_)
        try:
            out["dir"] = sorted(x for x in dir(app) if not x.startswith("_"))
        except Exception as exc:
            out["dir"] = f"FAIL {type(exc).__name__}"

        try:
            gets = sorted(getattr(app, "_prop_map_get_", {}) or {})
            out["prop_map_get"] = gets
        except Exception as exc:
            out["prop_map_get"] = f"FAIL {type(exc).__name__}"

        try:
            puts = sorted(getattr(app, "_prop_map_put_", {}) or {})
            out["prop_map_put"] = puts
        except Exception:
            out["prop_map_put"] = []

        # Test ciblé de chaque membre candidate
        probe = {}
        for attr in CANDIDATES_PROP + CANDIDATES_METH + CANDIDATES_DOC:
            try:
                v = getattr(app, attr)
                if callable(v):
                    probe[attr] = "METHOD"
                else:
                    probe[attr] = f"PROP = {v!r}"[:80]
            except Exception as exc:
                probe[attr] = f"FAIL {type(exc).__name__}"
        out["probe"] = probe
    finally:
        pythoncom.CoUninitialize()
    return out


def try_typed_binding() -> dict:
    """Liaison typée via comtypes sur la TLB AutoCAD (si trouvée)."""
    out: dict = {}
    try:
        import comtypes.client
    except Exception as exc:
        out["comtypes"] = f"absent {type(exc).__name__}"
        return out
    # Repérage d'une TLB AutoCAD
    import glob
    import os
    roots = [r"C:\Program Files\Autodesk\AutoCAD 2027",
             r"C:\Program Files\Common Files\Autodesk Shared"]
    tlbs = []
    for r in roots:
        if os.path.isdir(r):
            tlbs += glob.glob(os.path.join(r, "**", "*.tlb"),
                              recursive=True)[:40]
    acad_tlbs = [t for t in tlbs
                 if any(k in os.path.basename(t).lower()
                        for k in ("acax", "axdb", "acax22", "acax"))]
    out["tlb_candidates"] = [os.path.basename(t) for t in acad_tlbs][:10]
    if not acad_tlbs:
        out["note"] = "aucune TLB AutoCAD repérée dans les chemins scannés"
        return out
    tlb = acad_tlbs[0]
    try:
        mod = comtypes.client.GetModule(tlb)
        out["GetModule"] = f"OK {os.path.basename(tlb)}"
        out["module_attrs"] = sorted(
            x for x in dir(mod) if x.lower().startswith("acad"))[:20]
    except Exception as exc:
        out["GetModule"] = f"FAIL {type(exc).__name__}: {exc}"
    return out


def main() -> int:
    print("=" * 68)
    print("DÉCOUVERTE MEMBRES COM AUTOCAD (liaison dynamique vs typée)")
    print("=" * 68)
    late = try_late_binding()
    print("\n[1] Liaison dynamique (win32com GetActiveObject)")
    for k, v in late.items():
        if k in ("dir", "prop_map_get"):
            if isinstance(v, list):
                print(f"  {k} ({len(v)}): {v[:40]}")
            else:
                print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    print("\n[2] Membres candidats testés :")
    for k, v in (late.get("probe") or {}).items():
        print(f"    {'OK ' if not str(v).startswith('FAIL') else '---'}"
              f" {k}: {v}")

    print("\n[3] Liaison typée (comtypes + TLB) :")
    typed = try_typed_binding()
    for k, v in typed.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
