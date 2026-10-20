# -*- coding: utf-8 -*-
"""
gui/main_window.py — Fenêtre principale PyQt6 (spec §14.1-14.4).

Menus (§14.1) : Projet, Modèle, Intégrations, Calculs, Réglementation,
Vérifications, Rapports, Outils, Aide.
Espaces de travail (§14.2) : navigateur, connecteurs, boucle logiciels,
poteaux, rapports, journal. Tableau de bord (§14.3).

Règle §14.6 : aucune formule réglementaire dans l'UI. Les opérations longues
(COM Robot) passent par un QThread (§14.4) pour garder l'UI réactive.

N° de version : structcalc/version.py (source unique, miroir version_info.txt).
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QTextEdit, QLabel, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QMessageBox, QPushButton, QStatusBar, QToolBar,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont

from ..core.model import Project
from ..version import version_title, about_text, VERSION_STRING
from .dashboard import Dashboard
from .loop_tab import LoopTab
from .combos_tab import CombosTab


class _LogThread(QThread):
    """Exécute une opération COM longue hors UI (spec §14.4)."""
    finished_ok = pyqtSignal(str)

    def __init__(self, fn, *a, **kw):
        super().__init__()
        self._fn, self._a, self._kw = fn, a, kw

    def run(self):
        try:
            r = self._fn(*self._a, **self._kw)
            self.finished_ok.emit(str(r))
        except Exception as exc:
            self.finished_ok.emit(f"ERREUR : {exc}")


class _ObjThread(QThread):
    """
    Thread renvoyant un OBJET (ex. LoadResult du chargeur de projet).

    Symbole dédié `finished_obj` : le GUI reçoit la structure complète
    (projet + compteurs + message) au lieu d'une simple chaîne.
    L'échec n'est jamais muet : `failed(str)` porte le motif.
    """
    finished_obj = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, *a, **kw):
        super().__init__()
        self._fn, self._a, self._kw = fn, a, kw

    def run(self):
        try:
            self.finished_obj.emit(self._fn(*self._a, **self._kw))
        except Exception as exc:
            self.failed.emit(f"ERREUR : {exc}")


class _WorkflowThread(QThread):
    """
    Workflow complet hors UI (spec §14.4) : échanges de la boucle (transport
    + missions par maillon, voir interop/loop.py) puis constats de cohérence
    du pivot (core/coherence.py).

    Émet chaque ligne `step_done(dict)` (tableau de l'onglet Boucle) puis
    le rapport Markdown `finished_md(str)` (onglet Rapports). Un refus
    d'échange reste un refus motivé — jamais reformulé en succès.
    """
    step_done = pyqtSignal(dict)
    finished_md = pyqtSignal(str)

    def __init__(self, plan, project, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._project = project

    def run(self):
        from ..integration.interop.loop import exchange_plan
        results = []
        try:
            results = exchange_plan(self._plan, self._project)
        except Exception as exc:  # jamais de crash muet
            self.step_done.emit({
                "order": 0, "source": "—", "target": "—", "phase": "—",
                "action": "—", "success": False,
                "message": f"ERREUR MOTEUR D'ÉCHANGE : {exc}"})
        for r in results:
            self.step_done.emit(r)
        ok = sum(1 for r in results if r.get("success"))
        from ..core.coherence import coherence_findings, format_findings
        findings = coherence_findings(self._project)
        header = (
            "# Workflow complet — rapport\n\n"
            "| Résultat | Détail |\n|---|---|\n"
            f"| Échanges réussis | {ok}/{len(results)} |\n"
            f"| Constats de cohérence | {len(findings)} |\n\n"
            "Chaque refus/échec reste listé avec son motif dans l'onglet "
            "« Boucle logiciels » (aucun faux succès).\n")
        body = format_findings(self._project, findings)
        self.finished_md.emit(header + "\n" + body)


class MainWindow(QMainWindow):
    """
    Fenêtre principale STRUCTCALC PRO.

    Structure : splitter [navigateur | onglets (dashboard, boucle logiciels,
    poteaux, connecteurs, rapports, journal)].
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(version_title())
        self.resize(1280, 800)
        self.project: Optional[Project] = None
        self._threads: list = []
        self._workflow_thread: Optional[QThread] = None
        self._last_coherence_md: str = ""   # dernier rapport de vérification

        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        # Projet vide par défaut
        self.new_project()

        # Détection LIVE des logiciels au lancement (demande v1.3) :
        # LEDs vert/rouge + relance par les mêmes programmes (bouton).
        QTimer.singleShot(400, self.led_panel.refresh)

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------
    def _build_menus(self):
        mb = self.menuBar()
        specs = {
            "Projet": ["Nouveau projet", "Ouvrir…", "Enregistrer", "—",
                       "Quitter"],
            "Modèle": ["Importer depuis Robot", "Exporter vers Robot",
                       "—", "Vérifier la cohérence"],
            "Intégrations": ["Détecter les logiciels", "Connecter Robot",
                             "Connecter Revit", "—",
                             "Boucle logiciels (cases à cocher)",
                             "Workflow complet (boucle + vérifications)",
                             "Combinaisons & démarches",
                             "État des connecteurs"],
            "Calculs": ["Descente de charges", "Combinaisons",
                        "—", "Dimensionner les poteaux"],
            "Réglementation": ["BAEL 91 révisé 99", "RPS 2011",
                               "—", "Vérifier les articles"],
            "Vérifications": ["Lancer les vérifications", "Anomalies ouvertes",
                              "Données manquantes"],
            "Rapports": ["Note de calcul", "Fiche de poteau",
                         "Résumé de projet", "—", "Export XLSX",
                         "Exporter le dossier…", "—",
                         "Plans de coffrage (PDF)…",
                         "Plans de ferraillage (PDF)…",
                         "Dossier bureau de contrôle…"],
            "Outils": ["Journal", "Options"],
            "Aide": ["À propos", "Documentation"],
        }
        for name, items in specs.items():
            m = mb.addMenu(name)
            for it in items:
                if it == "—":
                    m.addSeparator()
                    continue
                act = QAction(it, self)
                act.triggered.connect(lambda _c, n=name, i=it: self._menu(n, i))
                m.addAction(act)

    def _build_toolbar(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)
        for label, handler in (
            ("Nouveau", self.new_project),
            ("Ouvrir projet", self.open_project_file),
            ("Détecter logiciels", self.detect_software),
            ("Boucle logiciels", self.show_loop_tab),
            ("Workflow complet", self.run_workflow_complet),
            ("Dimensionner poteaux", self.run_column_design),
        ):
            b = QPushButton(label)
            b.clicked.connect(handler)
            tb.addWidget(b)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Panneau gauche : navigateur de projet (§14.2) ---
        self.browser = QTreeWidget()
        self.browser.setHeaderLabels(["Élément", "Valeur"])
        self.browser.setMinimumWidth(260)
        splitter.addWidget(self.browser)

        # --- Onglets de travail ---
        self.tabs = QTabWidget()
        self.dashboard = Dashboard()
        self.tabs.addTab(self.dashboard, "Tableau de bord")

        # Onglet boucle logiciels (cases à cocher — demande utilisateur)
        self.loop_tab = LoopTab(project_provider=lambda: self.project)
        self.loop_tab.log.connect(self.log)
        self.tabs.addTab(self.loop_tab, "Boucle logiciels")

        # Onglet combinaisons & démarches (matrice 6x6 + workflows + cas)
        self.combos_tab = CombosTab()
        self.combos_tab.log.connect(self.log)
        self.tabs.addTab(self.combos_tab, "Combinaisons")

        # Onglet poteaux
        self.col_table = QTableWidget(0, 6)
        self.col_table.setHorizontalHeaderLabels(
            ["Section", "Aire (cm²)", "As (cm²)", "Candidat", "Rang", "À valider"])
        self.tabs.addTab(self.col_table, "Dimensionnement poteaux")

        # Onglet connecteurs : LEDs des logiciels (demande v1.3) + rapport
        from .soft_leds import SoftwareLedPanel
        conn_page = QWidget()
        conn_layout = QVBoxLayout(conn_page)
        conn_layout.setContentsMargins(4, 4, 4, 4)
        self.led_panel = SoftwareLedPanel()
        self.led_panel.log.connect(self.log)
        conn_layout.addWidget(self.led_panel)
        self.conn_text = QTextEdit()
        self.conn_text.setReadOnly(True)
        conn_layout.addWidget(self.conn_text, stretch=1)
        self.tabs.addTab(conn_page, "Connecteurs")

        # Onglet rapports
        self.report_text = QTextEdit()
        self.tabs.addTab(self.report_text, "Rapports")

        # Onglet journal (§14.2)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.tabs.addTab(self.log_text, "Journal")

        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._sb_label = QLabel(
            f"v{VERSION_STRING} — prêt, aucune conformité déclarée")
        sb.addWidget(self._sb_label)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        self._sb_label.setText(f"v{VERSION_STRING} — {msg}")

    def new_project(self):
        self.project = Project(sc_id="SC-PROJECT-000001", name="Nouveau projet")
        self._refresh_all()
        self.log("Nouveau projet créé (modèle interne vide).")

    def show_loop_tab(self):
        """Menu Intégrations -> ouvre l'onglet Boucle logiciels."""
        self.tabs.setCurrentWidget(self.loop_tab)
        self.log("Onglet « Boucle logiciels » : cochez les logiciels à "
                 "mettre en boucle (ex. Revit + Robot en conception/étude).")

    def _refresh_all(self):
        if self.project is None:
            return
        # Navigateur
        self.browser.clear()
        root = QTreeWidgetItem([self.project.name or self.project.sc_id, ""])
        self.browser.addTopLevelItem(root)
        counts = self.project.counts()
        for k, v in counts.items():
            QTreeWidgetItem(root, [k, str(v)])
        root.setExpanded(True)
        # Dashboard
        self.dashboard.refresh(self.project)

    def detect_software(self):
        """Détecte Robot/Revit. Opération COM potentiellement longue (§14.4)."""
        self.log("Détection des logiciels Autodesk…")

        def work():
            from ..detector_stub import detect_products
            return detect_products()

        t = _LogThread(work)
        t.finished_ok.connect(self._on_detect)
        self._threads.append(t)
        t.start()

    def _on_detect(self, result: str):
        self.conn_text.append(result)
        self.log("Détection terminée (voir onglet Connecteurs).")

    # ------------------------------------------------------------------
    # Projet > Ouvrir… (v1.2) — charge .rtd/.dwg dans le pivot SC-*
    # ------------------------------------------------------------------
    def open_project_file(self):
        """
        Ouvre un fichier projet (.rtd Robot / .dwg AutoCAD) et charge son
        modèle dans le pivot SC-* (ex. « Plan-villa.dwg »).

        L'ouverture COM réelle passe par un thread (§14.4) ; le chargeur
        (interop/loader.py) ne lève jamais d'exception : tout refus arrive
        ici avec son motif explicite (§5.4 : aucun document existant n'est
        fermé ni modifié).
        """
        start = str(Path.home() / "Desktop" / "projets de test")
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet STRUCTCALC", start,
            "Projets STRUCTCALC (*.rtd *.dwg);;Robot (*.rtd);;"
            "AutoCAD (*.dwg);;Tous les fichiers (*)")
        if not path:
            self.log("Ouverture annulée.")
            return
        self.log(f"Chargement de « {path} » — connexion au logiciel "
                 "propriétaire (peut prendre quelques secondes)…")

        def work():
            from ..integration.interop.loader import load_project_file
            return load_project_file(path)

        t = _ObjThread(work)
        t.finished_obj.connect(self._on_project_loaded)
        t.failed.connect(self.log)
        self._threads.append(t)
        t.start()

    def _on_project_loaded(self, res):
        self.conn_text.append(getattr(res, "message", str(res)))
        if not getattr(res, "ok", False) or getattr(res, "project", None) is None:
            self.log(f"Chargement REFUSÉ : {getattr(res, 'message', res)}")
            self.tabs.setCurrentWidget(self.conn_text)
            return
        self.project = res.project
        self._refresh_all()
        self.log(f"Projet chargé depuis {res.source} — {res.message}")
        self.log("Workflow complet : Intégrations > « Workflow complet "
                 "(boucle + vérifications) » ou onglet « Boucle logiciels ».")

    # ------------------------------------------------------------------
    # Modèle > Vérifier la cohérence (v1.2)
    # ------------------------------------------------------------------
    def check_coherence(self):
        """Constats de cohérence du pivot chargé (core/coherence.py)."""
        if self.project is None:
            self.log("Aucun projet chargé — faites d'abord "
                     "Projet > Ouvrir…")
            return
        from ..core.coherence import coherence_findings, format_findings
        findings = coherence_findings(self.project)
        md = format_findings(self.project, findings)
        self._last_coherence_md = md
        self.report_text.setMarkdown(md)
        self.tabs.setCurrentWidget(self.report_text)
        self.log(f"Cohérence du modèle : {len(findings)} constat(s) "
                 "(onglet Rapports) — aucune donnée inventée, aucune "
                 "conformité déclarée.")

    def export_dossier(self):
        """
        Dossier de rendu complet pour l'architecte (v1.2) :
        résumé d'étude (MD + PDF + XLSX), fiche(s) de poteau réellement
        présente(s), constats de cohérence, index honnête — écrits dans le
        dossier CHOISI par l'utilisateur (aucun fichier n'est écrit ailleurs
        sans son accord).
        """
        if self.project is None:
            self.log("REFUS — aucun projet chargé : faites d'abord "
                     "Projet > Ouvrir…")
            return
        dir_ = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de rendu…")
        if not dir_:
            self.log("Export du dossier annulé (aucun fichier écrit).")
            return
        from ..reporting.dossier import build_dossier
        files = build_dossier(self.project, dir_,
                              coherence_md=self._last_coherence_md)
        if files:
            self.log(f"Dossier de rendu écrit : {len(files)} fichier(s) "
                     f"dans « {dir_} » :")
            for f in files:
                self.log(f"  - {Path(f).name}")
        else:
            self.log(f"REFUS — aucun fichier écrit dans « {dir_} » "
                     "(aucun objet exploitable dans le modèle).")

    # ------------------------------------------------------------------
    # Rapports > Plans de coffrage / ferraillage / dossier BCT (v1.4)
    # ------------------------------------------------------------------
    def export_plan_coffrage(self):
        """Plans de coffrage PDF (vectoriels, un niveau par page, A3)."""
        if self.project is None:
            self.log("REFUS — aucun projet chargé : faites d'abord "
                     "Projet > Ouvrir…")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le(s) plan(s) de coffrage (PDF)",
            "plans_coffrage.pdf", "Document PDF (*.pdf)")
        if not path:
            self.log("Export des plans de coffrage annulé.")
            return
        from ..reporting.plan_coffrage import coffrage_pdf
        try:
            out = coffrage_pdf(self.project, path,
                               project_name=self.project.name)
        except RuntimeError as exc:
            self.log(f"REFUS — {exc}")
            return
        self.log(f"Plan(s) de coffrage écrit : {out} — dimensions de "
                 f"section DÉDUITES des labels Robot (convention R<b>x<h>) "
                 f"— déduction tracée sur le plan, à confirmer.")

    def export_plan_ferraillage(self):
        """Plans de ferraillage PDF (proposition d'armature, A_VALIDER)."""
        if self.project is None:
            self.log("REFUS — aucun projet chargé : faites d'abord "
                     "Projet > Ouvrir…")
            return
        from ..solver.column_design import (ColumnDesigner,
                                            ColumnMaterials,
                                            ColumnActions)
        cols = list((getattr(self.project, "columns", None)
                     or {}).values())
        if not cols:
            self.log("REFUS — aucun poteau dans le projet : 0 poteau = "
                     "0 plan de ferraillage (rien n'est inventé).")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le(s) plan(s) de ferraillage (PDF)",
            "plans_ferraillage.pdf", "Document PDF (*.pdf)")
        if not path:
            self.log("Export des plans de ferraillage annulé.")
            return
        from ..reporting.plan_ferraillage import (plan_reinforcement,
                                                  reinforcement_pdf)
        # Dimensionnement basique (démonstration) pour nourrir les plans
        d = ColumnDesigner()
        outcomes = d.search(
            height=3.0, buckling_y=3.0, buckling_z=3.0,
            materials=ColumnMaterials(fck=30, fyk=500, E=200000),
            actions=ColumnActions(N=200.0,
                                  combination="1.35G+1.5Q"))
        n_ok = 0
        for col in cols:
            rep = plan_reinforcement(col, self.project, outcomes=outcomes)
            if rep is None:
                self.log(f"Plan de ferraillage {col.sc_id} : refus motivé "
                         f"(donnée manquante ou dimensionnement absent).")
                continue
            base = os.path.splitext(path)[0]
            fpath = f"{base}_{col.sc_id}.pdf"
            try:
                reinforcement_pdf(rep, fpath,
                                  project_name=self.project.name)
                n_ok += 1
            except RuntimeError as exc:
                self.log(f"Plan {col.sc_id} : erreur d'écriture — {exc}")
        if n_ok:
            self.log(f"{n_ok} plan(s) de ferraillage écrit(s) — "
                     f"PROPOSITION À VALIDER par l'ingénieur (pas un plan "
                     f"d'exécution).")
        else:
            self.log("REFUS — aucun plan de ferraillage produit (0 objet "
                     "exploitable).")

    def export_dossier_bct(self):
        """Dossier de contrôle (bureau de contrôle, référentiel MA)."""
        if self.project is None:
            self.log("REFUS — aucun projet chargé : faites d'abord "
                     "Projet > Ouvrir…")
            return
        dir_ = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de sortie du dossier BCT…")
        if not dir_:
            self.log("Export du dossier BCT annulé.")
            return
        from ..reporting.dossier_bct import (build_dossier_bct,
                                             dossier_bct_md)
        from ..reporting.exports import export_pdf, export_xlsx
        d = build_dossier_bct(self.project)
        md = dossier_bct_md(d, project_name=self.project.name)
        out_md = os.path.join(dir_, "dossier_bct.md")
        try:
            with open(out_md, "w", encoding="utf-8") as fh:
                fh.write(md)
        except OSError as exc:
            self.log(f"Erreur d'écriture dossier BCT : {exc}")
            return
        try:
            export_pdf(md, os.path.join(dir_, "dossier_bct.pdf"),
                       title="Dossier de contrôle")
        except RuntimeError as exc:
            self.log(f"PDF BCT : {exc}")
        try:
            export_xlsx(md, os.path.join(dir_, "dossier_bct.xlsx"))
        except RuntimeError as exc:
            self.log(f"XLSX BCT : {exc}")
        self.log(f"Dossier BCT écrit dans « {dir_} » : liste de contrôle "
                 f"honnête (référentiel MA : BAEL 91 r99 + RPS 2011), "
                 f"aucun statut « CONFORME » décerné.")
        self.log(f"Synthèse : {len(d.generated)} GÉNÉRÉ / "
                 f"{len(d.to_validate)} À VALIDER / "
                 f"{len(d.incomplete)} À COMPLÉTER.")

    # ------------------------------------------------------------------
    # Intégrations > Workflow complet (v1.2)
    # ------------------------------------------------------------------
    def run_workflow_complet(self):
        """
        Workflow complet du projet chargé : échanges réciproques de la
        boucle (selon les cases cochées de l'onglet « Boucle logiciels »,
        chaque maillon accomplissant SA mission) puis constats de cohérence
        — rapport honnête dans l'onglet Rapports.
        """
        if (self._workflow_thread is not None
                and self._workflow_thread.isRunning()):
            self.log("Un workflow est déjà en cours d'exécution.")
            return
        if self.project is None:
            self.log("REFUS — aucun projet chargé : faites d'abord "
                     "Projet > Ouvrir… (ex. « Plan-villa.dwg »).")
            return
        if not any(self.project.counts().values()):
            self.log("REFUS — le modèle pivot est vide : rien à transporter "
                     "ni vérifier. Vérifiez que le chargement du fichier a "
                     "rapporté des objets (onglet Connecteurs).")
            return
        selection = self.loop_tab.selected()   # état des cases (thread UI)
        from ..integration.interop.loop import plan_loop
        plan = plan_loop(selection)
        if not plan.ok:
            self.log(f"Workflow REFUSÉ à la planification : {plan.error}")
            return
        self.tabs.setCurrentWidget(self.loop_tab)
        self.log(f"Workflow complet : {len(plan.steps)} échange(s) "
                 f"({' -> '.join(plan.order)}) + missions par maillon, "
                 "puis constats de cohérence…")
        self._workflow_thread = _WorkflowThread(plan, self.project)
        self._workflow_thread.step_done.connect(self.loop_tab.add_row)
        self._workflow_thread.finished_md.connect(self._on_workflow_done)
        self._workflow_thread.start()

    def _on_workflow_done(self, md: str):
        self._last_coherence_md = md
        self.report_text.setMarkdown(md)
        self.tabs.setCurrentWidget(self.report_text)
        self.log("Workflow complet terminé : résumé + constats de cohérence "
                 "dans l'onglet Rapports ; échanges détaillés (OK/refus "
                 "motivés) dans l'onglet « Boucle logiciels ».")

    def run_column_design(self):
        """Lance un dimensionnement de démonstration (couche SOLVER)."""
        if self.project is None:
            self.new_project()
        from ..solver.column_design import (
            ColumnDesigner, ColumnMaterials, ColumnActions,
        )
        d = ColumnDesigner()
        results = d.search(
            height=3.0, buckling_y=3.0, buckling_z=3.0,
            materials=ColumnMaterials(fck=30, fyk=500, E=200000),
            actions=ColumnActions(N=200.0, combination="1.35G+1.5Q"))
        self.col_table.setRowCount(0)
        for out in results:
            r = self.col_table.rowCount()
            self.col_table.insertRow(r)
            vals = [out.variant.designation,
                    f"{out.variant.area_cm2:.0f}",
                    f"{out.variant.As_provided_cm2:.1f}",
                    "Oui" if out.is_candidate else "Non",
                    str(out.rank or "—"),
                    ", ".join(out.to_validate) or "—"]
            for c, v in enumerate(vals):
                self.col_table.setItem(r, c, QTableWidgetItem(v))
        self.dashboard.refresh(self.project,
                               to_validate_count=len(results))
        self.log(f"Dimensionnement : {len(results)} variantes classées "
                 "(validation ingénieur requise).")

    def _menu(self, menu: str, item: str):
        # Traitement minimal et sûr des entrées de menu
        if menu == "Projet" and item == "Nouveau projet":
            self.new_project()
        elif menu == "Projet" and item == "Ouvrir…":
            self.open_project_file()
        elif menu == "Modèle" and item == "Vérifier la cohérence":
            self.check_coherence()
        elif (menu == "Intégrations"
              and item == "Workflow complet (boucle + vérifications)"):
            self.run_workflow_complet()
        elif menu == "Intégrations" and item == "Détecter les logiciels":
            self.detect_software()
        elif (menu == "Intégrations"
              and item == "Boucle logiciels (cases à cocher)"):
            self.show_loop_tab()
        elif (menu == "Intégrations"
              and item == "Combinaisons & démarches"):
            self.tabs.setCurrentWidget(self.combos_tab)
            self.log("Onglet « Combinaisons » : 30 sens dirigés, "
                     "7 démarches, 6 cas d'industrie (évaluation hub).")
        elif menu == "Calculs" and item == "Dimensionner les poteaux":
            self.run_column_design()
        elif (menu == "Rapports" and item in ("Résumé de projet",
                                               "Note de calcul")):
            from ..reporting.column_report import project_summary
            md = project_summary(self.project)
            self.report_text.setMarkdown(md)
            self.tabs.setCurrentWidget(self.report_text)
            self.log("Note de calcul / résumé affiché — statuts honnêtes "
                     "(§15.3) ; export via Rapports > Export XLSX ou "
                     "« Exporter le dossier… ».")
        elif menu == "Rapports" and item == "Fiche de poteau":
            cols = list((getattr(self.project, "columns", None)
                         or {}).values())
            if not cols:
                self.log("Aucune fiche : le projet chargé ne contient "
                         "aucun poteau — 0 objet = 0 fiche, rien n'est "
                         "inventé.")
            else:
                from ..reporting.column_report import column_fiche
                self.report_text.setMarkdown(
                    column_fiche(cols[0], project=self.project))
                self.tabs.setCurrentWidget(self.report_text)
                self.log(f"Fiche de poteau {cols[0].sc_id} affichée "
                         f"({len(cols)} poteau(x) réellement présent(s)).")
        elif menu == "Rapports" and item == "Export XLSX":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exporter le résumé d'étude (XLSX)",
                "resume_etude.xlsx", "Classeur Excel (*.xlsx)")
            if path:
                from ..reporting.exports import export_project_summary_xlsx
                out = export_project_summary_xlsx(self.project, path)
                self.log(f"Résumé d'étude exporté : {out}")
            else:
                self.log("Export XLSX annulé.")
        elif menu == "Rapports" and item == "Exporter le dossier…":
            self.export_dossier()
        elif menu == "Rapports" and item == "Plans de coffrage (PDF)…":
            self.export_plan_coffrage()
        elif menu == "Rapports" and item == "Plans de ferraillage (PDF)…":
            self.export_plan_ferraillage()
        elif (menu == "Rapports"
              and item == "Dossier bureau de contrôle…"):
            self.export_dossier_bct()
        elif menu == "Aide" and item == "À propos":
            QMessageBox.information(self, "À propos", about_text())
        else:
            self.log(f"Menu « {menu} » > « {item} » : fonction à implémenter.")
