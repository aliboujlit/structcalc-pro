# -*- coding: utf-8 -*-
"""
tools/probe_nw_saveas.py — Diagnostic SaveAs Navisworks (une seule session).

Constat live : OpenFile(dwg) OK mais SaveAs(.nwc) -> « Failed to save
document » (odviewdll_clr). Deux hypothèses à trancher SANS relancer
Navisworks à chaque fois :
  H1 : le modèle n'est pas encore chargé (chargement asynchrone) -> attendre ;
  H2 : .nwc n'est pas une cible SaveAs d'un DOCUMENT (c'est un cache),
       alors que .nwd EST le format document -> tester .nwd.

On teste .nwd et .nwc dans la même session, avec attente progressive.

Usage : python tools/probe_nw_saveas.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

WORK = os.path.join(os.environ.get("TEMP", "."), "sc_nw_live")
DWG = os.path.join(WORK, "sc_nw_source.dwg")
NWD = os.path.join(WORK, "sc_nw_result.nwd")
NWC = os.path.join(WORK, "sc_nw_result.nwc")


def say(m):
    print(m)
    sys.stdout.flush()


def try_save(nw, path, label):
    if os.path.isfile(path):
        os.remove(path)
    r = nw.save_as(path)
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    say(f"    SaveAs({label}) -> {r.status} fichier={exists}")
    if not r.ok:
        # extraire le cœur du message d'erreur COM
        msg = r.message
        if "Failed" in msg or "exception" in msg.lower():
            say(f"        err: ...{msg[-120:]}")
    return exists


def main():
    from structcalc.integration.interop import NavisworksConnector

    say("=" * 74)
    say("DIAGNOSTIC SaveAs Navisworks (.nwd vs .nwc + attente)")
    say("=" * 74)
    if not os.path.isfile(DWG):
        say(f"DWG absent ({DWG}) : relancer verify_navisworks_live d'abord")
        return 1
    say(f"DWG source : {os.path.getsize(DWG)} octets")

    nw = NavisworksConnector()
    say("connect (~20-70s)...")
    nw.connect(timeout=120.0)
    say("connect OK")
    try:
        r = nw.open_file(DWG)
        say(f"OpenFile -> {r.status}")
        if not r.ok:
            say("ABANDON : OpenFile échoue")
            return 1

        # H1 : attente de chargement, puis H2 : .nwd puis .nwc
        for wait in (0, 15, 30):
            if wait:
                say(f"  ...attente {wait}s (chargement asynchrone)")
                time.sleep(wait)
            say(f"  -- tentative (attente cumulée ~{wait}s) --")
            ok_nwd = try_save(nw, NWD, ".nwd")
            ok_nwc = try_save(nw, NWC, ".nwc")
            if ok_nwd or ok_nwc:
                say(f"\nSUCCES : nwd={ok_nwd} nwc={ok_nwc}")
                say("Verdict : " + ("SaveAs fonctionne (.nwd viable)"
                                    if ok_nwd else ".nwc viable"))
                return 0

        say("\nECHEC persistent : ni .nwd ni .nwc après attentes")
        return 1
    finally:
        nw.disconnect()
        say("disconnect")


if __name__ == "__main__":
    raise SystemExit(main())
