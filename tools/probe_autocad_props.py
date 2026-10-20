# -*- coding: utf-8 -*-
"""
tools/probe_autocad_props.py — Dernière vérification avant implémentation.

Vérifie les propriétés destinées au connecteur (jamais supposées) :
  - ent.Layer / ent.Handle (traçabilité SC-* <-> entité AutoCAD)
  - layers.Item(name), layer.Color, suppression
  - alternative texte : AddText avec 3 args scalaires / TextString via
    AddAttribute ?  -> on teste 3 formes puis on statue
  - suppression d'entité (Delete) pour cycle d'actualisation

Usage : python tools/probe_autocad_props.py
"""
from __future__ import annotations

import time

R = {}


def v6(vals):
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)


def t(label, fn):
    try:
        v = fn()
        R[label] = True
        print(f"  [OK  ] {label} -> {repr(v)[:80]}")
        return v
    except Exception as exc:
        R[label] = False
        print(f"  [FAIL] {label} -> {type(exc).__name__}: {str(exc)[:100]}")
        return None


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("PROPRIÉTÉS AUTOCAD pour le connecteur (vérification finale)")
    print("=" * 68)
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")

    docs = app.Documents
    d = docs.Add()
    ms = d.ModelSpace

    # Calque puis entité dessus
    layers = d.Layers
    t("layers.Count", lambda: layers.Count)
    lay = t("layers.Add('SC_COLUMN')", lambda: layers.Add("SC_COLUMN"))
    if lay is not None:
        t("layer.Color = 1", lambda: setattr(lay, "Color", 1) or lay.Color)
        t("layers.Item('SC_COLUMN')", lambda: layers.Item("SC_COLUMN"))

    line = t("AddLine", lambda: ms.AddLine(v6([0.0, 0.0, 0.0]),
                                           v6([5.0, 0.0, 0.0])))
    t("ent.Layer (lecture)", lambda: line.Layer)
    t("ent.Layer = 'SC_COLUMN'", lambda: setattr(line, "Layer",
                                                 "SC_COLUMN"))
    t("ent.Layer après affect.", lambda: line.Layer)
    t("ent.Handle", lambda: line.Handle)
    t("ent.Color", lambda: line.Color)

    # Identifier une entité par Handle -> utile mapping SC-*
    hl = line.Handle if R.get("ent.Handle") else None
    if hl:
        t("ModelSpace.ItemByRef(Handle)",
          lambda: d.ModelSpace.ItemByRef(hl) is not None)

    # Fermeture d'une polyligne / suppression
    poly = t("AddPolyline", lambda: ms.AddLightWeightPolyline(
        v6([0.0, 0.0, 4.0, 0.0, 4.0, 4.0, 0.0, 4.0])))
    t("ent.Delete()", lambda: poly.Delete() is None or True)
    t("Count après Delete", lambda: ms.Count)

    # --- Texte : 3 formes finales ---
    t("AddText(a,b,c) scalaires?",
      lambda: ms.AddText("SC", 0.25, 1.0))
    t("AddText(str, float, float)",
      lambda: ms.AddText("SC2", 0.25, 2.0))
    # via ActiveDocument.AddText ? (certaines expositions)
    t("doc.AddText ?",
      lambda: d.AddText("SC3", 0.25, v6([0.0, 0.0, 0.0])))

    print(f"\n  entités finales : "
          f"{[ms.Item(i).ObjectName for i in range(ms.Count)]}")

    try:
        d.Close(False)
    except Exception:
        pass

    ok = [k for k, v in R.items() if v]
    bad = [k for k, v in R.items() if not v]
    print("\n" + "=" * 68)
    print(f"CONFIRMÉS ({len(ok)}):")
    for k in ok:
        print(f"  + {k}")
    print(f"ÉCHOUÉS ({len(bad)}):")
    for k in bad:
        print(f"  - {k}")
    print("=" * 68)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
