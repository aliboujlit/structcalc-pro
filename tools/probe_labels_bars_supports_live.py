# -*- coding: utf-8 -*-
"""
tools/probe_labels_bars_supports_live.py — SONDAGE CIBLÉ v1.3 (20/10/2026).

3 défauts RÉELS constatés par la chaîne live plan-villa (v1.3.0) :
  A. Labels.GetAvailableNames : « This object does not support enumeration »
     -> materials=0, sections de label absentes (plan.py itérait en Python).
  B. Barres : plan.py trouvait 78/108 barres (serveur.Get(i) sur numéros
     non denses) alors que model.import_bars (collection TYPÉE GetAll().Get)
     lit les 108.
  C. Appuis : supports=0 silencieux — HasCalcSupport(n) en interne
     (except -> False muet) et node.GetLabelName(0) non ré-sondé ici.

Ce script RÉPOND, en live et sans écriture, à :
  - forme RÉELLE de GetAvailableNames(type) : Count/Get ? itérable ?
  - noms réels des labels sections/matériaux/appuis de la villa ;
  - énumération des barres : collection typée vs serveur.Get(i) (écart) ;
  - par nœud : HasCalcSupport(n) (résultat/exception) + GetLabelName(0).

Fermeture SANS sauvegarde (§5.4) de ce que le script a ouvert.

    chcp 65001 ; $env:PYTHONIOENCODING="utf-8" ; python -u tools\\probe_labels_bars_supports_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD_VILLA = (TEST_DIR / "Projet-Villa-avec-sous-sol" /
             "Projet Villa avec sous sol.rtd")

# Enums lues dans robotom.tlb (gen_py) — voir plan.py
LT_NODE_SUPPORT = 0
LT_BAR_SECTION = 3
LT_BAR_MATERIAL = 8


def banner(t: str) -> None:
    print()
    print("=" * 74)
    print(t)
    print("=" * 74, flush=True)


def _names(coll) -> tuple[list[str], str]:
    """Forme RÉELLE : Count/Get d'abord, itération Python ensuite."""
    try:
        n = int(coll.Count)
        try:
            return [str(coll.Get(i)) for i in range(1, n + 1)], "Count/Get"
        except Exception as exc:
            return [], f"Count={n} mais Get(i) KO : {exc}"
    except Exception:
        pass
    try:
        return [str(x) for x in coll], "iteration-python"
    except Exception as exc:
        return [], f"ni Count/Get ni iteration : {exc}"


