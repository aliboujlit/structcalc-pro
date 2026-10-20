# -*- coding: utf-8 -*-
"""
gui/combos_tab.py — Onglet « Combinaisons & démarches ».

Demande utilisateur : « toutes les combinaisons et démarches possibles à
produire entre les logiciels, avec les cas possibles dans cette industrie de
bureau des études et technologies ».

Contenu :
  1. MATRICE 6x6 : chaque cellule (source, cible) = faisabilité réelle
     évaluée par le hub selon les capacités VÉRIFIÉES (OK / REFUS + motif).
  2. DEMARCHES : les workflows bureau d'études (interop/combinaisons.py)
     avec leur chaîne et l'évaluation honnête de leurs jambages.
  3. CAS D'INDUSTRIE : typologies de projets, logiciels mobilisés,
     livrables et note de réalité (obstacles nommés, jamais minimisés).

Aucun logiciel n'est lancé pour afficher cet écran (capacités statiques,
pas de COM) — spec §19 : rien n'est présenté comme disponible sans preuve.
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView, QAbstractItemView, QTabWidget,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ..integration.interop.loop import SOFTWARE_NAMES, LABELS
from ..integration.interop.combinaisons import (
    WORKFLOWS, INDUSTRY_CASES, inventory,
)


class CombosTab(QWidget):
    """Onglet « Combinaisons & démarches » (matrice + workflows + cas)."""

    # Signal vers la fenêtre principale (journal / statut)
    log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        from ..version import VERSION_STRING, APP_NAME
        title = QLabel(f"Combinaisons & démarches — {APP_NAME} v{VERSION_STRING}")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        inv = inventory()
        sub = QLabel(
            f"{len(SOFTWARE_NAMES)} logiciels — {inv.n_senses} sens dirigés "
            f"(A -> B) — {inv.n_reciprocal} paires réciproques — "
            f"{len(WORKFLOWS)} démarches — {len(INDUSTRY_CASES)} cas "
            f"d'industrie. Faisabilité réelle évaluée par le hub "
            f"(capacités vérifiées, refus motivés).")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#a6adc8;")
        root.addWidget(sub)

        # --- Matrice 6x6 ---
        box = QGroupBox("Matrice des combinaisons (lignes = source, "
                        "colonnes = cible — via pivot SC-*)")
        box.setStyleSheet("QGroupBox{color:#cdd6f4;font-weight:bold;}")
        vbox = QVBoxLayout(box)

        refresh = QPushButton("Réévaluer les capacités (sans lancer de "
                              "logiciel)")
        refresh.setStyleSheet(
            "QPushButton{background:#313244;color:#cdd6f4;"
            "border:1px solid #45475a;border-radius:5px;padding:4px 10px;}")
        refresh.clicked.connect(self.refresh)
        hb = QHBoxLayout()
        hb.addWidget(refresh)
        hb.addStretch(1)
        vbox.addLayout(hb)

        self._matrix = QTableWidget(len(SOFTWARE_NAMES) + 1,
                                    len(SOFTWARE_NAMES) + 1)
        self._matrix.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._matrix.verticalHeader().setVisible(False)
        self._matrix.horizontalHeader().setVisible(False)
        self._matrix.setStyleSheet(
            "QTableWidget{background:#1e1e2e;color:#cdd6f4;"
            "gridline-color:#45475a;}")
        self._matrix.setMaximumHeight(260)
        vbox.addWidget(self._matrix)
        root.addWidget(box)

        # --- Onglets Démarches / Cas industrie ---
        inner = QTabWidget()
        inner.setStyleSheet(
            "QTabWidget::pane{border:1px solid #45475a;}"
            "QTabBar::tab{background:#313244;color:#a6adc8;padding:6px 12px;}"
            "QTabBar::tab:selected{background:#45475a;color:#cdd6f4;}")

        # Démarches
        self._wf_table = QTableWidget(0, 4)
        self._wf_table.setHorizontalHeaderLabels(
            ["Démarche", "Chaîne (boucle fermée)", "Jambages évalués",
             "Objectif / cas industrie"])
        self._wf_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._wf_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._wf_table.setStyleSheet(
            "QTableWidget{background:#1e1e2e;color:#cdd6f4;"
            "gridline-color:#45475a;}"
            "QHeaderView::section{background:#313244;color:#89b4fa;}")
        vh = self._wf_table.horizontalHeader()
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        inner.addTab(self._wf_table, "Démarches (workflows)")

        # Cas d'industrie
        self._case_table = QTableWidget(0, 4)
        self._case_table.setHorizontalHeaderLabels(
            ["Cas d'industrie", "Logiciels mobilisés",
             "Démarches", "Livrables / réalité honnête"])
        self._case_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._case_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._case_table.setStyleSheet(
            "QTableWidget{background:#1e1e2e;color:#cdd6f4;"
            "gridline-color:#45475a;}"
            "QHeaderView::section{background:#313244;color:#89b4fa;}")
        vh2 = self._case_table.horizontalHeader()
        vh2.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vh2.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        inner.addTab(self._case_table, "Cas d'industrie")
        root.addWidget(inner, 1)

        note = QLabel(
            "Évaluation honnête : OK = route faisable selon les capacités "
            "vérifiées ; REFUS = motif affiché au survol (ex. Revit sans "
            "add-in .NET, objets Civil 3D hors .NET). Aucun logiciel n'est "
            "lancé par cet écran.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#f38ba8;font-size:11px;")
        root.addWidget(note)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """(Ré)évalue les capacités via le hub — statique, sans COM."""
        try:
            from ..integration.interop import default_hub
            hub = default_hub()
            routes = hub.routes()
            reciprocal = hub.reciprocal_pairs()
        except Exception as exc:  # jamais de crash muet
            self._show_error(str(exc))
            return
        self._fill_matrix(routes, reciprocal)
        self._fill_workflows(routes)
        self._fill_cases()

    def _show_error(self, msg: str):
        self._matrix.setRowCount(0)
        self._matrix.setColumnCount(0)
        self._wf_table.setRowCount(0)
        self._case_table.setRowCount(0)

    # --- Matrice ---
    def _fill_matrix(self, routes: Dict, reciprocal):
        names = list(SOFTWARE_NAMES)
        m = self._matrix
        m.setRowCount(len(names) + 1)
        m.setColumnCount(len(names) + 1)
        m.setItem(0, 0, QTableWidgetItem("src \\ tgt"))
        for j, tgt in enumerate(names, start=1):
            it = QTableWidgetItem(LABELS[tgt])
            it.setForeground(Qt.GlobalColor.darkCyan)
            m.setItem(0, j, it)
        for i, src in enumerate(names, start=1):
            it = QTableWidgetItem(LABELS[src])
            it.setForeground(Qt.GlobalColor.darkCyan)
            m.setItem(i, 0, it)
            for j, tgt in enumerate(names, start=1):
                if src == tgt:
                    cell = QTableWidgetItem("—")
                    cell.setForeground(Qt.GlobalColor.gray)
                    cell.setToolTip("Même logiciel (route inutile)")
                    m.setItem(i, j, cell)
                    continue
                info = routes.get(src, {}).get(tgt, {})
                ok = info.get("feasible", False)
                if ok:
                    cell = QTableWidgetItem("OK")
                    cell.setForeground(Qt.GlobalColor.darkGreen)
                    cell.setToolTip(
                        f"{LABELS[src]} -> {LABELS[tgt]} : "
                        "route faisable (A -> pivot -> B)")
                else:
                    cell = QTableWidgetItem("REFUS")
                    cell.setForeground(Qt.GlobalColor.red)
                    missing = ", ".join(info.get("missing", []))
                    cell.setToolTip(
                        f"{LABELS[src]} -> {LABELS[tgt]} : "
                        f"{info.get('reason', '?')}"
                        + (f"\n{missing}" if missing else ""))
                m.setItem(i, j, cell)
        m.resizeColumnsToContents()

    # --- Démarches ---
    def _fill_workflows(self, routes: Dict):
        t = self._wf_table
        t.setRowCount(0)
        for w in WORKFLOWS:
            legs_txt = []
            n_ok = 0
            for s, tg in w.legs:
                info = routes.get(s, {}).get(tg, {})
                ok = info.get("feasible", False)
                n_ok += 1 if ok else 0
                legs_txt.append(
                    (f"{s}->{tg} : OK" if ok else
                     f"{s}->{tg} : REFUS ({info.get('reason', '?')}"
                     + (", " + ", ".join(info.get("missing", []))
                        if info.get("missing") else "") + ")"))
            r = t.rowCount()
            t.insertRow(r)
            vals = [
                w.name,
                w.chain_labels,
                f"{n_ok}/{len(w.legs)} faisables — " + " | ".join(legs_txt),
                f"{w.objective} [Cas : {w.industry_case}]"
                + (f"\nNote : {w.notes}" if w.notes else ""),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 2 and n_ok < len(w.legs):
                    item.setForeground(Qt.GlobalColor.red)
                t.setItem(r, c, item)
        t.resizeColumnsToContents()

    # --- Cas industrie ---
    def _fill_cases(self):
        t = self._case_table
        t.setRowCount(0)
        for c in INDUSTRY_CASES:
            r = t.rowCount()
            t.insertRow(r)
            vals = [
                c.name,
                c.software_labels,
                ", ".join(c.workflows),
                "Livrables : " + ", ".join(c.deliverables)
                + "\nRéalité : " + c.reality,
            ]
            for col, v in enumerate(vals):
                t.setItem(r, col, QTableWidgetItem(v))
        t.resizeColumnsToContents()
