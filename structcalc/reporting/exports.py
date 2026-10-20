# -*- coding: utf-8 -*-
"""
reporting/exports.py — Exports XLSX et PDF du reporting (spec §15.3).

Principe d'honnêteté : l'export contient EXACTEMENT le contenu Markdown produit
par `column_fiche()` / `project_summary()` (source de vérité unique). Aucune
donnée n'est ajoutée, masquée ni reformulée pour paraître « conforme » : les
statuts `A_VALIDER`, `NON_CONFORME`, `VERIFICATION_NON_IMPLEMENTE`,
`DONNEES_MANQUANTES` sont reproduits tels quels.

Architecture :
  - `parse_markdown()` : analyse en blocs (titre, section, texte, tableau) ;
  - `export_xlsx()`    : rendu openpyxl (une feuille par section `##`) ;
  - `export_pdf()`     : rendu reportlab (titres, paragraphes, tableaux).

Entrées de confort (`export_column_fiche_*`, `export_project_summary_*`)
appellent le générateur Markdown puis l'exporteur — donc la sortie exportée et
l'affichage ne peuvent pas diverger.

Si une bibliothèque d'export est absente, une erreur EXPLICITE est levée
(jamais de faux succès — spec §0).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Modèle de blocs Markdown
# ---------------------------------------------------------------------------

@dataclass
class Block:
    kind: str                 # "heading" | "text" | "table"
    level: int = 0            # niveau du titre (1 = #, 2 = ##)
    text: str = ""            # texte (heading/text)
    rows: List[List[str]] = field(default_factory=list)  # lignes (table)


def _split_row(line: str) -> List[str]:
    """Une ligne `| a | b |` -> ['a', 'b'] (bords et cellules vides gérés)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(line: str) -> bool:
    """Ligne de séparation de tableau markdown : |---|:---|"""
    s = line.strip()
    return bool(s) and s.startswith("|") and re.fullmatch(r"[\s|:\-]+", s) is not None


def parse_markdown(md_text: str) -> List[Block]:
    """Analyse un document Markdown en une liste de blocs ordonnés."""
    blocks: List[Block] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Titre
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            blocks.append(Block(kind="heading", level=len(m.group(1)),
                                text=m.group(2).strip()))
            i += 1
            continue

        # Bloc de tableau (lignes consécutives commençant par | )
        if stripped.startswith("|"):
            tbl: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not _is_separator(lines[i]):
                    tbl.append(_split_row(lines[i]))
                i += 1
            if tbl:
                blocks.append(Block(kind="table", rows=tbl))
            continue

        # Texte courant (non vide) ; regroupe les lignes consécutives
        if stripped:
            para = [stripped]
            i += 1
            while (i < len(lines) and lines[i].strip()
                   and not lines[i].strip().startswith("#")
                   and not lines[i].strip().startswith("|")):
                para.append(lines[i].strip())
                i += 1
            blocks.append(Block(kind="text", text=" ".join(para)))
            continue

        i += 1
    return blocks


# ---------------------------------------------------------------------------
# Export XLSX (openpyxl)
# ---------------------------------------------------------------------------

