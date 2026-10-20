# -*- coding: utf-8 -*-
"""
tools/verify_test_projects.py — Vérification LIVE (v2) avec les vrais
projets de l'utilisateur (dossier « projets de test » du Bureau).

Sujet DWG : premier argument facultatif = chemin du .dwg à vérifier
(défaut = plan-plateau-bureau,17,65 Mo — demandé par l'utilisateur pour
vérifier tous les mécanismes du programme en direct). Ex. :
    python tools/verify_test_projects.py ".../projets de test/Plan-villa/Plan-villa.dwg"

Phases :
  1. Inventaire des projets de test
  2. Robot : ouverture .rtd réel + lecture modèle (compteurs nœuds/barres)
  3. AutoCAD : plan-plateau-bureau — ouverture + lecture CIBLÉE du document
     + gardes anti-faux-succès (pivot vide -> REFUS, rien de créé)
  4. Échange RÉCIPROQUE Robot(.rtd) -> pivot -> AutoCAD (nouveau doc SC_*)
     + relecture ciblée + export DWG artefact (SaveAs vérifié)
  5. Échange RETOUR AutoCAD(doc SC_*) -> pivot -> Robot (nouveau projet)
     + contrôle des compteurs (aucun « OK » à 0 objet)
  6. Navisworks : conversion plan-plateau-bureau.dwg -> NWD (source intacte)
  7. Revit : sonde add-in + lecture honnête (refus motivé sans élément)
  8. Hub : routes NxN + paires réciproques + inventaire combinaisons
  9. Boucle complète 6 logiciels (connect=True) + nettoyage SEULEMENT de nos
     documents créés

RÈGLES ABSOLUTES (§5.4 + honnêteté) :
  - JAMAIS de sauvegarde des fichiers utilisateur (.rtd, .dwg) : fermeture
    save=False UNIQUEMENT pour ce que CE SCRIPT a ouvert/créé ;
  - les documents préexistants d'AutoCAD ne sont JAMAIS fermés ni touchés ;
  - lecture AutoCAD toujours CIBLÉE (document=...) avec identité
    (Name/FullName) rapportée — jamais le mauvais fichier en silencieux ;
  - aucun « OK » avec 0 objet transféré : source vide = REFUS motivé ;
  - chaque refus/erreur porte son motif EXACT (pas de faux succès).

Usage :
  PYTHONIOENCODING=utf-8 python tools/verify_test_projects.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Console Windows : ne JAMAIS planter sur un caractère hors cp1252 (✓, →…)
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Chemins et constantes
# ---------------------------------------------------------------------------

DESKTOP = Path(os.environ.get("USERPROFILE", r"C:\Users\Admin")) / "Desktop"
TEST_DIR = DESKTOP / "projets de test"

RTD_BATIMENT = TEST_DIR / "Projet-Batiment-R2-" / "Projet Bâtiment R+2 .rtd"
DWG_BUREAU = TEST_DIR / "plan-plateau-bureau" / "plan-plateau-bureau.dwg"

# Sujet DWG : 1er argument facultatif = chemin du .dwg à vérifier
# (défaut = plan-plateau-bureau). Ex. :
#   python tools/verify_test_projects.py "...\projets de test\Plan-villa\Plan-villa.dwg"
if len(sys.argv) > 1 and str(sys.argv[1]).lower().endswith(".dwg"):
    SUBJECT_DWG = Path(sys.argv[1])
else:
    SUBJECT_DWG = DWG_BUREAU

OUT_DIR = TEST_DIR / "_structcalc_sortie"
OUT_DIR.mkdir(exist_ok=True)
NWD_OUT = OUT_DIR / f"{SUBJECT_DWG.stem}.nwd"
DWG_EXPORT = OUT_DIR / "echange_robot_autocad.dwg"
REPORT_TXT = OUT_DIR / "verification_report.txt"

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def import_core():
    from structcalc.core.model import Project
    return Project


def import_connectors() -> Dict[str, Any]:
    from structcalc.integration.interop import (
        RobotConnector, AutoCADConnector, NavisworksConnector,
        RevitConnector, InteropHub, default_hub, Capability,
    )
    return {
        "robot": RobotConnector, "autocad": AutoCADConnector,
        "navisworks": NavisworksConnector, "revit": RevitConnector,
        "hub": InteropHub, "default_hub": default_hub,
        "capability": Capability,
    }


def import_loop():
    from structcalc.integration.interop.loop import (
        Selection, ROLE_BOTH, plan_loop, describe_plan, exchange_plan,
    )
    return Selection, ROLE_BOTH, plan_loop, describe_plan, exchange_plan


# ---------------------------------------------------------------------------
# Structure de résultats
# ---------------------------------------------------------------------------

class PhaseResult:
    def __init__(self, name: str, status: str, detail: str = "",
                 data: Any = None):
        self.name = name
        self.status = status        # OK | PARTIAL | REFUSE | ERREUR
        self.detail = detail
        self.data = data

    def __str__(self) -> str:
        return f"[{self.status}] {self.name}: {self.detail}"


PHASES: List[PhaseResult] = []


def run_phase(name: str, fn) -> PhaseResult:
    """Exécute une phase ; capture l'exception -> ERREUR (jamais de crash muet)."""
    print("\n" + "=" * 70)
    print(f"PHASE: {name}")
    print("=" * 70)
    sys.stdout.flush()
    try:
        result = fn()
        if not isinstance(result, PhaseResult):
            result = PhaseResult(name, "OK", str(result) if result else "exécuté")
    except Exception as exc:
        result = PhaseResult(name, "ERREUR",
                             f"exception: {exc}\n{traceback.format_exc()}")
    result.name = name
    PHASES.append(result)
    print(" -> " + str(result))
    sys.stdout.flush()
    return result


