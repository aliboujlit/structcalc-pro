# -*- coding: utf-8 -*-
"""
tools/probe_advsteel.py — Disponibilité COM d'Advance Steel 2027.

Contexte : l'instance AutoCAD active est « Autodesk Advance Steel 2027 »
(hôte acad.exe partagé, Version 26.0s LMS Tech). On cherche l'API COM des
objets ACIER (poutres, connexions, plaques, boulons) :

  1. ProgID registre dont le serveur pointe vers ADVS\\ ou AstorMain ;
  2. contenu de ADVS\\AstorMain5.tlb (bibliothèque de types) ;
  3. tentative d'activation des coclasses trouvées (si sûres).

Aucune méthode n'est supposée : on observe le registre et la TLB.

Usage : python tools/probe_advsteel.py
"""
from __future__ import annotations

import os
import sys

try:
    import winreg
    HAS = True
except ImportError:  # pragma: no cover
    HAS = False

ADVS_DIR = r"C:\Program Files\Autodesk\AutoCAD 2027\ADVS"
TLB = os.path.join(ADVS_DIR, "AstorMain5.tlb")

# Mots-clés servant à identifier un serveur COM Advance Steel
HINTS = ("astor", "advsteel", "advance steel", "advs", "asmain", "astorage",
         "asteel", "asconnection", "asdetail", "asreport")


def _v(k, name=""):
    try:
        return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def scan_progid() -> dict:
    """ProgID HKCR dont le serveur contient un mot-clé Advance Steel."""
    out = {}
    if not HAS:
        return {"error": "winreg indisponible"}
    root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
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
        for sub in ("LocalServer32", "InprocServer32"):
            try:
                sk = winreg.OpenKey(root, rf"CLSID\{clsid}\{sub}")
                path = str(_v(sk))
                kind = sub
                sk.Close()
            except OSError:
                continue
            low = (pid + " " + path).lower()
            if any(h in low for h in HINTS):
                out[pid] = {"clsid": clsid, "kind": kind,
                            "path": path.replace('"', "")}
            break
    winreg.CloseKey(root)
    return out


def inspect_tlb() -> dict:
    """Coclasses / interfaces de AstorMain5.tlb (lecture seule)."""
    out = {"exists": os.path.isfile(TLB)}
    if not out["exists"]:
        return out
    out["size"] = os.path.getsize(TLB)
    try:
        import comtypes.client
        mod = comtypes.client.GetModule(TLB)
        names = [n for n in dir(mod) if not n.startswith("_")]
        out["module"] = getattr(mod, "__name__", "?")
        out["count"] = len(names)
        out["names"] = sorted(names)[:60]
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:180]
    return out


def try_activate(progids) -> dict:
    """Tentative d'activation COM des ProgIDs sûrs (peut lancer)."""
    import pythoncom
    import win32com.client
    res = {}
    pythoncom.CoInitialize()
    for pid in progids:
        info = {}
        try:
            obj = win32com.client.Dispatch(pid)
            info["ok"] = True
            info["type"] = type(obj).__name__
            readable = {}
            for a in ("Name", "Version", "Caption", "Visible", "Application",
                      "Document", "Documents"):
                try:
                    v = getattr(obj, a)
                    if not callable(v):
                        readable[a] = repr(v)[:60]
                except Exception:
                    pass
            info["readable"] = readable
        except Exception as exc:
            info["ok"] = False
            info["err"] = f"{type(exc).__name__}: {exc}"[:160]
        res[pid] = info
    pythoncom.CoUninitialize()
    return res


def main() -> int:
    print("=" * 74)
    print("SONDAGE COM ADVANCE STEEL 2027")
    print("=" * 74)

    print("\n[1] Registre — ProgID vers serveur Advance Steel")
    progs = scan_progid()
    if "error" in progs:
        print("   ", progs["error"])
    elif not progs:
        print("    (aucun ProgID Advance Steel trouvé — AstorMain non exposé)")
    for pid, info in sorted(progs.items()):
        print(f"    {pid}")
        print(f"        {info['kind']} -> {info['path']}")

    print("\n[2] TLB AstorMain5")
    tlb = inspect_tlb()
    if not tlb["exists"]:
        print("    absent :", TLB)
    elif "error" in tlb:
        print(f"    {tlb['size']} octets, GetModule KO : {tlb['error']}")
    else:
        print(f"    {tlb['size']} octets, {tlb['count']} symboles")
        print("    noms :", tlb["names"][:40])

    if progs:
        print("\n[3] Activation (peut lancer Advance Steel)")
        acts = try_activate(sorted(progs))
        for pid, info in acts.items():
            if info["ok"]:
                print(f"    OK  {pid} type={info['type']} "
                      f"readable={info.get('readable', {})}")
            else:
                print(f"    KO  {pid} : {info['err']}")
    print("\n" + "=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
