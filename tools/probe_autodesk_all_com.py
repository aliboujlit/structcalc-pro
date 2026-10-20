# -*- coding: utf-8 -*-
"""
tools/probe_autodesk_all_com.py — Inventaire COM COMPLET des produits Autodesk.

Parcourt HKCR, résout chaque ProgID -> CLSID -> LocalServer32, et ne garde que
ceux dont l'exécutable est Autodesk. Donne la liste DÉFINITIVE des logiciels
pilotables en COM (aucune API n'est supposée : on observe le registre).

Teste aussi la disponibilité de pythonnet (pont .NET -> Revit/Civil 3D).

Usage : python tools/probe_autodesk_all_com.py [--json]
"""
from __future__ import annotations

import json
import sys

try:
    import winreg
    HAS = True
except ImportError:  # pragma: no cover
    HAS = False

# Exécutables / mots-clés Autodesk (détection large)
AUTODESK_HINTS = (
    "autodesk", "acad.exe", "robotstructure", "revit.exe",
    "navisworks", "inventor", "vault", "advancesteel", "aecc",
    "civil3d", "formit", "fushion", "fusion", "powermill",
    "featurecam", "hsm", "structural", "robot",
)


def _read(sk, name=""):
    try:
        v, _ = winreg.QueryValueEx(sk, name)
        return v
    except OSError:
        return None


def scan() -> dict:
    """Retourne {ProgID: {"clsid","server","path"}} pour les produits Autodesk."""
    out: dict = {}
    if not HAS:
        return {"error": "winreg indisponible"}
    try:
        root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    except OSError as e:
        return {"error": str(e)}

    i = 0
    while True:
        try:
            progid = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        # rapide : les ProgID contiennent un point (évite CLSID\\..., *\\CLSID)
        if "." not in progid:
            continue
        try:
            k = winreg.OpenKey(root, progid + r"\CLSID")
        except OSError:
            continue
        clsid = _read(k)
        k.Close()
        if not clsid:
            continue
        # LocalServer32 (serveurs exécutables) / InprocServer32 (DLL .NET)
        server = None
        for sub in (r"LocalServer32", r"InprocServer32"):
            try:
                sk = winreg.OpenKey(root, rf"CLSID\{clsid}\{sub}")
            except OSError:
                continue
            server = _read(sk)
            sk.Close()
            if server:
                break
        if not server:
            continue
        low = (progid + " " + str(server)).lower()
        if any(h in low for h in AUTODESK_HINTS):
            out[progid] = {"clsid": clsid, "server": sub if False else
                           ("LocalServer32" if "LocalServer32" in str(server)
                            or True else ""), "path": str(server)}
    winreg.CloseKey(root)
    return out


def pythonnet_available() -> dict:
    """Pont .NET (pythonnet) pour RevitAPI / AeccDb (objets managés)."""
    out = {}
    try:
        import clr  # noqa: F401
        out["pythonnet"] = True
        try:
            import pythonnet
            out["version"] = getattr(pythonnet, "__version__", "?")
        except Exception:
            out["version"] = "?"
    except Exception as exc:
        out["pythonnet"] = False
        out["reason"] = f"{type(exc).__name__}: {exc}"
    return out


def group_by_product(progs: dict) -> dict:
    """Regroupe les ProgID par produit pour un affichage lisible."""
    groups: dict = {}
    for pid, info in progs.items():
        p = info["path"].lower()
        if "acad.exe" in p or "advance steel" in p:
            g = "AutoCAD / Advance Steel (même hôte acad.exe)"
        elif "robotstructure" in p or "robot" in p:
            g = "Robot Structural Analysis"
        elif "revit" in p:
            g = "Revit"
        elif "navisworks" in p:
            g = "Navisworks"
        elif "inventor" in p:
            g = "Inventor"
        elif "vault" in p:
            g = "Vault"
        elif "aecc" in p or "civil" in p:
            g = "Civil 3D"
        else:
            g = "Autodesk (autre)"
        groups.setdefault(g, []).append((pid, info["path"]))
    return groups


def main() -> int:
    print("=" * 74)
    print("INVENTAIRE COM AUTOBEST/DETENTE — HKCR -> CLSID -> LocalServer32")
    print("=" * 74)
    progs = scan()
    if "error" in progs:
        print("  ERREUR :", progs["error"])
        return 1

    groups = group_by_product(progs)
    print(f"\n{len(progs)} ProgID COM Autodesk détectés "
          f"dans {len(groups)} produit(s) :\n")
    for g in sorted(groups):
        print(f"  [{g}]")
        for pid, path in sorted(groups[g]):
            short = path.split("\\")[-1] if "\\" in path else path
            print(f"      {pid:<34} -> {short}")
        print()

    print("[pont .NET]")
    pn = pythonnet_available()
    for k, v in pn.items():
        print(f"    {k}: {v}")

    print("\n" + "=" * 74)
    if "--json" in sys.argv:
        print(json.dumps({"progids": progs, "pythonnet": pn},
                         indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
