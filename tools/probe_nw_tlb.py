# -*- coding: utf-8 -*-
"""
tools/probe_nw_tlb.py — Enumération de la bibliothèque de types Navisworks.

Découverte : Navisworks 2027 livre `roamer.tlb` (bibliothèque de types COM) et
les assemblies officiels `Autodesk.Navisworks.Interop.ComApi(.Automation).dll`.
La sonde précédente marquait tous les membres « absents » car ma signature
GetIDsOfNames était fausse. Ici on lit la TLB : la liste des interfaces/méthodes
est la RÉALITÉ du COM, observée, jamais supposée.

Usage : python tools/probe_nw_tlb.py
"""
from __future__ import annotations

import os
import sys

TLB = r"C:\Program Files\Autodesk\Navisworks Manage 2027\roamer.tlb"
INTEROP = (r"C:\Program Files\Autodesk\Navisworks Manage 2027"
           r"\Autodesk.Navisworks.Interop.ComApiAutomation.dll")

# Mots-clés pertinents pour un pont structure/coordination
KEEP = ("document", "app", "file", "open", "save", "export", "model",
        "selection", "item", "propert", "version", "name", "visible",
        "clash", "geometry", "transform", "bounding", "load", "active",
        "state", "control", "automation", "command", "batch")


def main() -> int:
    print("=" * 74)
    print("TLB NAVISWORKS — roamer.tlb (bibliothèque de types COM)")
    print("=" * 74)
    if not os.path.isfile(TLB):
        print("  ABSENT :", TLB)
        return 1
    print(f"  fichier : {TLB}  ({os.path.getsize(TLB)} octets)")

    import comtypes
    import comtypes.client

    try:
        mod = comtypes.client.GetModule(TLB)
    except Exception as exc:
        print(f"  GetModule KO : {type(exc).__name__}: {exc}")
        return 1

    # Collecter les interfaces / coclasses du module généré
    ifaces = []
    for name in dir(mod):
        obj = getattr(mod, name)
        kind = type(obj).__name__
        if "Dual" in kind or "Dispatch" in kind or "IUnknown" in kind:
            members = [m for m in dir(obj)
                       if not m.startswith("_") and m not in
                       ("AddRef", "Release", "QueryInterface", "GetTypeInfoCount",
                        "GetTypeInfo", "GetIDsOfNames", "Invoke")]
            ifaces.append((name, kind, members))
        elif "Class" in kind or "coclass" in name.lower():
            ifaces.append((name, kind, []))

    print(f"\n  {len(ifaces)} interfaces/coclasses détectés\n")

    # 1) Tous les noms (aperçu)
    print("  --- noms des interfaces ---")
    for n, k, _ in sorted(ifaces):
        print(f"      {n:<48} [{k}]")

    # 2) Les membres des interfaces pertinentes
    print("\n  --- membres des interfaces pertinentes ---")
    for n, k, members in sorted(ifaces):
        low = n.lower()
        if any(t in low for t in KEEP) and members:
            print(f"\n      [{n}] ({len(members)} membres)")
            for m in sorted(members):
                print(f"          .{m}")

    # 3) CoClasses (ce qu'on peut instancier / rattacher)
    print("\n  --- coclasses (instanciables) ---")
    for n, k, _ in sorted(ifaces):
        if "Class" in k:
            print(f"      {n}")

    # 4) Repérer l'objet racine d'automation
    print("\n  --- recherche point d'entrée automation ---")
    hits = [(n, m) for n, _, ms in ifaces for m in ms
            if m.lower() in ("application", "documents", "controls",
                             "automation", "activecontrol")]
    if hits:
        for n, m in sorted(hits):
            print(f"      {n}.{m}")
    else:
        print("      (aucun membre 'Application/Documents' nommé ainsi)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
