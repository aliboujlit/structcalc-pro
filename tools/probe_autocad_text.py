# -*- coding: utf-8 -*-
"""
tools/probe_autocad_text.py — Test final des textes via liaison TYPÉE (TLB).

`AddText` échoue en liaison dynamique (float() sur le point). On teste :
  1. liaison typée comtypes (Acax26) pour AddText
  2. point en liste (pas tuple)
  3. MText avec rectangle 4 points XY (8 doubles)

Usage : python tools/probe_autocad_text.py
"""
from __future__ import annotations

import os
import tempfile

TYPED = {}


def load_typed():
    """Charge la TLB AutoCAD via comtypes et renvoie (app, module)."""
    import glob
    import comtypes.client
    base = r"C:\Program Files\Autodesk\AutoCAD 2027"
    tlbs = glob.glob(os.path.join(base, "**", "acax26fra.tlb"), recursive=True)
    if not tlbs:
        tlbs = glob.glob(os.path.join(base, "**", "acax26enu.tlb"),
                         recursive=True)
    if not tlbs:
        return None, None
    mod = comtypes.client.GetModule(tlbs[0])
    return mod, tlbs[0]


def v6(vals):
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("TEXTES AUTOCAD : liaison typée + variantes d'arguments")
    print("=" * 68)
    pythoncom.CoInitialize()

    mod, tlb = load_typed()
    print(f"TLB : {os.path.basename(tlb) if tlb else 'absente'}")

    # --- Attachement typé si possible ---
    app = None
    if mod is not None:
        try:
            # AcadApplication via comtypes : CreateObject ou GetActiveObject
            try:
                app = comtypes.client.GetActiveObject(
                    "AutoCAD.Application", dynamic=False)
                print("Attaché TYPÉ (GetActiveObject)")
            except Exception as e1:
                print(f"GetActiveObject typé FAIL {type(e1).__name__}")
                try:
                    import comtypes.client as cc
                    app = cc.CreateObject("AutoCAD.Application",
                                          dynamic=False)
                    print("CreateObject TYPÉ OK")
                except Exception as e2:
                    print(f"CreateObject typé FAIL {type(e2).__name__}")
        except Exception as exc:
            print(f"typé FAIL global {type(exc).__name__}")

    if app is None:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        print("Repli sur liaison DYNAMIQUE")

    docs = app.Documents
    d = docs.Add()
    print(f"doc : {d.Name}")

    results = {}

    def t(label, fn):
        try:
            fn()
            results[label] = True
            print(f"  [OK  ] {label}")
        except Exception as exc:
            results[label] = False
            print(f"  [FAIL] {label} -> {type(exc).__name__}: {exc}")

    # 1) point en LISTE
    t("AddText(liste pt)",
      lambda: d.ModelSpace.AddText("SC-A", 0.25, [1.0, 1.0, 0.0]))
    # 2) point en tuple 3 floats (déjà échoué en dyn, retesté en typé)
    t("AddText(tuple pt)",
      lambda: d.ModelSpace.AddText("SC-B", 0.25, (2.0, 2.0, 0.0)))
    # 3) point en VARIANT
    t("AddText(VARIANT pt)",
      lambda: d.ModelSpace.AddText("SC-C", 0.25, v6([3.0, 3.0, 0.0])))
    # 4) MText rectangle 8 doubles (4 points XY)
    t("AddMText(rect 8 doubles)",
      lambda: d.ModelSpace.AddMText(v6([0.0, 0.0, 6.0, 0.0, 6.0, 1.5,
                                        0.0, 1.5]), 0.0, "SC-MTEXT"))
    # 5) MText en 2 args (point inséré + largeur nulle ?)
    t("AddMText(tuple rect)",
      lambda: d.ModelSpace.AddMText((0.0, 0.0, 6.0, 1.5), 0.0, "SC2"))

    # Compter les textes
    try:
        names = [d.ModelSpace.Item(i).ObjectName
                 for i in range(d.ModelSpace.Count)]
        print(f"  entités : {names}")
        texts = [n for n in names if "Text" in n]
        print(f"  textes présents : {texts}")
    except Exception as exc:
        print(f"  comptage FAIL {type(exc).__name__}")

    try:
        d.Close(False)
    except Exception:
        pass

    ok = sum(1 for v in results.values() if v)
    print("\n" + "=" * 68)
    print(f"TEXTE OK : {ok}/{len(results)}")
    print("=" * 68)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