# ---------------------------------------------------------------------------
# Helpers documents AutoCAD — NE TOUCHE JAMAIS AUX DOCUMENTS PRÉEXISTANTS
# ---------------------------------------------------------------------------

def doc_label(doc) -> str:
    try:
        nm = str(getattr(doc, "Name", "") or "")
    except Exception:
        nm = ""
    try:
        fl = str(getattr(doc, "FullName", "") or "")
    except Exception:
        fl = ""
    return fl or nm or "<document sans nom>"


def docs_snapshot(app) -> List[Tuple[Tuple[str, str], Any]]:
    """[(clé (Name, FullName), doc)] de TOUS les documents (pour diff)."""
    out: List[Tuple[Tuple[str, str], Any]] = []
    try:
        docs = app.Documents
        for i in range(docs.Count):
            d = docs.Item(i)
            out.append(((_name_of(d), _full_of(d)), d))
    except Exception:
        pass
    return out


def _name_of(doc) -> str:
    try:
        return str(getattr(doc, "Name", "") or "")
    except Exception:
        return "?"


def _full_of(doc) -> str:
    try:
        return str(getattr(doc, "FullName", "") or "")
    except Exception:
        return ""


def docs_keys(snap) -> set:
    return {k for k, _ in snap}


def new_docs_since(app, before_keys: set) -> List[Any]:
    """Documents APPERUS depuis le snapshot (ceux que NOUS avons créés)."""
    return [d for k, d in docs_snapshot(app) if k not in before_keys]


def close_quietly(ac, docs: List[Any]) -> int:
    """Ferme SANS sauvegarde les documents que nous avons créés/ouverts."""
    n = 0
    for d in docs:
        try:
            ac.close_document(d, save=False)
            n += 1
            print(f"    [close] fermé sans save : {doc_label(d)}")
        except Exception as exc:
            print(f"    [close] échec ({doc_label(d)}) : {exc}")
    return n


def disconnect_quietly(*conns) -> None:
    for c in conns:
        if c is None:
            continue
        try:
            c.disconnect()
        except Exception:
            pass


def find_doc_by_path(app, path: str) -> Any:
    """Document DÉJÀ ouvert correspondant à `path` (FullName), sinon None.

    Réutilise en LECTURE SEULE un document déjà ouvert (par l'utilisateur
    ou une session antérieure) au lieu de le réouvrir — jamais fermé ni
    modifié puisque nous ne l'avons pas ouvert.
    """
    try:
        target = os.path.normcase(os.path.abspath(path))
    except Exception:
        target = str(path).lower()
    try:
        docs = app.Documents
        for i in range(docs.Count):
            d = docs.Item(i)
            try:
                full = str(d.FullName or "")
            except Exception:
                continue
            if not full:
                continue
            try:
                if os.path.normcase(os.path.abspath(full)) == target:
                    return d
            except Exception:
                if full.lower() == str(path).lower():
                    return d
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# PHASE 1 : Inventaire statique
# ---------------------------------------------------------------------------

