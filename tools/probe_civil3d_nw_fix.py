# -*- coding: utf-8 -*-
"""
tools/probe_civil3d_nw_fix.py — Correctifs + découverte honnête des membres.

[1] Civil 3D : l'erreur 0x8007007E (module introuvable) peut venir de
    dépendances DLL non résolubles hors du dossier Civil 3D. On ajoute
    le dossier C3D et la racine AutoCAD via os.add_dll_directory() puis
    on réessaie.

[2] Navisworks : `dir()` sur un CDispatch sans info de type est vide. On
    interroge GetIDsOfNames() — le COM lui-même confirme/quie une entité :
    si le nom résoud, il EXISTE ; sinon il n'existe pas. Aucune méthode
    n'est supposée, seulement OBSERVÉE.

Usage : python tools/probe_civil3d_nw_fix.py
"""
from __future__ import annotations

import os
import sys
import time

C3D_DIRS = (
    r"C:\Program Files\Autodesk\AutoCAD 2027\C3D",
    r"C:\Program Files\Autodesk\AutoCAD 2027",
)

# Noms candidats TESTÉS (découverte, pas d'invention) : le COM tranche.
NW_CANDIDATES = (
    # application / document
    "Name", "Version", "Caption", "Visible", "FileName", "FullName",
    "ActiveDocument", "Documents", "Files", "Application", "Path",
    # actions document
    "Open", "Save", "SaveAs", "Close", "New", "Append", "Merge",
    "Reload", "Export", "Clear", "Focus", "ZoomExtents",
    # sélection / propriété (API Navisworks classique)
    "SelectedItems", "CurrentSelection", "Properties", "ObjectFactory",
    "CreateData", "Data", "Clash", "Comments",
)

C3D_CANDIDATES = (
    "Name", "Version", "Visible", "Documents", "ActiveDocument",
    "Application", "Caption", "Path", "Close", "Quit", "State",
)


def add_dll_dirs() -> list:
    """Ajoute les dossiers à la recherche de DLL (Python >= 3.8)."""
    added = []
    for d in C3D_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            os.add_dll_directory(d)
            added.append(d)
        except (AttributeError, OSError) as exc:
            print(f"    add_dll_directory('{d}') KO : {exc}")
    return added


def probe_members(obj, names) -> dict:
    """Interroge GetIDsOfNames : existence RÉELLE de chaque membre."""
    import pythoncom
    found, missing = [], []
    for n in names:
        try:
            obj.GetIDsOfNames(pythoncom.IID_NULL, (n,), 1, 0x0409)
            found.append(n)
        except Exception:
            missing.append(n)
    return {"found": found, "missing": missing}


def try_civil3d() -> dict:
    import pythoncom
    import win32com.client

    print("\n[1] CIVIL 3D — avec ajout des dossiers DLL")
    pythoncom.CoInitialize()
    added = add_dll_dirs()
    print(f"    dossiers ajoutés : {added or '(aucun)'}")

    out = {}
    for pid in ("AeccXUiLand.AeccApplication.13.9",
                "AeccXUiLand.AeccDocument.13.9"):
        info = {}
        t0 = time.time()
        try:
            obj = win32com.client.Dispatch(pid)
            info["ok"] = True
            info["method"] = "Dispatch"
            info["type"] = type(obj).__name__
            info["members_probe"] = probe_members(obj, C3D_CANDIDATES)
            for attr in ("Name", "Version", "Caption"):
                try:
                    v = getattr(obj, attr)
                    if not callable(v):
                        info.setdefault("props", {})[attr] = repr(v)[:70]
                except Exception:
                    pass
            print(f"    OK  {pid} -> {info.get('props', {})}")
            print(f"        trouvés : {info['members_probe']['found']}")
        except Exception as exc:
            info["ok"] = False
            info["err"] = f"{type(exc).__name__}: {exc}"[:170]
            print(f"    KO  {pid} -> {info['err']}")
        info["elapsed"] = round(time.time() - t0, 1)
        out[pid] = info
    pythoncom.CoUninitialize()
    return out


def try_navisworks() -> dict:
    import pythoncom
    import win32com.client

    print("\n[2] NAVISWORKS — découverte des membres (GetIDsOfNames)")
    pythoncom.CoInitialize()
    out = {}
    t0 = time.time()
    try:
        app = win32com.client.Dispatch("Navisworks.Document.24")
    except Exception as exc:
        print(f"    KO Dispatch : {type(exc).__name__}: {exc}")
        pythoncom.CoUninitialize()
        return {"dispatch": {"ok": False, "err": str(exc)[:150]}}

    print(f"    Dispatch OK en {time.time() - t0:.1f}s")
    info = {"ok": True, "type": type(app).__name__}

    # propriétés lisibles immédiatement
    for attr in ("Name", "Version", "Caption", "Visible", "FileName",
                 "FullName", "Path"):
        try:
            v = getattr(app, attr)
            if not callable(v):
                info.setdefault("props", {})[attr] = repr(v)[:70]
        except Exception:
            pass
    print(f"    props : {info.get('props', {})}")

    # découverte honnête des membres
    info["members"] = probe_members(app, NW_CANDIDATES)
    print(f"    EXISTANTS : {info['members']['found']}")
    print(f"    absents   : {info['members']['missing']}")

    # tentative de descente : si 'Documents'/'Files'/'ActiveDocument'
    # existe, on l'inspecte (découverte récursive, toujours GetIDsOfNames)
    sub = {}
    for container in ("ActiveDocument", "Documents", "Files", "Application"):
        if container not in info["members"]["found"]:
            continue
        try:
            c = getattr(app, container)
            sub[container] = {
                "type": type(c).__name__,
                "count": _safe_count(c),
                "members": probe_members(
                    c, NW_CANDIDATES + ("Item", "Count", "Add", "Get"))["found"],
            }
            print(f"    .{container} -> type={sub[container]['type']} "
                  f"count={sub[container]['count']} "
                  f"membres={sub[container]['members']}")
        except Exception as exc:
            sub[container] = {"err": f"{type(exc).__name__}: {exc}"[:120]}
            print(f"    .{container} KO {sub[container]['err']}")
    info["sub"] = sub
    out["Navisworks.Document.24"] = info
    out["elapsed_total"] = round(time.time() - t0, 1)
    pythoncom.CoUninitialize()
    return out


def _safe_count(c):
    for a in ("Count",):
        try:
            v = getattr(c, a)
            if not callable(v):
                return int(v)
        except Exception:
            return None
    return None


def main() -> int:
    print("=" * 74)
    print("CORRECTIF CIVIL 3D + DÉCOUVERTE NAVISWORKS")
    print("=" * 74)
    c3d = try_civil3d()
    nw = try_navisworks()
    print("\n" + "=" * 74)
    print("SYNTHÈSE")
    print("=" * 74)
    for pid, i in c3d.items():
        print(f"  Civil3D {pid}: {'OK' if i.get('ok') else 'KO — ' + str(i.get('err',''))}")
    nwi = nw.get("Navisworks.Document.24", {})
    if nwi.get("ok"):
        print(f"  Navisworks : OK, membres existants = {nwi['members']['found']}")
    else:
        print(f"  Navisworks : KO {nwi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
