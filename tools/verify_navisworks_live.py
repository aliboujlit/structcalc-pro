# -*- coding: utf-8 -*-
"""
tools/verify_navisworks_live.py — Preuve d'exécution du pont Navisworks.

Le connecteur affirme (§19) que OpenFile/SaveAs sont VÉRIFIÉS. La sonde
probe_nw_discover a prouvé qu'ils EXISTAIENT (getattr) mais pas qu'ils
MARCHAIENT. Ici on exécute le pont RÉEL inter-logiciels :

    AutoCAD  --(capacité déjà vérifiée)-->  modele.dwg
    Navisworks --OpenFile(dwg)--> SaveAs--> modele.nwd

On vérifie ensuite que le fichier NWD EXISTE sur disque et n'est pas vide.
(.nwd est le format document VÉRIFIÉ ; .nwc échoue — c'est un cache, cf.
tools/probe_nw_saveas.py)
Aucun résultat n'est supposé : l'existence du fichier tranche.

Usage : python tools/verify_navisworks_live.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

WORK = os.path.join(os.environ.get("TEMP", "."), "sc_nw_live")
DWG = os.path.join(WORK, "sc_nw_source.dwg")
NWD = os.path.join(WORK, "sc_nw_result.nwd")   # .nwd = format VÉRIFIÉ (pas .nwc)


def say(msg):
    print(msg)
    sys.stdout.flush()


def build_dwg() -> bool:
    """Produit un DWG réel via le connecteur AutoCAD (retry/backoff intégré).

    Le Dispatch nu échoue en CO_E_SERVER_EXEC_FAILURE tant que le serveur
    s'enregistre : c'est le piège déjà géré par AutoCADConnector.connect().
    """
    from structcalc.integration.interop import AutoCADConnector
    import pythoncom as pc
    import win32com.client as wc

    ac = AutoCADConnector()
    ac.connect(timeout=120.0)   # attach/launch AVEC retry
    try:
        app = ac.app

        def v6(vals):
            return wc.VARIANT(pc.VT_ARRAY | pc.VT_R8, list(vals))

        doc = app.Documents.Add()
        ms = doc.ModelSpace
        # 2 poutres + 1 diagonale (VARIANT points, forme vérifiée)
        ms.AddLine(v6([0.0, 0.0, 0.0]), v6([6.0, 0.0, 0.0]))
        ms.AddLine(v6([0.0, 4.0, 0.0]), v6([6.0, 4.0, 0.0]))
        ms.AddLine(v6([0.0, 0.0, 0.0]), v6([0.0, 4.0, 3.0]))
        doc.SaveAs(DWG, 24)   # AC1018 (code vérifié)
        # Close peut lever CALL_REJECTED (transitoire, documenté) : le DWG
        # est DÉJÀ enregistré, on ne fait pas échouer la production pour ça.
        try:
            doc.Close(False)
        except Exception as exc:
            say(f"    (Close non bloquant : {type(exc).__name__})")
        say(f"    DWG produit : {os.path.getsize(DWG)} octets")
        return os.path.isfile(DWG) and os.path.getsize(DWG) > 0
    finally:
        ac.disconnect()


def nw_bridge() -> dict:
    """OpenFile(dwg) -> SaveAs(nwd) via le connecteur Navisworks."""
    from structcalc.integration.interop import NavisworksConnector

    out = {}
    nw = NavisworksConnector()
    det = nw.detect()
    out["installed"] = det.installed
    out["progs"] = list(det.progs)
    say(f"    detect : installed={det.installed} progs={det.progs}")

    if not det.installed:
        out["ok"] = False
        out["reason"] = "Navisworks non installé"
        return out

    t0 = time.time()
    say("    connect (~20s, lance Roamer.exe)...")
    try:
        nw.connect(timeout=120.0)
    except Exception as exc:
        out["ok"] = False
        out["reason"] = f"connect KO : {type(exc).__name__}: {exc}"
        return out
    out["connect_s"] = round(time.time() - t0, 1)
    say(f"    connect OK en {out['connect_s']}s (progid={getattr(nw,'_progid_used','?')})")

    try:
        say("    OpenFile(dwg)...")
        r_open = nw.open_file(DWG)
        out["open"] = r_open.to_dict()
        say(f"      -> {r_open.status} : {r_open.message[:110]}")

        if not r_open.ok:
            out["ok"] = False
            out["reason"] = "OpenFile refusé/échoué"
            return out

        # Navisworks charge le modèle en arrière-plan : on réessaie SaveAs
        say("    SaveAs(nwd) avec retry (chargement asynchrone éventuel)...")
        r_save = None
        for attempt in range(1, 11):
            r_save = nw.save_as(NWD)
            exists = os.path.isfile(NWD) and os.path.getsize(NWD) > 0
            say(f"      essai {attempt}: {r_save.status} "
                f"(fichier={exists})")
            if attempt == 1:
                say(f"      MESSAGE COMPLET : {r_save.message}")
            if r_save.ok and exists:
                break
            time.sleep(3.0)
        out["save"] = r_save.to_dict()
        out["nwd_exists"] = os.path.isfile(NWD)
        out["nwd_size"] = os.path.getsize(NWD) if out["nwd_exists"] else 0
        out["ok"] = bool(r_save.ok and out["nwd_size"] > 0)
        if not out["ok"]:
            out["reason"] = "SaveAs non confirmé par fichier produit"
        return out
    finally:
        nw.disconnect()
        say("    disconnect (sans quitter Navisworks, §5.4)")


def main() -> int:
    say("=" * 74)
    say("PREUVE LIVE — pont AutoCAD(DWG) -> Navisworks -> NWD")
    say("=" * 74)
    os.makedirs(WORK, exist_ok=True)
    for f in (DWG, NWD):
        if os.path.isfile(f):
            os.remove(f)

    say("\n[1] AutoCAD : production d'un DWG réel")
    if not build_dwg():
        say("    ECHEC : impossible de produire le DWG de test")
        say("\nRESULTAT : ECHEC (source indisponible)")
        return 1

    say("\n[2] Navisworks : OpenFile -> SaveAs")
    out = nw_bridge()

    say("\n" + "=" * 74)
    say("RESULTAT")
    say("=" * 74)
    say(f"    installed   : {out.get('installed')}")
    say(f"    connect     : {out.get('connect_s', '-')}s")
    if "open" in out:
        say(f"    open_file   : {out['open']['status']}")
    if "save" in out:
        say(f"    save_as     : {out['save']['status']}")
    say(f"    NWD produit : {out.get('nwd_exists')} "
        f"({out.get('nwd_size', 0)} octets)")

    if out.get("ok"):
        say("\nSUCCES : le pont DWG -> NWD est RÉELLEMENT exécuté.")
        say("Navisworks est donc un nœud FONCTIONNEL du maillage (coordination).")
        return 0
    say(f"\nECHEC : {out.get('reason', 'inconnu')}")
    say("(aucun succès simulé — §19)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