def main() -> int:
    from structcalc.integration.interop import default_hub
    hub = default_hub()
    rconn = hub.get("robot")

    opened = False
    try:
        rconn.connect(timeout=300.0)
    except Exception as exc:
        print(f"[REFUS] Robot : {exc}")
        return 1
    rc = rconn.rc
    try:
        if rc.is_project_open:
            live = ""
            try:
                live = str(rc.app.Project.FileName or "")
            except Exception:
                live = ""
            if Path(live).resolve() == RTD_VILLA.resolve():
                rc.adopt_live_project()
                print("Villa déjà ouverte : ADOPTION (§5.4).")
            else:
                print(f"[REFUS] projet étranger ouvert (§5.4) : {live}")
                return 1
        else:
            print(f"Ouverture visible : {RTD_VILLA.name} ...")
            rc.open_project(str(RTD_VILLA))
            opened = True
        S = rc.structure

        # ==================================================================
        banner("A — Labels.GetAvailableNames : forme réelle + noms villa")
        # ==================================================================
        labels: dict[int, list[str]] = {}
        for ltype, nom in ((LT_NODE_SUPPORT, "appuis (I_LT_NODE_SUPPORT=0)"),
                           (LT_BAR_SECTION, "sections (I_LT_BAR_SECTION=3)"),
                           (LT_BAR_MATERIAL,
                            "matériaux (I_LT_BAR_MATERIAL=8)")):
            try:
                coll = S.Labels.GetAvailableNames(ltype)
                kind = type(coll).__name__
                names, via = _names(coll)
                labels[ltype] = names
                print(f"  [{nom}] type={kind} via={via} n={len(names)}")
                for nm in names:
                    print(f"      - {nm!r}")
            except Exception as exc:
                print(f"  [{nom}] APPEL KO : {type(exc).__name__}: {exc}")
        # Itération Python pure (le chemin plan.py actuel) — pour preuve :
        try:
            coll = S.Labels.GetAvailableNames(LT_BAR_SECTION)
            _ = [str(x) for x in coll]
            print("  iteration-python sections : OK")
        except Exception as exc:
            print(f"  iteration-python sections : ECHEC (constat chaine) :"
                  f" {type(exc).__name__}: {exc}")

        # ==================================================================
        banner("B — Barres : collection TYPÉE vs serveur.Get(i) (villa)")
        # ==================================================================
        bars = S.Bars
        coll = bars.GetAll()
        nb = int(coll.Count)
        print(f"  GetAll().Count = {nb}")
        typed: dict[int, tuple[int, int]] = {}
        try:
            first = coll.Get(1) if nb else None
        except Exception:
            first = None
        if first is not None and hasattr(first, "Number"):
            for i in range(1, nb + 1):
                br = coll.Get(i)
                typed[int(br.Number)] = (int(br.StartNode), int(br.EndNode))
            print(f"  collection TYPÉE GetAll().Get(i) : {len(typed)} barre(s)"
                  " — numéros : "
                  f"{sorted(typed)[:15]}{' ...' if len(typed) > 15 else ''}")
        else:
            print("  collection TYPÉE indisponible (Get(1) sans Number)")
        server_ok: list[int] = []
        server_ko: list[int] = []
        for i in range(1, nb + 1):
            try:
                b = bars.Get(i)
                _ = int(b.Number)
                server_ok.append(i)
            except Exception:
                server_ko.append(i)
        print(f"  serveur.Get(i) 1..{nb} : {len(server_ok)} OK,"
              f" {len(server_ko)} ECHEC")
        if server_ko:
            print(f"      numéros manqués (gaps) : {server_ko[:40]}"
                  f"{' ...' if len(server_ko) > 40 else ''}")
        if typed:
            miss = sorted(set(typed) - set(server_ok))
            print(f"      barres RÉELLES absentes du parcours plan.py :"
                  f" {len(miss)} -> {miss[:30]}{' ...' if len(miss) > 30 else ''}")

        # ==================================================================
        banner("C — Appuis : HasCalcSupport(n) + node.GetLabelName(0)")
        # ==================================================================
        nodes = S.Nodes
        colln = nodes.GetAll()
        nn = int(colln.Count)
        print(f"  GetAll().Count = {nn}")
        rows = []
        err_h: dict[str, int] = {}
        err_l: dict[str, int] = {}
        for i in range(1, nn + 1):
            try:
                nd = colln.Get(i)
            except Exception:
                continue
            num = int(nd.Number)
            h_raw, h_err = None, ""
            try:
                h_raw = nodes.HasCalcSupport(num)
            except Exception as exc:
                h_err = f"{type(exc).__name__}: {exc}"
            lname, l_err = "", ""
            try:
                lname = str(nd.GetLabelName(LT_NODE_SUPPORT) or "")
            except Exception as exc:
                l_err = f"{type(exc).__name__}: {exc}"
            if h_err:
                err_h[h_err] = err_h.get(h_err, 0) + 1
            if l_err:
                err_l[l_err] = err_l.get(l_err, 0) + 1
            truthy = bool(h_raw) if not h_err else False
            if truthy or lname:
                rows.append((num, h_raw, lname))
        print(f"  HasCalcSupport : {nn - sum(err_h.values())}/{nn} appel(s)"
              f" sans exception ; résultats TRUTHY ou label non vide :"
              f" {len(rows)}")
        for num, h_raw, lname in rows[:20]:
            print(f"      nœud {num}: HasCalcSupport={h_raw!r}"
                  f"  GetLabelName(0)={lname!r}")
        if err_h:
            print(f"  exceptions HasCalcSupport : {err_h}")
        if err_l:
            print(f"  exceptions GetLabelName(0) : {err_l}")
        # Echantillon des 5 premiers nœuds quoi qu'il arrive (réponse nette)
        print("  échantillon nœuds 1..5 :")
        for i in range(1, min(5, nn) + 1):
            try:
                nd = colln.Get(i)
                num = int(nd.Number)
                try:
                    h = nodes.HasCalcSupport(num)
                except Exception as exc:
                    h = f"EXC {type(exc).__name__}: {exc}"
                try:
                    ln = str(nd.GetLabelName(LT_NODE_SUPPORT) or "")
                except Exception as exc:
                    ln = f"EXC {type(exc).__name__}: {exc}"
                print(f"      nœud {num}: HasCalcSupport={h!r}"
                      f"  label={ln!r}")
            except Exception as exc:
                print(f"      nœud(i={i}) KO : {exc}")

        banner("SYNTHESE (ce que le correctif devra utiliser)")
        print(f"  A labels sections={len(labels.get(LT_BAR_SECTION, []))}"
              f" materiaux={len(labels.get(LT_BAR_MATERIAL, []))}"
              f" appuis={len(labels.get(LT_NODE_SUPPORT, []))}")
        print(f"  B barres réelles={len(typed)} parcours plan.py="
              f"{len(server_ok)}")
        print(f"  C nœuds avec appui (signal réel)={len(rows)}")
        return 0
    finally:
        try:
            if opened:
                rc.close_project(save=False)
                print("\nVilla fermee SANS sauvegarde (S5.4).")
        except Exception as exc:
            print(f"\n[ERREUR] fermeture : {exc}")
        try:
            rconn.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
