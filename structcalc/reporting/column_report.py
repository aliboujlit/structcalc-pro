# -*- coding: utf-8 -*-
"""
reporting/column_report.py — Fiche de poteau et résumé de projet (spec §15.2, §15.3).

Produit des rapports TRAÇABLES et HONNÊTES :
  - fiche de poteau (§15.2) : identifiant, étage, section, matériaux, hauteurs,
    élancements, sollicitations déterminantes, vérifications, ferraillage,
    statut, références réglementaires ;
  - résumé de projet (§15.3) : ne présente JAMAIS une étude incomplète comme
    conforme. Les statuts non conformes / manquants / non implémentés sont
    AFFICHÉS, pas masqués.

Sortie : Markdown lisible (les exports PDF/XLSX viennent en complément).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..core.status import RegulatoryStatus, REGULATORY_STATUS_LABELS_FR


def _fmt(v, unit=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s} {unit}".strip()
    return f"{v} {unit}".strip()


def _status_badge(status: RegulatoryStatus) -> str:
    label = REGULATORY_STATUS_LABELS_FR.get(status, str(status))
    # Marqueur visuel selon gravité
    if status == RegulatoryStatus.CONFORME:
        return f"[OK] {label}"
    if status == RegulatoryStatus.NON_CONFORME:
        return f"[X] {label}"
    if status in (RegulatoryStatus.VERIFICATION_NON_IMPLEMENTE,
                  RegulatoryStatus.DONNEES_MANQUANTES):
        return f"[!] {label}"
    return f"[?] {label}"


def column_fiche(column, project=None, outcomes: Optional[List] = None,
                 materials=None) -> str:
    """
    Génère une fiche de poteau (Markdown) conforme au contenu §15.2.

    `outcomes` : liste de DesignOutcome du solver (variantes évaluées).
    Affiche les statuts honnêtes de chaque vérification.
    """
    lines: List[str] = []
    lines.append(f"# Fiche de poteau — {getattr(column, 'sc_id', '?')}")
    lines.append("")
    lines.append(f"_Généré le {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}_")
    lines.append("")

    # Identification
    lines.append("## 1. Identification")
    lines.append(f"- **Identifiant** : {getattr(column, 'sc_id', '—')}")
    lines.append(f"- **Nom** : {getattr(column, 'name', '') or '—'}")
    lines.append(f"- **Niveau / étage** : {getattr(column, 'storey', None) or '—'}")
    lines.append(f"- **Nœud de départ** : {getattr(column, 'start_node', None) or '—'}")
    lines.append(f"- **Nœud d'arrivée** : {getattr(column, 'end_node', None) or '—'}")
    lines.append("")

    # Géométrie et matériaux
    lines.append("## 2. Géométrie et matériaux")
    h = getattr(column, "height", None)
    lines.append(f"- **Hauteur** : {_fmt(getattr(h, 'value', None), getattr(h, 'unit', 'm'))}")
    by = getattr(column, "buckling_length_y", None)
    bz = getattr(column, "buckling_length_z", None)
    lines.append(f"- **Longueur de flambement y / z** : "
                 f"{_fmt(getattr(by, 'value', None))} / {_fmt(getattr(bz, 'value', None))}")
    lines.append(f"- **Section** : {getattr(column, 'section', None) or '—'}")
    lines.append(f"- **Matériau** : {getattr(column, 'material', None) or '—'}")
    lines.append(f"- **Liaison haut/bas** : "
                 f"{getattr(column, 'fixity_top', '') or '—'} / "
                 f"{getattr(column, 'fixity_bottom', '') or '—'}")
    lines.append("")

    # Vérifications (variantes du solver)
    lines.append("## 3. Vérifications réglementaires")
    if not outcomes:
        lines.append("_Aucune vérification exécutée pour cette fiche._")
        lines.append("")
    else:
        lines.append("| Section | Check | Statut | Détail |")
        lines.append("|---|---|---|---|")
        for out in outcomes:
            for c in out.checks:
                lines.append(
                    f"| {out.variant.designation} | {c.check_id} | "
                    f"{_status_badge(c.status)} | {c.message} |")
        lines.append("")

    # Références réglementaires
    lines.append("## 4. Références réglementaires")
    lines.append("- BAEL 91 révisé 99 (poteaux comprimés, élancement) — "
                 "**articles à confirmer sur l'édition officielle**")
    lines.append("- RPS 2011 (contrôles parasismiques) — **non implémentés**")
    lines.append("")

    # Avertissement d'honnêteté (spec §15.3)
    lines.append("## 5. Avertissement")
    lines.append("> Les vérifications ci-dessus ne sont PAS présentées comme "
                 "conformes : les articles réglementaires ne sont pas encore "
                 "vérifiés indépendamment, et certains contrôles (flexion "
                 "composée, second ordre, parasismique) ne sont pas "
                 "implémentés. Validation ingénieur REQUISE (spec §15.3).")
    lines.append("")
    return "\n".join(lines)


def project_summary(project) -> str:
    """
    Résumé de projet (Markdown). Affiche l'état honnête du modèle (§15.3) :
    objets, données manquantes, éléments à valider.
    """
    lines: List[str] = []
    lines.append(f"# Résumé de projet — {getattr(project, 'name', '') or getattr(project, 'sc_id', '?')}")
    lines.append("")
    lines.append(f"_Généré le {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}_")
    lines.append("")

    counts = project.counts()
    lines.append("## 1. Contenu du modèle")
    lines.append("| Type | Nombre |")
    lines.append("|---|---|")
    for k, v in counts.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Données manquantes (spec §4.2) — AFFICHÉES, jamais masquées
    gaps = project.data_gaps()
    lines.append("## 2. Données manquantes")
    if not gaps:
        lines.append("_Aucune donnée manquante détectée dans les objets contrôlés._")
    else:
        lines.append("> **Attention** : les propriétés suivantes sont MANQUANTES "
                     "et ne doivent pas être inventées (spec §4.2) :")
        for obj_id, props in gaps.items():
            lines.append(f"- `{obj_id}` : {', '.join(props)}")
    lines.append("")

    lines.append("## 3. Statut global")
    lines.append("> **Aucune conformité réglementaire n'est déclarée.** "
                 "Le dimensionnement et les vérifications BAEL/RPS nécessitent "
                 "la validation d'un ingénieur compétent (spec §20).")
    lines.append("")
    return "\n".join(lines)
