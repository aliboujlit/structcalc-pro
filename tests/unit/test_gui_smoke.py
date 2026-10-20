# -*- coding: utf-8 -*-
"""
tests/unit/test_gui_smoke.py — Test de fumée de la fenêtre principale (spec §14).

Vérifie que la GUI s'instancie, expose les onglets/menus attendus et que le
dimensionnement (couche SOLVER) s'affiche SANS aucune formule dans l'UI
(spec §14.6). Nécessite PyQt6 ; marqué `gui` pour pouvoir être exclu.

    python -m pytest tests/unit/test_gui_smoke.py -q
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    """QApplication unique pour la session de tests GUI."""
    import sys
    qapp = QApplication.instance() or QApplication(sys.argv)
    return qapp


@pytest.fixture
def window(app):
    from structcalc.gui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()


def test_main_window_title_and_size(window):
    assert "STRUCTCALC" in window.windowTitle()
    assert window.width() >= 800


def test_expected_menus_present(window):
    """Menus spec §14.1 : Projet, Modèle, Intégrations, Calculs, ..."""
    from PyQt6.QtGui import QAction
    labels = [a.text() for a in window.menuBar().actions()]
    for expected in ("Projet", "Modèle", "Intégrations", "Calculs",
                     "Réglementation", "Vérifications", "Rapports",
                     "Outils", "Aide"):
        assert expected in labels, f"menu manquant : {expected}"


def test_expected_workspaces_present(window):
    """Espaces de travail spec §14.2 : dashboard, boucle logiciels,
    combinaisons, poteaux, connecteurs, rapports, journal."""
    assert window.tabs.count() == 7
    for i in range(window.tabs.count()):
        assert window.tabs.tabText(i)  # onglet non vide
    # Onglet « Boucle logiciels » : cases à cocher présentes (demande user)
    names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert "Boucle logiciels" in names
    assert "Combinaisons" in names


def test_combos_tab_matrix_workflows_and_cases(window):
    """Onglet Combinaisons : matrice 6x6 évaluée (pas de faux OK),
    7 démarches et 6 cas d'industrie affichés (inventaire complet)."""
    from structcalc.integration.interop.combinaisons import (
        WORKFLOWS, INDUSTRY_CASES, SOFTWARE_NAMES)
    mt = window.combos_tab._matrix
    assert mt.rowCount() == len(SOFTWARE_NAMES) + 1
    assert mt.columnCount() == len(SOFTWARE_NAMES) + 1
    # Remplissage : la diagonale est « — », les autres OK ou REFUS
    values = set()
    for i in range(1, mt.rowCount()):
        for j in range(1, mt.columnCount()):
            if i == j:
                assert mt.item(i, j).text() == "—"
            else:
                v = mt.item(i, j).text()
                assert v in ("OK", "REFUS")
                values.add(v)
    assert "REFUS" in values  # au moins un refus honnête affiché
    # Démarches + cas industrie complets
    assert window.combos_tab._wf_table.rowCount() == len(WORKFLOWS)
    assert window.combos_tab._case_table.rowCount() == len(INDUSTRY_CASES)


def test_loop_tab_lists_six_autodesk_software_with_checkboxes(window):
    """La boucle expose les 6 logiciels Autodesk en cases à cocher,
    chacun avec un rôle (Conception / Étude / les deux)."""
    from PyQt6.QtWidgets import QCheckBox, QComboBox
    from structcalc.integration.interop.loop import SOFTWARE_NAMES
    boxes = {c.text(): c for c in window.loop_tab.findChildren(QCheckBox)}
    assert len(boxes) == 6
    roles = window.loop_tab.findChildren(QComboBox)
    assert len(roles) == 6
    # Selection vide -> plan REFUSE avec motif explicite (pas de faux succes)
    assert window.loop_tab.plan() is False
    assert "Aucun logiciel" in window.loop_tab._plan.error


def test_loop_tab_version_shown(window):
    """L'onglet affiche le numéro de version de structcalc/version.py."""
    from structcalc.version import VERSION_STRING
    from PyQt6.QtWidgets import QLabel
    assert VERSION_STRING in window.windowTitle()
    texts = " | ".join(l.text() for l in window.loop_tab.findChildren(QLabel))
    assert VERSION_STRING in texts


