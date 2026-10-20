# -*- coding: utf-8 -*-
"""
tools/probe_nw_progids.py — Tous les ProgID COM Navisworks enregistrés.

Balaye HKCR et garde tout serveur (Inproc/Local) pointant vers le dossier
Navisworks. Donne la liste exacte des coclasses instanciables, avec leur type
de serveur — base factuelle pour le connecteur (aucune API supposée).

Usage : python tools/probe_nw_progids.py
"""
from __future__ import annotations

import os

try:
    import winreg
    HAS = True
except ImportError:  # pragma: no cover
    HAS = False

NW_DIRS = (
    r"c:\program files\autodesk\navisworks manage 2027",
    r"c:\program files\autodesk\navisworks simulate 2027",
)


def _v(k, name=""):
    try:
        return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def main() -> int:
    print("=" * 74)
    print("ProgID COM NAVISWORKS ENREGISTRÉS (HKCR)")
    print("=" * 74)
    if not HAS:
        print("  winreg indisponible")
        return 1

    root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    found = []
    i = 0
    while True:
        try:
            pid = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if "." not in pid:
            continue
        try:
            k = winreg.OpenKey(root, pid + r"\CLSID")
            clsid = _v(k)
            k.Close()
        except OSError:
            continue
        if not clsid:
            continue
        server, kind, path = None, None, None
        for sub in ("LocalServer32", "InprocServer32"):
            try:
                sk = winreg.OpenKey(root, rf"CLSID\{clsid}\{sub}")
                path = _v(sk)
                kind = sub
                sk.Close()
                break
            except OSError:
                continue
        if not path:
            continue
        if any(d in str(path).lower() for d in NW_DIRS):
            found.append((pid, clsid, kind, str(path)))
    winreg.CloseKey(root)

    print(f"\n  {len(found)} ProgID -> dossier Navisworks\n")
    for pid, clsid, kind, path in sorted(found):
        exe = os.path.basename(path.replace('"', ""))
        short = "Local (hors-processus)" if kind == "LocalServer32" \
            else "Inproc (en-processus)"
        print(f"    {pid}")
        print(f"        clsid = {clsid}")
        print(f"        {short}  ->  {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
