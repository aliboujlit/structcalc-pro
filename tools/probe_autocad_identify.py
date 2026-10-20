# -*- coding: utf-8 -*-
"""
tools/probe_autocad_identify.py — Identifie les codes AcSaveAsType (DWG vs DXF)
et valide Documents.Open avec retry (CALL_REJECTED).

Méthode : un document vierge PAR code ; lecture des premiers octets du
fichier pour déterminer le format réel (DWG = 'AC10xx', DXF = '  0'/SECTION).

Usage : python tools/probe_autocad_identify.py
"""
from __future__ import annotations

import os
import tempfile
import time

CODES = (1, 5, 6, 10, 12, 14, 16, 22, 23, 24, 25, 30, 35)


def magic(path: str) -> str:
    """Identifie le format par les octets de tête."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError as exc:
        return f"lecture KO {exc}"
    if head[:2] == b"AC":
        return f"DWG ({head[:6].decode('ascii', 'replace')})"
    if b"SECTION" in head or head.lstrip()[:2] in (b" 0", b"0\n", b"999",
                                                    b"0\r"):
        return "DXF"
    return f"inconnu ({head[:16]!r})"


def v6(vals):
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)


def open_with_retry(docs, path, tries=12, delay=1.5):
    """Documents.Open + attente que le document soit réellement actif."""
    last = None
    for i in range(tries):
        try:
            d = docs.Open(path)
        except Exception as exc:
            last = exc
            time.sleep(delay)
            continue
        # attendre ModelSpace disponible (CALL_REJECTED = doc pas prête)
        for _ in range(10):
            try:
                _ = d.ModelSpace.Count
                return d
            except Exception as exc:
                last = exc
                time.sleep(delay)
        time.sleep(delay)
    raise RuntimeError(f"Open non exploitable après {tries} essais : {last}")


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("IDENTIFICATION codes SaveAs (DWG vs DXF) + Open avec retry")
    print("=" * 68)
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")
    docs = app.Documents

    tmpdir = tempfile.gettempdir()
    results = {}

    # ---- 1) Un doc vierge par code ----
    print("\n[1] Format produit par chaque code :")
    for code in CODES:
        path = os.path.join(tmpdir, f"sc_id_{code}.dwg")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            d = docs.Add()
            d.ModelSpace.AddLine(v6([0.0, 0.0, 0.0]), v6([3.0, 0.0, 0.0]))
            d.SaveAs(path, code)
            time.sleep(0.4)
            if os.path.exists(path):
                m = magic(path)
                results[code] = m
                print(f"  code={code:<3} -> {m}")
            else:
                results[code] = "aucun fichier"
                print(f"  code={code:<3} -> aucun fichier")
            try:
                d.Close(False)
            except Exception:
                pass
        except Exception as exc:
            results[code] = "FAIL"
            print(f"  code={code:<3} -> FAIL {type(exc).__name__}")
            try:
                d.Close(False)
            except Exception:
                pass

    dwg_codes = [c for c, v in results.items() if v.startswith("DWG")]
    dxf_codes = [c for c, v in results.items() if v == "DXF"]
    print(f"\n  Codes DWG : {dwg_codes}")
    print(f"  Codes DXF : {dxf_codes}")

    # ---- 2) Cycle complet avec le MEILLEUR code DWG ----
    print("\n[2] Cycle écriture -> SaveAs -> Open(retry) -> lecture :")
    cycle_ok = False
    if dwg_codes:
        best = dwg_codes[-1]     # le plus récent
        path = os.path.join(tmpdir, "sc_cycle2.dwg")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        d = docs.Add()
        d.ModelSpace.AddLine(v6([0.0, 0.0, 0.0]), v6([5.0, 0.0, 0.0]))
        d.ModelSpace.AddLightWeightPolyline(
            v6([0.0, 0.0, 5.0, 0.0, 5.0, 5.0, 0.0, 5.0]))
        print(f"  écrit {d.ModelSpace.Count} entités, SaveAs(code={best})")
        try:
            d.SaveAs(path, best)
            time.sleep(0.5)
            print(f"  fichier : {magic(path)} ({os.path.getsize(path)} o)")
            d.Close(False)
            o = open_with_retry(docs, path)
            print(f"  Open OK -> {o.Name}, Count={o.ModelSpace.Count}")
            names = [o.ModelSpace.Item(i).ObjectName
                     for i in range(o.ModelSpace.Count)]
            print(f"  entités relues : {names}")
            geo = (tuple(o.ModelSpace.Item(0).StartPoint),
                   tuple(o.ModelSpace.Item(0).EndPoint))
            print(f"  géométrie Item(0) : {geo}")
            cycle_ok = bool(names)
            o.Close(False)
        except Exception as exc:
            print(f"  CYCLE FAIL : {type(exc).__name__}: {exc}")
            try:
                d.Close(False)
            except Exception:
                pass

    # ---- 3) AddText / alternatives ----
    print("\n[3] Textes :")
    d2 = docs.Add()
    for label, fn in (
        ("AddText(tuple)", lambda: d2.ModelSpace.AddText(
            "SC", 0.25, (0.0, 0.0, 0.0))),
        ("AddText(VARIANT)", lambda: d2.ModelSpace.AddText(
            "SC", 0.25, v6([0.0, 0.0, 0.0]))),
        ("AddMText(VARIANT rect)", lambda: d2.ModelSpace.AddMText(
            v6([0.0, 0.0, 5.0, 1.0]), 0.0, "SC")),
    ):
        try:
            fn()
            print(f"  [OK  ] {label}")
        except Exception as exc:
            print(f"  [FAIL] {label} -> {type(exc).__name__}: {exc}")
    try:
        d2.Close(False)
    except Exception:
        pass

    print("\n" + "=" * 68)
    print(f"DWG codes fiables : {dwg_codes}")
    print(f"Cycle complet {'OK' if cycle_ok else 'ÉCHOUÉ'}")
    print("=" * 68)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
