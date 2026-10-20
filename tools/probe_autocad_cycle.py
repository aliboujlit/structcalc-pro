# -*- coding: utf-8 -*-
"""
tools/probe_autocad_cycle.py — Cycle complet DWG : écrire -> SaveAs -> Open -> lire.

Valide l'interchange par FICHIER (essentiel pour l'interopérabilité) :
  1. doc vierge + géométrie (AddLine/AddPolyline VARIANT)
  2. SaveAs(code) en PREMIER appel (teste 23 vs ordre d'appel)
  3. fermeture puis Documents.Open(path)
  4. relecture des entités + géométrie
  5. fermeture sans sauvegarde

Réponses attendues : quel code AcSaveAsType est fiable pour DWG,
et si le cycle de relecture fonctionne.

Usage : python tools/probe_autocad_cycle.py
"""
from __future__ import annotations

import os
import tempfile

R: dict = {}


def rec(op, fn):
    try:
        v = fn()
        R[op] = True
        print(f"  [OK  ] {op} -> {repr(v)[:85]}")
        return v
    except Exception as exc:
        R[op] = False
        print(f"  [FAIL] {op} -> {type(exc).__name__}: {exc}")
        return None


def v6(vals):
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)


def make_geo(ms):
    """Écrit 1 ligne + 1 contour de dalle (5x5)."""
    rec("AddLine(VARIANT)", lambda: ms.AddLine(v6([0.0, 0.0, 0.0]),
                                               v6([5.0, 0.0, 0.0])))
    rec("AddPolyline(4 pts)", lambda: ms.AddLightWeightPolyline(
        v6([0.0, 0.0, 5.0, 0.0, 5.0, 5.0, 0.0, 5.0])))


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("CYCLE COMPLET DWG : écriture -> SaveAs -> Open -> lecture")
    print("=" * 68)
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")

    docs = app.Documents
    tmp = os.path.join(tempfile.gettempdir(), "sc_cycle.dwg")
    for p in (tmp, os.path.splitext(tmp)[0] + ".dxf"):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    # ---- 1) Écriture + SaveAs EN PREMIER APPEL ----
    doc = docs.Add()
    make_geo(doc.ModelSpace)
    rec("Count(avant save)", lambda: doc.ModelSpace.Count)

    saved_code = None
    for code in (23, 24, 15, 14, 12, 1):
        r = rec(f"SaveAs(code={code}) [1er appel doc]",
                lambda c=code: doc.SaveAs(tmp, c))
        if r is not None and os.path.exists(tmp):
            saved_code = code
            break
    rec("SaveAs code retenu", lambda: saved_code)
    rec("taille fichier(octets)", lambda: os.path.getsize(tmp))
    rec("doc.FullName", lambda: doc.FullName)

    # ---- 2) Fermeture ----
    rec("doc.Close(False)", lambda: doc.Close(False))

    # ---- 3) Réouverture ----
    odoc = rec("Documents.Open(path)", lambda: docs.Open(tmp))
    if odoc is not None:
        oms = odoc.ModelSpace
        rec("Open: ModelSpace.Count", lambda: oms.Count)
        e0 = rec("Open: Item(0)", lambda: oms.Item(0))
        if e0 is not None:
            rec("Open: ObjectName", lambda: e0.ObjectName)
            rec("Open: géométrie",
                lambda: (tuple(e0.StartPoint), tuple(e0.EndPoint)))
        # Parcours complet des entités
        def all_names():
            names = []
            for i in range(oms.Count):
                names.append(oms.Item(i).ObjectName)
            return names
        rec("Open: toutes entités", lambda: all_names())
        rec("Open: Close(False)", lambda: odoc.Close(False))

    # ---- 4) Test AddText isolé (hors SaveAs) ----
    d2 = docs.Add()
    try:
        rec("AddText tuple simple",
            lambda: d2.ModelSpace.AddText("SC", 0.25, (0.0, 0.0, 0.0)))
    except Exception:
        pass
    if R.get("AddText tuple simple") is False:
        rec("AddText VARIANT",
            lambda: d2.ModelSpace.AddText("SC", 0.25, v6([0.0, 0.0, 0.0])))
    if R.get("AddText VARIANT") is False:
        # Essaye via MText (alternative)
        try:
            rec("AddMText(rect)",
                lambda: d2.ModelSpace.AddMText(v6([0.0, 0.0, 5.0, 1.0]), 0.0,
                                                "SC"))
        except Exception:
            pass
    rec("d2.Close(False)", lambda: d2.Close(False))

    ok = sum(1 for v in R.values() if v)
    bad = [k for k, v in R.items() if not v]
    print("\n" + "=" * 68)
    print(f"CONFIRMÉS : {ok} | ÉCHOUÉS : {len(bad)}")
    for k in bad:
        print(f"  FAIL {k}")
    print(f"Code DWG fiable : SaveAs code={saved_code}")
    print("=" * 68)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
