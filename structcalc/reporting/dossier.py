# -*- coding: utf-8 -*-
"""
reporting/dossier.py — Dossier de rendu à remettre (spec §3.7, §15.3).

À partir du projet chargé, écrit dans un dossier CHOISI par l'utilisateur
le dossier complet de rendu (bureau d'études -> architecte) :

  - resume_etude.md / .xlsx / .pdf   : résumé de l'étude (statuts honnêtes)
  - fiche_poteau_<SC-ID>.md/.xlsx/.pdf pour CHAQUE poteau réellement présent
  - rapport_coherence.md             : constats de cohérence (si fournis)
  - LISEZ-MOI.txt                    : index de ce qui EST dans le dossier

RÈGLES :
  - aucun fichier n'affirme une conformité non vérifiée (§15.3) — les
    statuts (MISSING / CONFLICT / ASSUMED / à valider) voyagent tels quels ;
  - aucun objet inventé : seuls les objets RÉELLEMENT présents produisent
    un document (0 poteau = 0 fiche, et c'est écrit dans l'index) ;
  - n'élève JAMAIS d'exception : échec d'un fichier = le reste du dossier
    est produit et la liste retournée reflète la réalité écrite.
"""

from __future__ import annotations

import os
from typing import List

from .column_report import column_fiche, project_summary
from .exports import export_pdf, export_xlsx


def build_dossier(project, out_dir: str, coherence_md: str = "") -> List[str]:
    """
    Écrit le dossier de rendu dans `out_dir` (créé si besoin).

    Retourne la liste des fichiers RÉELLEMENT écrits (chemins absolus) —
    un échec d'écriture est ignoré individuellement, sans interrompre le
    reste du dossier.
    """
    written: List[str] = []

    def _put(name: str, text: str) -> None:
        try:
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written.append(os.path.abspath(path))
        except OSError:
            pass

    def _xlsx(name: str, md: str) -> None:
        try:
            path = export_xlsx(md, os.path.join(out_dir, name))
            if path:
                written.append(os.path.abspath(path))
        except Exception:
            pass

    def _pdf(name: str, md: str, title: str) -> None:
        try:
            path = export_pdf(md, os.path.join(out_dir, name), title=title)
            if path:
                written.append(os.path.abspath(path))
        except Exception:
            pass

    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return written

    # 1) Résumé de l'étude (« note de calcul » du projet chargé, statuts
    #    honnêtes — jamais transformé en document conforme, §15.3)
    try:
        md = project_summary(project)
    except Exception:
        md = ""
    if md:
        _put("resume_etude.md", md)
        _xlsx("resume_etude.xlsx", md)
        _pdf("resume_etude.pdf", md, "Résumé d'étude - STRUCTCALC PRO")

    # 2) Fiches de poteau — UNE par poteau RÉELLEMENT présent (0 = 0)
    cols = list((getattr(project, "columns", None) or {}).values())
    for col in cols:
        try:
            fmd = column_fiche(col, project=project)
        except Exception:
            continue
        if not fmd:
            continue
        safe = str(getattr(col, "sc_id", "poteau")).replace("/", "-")
        _put(f"fiche_poteau_{safe}.md", fmd)
        _xlsx(f"fiche_poteau_{safe}.xlsx", fmd)
        _pdf(f"fiche_poteau_{safe}.pdf", fmd, f"Fiche de poteau {safe}")

    # 3) Constats de cohérence / rapport de vérification (si fournis)
    if coherence_md and coherence_md.strip():
        _put("rapport_coherence.md", coherence_md)

    # 4) Index honnête : ce qui EST dans le dossier, sans promesse
    has_fiche = any(os.path.basename(w).startswith("fiche_poteau")
                    for w in written)
    listing = [
        "Dossier de rendu STRUCTCALC PRO",
        "",
        "Contenu reel (aucune conformite non verifiee n'est declaree) :",
        "",
        "- LISEZ-MOI.txt",
    ]
    for w in sorted(written):
        listing.append(f"- {os.path.basename(w)}")
    if not has_fiche:
        listing.append(
            "- (aucune fiche de poteau : le projet charge ne contient "
            "aucun poteau - rien n'est invente)")
    _put("LISEZ-MOI.txt", "\n".join(listing) + "\n")

    return written
