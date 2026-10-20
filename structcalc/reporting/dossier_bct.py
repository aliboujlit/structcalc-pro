# -*- coding: utf-8 -*-
"""
reporting/dossier_bct.py — Dossier de contrôle (bureau de contrôle).

Référentiel déclaré : RÈGLES MAROCAINES — base BAEL 91 révisé 99 (béton
armé) + RPS 2011 (parasismique), choix confirmé par l'utilisateur
(20/10/2026). Le programme ne prétend PAS maîtriser l'intégralité du
référentiel marocain : chaque pièce du dossier porte un ÉTAT honnête :

  GÉNÉRÉ           — document produit par le programme à partir du modèle
  À VALIDER        — produit mais contenant des vérifications A_VALIDER
                     (validation ingénieur requise avant remise)
  À COMPLÉTER      — pièce administrative/fournie par l'entreprise, le
                     programme ne peut pas la produire (motif exact)
  NON IMPLÉMENTÉ   — contrôle réglementaire existant dans le référentiel
                     mais non implémenté dans le programme (motif exact)
  NON APPLICABLE   — pièce sans objet pour ce projet (motif)

RÈGLE ABSOLUE (spec §0, §15.3) : aucun statut « CONFORME » n'est décerné
par ce module. Le dossier est une LISTE DE CONTRÔLE honnête destinée au
bureau de contrôle — pas une attestation de conformité.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from ..version import __version__


@dataclass
class PieceBCT:
    """Une pièce du dossier de contrôle."""
    code: str                 # ex. "BCT-01"
    titre: str
    etat: str                 # GÉNÉRÉ | À VALIDER | À COMPLÉTER | ...
    motif: str = ""           # raison exacte de l'état (jamais vide)
    fichier: str = ""         # chemin si GÉNÉRÉ par le programme


@dataclass
class DossierBCT:
    pieces: List[PieceBCT] = field(default_factory=list)

    @property
    def generated(self) -> List[PieceBCT]:
        return [p for p in self.pieces if p.etat == "GÉNÉRÉ"]

    @property
    def to_validate(self) -> List[PieceBCT]:
        return [p for p in self.pieces if p.etat == "À VALIDER"]

    @property
    def incomplete(self) -> List[PieceBCT]:
        return [p for p in self.pieces
                if p.etat in ("À COMPLÉTER", "NON IMPLÉMENTÉ")]


def build_dossier_bct(project, files_written=None,
                      design_done: bool = False) -> DossierBCT:
    """
    Assemble la liste de contrôle du dossier BCT à partir de l'état RÉEL
    du projet chargé et des fichiers effectivement écrits.

    `files_written` : liste des chemins réellement produits (dossier de
    rendu, plans…) — seuls ces fichiers sont listés comme GÉNÉRÉ.
    `design_done` : True si un dimensionnement a été exécuté dans la
    session (SOLVER) — sinon les pièces d'armature sont refusées.
    """
    files = [str(f) for f in (files_written or [])]
    cols = list((getattr(project, "columns", None) or {}).values())
    nodes = list((getattr(project, "nodes", None) or {}).values())
    has_model = bool(cols or nodes)

    def _find(*prefixes):
        for f in files:
            for pre in prefixes:
                if pre.lower() in f.lower():
                    return f
        return ""

    d = DossierBCT()

    # -- Modèle et plans ------------------------------------------------
    d.pieces.append(PieceBCT(
        "BCT-01", "Note de calcul BAEL 91 révisé 99 (poteaux)",
        etat="À VALIDER" if has_model else "À COMPLÉTER",
        motif=("Articles transcrits mais NON vérifiés indépendamment "
               "(A_VALIDER) : la note expose les formules, coefficients "
               "(γc=1,5 / γs=1,15) et cas de référence — conformité "
               "à établir par l'ingénieur avant remise."
               if has_model else
               "Aucun modèle structuré chargé : rien à calculer, "
               "aucune note produite (0 objet = 0 document)."),
        fichier=_find("resume_etude", "note_calcul")))

    d.pieces.append(PieceBCT(
        "BCT-02", "Plan de coffrage (par niveau)",
        etat="GÉNÉRÉ" if _find("coffrage") else "À COMPLÉTER",
        motif=("Plan(s) PDF vectoriel(aux) généré(s) depuis le modèle "
               "Robot réel (cotes en m, dimensions de section déduites "
               "des labels R<b>x<h> — déduction tracée sur le plan)."
               if _find("coffrage") else
               "Aucun plan de coffrage écrit : soit le modèle est vide, "
               "soit l'export n'a pas été lancé (Rapports > Plans de "
               "coffrage)."),
        fichier=_find("coffrage")))

    d.pieces.append(PieceBCT(
        "BCT-03", "Plan de ferraillage (poteaux)",
        etat=("À VALIDER" if _find("ferraillage") else "À COMPLÉTER"),
        motif=("PROPOSITION d'armature issue du dimensionnement "
               "(barres HA Ø12–Ø32, cadres) — chaque page est marquée "
               "« À VALIDER » : espacements, longueurs d'attente et "
               "recouvrements restent sous responsabilité ingénieur."
               if _find("ferraillage") else
               "Aucun plan de ferraillage écrit : le dimensionnement "
               "(Calculs > Dimensionner les poteaux) puis l'export "
               "(Rapports > Plans de ferraillage) sont requis."),
        fichier=_find("ferraillage")))

    d.pieces.append(PieceBCT(
        "BCT-04", "Nomenclature d'acier",
        etat=("À VALIDER" if _find("ferraillage", "nomenclature")
              else "À COMPLÉTER"),
        motif=("Masses calculées (ρ=7850 kg/m3) sur propositions "
               "d'armature — quantités À CONFIRMER (varient avec les "
               "longueurs d'attente/recouvrement retenues)."
               if _find("ferraillage", "nomenclature") else
               "Produite avec le plan de ferraillage (non généré)."),
        fichier=_find("ferraillage", "nomenclature")))

    # -- Parasismique (RPS 2011) ----------------------------------------
    seismic = [lc for lc in (getattr(project, "load_cases", {}) or
                             {}).values()
               if getattr(lc, "kind", "") == "seismic"]
    d.pieces.append(PieceBCT(
        "BCT-05", "Dossier parasismique RPS 2011 (zones sismiques MA/I–IV)",
        etat="NON IMPLÉMENTÉ",
        motif=("Le contrôle du spectre de réponse (ag, S, Tc…) n'est PAS "
               "implémenté dans le programme — aucun paramètre de site "
               "n'a été lu depuis Robot (refus motivé : valeurs "
               "inventées interdites). Le programme fournit la LISTE des "
               "cas sismiques présents dans l'étude"
               + (f" ({len(seismic)} cas détectés)" if seismic
                  else " (aucun cas sismique détecté)")
               + " ; le dossier RPS (spectre, coefficients de site, "
                 "détails parasismiques) reste À PRODUIRE par l'ingénieur."),
        fichier=""))

    # -- Pièces administratives / entreprise -----------------------------
    d.pieces.append(PieceBCT(
        "BCT-06", "Certificats matière (béton : C25/30 ou classe retenue)",
        etat="À COMPLÉTER",
        motif=("Pièce fournie par le BET / l'entreprise (certificat de "
               "qualité du béton) : le programme ne détient aucune "
               "donnée de fournisseur et n'en invente pas.")))

    d.pieces.append(PieceBCT(
        "BCT-07", "Certificats matière (acier HA : classe retenue)",
        etat="À COMPLÉTER",
        motif=("Classe d'acier NON LUE dans l'étude Robot (aucun label "
               "armature) — l'hypothèse HA500 est AFFICHÉE dans les "
               "documents de calcul, le certificat matière est À FOURNIR.")))

    d.pieces.append(PieceBCT(
        "BCT-08", "Rapport d'essais béton (contrôle à la prise / 28 j)",
        etat="À COMPLÉTER",
        motif=("Rapport d'essais du laboratoire agréé : pièce "
               "d'exécution hors périmètre du programme (aucune donnée "
               "d'essai n'est saisie ni produite).")))

    d.pieces.append(PieceBCT(
        "BCT-09", "Dossier d'exécution (plans cotés d'exécution, fiches)",
        etat="À COMPLÉTER",
        motif=("Plans d'exécution cotés en mm avec tolérances de "
               "ferraillage : les plans générés (BCT-02/03) sont des "
               "propositions à mm/préciser — la version d'exécution est "
               "établie par le BET après validation.")))

    d.pieces.append(PieceBCT(
        "BCT-10", "Attestation d'assurance / qualification du BET",
        etat="À COMPLÉTER",
        motif=("Pièce administrative de l'entreprise de conception : "
               "hors périmètre du programme.")))

    d.pieces.append(PieceBCT(
        "BCT-11", "Relevé de compatibilité géotechnique",
        etat="À COMPLÉTER",
        motif=("Rapport de sol du laboratoire agréé : donnée d'entrée "
               "du BET (portance, tassement) — non lue dans Robot ni "
               "dans le programme.")))

    # -- Synthèse dimensionnement ---------------------------------------
    d.pieces.append(PieceBCT(
        "BCT-12", "Fiches de poteau (dimensionnement par poteau)",
        etat=("GÉNÉRÉ" if _find("fiche_poteau") else "À COMPLÉTER"),
        motif=("Fiches MD/PDF/XLSX générées pour chaque poteau "
               "RÉELLEMENT présent (statuts honnêtes A_VALIDER)."
               if _find("fiche_poteau") else
               "Aucune fiche générée (export non lancé ou modèle vide)."),
        fichier=_find("fiche_poteau")))

    return d


def dossier_bct_md(d: DossierBCT, project_name: str = "") -> str:
    """Rendu Markdown de la liste de contrôle (source pour PDF/XLSX)."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = [
        f"# Dossier de contrôle — {project_name or 'projet'}",
        "",
        f"_Généré par STRUCTCALC PRO v{__version__} le {now}_",
        "",
        "**Référentiel déclaré : règles marocaines — base BAEL 91 révisé 99 "
        "(béton armé) + RPS 2011 (parasismique).**",
        "",
        "> Ce document est une LISTE DE CONTRÔLE honnête, pas une "
        "attestation de conformité : aucun statut « CONFORME » n'est "
        "décerné. Les vérifications réglementaires portent le statut "
        "A_VALIDER tant que les articles ne sont pas vérifiés "
        "indépendamment (spec §11.3, §15.3).",
        "",
        "## État des pièces",
        "",
        "| Code | Pièce | État | Motif / précision |",
        "|---|---|---|---|",
    ]
    for p in d.pieces:
        lines.append(f"| {p.code} | {p.titre} | **{p.etat}** | {p.motif} |")
    lines += [
        "",
        "## Synthèse",
        "",
        f"- Pièces GÉNÉRÉES par le programme : **{len(d.generated)}**",
        f"- Pièces À VALIDER (ingénieur) : **{len(d.to_validate)}**",
        f"- Pièces À COMPLÉTER / NON IMPLÉMENTÉES : "
        f"**{len(d.incomplete)}**",
        "",
    ]
    for p in d.generated:
        if p.fichier:
            lines.append(f"- GÉNÉRÉ : `{p.fichier}` ({p.code})")
    for p in d.to_validate:
        lines.append(f"- À VALIDER avant remise : {p.titre} ({p.code})")
    lines += [
        "",
        "## Avertissement",
        "",
        "> La conformité réglementaire (BAEL 91 r99, RPS 2011) n'est "
        "PAS établie par ce dossier : les articles cités ne sont pas "
        "encore vérifiés indépendamment. Validation ingénieur REQUISE "
        "avant toute remise au bureau de contrôle (spec §15.3).",
        "",
    ]
    return "\n".join(lines)