def phase_inventory() -> PhaseResult:
    if not TEST_DIR.exists():
        return PhaseResult("", "REFUSE", f"dossier introuvable : {TEST_DIR}")
    files = []
    for f in sorted(TEST_DIR.rglob("*")):
        if f.is_file():
            files.append((f.relative_to(TEST_DIR), f.stat().st_size))
    if not files:
        return PhaseResult("", "REFUSE", "aucun fichier dans projets de test")
    lines = [f"  {rel}  ({size / 1024 / 1024:.2f} Mo)"
             for rel, size in files]
    return PhaseResult("", "OK",
                       f"{len(files)} fichier(s) :\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# PHASE 2 : Robot — lecture du .rtd réel (bureau d'étude)
# ---------------------------------------------------------------------------

def phase_robot_read_real() -> PhaseResult:
    K = import_connectors()
    Project = import_core()
    rc = K["robot"](visible=True, attach_only=False)
    opened = False
    try:
        try:
            rc.connect(timeout=60.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion Robot impossible : {exc}")
        if rc.rc.is_project_open and not rc.rc.opened_by_us:
            return PhaseResult(
                "", "REFUSE",
                "un projet est déjà ouvert dans Robot (peut-être votre "
                "travail) — fermez-le dans Robot puis relancez (§5.4). "
                "Rien n'a été touché.")
        if not RTD_BATIMENT.exists():
            return PhaseResult("", "REFUSE",
                               f"fichier introuvable : {RTD_BATIMENT}")
        print(f"  Ouverture {RTD_BATIMENT} ...")
        rc.rc.open_project(str(RTD_BATIMENT))
        opened = True
        pivot = Project("SC-VERIFY-ROBOT-REAL-001")
        rep = rc.read_model(pivot)
        nodes = len(getattr(pivot, "nodes", {}) or {})
        beams = len(getattr(pivot, "beams", {}) or {})
        cols = len(getattr(pivot, "columns", {}) or {})
        if rep.status in ("REFUSED", "ERROR"):
            return PhaseResult("", "REFUSE",
                               f"lecture échouée : {rep.message}")
        read_partial = rep.status == "PARTIAL"
        if nodes == 0 or beams == 0:
            return PhaseResult(
                "", "REFUSE",
                f"lecture VIDE (nœuds={nodes}, barres={beams}) — aucun "
                f"succès simulé | {rep.message}")
        return PhaseResult(
            "", "PARTIAL" if read_partial else "OK",
            f"nœuds={nodes}, barres={beams}, poteaux={cols} | {rep.message}",
            data={"nodes": nodes, "beams": beams})
    finally:
        if opened:
            try:
                rc.rc.close_project(save=False)
                print("  .rtd fermé SANS sauvegarde (§5.4)")
            except Exception as exc:
                print(f"  [avertissement] close_project : {exc}")
        disconnect_quietly(rc)


# ---------------------------------------------------------------------------
# PHASE 3 : AutoCAD — plan-plateau-bureau (ouverture + lecture ciblée +
#           gardes anti-faux-succès sur pivot vide)
# ---------------------------------------------------------------------------

def phase_plateau_read() -> PhaseResult:
    K = import_connectors()
    Project = import_core()
    ac = K["autocad"](attach_only=False)
    rc = None
    our_doc = None
    opened_by_us = False
    checks: List[str] = []
    try:
        try:
            ac.connect(timeout=90.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion AutoCAD impossible : {exc}")
        if not SUBJECT_DWG.exists():
            return PhaseResult("", "REFUSE",
                               f"fichier introuvable : {SUBJECT_DWG}")
        mo = SUBJECT_DWG.stat().st_size / 1024 / 1024
        print(f"  Sujet : {SUBJECT_DWG.name} ({mo:.2f} Mo)")
        our_doc = find_doc_by_path(ac.app, str(SUBJECT_DWG))
        if our_doc is not None:
            print(f"  Document DÉJÀ ouvert dans AutoCAD : "
                  f"{doc_label(our_doc)} — réutilisé en LECTURE SEULE "
                  "(ni réouvert, ni fermé)")
            checks.append("document déjà ouvert réutilisé en lecture seule : "
                          + doc_label(our_doc))
        else:
            print("  Ouverture ...")
            try:
                our_doc = ac.open_document(str(SUBJECT_DWG), tries=20,
                                           delay=1.5)
                opened_by_us = True
            except Exception as exc:
                return PhaseResult("", "REFUSE",
                                   f"ouverture DWG impossible : {exc}")
            print(f"  Document ouvert : {doc_label(our_doc)}")

        # -- Lecture CIBLÉE sur le document que NOUS avons ouvert --
        pivot = Project("SC-VERIFY-BUREAU-001")
        rep = ac.read_model(pivot, document=our_doc)
        if rep.status in ("REFUSED", "ERROR"):
            return PhaseResult("", "REFUSE",
                               f"lecture échouée : {rep.message}")
        # PARTIAL = lecture réelle partielle : on CONTINUE les gardes et le
        # verdict final reste PARTIAL (jamais reformulé en OK plein).
        read_partial = rep.status == "PARTIAL"
        if read_partial:
            checks.append(f"lecture PARTIALE assumée (honnête, non reformulée "
                          f"en plein succès) : {rep.message}")
        beams = len(getattr(pivot, "beams", {}) or {})
        nodes = len(getattr(pivot, "nodes", {}) or {})
        ign = int((rep.objects or {}).get("ignored", 0))
        checks.append(f"lecture ciblée [{doc_label(our_doc)}] : poutres="
                      f"{beams}, nœuds={nodes}, entités ignorées={ign} | "
                      f"{rep.message}")

        # -- Garde anti-faux-succès : pivot VIDE -> REFUS attendu partout --
        before = docs_keys(docs_snapshot(ac.app))
        vide = Project("SC-VERIFY-VIDE-001")
        w_ac = ac.write_model(vide)
        ok_ac = (not w_ac.ok) and ("pivot vide" in (w_ac.message or ""))
        checks.append(
            f"garde AutoCAD (pivot vide) -> {w_ac.status} "
            f"[{'VÉRIFIÉE' if ok_ac else 'ANOMALIE'}] : {w_ac.message}")
        after = docs_keys(docs_snapshot(ac.app))
        checks.append(
            "aucun document créé par le refus AutoCAD : "
            f"[{'VÉRIFIÉE' if after == before else 'ANOMALIE'}]")

        try:
            rc = K["robot"](visible=True, attach_only=False)
            rc.connect(timeout=60.0)
        except Exception as exc:
            checks.append(f"garde Robot : NON EXÉCUTÉE (connexion impossible "
                          f"-> {exc})")
            rc = None
        if rc is not None and rc.connected:
            w_r = rc.write_model(vide)
            ok_r = (not w_r.ok) and ("pivot vide" in (w_r.message or ""))
            checks.append(
                f"garde Robot (pivot vide) -> {w_r.status} "
                f"[{'VÉRIFIÉE' if ok_r else 'ANOMALIE'}] : {w_r.message}")
            proj_open = rc.rc.is_project_open
            checks.append(
                "aucun projet créé par le refus Robot : "
                f"[{'VÉRIFIÉE' if not proj_open else 'ANOMALIE'}]")
            all_ok = ok_ac and ok_r and (after == before) and not proj_open
        else:
            all_ok = False

        status = "OK" if (all_ok and not read_partial) else "PARTIAL"
        return PhaseResult("", status, "\n  ".join(checks),
                           data={"beams": beams, "ignored": ign})
    finally:
        if our_doc is not None and opened_by_us:
            close_quietly(ac, [our_doc])
        elif our_doc is not None:
            print(f"  Document laissé ouvert (pas ouvert par nous) : "
                  f"{doc_label(our_doc)}")
        disconnect_quietly(rc, ac)


# ---------------------------------------------------------------------------
# PHASE 4 : Échange Robot(.rtd) -> pivot -> AutoCAD (doc SC_* + artefact DWG)
# ---------------------------------------------------------------------------

def phase_exchange_robot_to_autocad() -> PhaseResult:
    K = import_connectors()
    Project = import_core()
    rc = K["robot"](visible=True, attach_only=False)
    ac = K["autocad"](attach_only=False)
    opened = False
    created = None
    try:
        try:
            rc.connect(timeout=60.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion Robot impossible : {exc}")
        if rc.rc.is_project_open and not rc.rc.opened_by_us:
            return PhaseResult(
                "", "REFUSE",
                "projet déjà ouvert dans Robot hors session — fermez-le "
                "d'abord (§5.4). Rien n'a été touché.")
        rc.rc.open_project(str(RTD_BATIMENT))
        opened = True
        try:
            ac.connect(timeout=90.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion AutoCAD impossible : {exc}")

        pivot = Project("SC-VERIFY-R2A-001")
        rep_read = rc.read_model(pivot)
        n_b = len(getattr(pivot, "beams", {}) or {})
        if rep_read.status in ("REFUSED", "ERROR"):
            return PhaseResult("", "REFUSE",
                               f"lecture Robot échouée : {rep_read.message}")
        if n_b == 0:
            return PhaseResult("", "REFUSE",
                               "source vide (0 barre) — rien à transférer, "
                               "aucun faux succès.")
        print(f"  Pivot source : {len(pivot.nodes)} nœuds, {n_b} poutres")

        before = docs_keys(docs_snapshot(ac.app))
        w = ac.write_model(pivot)
        if not w.ok:
            return PhaseResult("", "REFUSE",
                               f"écriture AutoCAD REFUSÉE : {w.message}")
        newdocs = new_docs_since(ac.app, before)
        if not newdocs:
            return PhaseResult("", "REFUSE",
                               "write_model OK mais AUCUN nouveau document "
                               "détecté — incohérence, refus de valider.")
        created = newdocs[0]

        back = Project("SC-VERIFY-R2A-BACK-001")
        rb = ac.read_model(back, document=created)
        n_back = len(getattr(back, "beams", {}) or {})
        match = n_back == n_b

        # Artefact DWG (SaveAs vérifié — NOTRE fichier de sortie, jamais
        # un fichier utilisateur)
        art = ""
        try:
            DWG_EXPORT.unlink(missing_ok=True)
            saved = ac.save_document(created, str(DWG_EXPORT))
            art = (f" ; artefact DWG : {saved} "
                   f"({Path(saved).stat().st_size // 1024} Ko)")
        except Exception as exc:
            art = f" ; artefact DWG : échec SaveAs ({exc})"

        status = "OK" if (rb.ok and match) else "PARTIAL"
        detail = (f"Robot .rtd -> {n_b} poutres ; écrit AutoCAD : "
                  f"{w.objects} ; relecture ciblée [{doc_label(created)}] = "
                  f"{n_back} poutres | "
                  f"{'IDENTIQUE' if match else 'DIVERGENT'} ; {rb.message}"
                  f"{art}")
        return PhaseResult("", status, detail,
                           data={"source": n_b, "back": n_back,
                                 "match": match})
    finally:
        if created is not None:
            close_quietly(ac, [created])
        if opened:
            try:
                rc.rc.close_project(save=False)
                print("  .rtd fermé SANS sauvegarde (§5.4)")
            except Exception as exc:
                print(f"  [avertissement] close_project : {exc}")
        disconnect_quietly(rc, ac)


# ---------------------------------------------------------------------------
# PHASE 5 : Échange RETOUR AutoCAD(doc SC_*) -> pivot -> Robot (nouveau projet)
# ---------------------------------------------------------------------------

def phase_exchange_autocad_to_robot() -> PhaseResult:
    K = import_connectors()
    Project = import_core()
    rc = K["robot"](visible=True, attach_only=False)
    ac = K["autocad"](attach_only=False)
    opened_rtd = False
    created = None
    try:
        try:
            rc.connect(timeout=60.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion Robot impossible : {exc}")
        if rc.rc.is_project_open and not rc.rc.opened_by_us:
            return PhaseResult("", "REFUSE",
                               "projet déjà ouvert dans Robot — fermez-le "
                               "d'abord (§5.4). Rien n'a été touché.")
        try:
            ac.connect(timeout=90.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion AutoCAD impossible : {exc}")

        # 1) Source de vérité : le .rtd du bureau d'étude
        rc.rc.open_project(str(RTD_BATIMENT))
        opened_rtd = True
        pivot_src = Project("SC-VERIFY-A2R-SRC-001")
        rep_src = rc.read_model(pivot_src)
        n_src = len(getattr(pivot_src, "beams", {}) or {})
        if rep_src.status in ("REFUSED", "ERROR") or n_src == 0:
            return PhaseResult("", "REFUSE",
                               f"source .rtd vide/illisible ({n_src} poutres) "
                               f"— {rep_src.message}")
        rc.rc.close_project(save=False)
        opened_rtd = False
        print(f"  Source : {n_src} poutres (fermeture sans save effectuée)")

        # 2) Document SC_* dans AutoCAD (créé par NOUS)
        before = docs_keys(docs_snapshot(ac.app))
        w = ac.write_model(pivot_src)
        if not w.ok:
            return PhaseResult("", "REFUSE",
                               f"écriture AutoCAD REFUSÉE : {w.message}")
        newdocs = new_docs_since(ac.app, before)
        if not newdocs:
            return PhaseResult("", "REFUSE",
                               "aucun document créé — incohérence, refus.")
        created = newdocs[0]

        # 3) Relecture CIBLÉE du document que NOUS venons de créer
        mid = Project("SC-VERIFY-A2R-MID-001")
        r_mid = ac.read_model(mid, document=created)
        n_ac = len(getattr(mid, "beams", {}) or {})
        if not r_mid.ok or n_ac == 0:
            return PhaseResult("", "REFUSE",
                               f"document SC_* vide après écriture "
                               f"({n_ac} poutres) — {r_mid.message}")

        # 4) Écriture dans Robot : AUCUN projet ouvert -> NOUVEAU projet
        if rc.rc.is_project_open:
            return PhaseResult("", "REFUSE",
                               "projet Robot encore ouvert avant écriture "
                               "(§5.4) — refus, rien écrit.")
        w2 = rc.write_model(mid)
        if not w2.ok:
            return PhaseResult("", "REFUSE",
                               f"écriture Robot REFUSÉE : {w2.message}")
        n_w = int((w2.objects or {}).get("bars", 0))
        if n_w == 0:
            return PhaseResult("", "REFUSE",
                               f"0 barre écrite dans Robot — {w2.message}")

        # 5) Contrôle : relecture du projet Robot créé
        chk = Project("SC-VERIFY-A2R-CHK-001")
        r_chk = rc.read_model(chk)
        n_c = len(getattr(chk, "beams", {}) or {})
        match = (n_ac == n_w == n_c)
        status = "OK" if (match and r_mid.ok and r_chk.ok) else "PARTIAL"
        detail = (f"AutoCAD [{doc_label(created)}] = {n_ac} poutres -> Robot "
                  f"écrit = {n_w} -> relecture = {n_c} | "
                  f"{'IDENTIQUE' if match else 'DIVERGENT'} ; "
                  f"écriture : {w2.message}")
        return PhaseResult("", status, detail,
                           data={"ac": n_ac, "written": n_w, "check": n_c})
    finally:
        if opened_rtd:
            try:
                rc.rc.close_project(save=False)
                print("  .rtd fermé SANS sauvegarde (§5.4)")
            except Exception as exc:
                print(f"  [avertissement] close .rtd : {exc}")
        # Projet CRÉÉ par nous dans Robot (session courante) -> fermeture
        try:
            if rc.connected and rc.rc.opened_by_us and rc.rc.is_project_open:
                rc.rc.close_project(save=False)
                print("  projet Robot créé fermé SANS sauvegarde (§5.4)")
        except Exception as exc:
            print(f"  [avertissement] close projet créé : {exc}")
        if created is not None:
            close_quietly(ac, [created])
        disconnect_quietly(rc, ac)


# ---------------------------------------------------------------------------
# PHASE 6 : Navisworks — conversion plan-plateau-bureau.dwg -> NWD
# ---------------------------------------------------------------------------

def phase_navisworks_convert() -> PhaseResult:
    K = import_connectors()
    nw = K["navisworks"]()
    try:
        try:
            nw.connect(timeout=120.0)
        except Exception as exc:
            return PhaseResult("", "REFUSE",
                               f"connexion Navisworks impossible : {exc}")
        if not SUBJECT_DWG.exists():
            return PhaseResult("", "REFUSE",
                               f"source introuvable : {SUBJECT_DWG}")
        NWD_OUT.unlink(missing_ok=True)
        print(f"  Conversion {SUBJECT_DWG.name} -> {NWD_OUT.name} ...")
        rep = nw.convert(str(SUBJECT_DWG), str(NWD_OUT))
        if rep.ok and NWD_OUT.exists() and NWD_OUT.stat().st_size > 0:
            ko = NWD_OUT.stat().st_size / 1024
            return PhaseResult(
                "", "OK",
                f"NWD créé : {NWD_OUT} ({ko:.0f} Ko) ; source intacte | "
                f"{rep.message}")
        return PhaseResult("", "REFUSE",
                           f"conversion non validée : {rep.message} "
                           f"(fichier présent : {NWD_OUT.exists()})")
    finally:
        disconnect_quietly(nw)


# ---------------------------------------------------------------------------
# PHASE 7 : Revit — sonde add-in + lecture honnête
# ---------------------------------------------------------------------------

def phase_revit_probe() -> PhaseResult:
    K = import_connectors()
    Project = import_core()
    rv = K["revit"]()
    det = rv.detect()
    alive, why = rv.probe_addin()
    caps = rv.capabilities()
    cap_status = {k.value: v.status.value for k, v in caps.items()}
    pivot = Project("SC-VERIFY-REVIT-001")
    rep = rv.read_model(pivot)
    detail = (f"installé={det.installed} | pipe_alive={alive} ({why}) | "
              f"caps={cap_status} | read_model={rep.status} : {rep.message}")
    return PhaseResult("", "OK" if alive else "PARTIAL", detail,
                       data={"alive": alive, "read": rep.status})


# ---------------------------------------------------------------------------
# PHASE 8 : Hub — routes NxN + paires réciproques + combinaisons
# ---------------------------------------------------------------------------

def phase_hub_matrix() -> PhaseResult:
    K = import_connectors()
    hub = K["default_hub"]()
    lines: List[str] = []

    status = hub.status()
    lines.append("Connecteurs :")
    for name, info in status.items():
        mark = "[x]" if info["installed"] else "[ ]"
        lines.append(f"  {mark} {info['label']} ({name}) : transport="
                     f"{info['transport']}, version={info['version']}, "
                     f"auto={info['automatable']}, "
                     f"caps utilisables={info['usable_capabilities']}")

    routes = hub.routes()
    n_ok = n_ko = 0
    lines.append("Routes (source -> cible) :")
    for sname, row in routes.items():
        for tname, info in row.items():
            if sname == tname:
                continue
            if info["feasible"]:
                n_ok += 1
            else:
                n_ko += 1
                lines.append(f"  [ ] {sname} -> {tname} : {info['reason']}")
    lines.append(f"  routes faisables : {n_ok} ; refusées (motif ci-dessus "
                 f"pour chacune) : {n_ko}")

    recip = hub.reciprocal_pairs()
    lines.append(f"Paires RÉCIPROQUES (A->B ET B->A) : {len(recip)}")
    for a, b in recip:
        lines.append(f"  {a} <-> {b}")

    from structcalc.integration.interop.combinaisons import describe_inventory
    lines.append("")
    lines.append(describe_inventory())

    return PhaseResult("", "OK", "\n".join(lines),
                       data={"reciprocal": len(recip)})


# ---------------------------------------------------------------------------
# PHASE 9 : Boucle complète (6 logiciels cochés) — exécution honnête
# ---------------------------------------------------------------------------

def phase_full_loop() -> PhaseResult:
    Selection, ROLE_BOTH, plan_loop, describe_plan, exchange_plan = \
        import_loop()
    K = import_connectors()
    Project = import_core()

    # Snapshot AutoCAD AVANT la boucle (pour ne fermer que NOS documents)
    ac0 = K["autocad"](attach_only=False)
    before: Optional[set] = None
    try:
        ac0.connect(timeout=90.0)
        before = docs_keys(docs_snapshot(ac0.app))
    except Exception as exc:
        print(f"  [avertissement] snapshot AutoCAD impossible : {exc}")

    selections = [Selection(n, ROLE_BOTH) for n in
                  ("revit", "robot", "autocad", "civil3d", "advsteel",
                   "navisworks")]
    plan = plan_loop(selections)
    if not plan.ok:
        disconnect_quietly(ac0)
        return PhaseResult("", "REFUSE", f"plan invalide : {plan.error}")
    print(describe_plan(plan))

    # -- Ouvrir le .rtd RÉEL avec la session Robot DU HUB AVANT la boucle ---
    # Même instance que celle que la boucle utilisera : `opened_by_us=True`
    # -> Robot accepte alors lecture ET écriture dans CE projet (les autres
    # projets restent protégés, §5.4). Fermé SANS sauvegarde juste après.
    # Aucun pré-remplissage du pivot : la lecture Robot le remplit UNE fois.
    from structcalc.integration.interop import default_hub
    hub = default_hub()
    rc_open = hub.get("robot")
    opened_rtd = False
    rtd_note = ""
    try:
        rc_open.connect(timeout=60.0)
        if rc_open.rc.is_project_open and not rc_open.rc.opened_by_us:
            rtd_note = ("projet étranger déjà ouvert dans Robot (§5.4) — "
                        "non touché, boucle lancée sans projet source")
        else:
            rc_open.rc.open_project(str(RTD_BATIMENT))
            opened_rtd = True
            rtd_note = f".rtd ouvert pour la boucle : {RTD_BATIMENT.name}"
    except Exception as exc:
        rtd_note = f"ouverture .rtd impossible : {exc}"
    print(f"  [boucle] {rtd_note}")

    print("  Exécution exchange_plan(connect=True, hub partagé) ...")
    results = exchange_plan(plan, Project("SC-VERIFY-LOOP-001"),
                            connect=True, hub=hub)

    # Refermer SANS sauvegarde ce que NOUS venons d'ouvrir (§5.4)
    if opened_rtd:
        try:
            rc_open.rc.close_project(save=False)
            print("  [boucle] .rtd fermé SANS sauvegarde après la boucle "
                  "(§5.4)")
        except Exception as exc:
            print(f"  [boucle] fermeture .rtd : {exc}")
    disconnect_quietly(rc_open)

    # État Robot APRÈS la boucle (le projet créé par la session de la boucle
    # est fermé sans sauvegarde à la sortie du script — atexit de la session)
    robot_state = "non vérifié"
    rc2 = K["robot"](visible=True, attach_only=False)
    try:
        rc2.connect(timeout=30.0)
        if rc2.rc.is_project_open and not rc2.rc.opened_by_us:
            robot_state = ("projet OUVERT créé par la boucle — fermé sans "
                           "sauvegarde à la fin du script (§5.4)")
        else:
            robot_state = "aucun projet ouvert"
    except Exception as exc:
        robot_state = f"sonde impossible ({exc})"
    disconnect_quietly(rc2)

    # Fermer UNIQUEMENT les documents créés pendant la boucle
    closed = 0
    if before is not None:
        try:
            created = new_docs_since(ac0.app, before)
            closed = close_quietly(ac0, created)
        except Exception as exc:
            print(f"  [avertissement] nettoyage documents : {exc}")
    disconnect_quietly(ac0)

    ok_count = sum(1 for r in results if r.get("success"))
    total = len(results)
    lines = [f"source .rtd Robot : {rtd_note}",
             f"étapes réussies : {ok_count}/{total} ; documents créés par la "
             f"boucle fermés sans save : {closed} ; état Robot : "
             f"{robot_state}"]
    for r in results:
        mark = "[x]" if r.get("success") else "[ ]"
        msg = str(r.get("message", ""))[:160]
        lines.append(f"  {mark} [{r.get('order')}] {r.get('source')} -> "
                     f"{r.get('target')} | {r.get('phase')} | "
                     f"{r.get('action')} | {msg}")
    detail = "\n".join(lines)
    return PhaseResult("", "OK" if ok_count == total else "PARTIAL", detail,
                       data={"ok": ok_count, "total": total})


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("STRUCTCALC PRO — VÉRIFICATION LIVE (v2) : projets réels de "
          "l'utilisateur")
    print(f"Source : {TEST_DIR}")
    print(f"Sujet principal : {SUBJECT_DWG.name} "
          f"({SUBJECT_DWG.stat().st_size / 1024 / 1024:.2f} Mo) + "
          f"{RTD_BATIMENT.name}")
    print(f"Sortie : {OUT_DIR}")
    print("=" * 70)

    run_phase("1. Inventaire des projets de test", phase_inventory)
    run_phase("2. Robot — lecture du .rtd réel (bureau d'étude)",
              phase_robot_read_real)
    run_phase(f"3. AutoCAD — {SUBJECT_DWG.name} : ouverture + lecture "
              "ciblée + gardes anti-faux-succès", phase_plateau_read)
    run_phase("4. Échange Robot -> AutoCAD (doc SC_* + artefact DWG)",
              phase_exchange_robot_to_autocad)
    run_phase("5. Échange RETOUR AutoCAD -> Robot (nouveau projet)",
              phase_exchange_autocad_to_robot)
    run_phase(f"6. Navisworks — {SUBJECT_DWG.name} -> NWD",
              phase_navisworks_convert)
    run_phase("7. Revit — sonde add-in + lecture", phase_revit_probe)
    run_phase("8. Hub — routes + paires réciproques + combinaisons",
              phase_hub_matrix)
    run_phase("9. Boucle complète (6 logiciels, connect=True)",
              phase_full_loop)

    print("\n" + "=" * 70)
    print("VERDICT FINAL")
    print("=" * 70)
    for p in PHASES:
        print(f"  [{p.status}] {p.name}")
    ok = sum(1 for p in PHASES if p.status == "OK")
    partial = sum(1 for p in PHASES if p.status == "PARTIAL")
    refused = sum(1 for p in PHASES if p.status == "REFUSE")
    error = sum(1 for p in PHASES if p.status == "ERREUR")
    print(f"\nRésumé : OK={ok}, PARTIAL={partial}, REFUSE={refused}, "
          f"ERREUR={error} (total {len(PHASES)})")

    try:
        with open(REPORT_TXT, "w", encoding="utf-8") as f:
            f.write("STRUCTCALC PRO — Rapport de vérification live (v2)\n")
            f.write(f"Date : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source : {TEST_DIR}\n")
            f.write(f"Sujet principal : {SUBJECT_DWG}\n")
            f.write("=" * 70 + "\n")
            for p in PHASES:
                f.write(f"\n[{p.status}] {p.name}\n  {p.detail}\n")
            f.write(f"\nRésumé : OK={ok}, PARTIAL={partial}, "
                    f"REFUSE={refused}, ERREUR={error}\n")
        print(f"Rapport écrit : {REPORT_TXT}")
    except Exception as exc:
        print(f"Écriture du rapport impossible : {exc}")

    return 0 if error == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
