# -*- coding: utf-8 -*-
"""
tools/probe_nw_step.py — Localisation du crash COM Navisworks (pas à pas).

Le Dispatch seul fonctionnait (probe_civil3d_nw_fix : Visible=False lu).
Le lancement complet plante en natif. On isole l'étape fautife avec flush
explicite à chaque étape. Aucune méthode supposée.

Usage : python tools/probe_nw_step.py
"""
from __future__ import annotations

import sys


def say(msg):
    print(msg)
    sys.stdout.flush()


def main():
    say("Etape 0 : import")
    import pythoncom
    import win32com.client
    say("Etape 1 : CoInitialize")
    pythoncom.CoInitialize()
    say("Etape 2 : Dispatch Navisworks.Document.24")
    obj = win32com.client.Dispatch("Navisworks.Document.24")
    say("Etape 3 : Dispatch OK, type=" + type(obj).__name__)

    # propriétés lisibles via getattr (= GetIDsOfNames réel)
    say("Etape 4 : getattr('Visible')")
    try:
        v = obj.Visible
        say("    Visible = " + repr(v))
    except Exception as exc:
        say("    Visible KO : " + type(exc).__name__)

    say("Etape 5 : getattr('Name')")
    try:
        say("    Name = " + repr(obj.Name))
    except Exception as exc:
        say("    Name KO : " + type(exc).__name__)

    say("Etape 6 : _oleobj_")
    try:
        ole = obj._oleobj_
        say("    ole = " + repr(ole))
    except Exception as exc:
        say("    _oleobj_ KO : " + type(exc).__name__)
        ole = None

    if ole is not None:
        say("Etape 7 : GetTypeInfo()")
        try:
            ti = ole.GetTypeInfo()
            say("    ti = " + repr(ti))
        except Exception as exc:
            say("    GetTypeInfo KO : " + type(exc).__name__)
            ti = None
        if ti is not None:
            say("Etape 8 : GetTypeAttr()")
            try:
                attr = ti.GetTypeAttr()
                say("    cFuncs=" + str(attr.cFuncs)
                    + " typekind=" + str(int(attr.typekind)))
            except Exception as exc:
                say("    GetTypeAttr KO : " + type(exc).__name__)

    say("Etape 9 : Release")
    try:
        obj = None
        say("    release OK")
    except Exception as exc:
        say("    release KO " + type(exc).__name__)

    say("Etape 10 : CoUninitialize")
    try:
        pythoncom.CoUninitialize()
        say("    OK")
    except Exception as exc:
        say("    KO " + type(exc).__name__)

    say("TERMINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
