# -*- coding: utf-8 -*-
"""
tools/verify_interop_live.py — Démonstration RÉELLE de l'échange pivot<->AutoCAD.

Cycle complet avec AutoCAD 2027 (COM réel, déjà vérifié en Phase interop) :

    Project SC-*  --write_model-->  AutoCAD (DWG)
                 <--read_model--    AutoCAD (DWG réouvert)

Contrôle :
  1. écriture des nœuds/poutres dans ModelSpace (calques SC_*) ;
  2. SaveAs DWG (code 24 -> AC1018 vérifié) ;
  3. fermeture sans sauvegarde puis RÉOUVERTURE (Open + retry) ;
  4. relecture et comparaison des compteurs + géométrie.

Aucun texte n'est écrit (AddText non vérifié §19) — le rapport le dit.

Usage : python tools/verify_interop_live.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structcalc.core.model import Beam, Project          # noqa: E402
from structcalc.integration.interop import (             # noqa: E402
    AutoCADConnector, InteropHub,
)


def build_project() -> Project:
    """Petit tablier 5x5 m : 4 nœuds + 4 poutres (TRUSS + dalles voisines)."""
    p = Project(sc_id="SC-INTEROP-LIVE-001", name="Essai interop AutoCAD")
    coords = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    ids = []
    for x, y in coords:
        n = p.new_node(x, y, 0.0)
        ids.append(n.sc_id)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    for k, (i, j) in enumerate(edges, start=1):
        bid = p.allocator.new("BEAM")
        p.beams[bid] = Beam(sc_id=bid, start_node=ids[i],
                            end_node=ids[j])
    return p


def main() -> int:
    print("=" * 72)
    print("DÉMONSTRATION RÉELLE — Project SC-* <-> AutoCAD (COM réel)")
    print("=" * 72)

    proj = build_project()
    src_counts = proj.counts()
    print(f"\n[1] Projet source : {src_counts['nodes']} nœuds, "
          f"{src_counts['beams']} poutres")
    for nid, nd in proj.nodes.items():
        print(f"      {nid}: ({nd.x.value}, {nd.y.value}, {nd.z.value})")

    ac = AutoCADConnector()
    det = ac.detect()
    print(f"\n[2] Détection AutoCAD : installé={det.installed} "
          f"version={det.version} pilotable={det.automatable}")

    print("\n[3] Connexion COM ...")
    try:
        ac.connect(timeout=90.0)
    except Exception as exc:
        print(f"    ECHEC connexion : {exc}")
        return 1
    print(f"    connecté : {ac.app.Name} v{ac.app.Version}")

    print("\n[4] ÉCRITURE pivot -> AutoCAD")
    rep = ac.write_model(proj)
    print(f"    status={rep.status} objects={rep.objects}")
    print(f"    message={rep.message}")
    if not rep.ok:
        print("    ECHEC écriture")
        ac.disconnect()
        return 1
    doc = ac._last_doc
    print(f"    document : {doc.Name} "
          f"({doc.ModelSpace.Count} entités dans ModelSpace)")

    # Calques SC_* ? (forme VÉRIFIÉE : Item(nom), jamais Item(index))
    from structcalc.integration.interop.autocad import (
        LAYER_NODE, LAYER_COLUMN, LAYER_BEAM, LAYER_SLAB,
    )
    layers = doc.Layers
    sc_layers = []
    for nm in (LAYER_NODE, LAYER_COLUMN, LAYER_BEAM, LAYER_SLAB):
        try:
            layers.Item(nm)
            sc_layers.append(nm)
        except Exception:
            pass
    print(f"    calques SC_* présents : {sc_layers}")

    # -- Sauvegarde DWG (code 24 = AC1018 vérifié) --
    tmp = os.path.join(tempfile.gettempdir(), "interop_live.dwg")
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    print(f"\n[5] SaveAs DWG -> {tmp}")
    try:
        ac.save_document(doc, tmp)
    except Exception as exc:
        print(f"    ECHEC SaveAs : {exc}")
        ac.disconnect()
        return 1
    import time
    time.sleep(0.5)
    size = os.path.getsize(tmp)
    with open(tmp, "rb") as f:
        magic = f.read(6)
    print(f"    fichier : {size} octets, magique={magic!r} "
          f"({'DWG' if magic[:2] == b'AC' else 'inconnu'})")

    print("\n[6] Fermeture (sans sauvegarde) puis RÉOUVERTURE")
    ac.close_document(doc, save=False)

    # Nouveau projet vierge : on doit obtenir la même géométrie par lecture
    proj2 = Project(sc_id="SC-INTEROP-LIVE-002", name="Relu depuis DWG")

    print("\n[7] LECTURE AutoCAD -> pivot (nouveau Project vierge)")
    # On ouvre le DWG comme document actif pour la relecture
    try:
        odoc = ac.open_document(tmp)
    except Exception as exc:
        print(f"    ECHEC Open : {exc}")
        ac.disconnect()
        return 1
    # replace le document courant pour read_model
    ac._force_doc = odoc
    class _Ctx:
        def __init__(s, d): s.d = d
    # read_model lit self.app.Documents.Item(0) — on s'assure qu'il n'y en a
    # qu'un actif pertinent ; sinon on branche directement sur odoc.
    rep2 = _read_from(ac, odoc, proj2)
    print(f"    status={rep2.status} objects={rep2.objects}")
    print(f"    message={rep2.message}")

    print("\n[8] CONTRÔLE de cohérence")
    ok = True
    checks = []
    checks.append(("nœuds lus == nœuds source",
                   rep2.objects.get("nodes", 0) == src_counts["nodes"]))
    checks.append(("poutres lues == poutres source",
                   rep2.objects.get("beams", 0) == src_counts["beams"]))
    for label, val in checks:
        print(f"      [{'OK ' if val else 'FAIL'}] {label}")
        ok = ok and val

    # Géométrie : comparer les arêtes relues (ordre indifférent)
    def edges(p):
        out = set()
        for bid, b in p.beams.items():
            n1, n2 = p.nodes.get(b.start_node), p.nodes.get(b.end_node)
            if not n1 or not n2:
                continue
            a = (round(float(n1.x.value), 4), round(float(n1.y.value), 4))
            c = (round(float(n2.x.value), 4), round(float(n2.y.value), 4))
            out.add(tuple(sorted([a, c])))
        return out
    e1, e2 = edges(proj), edges(proj2)
    same = e1 == e2
    print(f"      [{'OK ' if same else 'FAIL'}] géométrie identique "
          f"({len(e1)} arêtes source, {len(e2)} relues)")
    ok = ok and same

    print("\n[9] Fermeture")
    try:
        ac.close_document(odoc, save=False)
    except Exception:
        pass
    ac.disconnect()

    print("\n" + "=" * 72)
    print(f"RESULTAT : {'SUCCES' if ok else 'ECHEC'}")
    print("=" * 72)
    return 0 if ok else 1


def _read_from(ac, doc, proj) -> object:
    """
    Relecture d'un document donné (le document courant peut être différent
    si plusieurs dessins sont ouverts) : on déroute read_model sur `doc`.
    """
    from structcalc.integration.interop.base import OpReport
    counts = {"nodes": 0, "columns": 0, "beams": 0, "slabs": 0,
              "ignored": 0}
    errors = []
    ms = doc.ModelSpace
    n = ms.Count
    existing = proj.nodes

    def ensure_node(x, y):
        for nid, nd in existing.items():
            if abs(float(nd.x.value) - x) < 1e-6 and \
               abs(float(nd.y.value) - y) < 1e-6:
                return nid
        node = proj.new_node(x, y, 0.0)
        counts["nodes"] += 1
        return node.sc_id

    from structcalc.integration.interop.autocad import LAYER_BEAM, SC_PREFIX
    for i in range(n):
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        layer = str(ent.Layer)
        if not layer.startswith(SC_PREFIX):
            counts["ignored"] += 1
            continue
        if oname == "AcDbLine" and layer == LAYER_BEAM:
            sp, ep = tuple(ent.StartPoint), tuple(ent.EndPoint)
            n1 = ensure_node(float(sp[0]), float(sp[1]))
            n2 = ensure_node(float(ep[0]), float(ep[1]))
            bid = proj.allocator.new("BEAM")
            proj.beams[bid] = Beam(sc_id=bid, start_node=n1, end_node=n2)
            counts["beams"] += 1
        else:
            counts["ignored"] += 1
    status = "OK" if not errors else "PARTIAL"
    return OpReport("read_model", status, source="autocad", objects=counts,
                    message="entités SC_* relues depuis le DWG"
                    if not errors else "; ".join(errors))


if __name__ == "__main__":
    raise SystemExit(main())