def test_loop_tab_revit_robot_selection_builds_closed_loop(window):
    """Demande utilisateur : cocher Revit + Robot (conception etude)
    -> boucle fermee Revit -> Robot -> Revit, planifiee sans COM."""
    from structcalc.integration.interop.loop import ROLE_CONCEPTION, ROLE_ETUDE
    boxes = {c.text(): c for c in window.loop_tab.findChildren(
        __import__("PyQt6.QtWidgets", fromlist=["QCheckBox"]).QCheckBox)}
    roles = window.loop_tab.findChildren(
        __import__("PyQt6.QtWidgets", fromlist=["QComboBox"]).QComboBox)
    # Cocher les deux logiciels
    revit_box = [c for t, c in boxes.items() if "Revit" in t][0]
    robot_box = [c for t, c in boxes.items() if "Robot" in t][0]
    revit_box.setChecked(True)
    robot_box.setChecked(True)
    # Roles : conception pour Revit, etude pour Robot
    from structcalc.integration.interop.loop import AVAILABLE_SOFTWARE
    idx_revit = [s.name for s in AVAILABLE_SOFTWARE].index("revit")
    idx_robot = [s.name for s in AVAILABLE_SOFTWARE].index("robot")
    roles[idx_revit].setCurrentIndex(0)  # Conception
    roles[idx_robot].setCurrentIndex(1)  # Etude
    # Plan = boucle fermee de 2 etapes (aller + retour), sans connexion COM
    assert window.loop_tab.plan() is True
    plan = window.loop_tab._plan
    assert plan.order == ["revit", "robot"]
    assert len(plan.steps) == 2
    assert plan.steps[0].phase.endswith("(aller)")
    assert plan.steps[1].phase.endswith("(retour)")
    # Apercu affiche dans l'onglet (texte lisible, sans jargon)
    preview = window.loop_tab._plan_view.toPlainText()
    assert "Revit" in preview and "Robot" in preview and "->" in preview
    # Nettoyage pour les autres tests
    revit_box.setChecked(False)
    robot_box.setChecked(False)


def test_dashboard_shows_integrity_warning(window):
    """Le tableau de bord porte l'avertissement permanent (spec §20)."""
    from PyQt6.QtWidgets import QLabel
    labels = window.dashboard.findChildren(QLabel)
    joined = " ".join(l.text() for l in labels)
    assert "conformité" in joined.lower() or "ingénieur" in joined.lower()


def test_new_project_populates_browser_and_dashboard(window):
    window.new_project()
    assert window.project is not None
    # Navigateur : racine + lignes de comptage
    assert window.browser.topLevelItemCount() == 1
    root = window.browser.topLevelItem(0)
    assert root.childCount() >= 3
    # Dashboard : nœuds/poteaux à 0 au départ
    assert window.dashboard.cards["nodes"]._value.text() == "0"


def test_column_design_populates_table_without_formula_in_ui(window):
    """Le dimensionnement remplit le tableau via le SOLVER — l'UI n'a aucune
    formule (spec §14.6) : elle n'affiche que des résultats."""
    window.run_column_design()
    assert window.col_table.rowCount() > 0
    # Chaque ligne : designation, aire, As, candidat, rang, à valider
    item = window.col_table.item(0, 0)
    assert item is not None and item.text()
    # Aucune mention de formule codée dans l'onglet
    header = window.col_table.horizontalHeaderItem(5).text()
    assert header == "À valider"


def test_menu_action_about_shows_no_conformity_claim(window, monkeypatch):
    """Le « À propos » ne prétend à aucune conformité (spec §20)."""
    from PyQt6.QtWidgets import QMessageBox
    captured = {}
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: captured.update(msg=a[-1])))
    window._menu("Aide", "À propos")
    assert "conformité" in captured["msg"]
    assert "validation" in captured["msg"]


# ---------------------------------------------------------------------------
# LEDs des logiciels (demande v1.3) : vert = connecté vérifié, rouge = motif
# ---------------------------------------------------------------------------

def test_led_panel_six_rows_present(window):
    """Onglet Connecteurs : 6 LEDs (un par logiciel) + boutons relance."""
    from PyQt6.QtWidgets import QPushButton
    assert len(window.led_panel._rows) == 6
    btns = [b.text() for b in window.led_panel.findChildren(QPushButton)]
    assert "Actualiser" in btns
    assert "Démarrer les logiciels manquants" in btns


def test_led_panel_paints_green_only_when_verified(window, monkeypatch):
    """Vert UNIQUEMENT pour un statut connecté VÉRIFIÉ ; rouge = motif."""
    from structcalc.gui import soft_leds
    monkeypatch.setattr(soft_leds, "status_all", lambda: [
        {"key": "robot", "label": "Robot", "running": True,
         "connected": True, "exe": "", "detail": "actif — attachement prouvé"},
        {"key": "autocad", "label": "AutoCAD", "running": False,
         "connected": False, "exe": "", "detail": "fermé (acad.exe absent)"},
        {"key": "civil3d", "label": "Civil 3D", "running": False,
         "connected": False, "exe": "", "detail": "fermé"},
        {"key": "advsteel", "label": "Advance Steel", "running": False,
         "connected": False, "exe": "", "detail": "fermé"},
        {"key": "revit", "label": "Revit", "running": False,
         "connected": False, "exe": "", "detail": "fermé"},
        {"key": "navisworks", "label": "Navisworks", "running": False,
         "connected": False, "exe": "", "detail": "fermé"},
    ])
    logs = []
    window.led_panel.log.connect(logs.append)
    window.led_panel.refresh()
    dot_r, _n, state_r = window.led_panel._rows["robot"]
    assert "a6e3a1" in dot_r.styleSheet()              # VERT vérifié
    assert state_r.text().startswith("connecté —")
    dot_a, _n2, state_a = window.led_panel._rows["autocad"]
    assert "f38ba8" in dot_a.styleSheet()              # ROUGE
    assert state_a.text().startswith("non connecté —")
    assert "fermé" in state_a.text()                   # motif affiché
    assert logs and "1/6" in logs[-1]
