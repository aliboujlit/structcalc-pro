# -*- coding: utf-8 -*-
"""
tools/probe_autodesk_interop.py — Sonde d'interopérabilité Autodesk.

Ne LANCE aucun logiciel : lecture de registre + disponibilité des liaisons
Python uniquement. But : déterminer honnêtement quels connecteurs sont
réellement possibles (spec §19 : aucune API inventée).

Usage : python tools/probe_autodesk_interop.py [--json]
"""
from __future__ import annotations

import json
import os
import sys

try:
    import winreg
    HAS_WINREG = True
except Exception:            # pragma: no cover - plateformes non Windows
    HAS_WINREG = False

# Préfixes de ProgID COM qu'on cherche (sans lancer l'application)
PROGID_PREFIXES = (
    "Robot.Application",       # Robot Structural Analysis (prouvé Phase 0)
    "AutoCAD.Application",     # AutoCAD (+ hôte COM de Civil 3D)
    "Aecc",                    # Civil 3D / civil (COM historique)
    "AdWindows",               # hôte vertical Autodesk
    "Revit",                   # Revit (normalement absent -> .NET)
)

# Fichiers .NET Revit (présence = API .NET installée, pas de COM)
REVIT_DLLS = ("RevitAPI.dll", "RevitAPIUI.dll")


def scan_progids() -> dict:
    """Parcourt HKCR et repère les ProgIDs par préfixe (sans exécution)."""
    found: dict = {p: [] for p in PROGID_PREFIXES}
    if not HAS_WINREG:
        return {"error": "winreg indisponible", "found": found}
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    except OSError as e:
        return {"error": str(e), "found": found}
    i = 0
    while True:
        try:
            name = winreg.EnumKey(key, i)
        except OSError:
            break
        i += 1
        for p in PROGID_PREFIXES:
            if name == p or name.startswith(p + "."):
                if name not in found[p]:
                    found[p].append(name)
    winreg.CloseKey(key)
    return {"found": found}


def scan_installed_products() -> list:
    """Produits Autodesk via les clés de désinstallation."""
    out: list = []
    if not HAS_WINREG:
        return out
    roots = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for root in roots:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                k = winreg.OpenKey(hive, root)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, j)
                except OSError:
                    break
                j += 1
                try:
                    sk = winreg.OpenKey(k, sub)
                    disp, _ = winreg.QueryValueEx(sk, "DisplayName")
                    winreg.CloseKey(sk)
                except (OSError, FileNotFoundError):
                    continue
                if isinstance(disp, str) and "Autodesk" in disp:
                    if disp not in out:
                        out.append(disp)
            winreg.CloseKey(k)
    return sorted(out)


def scan_autodesk_families() -> list:
    """Familles présentes sous HKLM\\SOFTWARE\\Autodesk."""
    if not HAS_WINREG:
        return []
    out = []
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Autodesk")
    except OSError:
        return []
    i = 0
    while True:
        try:
            n = winreg.EnumKey(k, i)
        except OSError:
            break
        i += 1
        out.append(n)
    winreg.CloseKey(k)
    return sorted(out)


def scan_revit_dlls() -> list:
    """Recherche RevitAPI.dll dans les emplacements typiques (lecture seule)."""
    hits = []
    candidates = []
    for base in (r"C:\Program Files\Autodesk",
                 r"C:\Program Files (x86)\Autodesk"):
        if os.path.isdir(base):
            for prod in os.listdir(base):
                candidates.append(os.path.join(base, prod))
    for c in candidates:
        for root, _dirs, files in os.walk(c):
            # limiter la profondeur
            if root.count(os.sep) - c.count(os.sep) > 4:
                _dirs[:] = []
                continue
            for dll in REVIT_DLLS:
                if dll in files and dll not in [h[1] for h in hits]:
                    hits.append((os.path.basename(root), dll,
                                 os.path.join(root, dll)))
    return hits


def python_bindings() -> dict:
    """Disponibilité des liaisons COM Python (pas d'exécution)."""
    out = {}
    for mod in ("win32com.client", "comtypes.client"):
        try:
            __import__(mod)
            out[mod] = True
        except Exception:
            out[mod] = False
    return out


def main() -> int:
    data = {
        "progids": scan_progids(),
        "installed_products": scan_installed_products(),
        "autodesk_families": scan_autodesk_families(),
        "revit_dlls": scan_revit_dlls(),
        "python_bindings": python_bindings(),
        "winreg_available": HAS_WINREG,
    }

    print("=" * 68)
    print("SONDE INTEROPÉRABILITÉ AUTODESK (registre, sans lancer un logiciel)")
    print("=" * 68)

    print("\n[1] ProgID COM détectés (clé = pilote COM possible) :")
    for p, names in data["progids"]["found"].items():
        if names:
            print(f"    OK   {p}  ->  {names[:6]}")
        else:
            print(f"    ABSENT {p}")

    print("\n[2] Produits Autodesk installés :")
    for d in data["installed_products"]:
        print(f"    - {d}")
    if not data["installed_products"]:
        print("    (aucun trouvé)")

    print("\n[3] Familles HKLM\\SOFTWARE\\Autodesk :")
    print("    " + (", ".join(data["autodesk_families"]) or "(aucune)"))

    print("\n[4] Revit API .NET (.dll) :")
    for prod, dll, path in data["revit_dlls"]:
        print(f"    - {dll} ({prod})")
    if not data["revit_dlls"]:
        print("    (non trouvé)")

    print("\n[5] Liaisons COM Python :")
    for m, ok in data["python_bindings"].items():
        print(f"    {'OK    ' if ok else 'ABSENT'} {m}")

    if "--json" in sys.argv:
        print("\nJSON:\n" + json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
