# -*- coding: utf-8 -*-
"""
tools/probe_nw_discover.py — Découverte des membres CALLABLES de Navisworks.

Leçon des sondes précédentes :
  - Seul Navisworks.Document.24 (Local/Roamer) est sûr ; les coclasses Inproc
    (lcodieD.dll) plantent en natif, on ne les touche pas.
  - Il n'y a PAS de typeinfo -> GetIDsOfNames/typeinfo inopérants.
  - Je filtrais à tort les membres appelables : une mthode Open/Save/Export
    est CALLABLE et donc était ignoree. Ici on teste chaque nom via getattr
    et on note valeur OU callable.

Aucune mthode n'est supposee : le COM confirme ou infirme chaque nom.

Usage : python tools/probe_nw_discover.py
"""
from __future__ import annotations

import sys

# Noms candidats testes (decouverte, pas d'invention)
CANDIDATES = (
    # application / document
    "Name", "Version", "Caption", "Visible", "FileName", "FullName", "Path",
    "ActiveDocument", "Documents", "Application", "Parent", "Control",
    # actions document
    "Open", "Save", "SaveAs", "Close", "New", "Append", "Merge", "Reload",
    "Export", "Clear", "Focus", "ZoomExtents", "Redraw", "Update",
    # version 24 spcifique Navisworks (batch)
    "OpenFile", "SaveFile", "SaveAsFile", "LoadFile", "CurrentFile",
    # selection / proprit
    "SelectedItems", "CurrentSelection", "Properties", "ObjectFactory",
    "CreateData", "Data", "Clash", "Comments", "Items", "Count", "Value",
    # automation classique
    "Quit", "Exit", "Execute", "Command", "Run", "DoFile", "Batch",
)


def say(msg):
    print(msg)
    sys.stdout.flush()


def discover(obj, label):
    say("")
    say("--- " + label)
    callables_found = []
    values_found = []
    missing = []
    for n in CANDIDATES:
        try:
            v = getattr(obj, n)
        except AttributeError:
            missing.append(n)
            continue
        except Exception as exc:
            say("    " + n + " : erreur " + type(exc).__name__)
            continue
        if callable(v):
            # compter les paramtres si possible (sans appeler)
            try:
                import inspect
                params = len(inspect.signature(v).parameters)
            except Exception:
                params = "?"
            callables_found.append((n, params))
            say("    CALLABLE  " + n + "   (params=" + str(params) + ")")
        else:
            values_found.append((n, repr(v)[:70]))
            say("    VALEUR    " + n + " = " + repr(v)[:70])
    return callables_found, values_found, missing


def main():
    import pythoncom
    import win32com.client

    say("Import + CoInitialize")
    pythoncom.CoInitialize()
    say("Dispatch Navisworks.Document.24 (~20s, lance Roamer)")
    obj = win32com.client.Dispatch("Navisworks.Document.24")
    say("OK type=" + type(obj).__name__)

    callables_found, values_found, missing = discover(
        obj, "Navisworks.Document.24")

    say("")
    say("=" * 74)
    say("SYNTHESE")
    say("=" * 74)
    say("CALLABLES : " + str([c[0] for c in callables_found]))
    say("VALEURS   : " + str([v[0] for v in values_found]))
    say("absents   : " + str(missing))

    # Tentative BLOQUANTE : si 'Open' existe, l'essayer est RUPTURISTE.
    # On n'appelle RIEN de destructif ici. On se contente de la dcouverte.

    obj = None
    pythoncom.CoUninitialize()
    say("TERMINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
