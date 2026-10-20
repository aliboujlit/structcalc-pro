# -*- coding: utf-8 -*-
"""
tools/build_architect_dossier.py — DOSSIER À REMETTRE À L'ARCHITECTE.

Automatique (aucun codage utilisateur), en accès EXCLUSIF sur Robot —
ne jamais lancer pendant qu'une autre session COM travaille.

Pipeline :
  1. Robot : ouverture du .rtd d'étude RÉEL -> pivot SC-* (fermeture
     SANS sauvegarde à la fin, §5.4 ; projet étranger = refus motivé) ;
  2. Étude : case « Poids propre » -> CALCUL -> lecture des réactions
     (résultats RÉELS ; indisponibles = écrit tel quel, JAMAIS inventé) ;
  3. Reporting : resume_etude.md/.xlsx/.pdf + rapport de cohérence +
     index honnête (reporting/dossier.py, §15.3) ;
  4. Livrables déjà produits copiés dedans : plan DWG transféré,
     maquette NWD, rapport de vérification.

Sortie : <projets de test>\\_structcalc_sortie\\dossier_architecte\\

Lance :
    $env:PYTHONIOENCODING="utf-8"
    python tools/build_architect_dossier.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(errors="replace") if hasattr(
    sys.stdout, "reconfigure") else None

TEST_DIR = Path(r"C:\Users\Admin\Desktop\projets de test")
RTD = TEST_DIR / "Projet-Batiment-R2-" / "Projet Bâtiment R+2 .rtd"
SORTIE = TEST_DIR / "_structcalc_sortie"
OUT = SORTIE / "dossier_architecte"

COPIES = [
    (SORTIE / "echange_robot_autocad.dwg", "plans" / Path(),
     "Plan transfere Robot->AutoCAD (119 poutres SC_*)"),
    (TEST_DIR / "Plan-villa" / "Plan-villa.nwd", "coordination" / Path(),
     "Maquette de coordination NWD (Plan-villa)"),
    (SORTIE / "verification_report.txt", Path(),
     "Rapport de verification live 9 phases"),
]


def _line(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    _line("=" * 70)
    _line("STRUCTCALC PRO — dossier de rendu pour l'architecte")
    _line(f"Etude source : {RTD.name}")
    _line(f"Dossier       : {OUT}")
    _line("=" * 70)
    if not RTD.exists():
        _line(f"[REFUS] .rtd introuvable : {RTD}")
        return 1
    try:
        OUT.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _line(f"[REFUS] creation dossier : {exc}")
        return 1

    # --- 1) Robot : modele reel dans le pivot ---------------------------
    from structcalc.core.model import Project
    from structcalc.integration.robot.connection import RobotConnection

    rc = RobotConnection(visible=True, attach_only=False)
    project = None
    study_lines: list[str] = []
    try:
        rc.connect(timeout=90.0)
    except Exception as exc:
        _line(f"[REFUS] connexion Robot : {exc}")
        return 1
    opened = False
    try:
        if rc.is_project_open and not rc.opened_by_us:
            _line("[REFUS] projet deja ouvert dans Robot (votre session) "
                  "-- fermez-le puis relancez (5.4).")
            return 1
        _line(f"  Ouverture {RTD.name} ...")
        rc.open_project(str(RTD))
        opened = True
        project = Project(sc_id="SC-PROJECT-000001", name=RTD.stem)
        rep = rc.read_model(project)
        counts = project.counts()
        _line(f"  [OK] modele lu ({rep.status}) : {counts}")
        study_lines.append(f"- Lecture du modele : {rep.status} — {counts}")
        if getattr(rep, "message", ""):
            study_lines.append(f"- Details lecture : {rep.message}")

        # --- 2) Etude PENDANT que le projet est ouvert (voir enfin) ------
        # (les operations Robot exigent un projet ouvert ; le projet est
        # le NOTRE ici -> allowed, et la fermeture SANS save suit)
        from structcalc.integration.robot import loads, results
        try:
            cases = loads.list_cases(rc)
            _line(f"  Cases de charge existantes : {len(cases)}")
            study_lines.append(
                f"- Cases de charge existantes : {len(cases)}")
            if not cases:
                r = loads.export_dead_load_case(rc, number=1,
                                                name="Poids propre",
                                                analyze=False)
                _line(f"  [OK] case poids propre creee : {r}")
                study_lines.append(f"- Case creee : {r}")
            rcalc = loads.calculate(rc)
            _line(f"  Calcul : {rcalc}")
            study_lines.append(f"- Calcul : {rcalc}")
            avail = int(rcalc.get("results_available", 0) or 0)
            if avail:
                try:
                    reac = results.import_reactions(rc, case_number=1)
                    n = len(reac) if hasattr(reac, "__len__") else "?"
                    _line(f"  [OK] reactions lues : {n} valeur(s)")
                    study_lines.append(
                        f"- Resultats : reactions lues = {n} valeur(s) "
                        "(donnees reelles Robot, non inventees)")
                except Exception as exc:
                    _line(f"  [REFUS] lectures des reactions : {exc}")
                    study_lines.append(
                        f"- Resultats : lecture des reactions REFUSEE "
                        f"({exc}) -- rien n'est invente")
            else:
                _line("  [REFUS] Aucun resultat disponible (modeles sans "
                      "appuis/charges valides) -- rien n'est invente")
                study_lines.append(
                    "- Resultats : AUCUN disponible (0) — aucun nombre "
                    "n'est invente")
        except Exception as exc:
            _line(f"  [REFUS] etude : {exc}")
            study_lines.append(f"- Etude : refusee ({exc})")
    finally:
        if opened:
            try:
                rc.close_project(save=False)
                _line("  .rtd ferme SANS sauvegarde (5.4)")
            except Exception as exc:
                _line(f"  [ERREUR] fermeture .rtd : {exc}")

    if project is None:
        rc.disconnect()
        _line("[REFUS] aucun modele charge.")
        return 1

    # Session Robot terminee : deconnexion (projet deja ferme sans save)
    try:
        rc.disconnect()
    except Exception:
        pass

    # --- 3) Reporting : dossier MD/PDF/XLSX honnete ---------------------
    from structcalc.core.coherence import coherence_findings, format_findings
    from structcalc.reporting.dossier import build_dossier

    findings = coherence_findings(project)
    coherence_md = format_findings(project, findings)
    files = build_dossier(project, str(OUT), coherence_md=coherence_md)
    # Bloc resultats de l'etude dans le resume
    try:
        resume = OUT / "resume_etude.md"
        body = resume.read_text(encoding="utf-8")
        body += "\n\n## Etude structurelle (Robot 2027 — resultats reels)\n\n"
        body += "\n".join(study_lines) + "\n"
        resume.write_text(body, encoding="utf-8")
    except OSError as exc:
        _line(f"  [ERREUR] integration resultats : {exc}")
    _line(f"  Reporting : {len(files)} fichier(s) ecrit(s)")

    # --- 4) Copie des livrables existants --------------------------------
    copied = 0
    for src, sub, label in COPIES:
        if not src.exists():
            _line(f"  [absent] {src.name} ({label})")
            continue
        try:
            dest_dir = OUT / sub
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / src.name)
            copied += 1
            _line(f"  [OK] copie {sub / src.name} — {label}")
        except OSError as exc:
            _line(f"  [ERREUR] copie {src.name} : {exc}")

    # --- Index final ------------------------------------------------------
    _line("-" * 70)
    _line(f"DOSSIER PRET : {OUT}")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            _line(f"  {p.relative_to(OUT)}  ({p.stat().st_size} o)")
    _line("Note honnete : les documents affichent les statuts reels "
          "(aucune conformite non verifiee declaree, 15.3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
