# -*- coding: utf-8 -*-
"""
gui/loop_tab.py — Onglet « Boucle logiciels » (cases à cocher).

Demande utilisateur :
  1) cocher les logiciels à mettre en boucle (ex. Revit + Robot « en
     conception et étude ») ;
  2) « chaque logiciel doit accomplir les missions dont il est conçu » —
     chaque maillon exécute sa mission propre (voir interop/loop.py) :
       - Revit      -> Conception BIM (modèle, add-in .NET)
       - Robot      -> Étude : write_loads (charges) puis read_results
       - AutoCAD / Civil 3D / Advance Steel -> Plans DWG
       - Navisworks -> Coordination NWD (conversion de fichiers)

Composition :
  - une ligne par logiciel : [case à cocher] + rôle (Conception / Étude /
    Conception + Étude) + mission conçue affichée ;
  - boutons Tout cocher / Tout décocher / Planifier / Lancer la boucle ;
  - aperçu du plan (chaîne fermée + missions, voir loop.py) ;
  - tableau des échanges : transport modèle + lignes de MISSION ; chaque
    REFUS/ÉCHEC s'affiche avec son MOTIF venu du hub (jamais reformulé en
    succès — spec §19/§20).

Aucune formule réglementaire ici (§14.6). L'exécution COM passe par un
QThread (§14.4) pour garder l'UI réactive.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QHeaderView,
    QAbstractItemView, QPlainTextEdit, QGridLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from ..integration.interop.loop import (
    AVAILABLE_SOFTWARE, LABELS, ROLE_LABELS, ROLES, ROLE_BOTH, PROFILES,
    MISSION_LABELS, Selection, plan_loop, describe_plan, LoopPlan,
)


class _LoopThread(QThread):
    """
    Exécute les échanges + missions de la boucle hors UI (spec §14.4).

    Émet `step_done(dict)` après CHAQUE ligne (transport ou mission) pour un
    affichage vivant, puis `all_done(int, int)` (réussies, total).
    """

    step_done = pyqtSignal(dict)
    all_done = pyqtSignal(int, int)

    def __init__(self, plan: LoopPlan, project, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._project = project

    def run(self):
        from ..integration.interop.loop import exchange_plan  # lazy (COM)
        try:
            results = exchange_plan(self._plan, self._project)
        except Exception as exc:  # jamais de crash muet
            self.step_done.emit({
                "order": 0, "source": "—", "target": "—", "phase": "—",
                "action": "—", "success": False,
                "message": f"ERREUR MOTEUR D'ÉCHANGE : {exc}"})
            self.all_done.emit(0, 1)
            return
        ok = sum(1 for r in results if r.get("success"))
        for r in results:
            self.step_done.emit(r)
        self.all_done.emit(ok, len(results))


class LoopTab(QWidget):
    """Onglet « Boucle logiciels » — sélection par cases à cocher."""

    # Signal vers la fenêtre principale (journal / statut)
    log = pyqtSignal(str)

    def __init__(self, project_provider=None, parent=None):
        super().__init__(parent)
        # Callable renvoyant le projet courant (modèle pivot SC-*)
        self._project_provider = project_provider
        self._thread: Optional[_LoopThread] = None
        self._plan: Optional[LoopPlan] = None
        self._boxes: Dict[str, QCheckBox] = {}
        self._roles: Dict[str, QComboBox] = {}
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # --- En-tête avec numéro de version ---
        from ..version import VERSION_STRING, APP_NAME
        title = QLabel(f"Boucle de logiciels — {APP_NAME} v{VERSION_STRING}")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        hint = QLabel(
            "Cochez les logiciels à mettre en boucle et donnez-leur un rôle. "
            "La boucle est FERMÉE : dernier maillon -> premier maillon "
            "(retour réciproque via le pivot SC-*). "
            "Chaque maillon accomplit SA MISSION (Robot = charges + "
            "résultats, AutoCAD/Civil 3D/Advance Steel = plans DWG, "
            "Navisworks = coordination NWD, Revit = modèle BIM). "
            "Exemple : Revit (conception) + Robot (étude) "
            "=> Revit -> Robot -> Revit.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#a6adc8;")
        root.addWidget(hint)

        # --- Groupe : logiciels cochables ---
        box = QGroupBox("Logiciels à mettre en boucle (cochez vos cases)")
        box.setStyleSheet(
            "QGroupBox{color:#cdd6f4;font-weight:bold;}"
            "QCheckBox{color:#cdd6f4;padding:2px;}"
            "QComboBox{background:#313244;color:#cdd6f4;"
            "border:1px solid #45475a;border-radius:4px;padding:2px;}"
        )
        grid = QGridLayout(box)
        grid.setColumnStretch(2, 1)
        for col, lab in enumerate(("Actif", "Rôle", "Mission conçue")):
            header = QLabel(lab)
            header.setStyleSheet("color:#89b4fa;font-weight:bold;")
            grid.addWidget(header, 0, col)

        for row, sw in enumerate(AVAILABLE_SOFTWARE, start=1):
            cb = QCheckBox(sw.label)
            cb.stateChanged.connect(self._on_selection_changed)
            role = QComboBox()
            for r in ROLES:
                role.addItem(ROLE_LABELS[r], r)
            role.setCurrentIndex(ROLES.index(ROLE_BOTH))
            role.setEnabled(False)
            prof = PROFILES[sw.name]
            info = QLabel(
                f"{MISSION_LABELS[prof.mission]} — {sw.hint}")
            info.setWordWrap(True)
            info.setStyleSheet("color:#a6adc8;font-size:11px;")
            grid.addWidget(cb, row, 0)
            grid.addWidget(role, row, 1)
            grid.addWidget(info, row, 2)
            self._boxes[sw.name] = cb
            self._roles[sw.name] = role
        root.addWidget(box)

        # --- Boutons de sélection / exécution ---
        btns = QHBoxLayout()
        b_all = QPushButton("Tout cocher")
        b_none = QPushButton("Tout décocher")
        b_plan = QPushButton("Planifier la boucle")
        b_run = QPushButton("Lancer la boucle")
        b_run.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "border-radius:6px;padding:6px 14px;}")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none.clicked.connect(lambda: self._set_all(False))
        b_plan.clicked.connect(self.plan)
        b_run.clicked.connect(self.run)
        self._run_btn = b_run
        for w in (b_all, b_none, b_plan, b_run):
            btns.addWidget(w)
        btns.addStretch(1)
        root.addLayout(btns)

        # --- Aperçu du plan ---
        self._plan_view = QPlainTextEdit()
        self._plan_view.setReadOnly(True)
        self._plan_view.setPlaceholderText(
            "Aperçu du plan de boucle : cochez au moins 2 logiciels, "
            "puis cliquez « Planifier la boucle ».")
        self._plan_view.setMaximumHeight(170)
        self._plan_view.setStyleSheet(
            "QPlainTextEdit{background:#181825;color:#cdd6f4;"
            "border:1px solid #45475a;border-radius:6px;}")
        root.addWidget(self._plan_view)

        # --- Tableau des échanges + missions ---
        lbl = QLabel("Échanges et missions (réussite/refus + motif)")
        lbl.setStyleSheet("color:#89b4fa;font-weight:bold;")
        root.addWidget(lbl)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["#", "De -> Vers (via pivot)", "Phase", "Action / mission",
             "Issue", "Motif / détail"])
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        hdr_view = self._table.horizontalHeader()
        hdr_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            "QTableWidget{background:#1e1e2e;color:#cdd6f4;"
            "gridline-color:#45475a;}"
            "QHeaderView::section{background:#313244;color:#89b4fa;}")
        root.addWidget(self._table, 1)

        note = QLabel(
            "Un refus s'affiche AVEC son motif (ex. Revit sans add-in .NET ; "
            "Navisworks sans chemin de fichier pour la conversion NWD) : "
            "aucun faux succès, aucune conformité déclarée.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#f38ba8;font-size:11px;")
        root.addWidget(note)

    # ------------------------------------------------------------------
    # Sélection
    # ------------------------------------------------------------------
    def _on_selection_changed(self, _state):
        for name, cb in self._boxes.items():
            self._roles[name].setEnabled(cb.isChecked())

    def _set_all(self, checked: bool):
        for cb in self._boxes.values():
            cb.setChecked(checked)
        self._on_selection_changed(0)

    def selected(self) -> List[Selection]:
        """Sélection courante -> objets Selection (logique testable)."""
        out: List[Selection] = []
        for name, cb in self._boxes.items():
            if cb.isChecked():
                role = self._roles[name].currentData()
                out.append(Selection(name=name, role=role or ROLE_BOTH))
        return out

    # ------------------------------------------------------------------
    # Planification / exécution
    # ------------------------------------------------------------------
    def plan(self) -> bool:
        self._plan = plan_loop(self.selected())
        self._plan_view.setPlainText(describe_plan(self._plan))
        if self._plan.ok:
            self.log.emit(f"Boucle planifiée : {len(self._plan.steps)} "
                          f"échange(s) — {', '.join(self._plan.order)} "
                          "(missions par maillon dans l'aperçu)")
        else:
            self.log.emit(f"Boucle refusée : {self._plan.error}")
        return self._plan.ok

    def run(self):
        if self._thread is not None and self._thread.isRunning():
            self.log.emit("Une boucle est déjà en cours d'exécution.")
            return
        if self._plan is None or not self._plan.ok:
            if not self.plan():
                # Refus affiché dans le tableau aussi (motif visible)
                err = self._plan.error if self._plan else "plan absent"
                self._add_row({
                    "order": 0, "source": "—", "target": "—",
                    "phase": "Planification", "action": "—",
                    "success": False, "message": err})
                return

        project = None
        if self._project_provider is not None:
            try:
                project = self._project_provider()
            except Exception as exc:
                project = None
                self.log.emit(f"Projet introuvable ({exc}) : échanges "
                              "demandés sans modèle pivot.")

        self._table.setRowCount(0)
        self._run_btn.setEnabled(False)
        self.log.emit(f"Lancement de la boucle ({len(self._plan.steps)} "
                      "échanges + missions par maillon)…")

        self._thread = _LoopThread(self._plan, project)
        self._thread.step_done.connect(self._add_row)
        self._thread.all_done.connect(self._on_done)
        self._thread.start()

    def _add_row(self, r: dict):
        row = self._table.rowCount()
        self._table.insertRow(row)
        success = bool(r.get("success"))
        vals = [
            str(r.get("order", "")),
            f"{r.get('source', '')} -> pivot -> {r.get('target', '')}",
            str(r.get("phase", "")),
            str(r.get("action", "")),
            "OK" if success else "REFUS / ÉCHEC",
            str(r.get("message", "")),
        ]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c == 4:
                it.setForeground(
                    Qt.GlobalColor.darkGreen if success
                    else Qt.GlobalColor.red)
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self._table.setItem(row, c, it)
        self._table.scrollToBottom()

    def add_row(self, r: dict):
        """Ajoute une ligne au tableau (usage externe : Workflow complet)."""
        self._add_row(r)

    def _on_done(self, ok: int, total: int):
        self._run_btn.setEnabled(True)
        msg = (f"Boucle terminée : {ok}/{total} ligne(s) réussie(s) "
               "(transport + missions).")
        if ok < total:
            msg += (" Les refus/échecs sont listés avec leur motif "
                    "(aucun faux succès).")
        self.log.emit(msg)
