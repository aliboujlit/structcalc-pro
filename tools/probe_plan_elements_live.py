# -*- coding: utf-8 -*-
"""
probe_plan_elements_live.py — Sondage LIVE (lecture seule) des éléments du
modèle Robot : storeys, materials/sections (labels), charges (records), types
structurels des barres, enums robotom.tlb.

Rôle (spec §19) : découvrir les MEMBRES RÉELLEMENT EXISTANTS de RobotOM 2027
avant d'écrire le lecteur plan (aucune API inventée). Aucune écriture dans
Robot (lecture seule + fermeture sans save de ce que le programme ouvre).

Sortie : %TEMP%\\probe_plan_elements.txt (UTF-8).
"""

from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from structcalc.integration.robot import connection as rconn  # noqa: E402

VILLA = (r"C:\Users\Admin\Desktop\projets de test\Projet-Villa-avec-sous-sol"
         r"\Projet Villa avec sous sol.rtd")
OUT = os.path.join(os.environ.get("TEMP", "."), "probe_plan_elements.txt")

out_lines: list[str] = []


def w(s: str = "") -> None:
    out_lines.append(str(s))


def section(title: str) -> None:
    w()
    w("=" * 20 + " " + title + " " + "=" * 20)


def dump_dir(obj, label: str) -> None:
    section(label)
    try:
        names = [n for n in dir(obj) if not n.startswith("_")]
        w(" | ".join(names))
    except Exception as exc:
        w(f"dir() impossible : {exc!r}")


def try_attr(obj, attr: str, label: str) -> object | None:
    """Tente obj.attr (propriété ou méthode) et journalise le résultat."""
    try:
        val = getattr(obj, attr)
        w(f"{label}.{attr} = {val!r}")
        return val
    except Exception as exc:
        w(f"{label}.{attr} -> {type(exc).__name__}: {exc}")
        return None


def try_call(obj, attr: str, args, label: str) -> object | None:
    try:
        fn = getattr(obj, attr)
        val = fn(*args)
        w(f"{label}.{attr}{args!r} = {val!r}")
        return val
    except Exception as exc:
        w(f"{label}.{attr}{args!r} -> {type(exc).__name__}: {exc}")
        return None


