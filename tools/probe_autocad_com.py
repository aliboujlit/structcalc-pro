# -*- coding: utf-8 -*-
"""
tools/probe_autocad_com.py — Sonde COM AutoCAD (Phase 0-style).

Vérifie par EXÉCUTION les signatures COM réelles d'AutoCAD, pour n'utiliser
ensuite que des opérations confirmées (spec §19 : aucune API inventée).

Teste : Dispatch/GetActiveObject, Documents.Add, ModelSpace.AddLine,
lecture des entités (ObjectName/StartPoint/EndPoint), Layers, SaveAs,
Regen, Close/Quit sans sauvegarde.

Sortie : trace + JSON des opérations CONFIRMÉES / ÉCHOUÉES.

Usage : python tools/probe_autocad_com.py [--json]
"""
from __future__ import annotations

import json
import sys

RESULTS: dict = {}


def record(op: str, ok: bool, detail: str = "") -> bool:
    RESULTS[op] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'OK  ' if ok else 'FAIL'}] {op}"
          f"{' — ' + detail if detail else ''}")
    return bool(ok)


def main() -> int:
    import pythoncom
    import win32com.client

    print("=" * 68)
    print("SONDE COM AUTOCAD 2027 (exécution réelle, sans sauvegarde)")
    print("=" * 68)

    pythoncom.CoInitialize()
    app = None
    doc = None

    try:
        # 1) Connexion
        try:
            app = win32com.client.GetActiveObject("AutoCAD.Application")
            record("GetActiveObject", True, "instance active détectée")
        except Exception as exc:
            record("GetActiveObject", False, type(exc).__name__)
            try:
                app = win32com.client.Dispatch("AutoCAD.Application")
                record("Dispatch", True, "nouvelle instance lancée")
            except Exception as exc2:
                record("Dispatch", False, f"{type(exc2).__name__}: {exc2}")
                return finish(None, None)

        if app is None:
            return finish(None, None)

        # Version / visibilité
        try:
            ver = app.Version
            record("app.Version", True, str(ver))
        except Exception as exc:
            record("app.Version", False, type(exc).__name__)
        try:
            app.Visible = True
            record("app.Visible = True", True)
        except Exception as exc:
            record("app.Visible = True", False, type(exc).__name__)

        # 2) Documents
        try:
            doc = app.Documents.Add()
            record("Documents.Add()", True,
                   f"doc={doc.Name}")
        except Exception as exc:
            record("Documents.Add()", False, f"{type(exc).__name__}: {exc}")

        if doc is None:
            return finish(app, None)

        # 3) Écriture : AddLine (points = 3 doubles)
        line = None
        try:
            line = doc.ModelSpace.AddLine((0.0, 0.0, 0.0),
                                          (5.0, 3.0, 0.0))
            record("ModelSpace.AddLine(p1, p2)", True,
                   f"type={type(line).__name__}")
        except Exception as exc:
            record("ModelSpace.AddLine(p1, p2)", False,
                   f"{type(exc).__name__}: {exc}")

        # 3bis) variante en tuple de tuples (certains contextes)
        if line is None:
            try:
                line = doc.ModelSpace.AddLine((0.0, 0.0, 0.0),
                                              (5.0, 3.0, 0.0))
                record("ModelSpace.AddLine (2e essai)", True)
            except Exception as exc:
                record("ModelSpace.AddLine (2e essai)", False,
                       type(exc).__name__)

        # 4) Comptage + lecture
        try:
            n = doc.ModelSpace.Count
            record("ModelSpace.Count", True, f"n={n}")
        except Exception as exc:
            record("ModelSpace.Count", False, type(exc).__name__)
            n = 0

        try:
            ent = doc.ModelSpace.Item(0)
            oname = ent.ObjectName
            record("ModelSpace.Item(0).ObjectName", True, str(oname))
        except Exception as exc:
            record("ModelSpace.Item(0).ObjectName", False,
                   f"{type(exc).__name__}: {exc}")
            ent = None

        # 5) Lecture géométrique d'une ligne
        if ent is not None:
            try:
                sp = tuple(ent.StartPoint)
                ep = tuple(ent.EndPoint)
                record("Line.StartPoint / EndPoint", True, f"{sp} -> {ep}")
            except Exception as exc:
                record("Line.StartPoint / EndPoint", False,
                       f"{type(exc).__name__}: {exc}")

        # 6) Couches
        try:
            layers = doc.Layers
            record("doc.Layers", True)
            try:
                lay = layers.Add("SC_PROBE")
                record("Layers.Add(name)", True)
                lay.Color = 5
                record("layer.Color = int", True)
            except Exception as exc:
                record("Layers.Add(name)", False, type(exc).__name__)
        except Exception as exc:
            record("doc.Layers", False, type(exc).__name__)

        # 7) Regen
        try:
            doc.Regen(1)   # acRegenAll = 1
            record("doc.Regen(1)", True)
        except Exception as exc:
            record("doc.Regen(1)", False, type(exc).__name__)

        # 8) Sauvegarde sous (test écriture fichier TEMP)
        import os
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "sc_probe_autocad.dwg")
        try:
            doc.SaveAs(tmp, 0)   # acSaveAsCurrentVersion = 0 (probe)
            record("doc.SaveAs(path, 0)", True,
                   f"existe={os.path.exists(tmp)}")
        except Exception as exc:
            record("doc.SaveAs(path, 0)", False, f"{type(exc).__name__}: {exc}")

        # 9) Blocs / sections (utiles échanges)
        try:
            record("doc.Blocks", True) if doc.Blocks else None
        except Exception as exc:
            record("doc.Blocks", False, type(exc).__name__)

        # 10) Documents.Open (lecture DWG existant)
        try:
            record("doc.FullName", True, str(doc.FullName))
        except Exception as exc:
            record("doc.FullName", False, type(exc).__name__)

        return finish(app, doc)

    finally:
        pythoncom.CoUninitialize()


def finish(app, doc) -> int:
    """Fermeture SANS sauvegarde (règle §5.4) puis rapport."""
    print("\n--- Fermeture sans sauvegarde ---")
    if doc is not None:
        try:
            doc.Close(False)   # Save=False
            print("  doc.Close(False) : OK")
        except Exception as exc:
            print(f"  doc.Close(False) : FAIL {type(exc).__name__}")
    if app is not None:
        try:
            # Ne quitte PAS une instance que l'utilisateur aurait ouverte
            # (ici : instance créée par la sonde uniquement)
            pass
        except Exception:
            pass

    confirmed = [k for k, v in RESULTS.items() if v["ok"]]
    failed = [k for k, v in RESULTS.items() if not v["ok"]]
    print("\n" + "=" * 68)
    print(f"CONFIRMÉS : {len(confirmed)} | ÉCHOUÉS : {len(failed)}")
    if failed:
        print("Échecs :")
        for k in failed:
            print(f"  - {k}: {RESULTS[k]['detail']}")
    print("=" * 68)
    if "--json" in sys.argv:
        print("JSON:\n" + json.dumps(RESULTS, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
