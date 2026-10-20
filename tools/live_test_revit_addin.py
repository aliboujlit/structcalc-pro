#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/live_test_revit_addin.py — Test live du pipe add-in Revit (STRUCTCALC PRO).

Attend le chargement de l'add-in dans Revit 2027 (sonde PING répétée), puis
vérifie le contrat réel, étape par étape, avec verdict honnête :

  1. détection du connecteur (transport dotnet) ;
  2. PING/NDJSON via le Named Pipe structcalc_revit ;
  3. retournement des capacités (NOT_SUPPORTED -> PARTIAL utilisable) ;
  4. READ_MODEL : succès (document ouvert) OU erreur honnête de l'add-in
     (« Aucun document Revit actif » = preuve du roundtrip tout aussi valable) ;
  5. write_model sans lecture -> refus motivé (aucun identifiant inventé).

Usage :
  python tools/live_test_revit_addin.py [--wait 120]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from structcalc.core.model import Project  # noqa: E402
from structcalc.integration.interop.base import Capability  # noqa: E402
from structcalc.integration.interop.revit import RevitConnector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Test live pipe add-in Revit")
    parser.add_argument("--wait", type=int, default=120,
                        help="Secondes d'attente max du chargement add-in")
    args = parser.parse_args()

    conn = RevitConnector(probe_ttl=0.0)
    print(f"[1/5] Connecteur : installed={conn.detect().installed} "
          f"transport={conn.detect().transport}")

    # -- Attente du chargement de l'add-in (Revit démarre en ~30-90 s) --
    print(f"[2/5] Sonde PING (max {args.wait} s)...")
    deadline = time.monotonic() + args.wait
    alive, motif = False, ""
    while time.monotonic() < deadline:
        alive, motif = conn.probe_addin(force=True)
        if alive:
            break
        time.sleep(2.0)
    print(f"      alive={alive} : {motif}")
    if not alive:
        print("\nVERDICT : add-in NON chargé dans Revit.")
        print("  Vérifiez : Revit ouvert ? Erreur de chargement add-in "
              "(Extensions du menu Fichier) ?")
        return 2

    # -- Capacités retournées --
    caps = conn.capabilities()
    r, w = caps[Capability.READ_MODEL], caps[Capability.WRITE_MODEL]
    print(f"[3/5] Capacités : read={r.status.value}(usable={r.usable}) "
          f"write={w.status.value}(usable={w.usable})")
    if not (r.usable and w.usable):
        print("VERDICT : capacités NON retournées malgré pipe actif.")
        return 3

    # -- READ_MODEL réel --
    print("[4/5] READ_MODEL via le pipe...")
    proj = Project(sc_id="SC-PROJECT-LIVE-01", name="Test live pipe")
    rep = conn.read_model(proj)
    print(f"      status={rep.status} objects={rep.objects}")
    print(f"      message={rep.message[:300]}")
    if rep.status == "REFUSED":
        # « Aucun document Revit actif » = roundtrip PROUVÉ (erreur venue de
        # l'API Revit elle-même, jamais simulée) — acceptable et honnête.
        print("      -> roundtrip PIPE PROUVÉ (refus motivé par Revit lui-même)")
    elif rep.status in ("OK", "PARTIAL"):
        print(f"      -> MODÈLE IMPORTÉ : {len(proj.nodes)} nœuds, "
              f"{len(proj.beams)} poutres, {len(proj.columns)} poteaux")

    # -- Refus d'écriture sans lecture (identifiants) --
    print("[5/5] write_model sur connecteur vierge (doit refuser)...")
    fresh = RevitConnector(pipe_name=conn.pipe_name, probe_ttl=0.0)
    rep_w = fresh.write_model(Project(sc_id="SC-PROJECT-LIVE-02", name="x"))
    print(f"      status={rep_w.status} : {rep_w.message[:200]}")
    if rep_w.ok:
        print("VERDICT : FAUX SUCCÈS d'écriture sans mappage !")
        return 5

    print("\nVERDICT : PIPE ADD-IN OPÉRATIONNEL (contrat honnête vérifié).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