def main() -> int:
    rc = rconn.RobotConnection(visible=True)
    try:
        rc.connect(timeout=240.0)
    except Exception as exc:
        w(f"connect() KO : {exc}")
        traceback.print_exc(file=sys.stderr)
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out_lines))
        return 2

    opened = False
    try:
        cur = ""
        try:
            cur = str(rc.project.FileName or "")
        except Exception:
            pass
        if "villa" in cur.lower() and rc.is_project_open:
            w(f"Adoption du projet deja ouvert : {cur}")
        else:
            w(f"Ouverture du fichier : {VILLA}")
            rc.open_project(VILLA)
            opened = True
        w(f"Projet ouvert : {rc.is_project_open}")

        S = rc.structure
        app = rc.app

        dump_dir(app, "APP DIR")
        dump_dir(S, "STRUCTURE DIR")
        dump_dir(rc.project, "PROJECT DIR")

        # --- storeys ---------------------------------------------------
        section("STOREYS CANDIDATES")
        for name in ("Storeys", "BuildingStoreys", "Levels", "Stories"):
            try_attr(S, name, "structure")
            try_attr(app, name, "app")
        try_attr(rc.project, "Model", "project")

        # --- materials / sections (labels) -----------------------------
        section("MATERIALS / SECTIONS")
        for name in ("Materials", "Sections", "Labels", "BarLabels",
                     "ReinforcementBars", "DesignSections"):
            try_attr(S, name, "structure")

        # --- cas de charge + records -----------------------------------
        section("CASE RECORDS")
        cases = None
        try:
            cases = S.Cases
            dump_dir(cases, "CASES DIR")
            n = int(cases.GetAll().Count)
            w(f"GetAll().Count = {n}")
            for i in range(1, min(n, 11) + 1):
                c = cases.Get(i)
                w(f"case[{i}] name={getattr(c, 'Name', '')!r}")
                if i == 1:
                    dump_dir(c, "CASE[1] DIR")
                    recs = None
                    try:
                        recs = c.Records
                        dump_dir(recs, "CASE[1] RECORDS DIR")
                        for meth in ("Count", "GetAll", "GetIndex", "GetId"):
                            try_attr(recs, meth, "records")
                        nrec = None
                        try:
                            nrec = int(recs.GetAll().Count)
                        except Exception:
                            try:
                                nrec = int(recs.Count)
                            except Exception:
                                pass
                        w(f"records count = {nrec!r}")
                        if nrec:
                            r1 = recs.Get(1)
                            dump_dir(r1, "RECORD[1] DIR")
                            for prop in ("Type", "Number", "Kind", "Value",
                                         "Unity", "Name", "CaseName",
                                         "Objects", "Description"):
                                try_attr(r1, prop, "record[1]")
                    except Exception as exc:
                        w(f"records KO : {exc!r}")
        except Exception as exc:
            w(f"cases KO : {exc!r}")

        # --- barres : type structurel + labels -------------------------
        section("BAR STRUCTURAL + LABELS")
        try:
            bars = S.Bars
            dump_dir(bars, "BARS DIR")
            n = int(bars.GetAll().Count)
            w(f"bars GetAll().Count = {n}")
            for i in (1, 2, 5, n):
                try:
                    b = bars.Get(i)
                    dump_dir(b, f"BAR[{i}] DIR")
                    for prop in ("StructuralType", "StartNode", "EndNode"):
                        try_attr(b, prop, f"bar[{i}]")
                    for lab in (0, 3):
                        try_call(b, "GetLabelName", (lab,), f"bar[{i}]")
                    try_call(b, "GetLabel", (0,), f"bar[{i}]")
                except Exception as exc:
                    w(f"bar[{i}] KO : {exc!r}")
        except Exception as exc:
            w(f"bars KO : {exc!r}")

        # --- nœuds : appuis --------------------------------------------
        section("NODE SUPPORTS")
        try:
            nodes = S.Nodes
            dump_dir(nodes, "NODES DIR")
            nd = nodes.Get(1)
            dump_dir(nd, "NODE[1] DIR")
            for prop in ("HasCalcSupport", "CalcSupport", "Type"):
                try_attr(nd, prop, "node[1]")
            try_call(nd, "HasCalcSupport", (), "node[1]")
            try_call(nd, "GetCalcSupport", (), "node[1]")
        except Exception as exc:
            w(f"nodes KO : {exc!r}")

        # --- enums robotom.tlb (gen_py) --------------------------------
        section("TLB ENUMS")
        try:
            gen_path = getattr(__import__("win32com"), "__gen_path__", "")
            w(f"gen_path = {gen_path!r}")
            for root, _dirs, files in os.walk(gen_path):
                for fn in files:
                    if fn.endswith(".py") and ("0002" not in root or True):
                        p = os.path.join(root, fn)
                        try:
                            with open(p, "r", encoding="utf-8",
                                      errors="replace") as fh:
                                txt = fh.read()
                        except Exception:
                            continue
                        if "IRobotLabelType" in txt or "RobotLoadRecordType" in txt:
                            w(f"--- {p} ---")
                            for line in txt.splitlines():
                                if any(k in line for k in (
                                        "I_LT_", "BST_", "_BST", "I_LRT_",
                                        "IRobotBarStructuralType =",
                                        "IRobotLabelType =", "NODE_TYPE",
                                        "I_NT_", "I_CN_", "I_CBT_")):
                                    w(line.strip())
        except Exception as exc:
            w(f"enums KO : {exc!r}")

    except Exception:
        w("ERREUR GENERALE :")
        w(traceback.format_exc())
    finally:
        try:
            if opened:
                rc.close_project(save=False)
                w("close_project(save=False) — de ce que le programme a ouvert.")
            rc.disconnect(quit_app=True)
            w("disconnect(quit_app=True).")
        except Exception as exc:
            w(f"fermeture KO : {exc!r}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines))
    print("PROBE OK ->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