def export_xlsx(md_text: str, path: str) -> str:
    """
    Exporte le Markdown vers un classeur XLSX. Une feuille par section `##`
    (le titre `#` et le texte initial vont dans la première feuille).
    Retourne le chemin écrit. Lève une erreur explicite en cas d'échec.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Export XLSX impossible : 'openpyxl' indisponible "
            f"({exc}). Installez-le pour activer l'export §15.3."
        ) from exc

    blocks = parse_markdown(md_text)
    wb = Workbook()
    first = wb.active
    first.title = "Document"
    sheets = [first]
    cur = first
    r = 1

    def _sanitize(title: str) -> str:
        t = re.sub(r"[\\/*?:\[\]]", "-", title).strip() or "Section"
        return t[:31]

    header_fill = PatternFill("solid", fgColor="DDEBF7")

    def _write_table(ws, rows, start_row):
        if not rows:
            return start_row
        ncol = max(len(x) for x in rows)
        rr = start_row
        for ri, row in enumerate(rows):
            for ci in range(ncol):
                val = row[ci] if ci < len(row) else ""
                cell = ws.cell(row=rr, column=ci + 1, value=val)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if ri == 0:  # ligne d'en-tête du tableau
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
            rr += 1
        return rr

    for blk in blocks:
        if blk.kind == "heading" and blk.level >= 2:
            # nouvelle feuille par section ##
            cur = wb.create_sheet(_sanitize(blk.text))
            sheets.append(cur)
            r = 1
            c = cur.cell(row=r, column=1, value=blk.text)
            c.font = Font(bold=True, size=12)
            r += 2
        elif blk.kind == "heading":  # titre # dans la feuille courante
            c = cur.cell(row=r, column=1, value=blk.text)
            c.font = Font(bold=True, size=14)
            r += 2
        elif blk.kind == "text":
            c = cur.cell(row=r, column=1, value=blk.text)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            r += 1
        elif blk.kind == "table":
            r = _write_table(cur, blk.rows, r) + 1

    # Largeur de colonne raisonnable sur chaque feuille
    for ws in sheets:
        for col in ws.columns:
            letter = col[0].column_letter
            ws.column_dimensions[letter].width = 30

    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Export PDF (reportlab)
# ---------------------------------------------------------------------------

def _md_inline(text: str) -> str:
    """Échappe le texte pour reportlab Paragraph puis ré-applique le gras."""
    t = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)          # code en ligne -> texte
    t = re.sub(r"\[([^\]]+)\]", r"\1", t)       # [OK] -> OK (badge texte)
    return t


def export_pdf(md_text: str, path: str, title: str = "") -> str:
    """
    Exporte le Markdown vers un PDF. Retourne le chemin écrit. Lève une
    erreur explicite si reportlab est indisponible (jamais de faux succès).
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Export PDF impossible : 'reportlab' indisponible "
            f"({exc}). Installez-le pour activer l'export §15.3."
        ) from exc

    blocks = parse_markdown(md_text)
    styles = getSampleStyleSheet()
    st_h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16,
                           alignment=TA_LEFT, spaceAfter=8)
    st_h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                           textColor=colors.HexColor("#1a4f8b"),
                           spaceBefore=10, spaceAfter=4)
    st_body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9,
                             leading=12, spaceAfter=4)
    st_cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7.5,
                             leading=9)
    st_cell_b = ParagraphStyle("cellb", parent=st_cell, fontName="Helvetica-Bold")

    story = []
    if title:
        story.append(Paragraph(_md_inline(title), st_h1))

    usable_w = A4[0] - 30 * mm

    for blk in blocks:
        if blk.kind == "heading":
            story.append(Paragraph(_md_inline(blk.text),
                                   st_h1 if blk.level == 1 else st_h2))
        elif blk.kind == "text":
            story.append(Paragraph(_md_inline(blk.text), st_body))
        elif blk.kind == "table" and blk.rows:
            ncol = max(len(r) for r in blk.rows)
            data = []
            for ri, row in enumerate(blk.rows):
                cells = []
                for ci in range(ncol):
                    txt = row[ci] if ci < len(row) else ""
                    cells.append(Paragraph(_md_inline(txt),
                                           st_cell_b if ri == 0 else st_cell))
                data.append(cells)
            col_w = usable_w / ncol
            tbl = Table(data, colWidths=[col_w] * ncol, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(story)
    return path


# ---------------------------------------------------------------------------
# Entrées de confort (source de vérité = générateur Markdown)
# ---------------------------------------------------------------------------

def export_column_fiche_xlsx(column, outcomes=None, path="fiche_poteau.xlsx",
                             project=None, materials=None) -> str:
    from .column_report import column_fiche
    md = column_fiche(column, project=project, outcomes=outcomes,
                      materials=materials)
    return export_xlsx(md, path)


def export_column_fiche_pdf(column, outcomes=None, path="fiche_poteau.pdf",
                            project=None, materials=None) -> str:
    from .column_report import column_fiche
    md = column_fiche(column, project=project, outcomes=outcomes,
                      materials=materials)
    title = f"Fiche de poteau — {getattr(column, 'sc_id', '')}"
    return export_pdf(md, path, title=title)


def export_project_summary_xlsx(project, path="resume_projet.xlsx") -> str:
    from .column_report import project_summary
    return export_xlsx(project_summary(project), path)


def export_project_summary_pdf(project, path="resume_projet.pdf") -> str:
    from .column_report import project_summary
    title = f"Résumé de projet — {getattr(project, 'name', '')}"
    return export_pdf(project_summary(project), path, title=title)
