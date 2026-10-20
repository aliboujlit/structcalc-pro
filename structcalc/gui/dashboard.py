# -*- coding: utf-8 -*-
"""
gui/dashboard.py — Tableau de bord (spec §14.3).

Affiche : état du modèle, logiciels connectés, calculs disponibles,
vérifications exécutées, anomalies ouvertes, données manquantes,
résultats obsolètes, actions nécessitant validation.

AUCUNE formule ici (spec §14.6) : uniquement des données/agrégats fournis
par le modèle et les connecteurs.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame, QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class _StatCard(QFrame):
    """Petite carte statistique du tableau de bord."""

    def __init__(self, title: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame{background:#1e1e2e;border-radius:8px;padding:8px;}"
            "QLabel{color:#cdd6f4;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self._title = QLabel(title)
        self._title.setStyleSheet("color:#a6adc8;font-size:11px;")
        self._value = QLabel("0")
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        self._value.setFont(f)
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._sub = QLabel("")
        self._sub.setStyleSheet("color:#89b4fa;font-size:10px;")
        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._sub)

    def set(self, value, sub: str = "", color: Optional[str] = None):
        self._value.setText(str(value))
        self._sub.setText(sub)
        if color:
            self._value.setStyleSheet(f"color:{color};")


class Dashboard(QWidget):
    """
    Tableau de bord synthétique (spec §14.3).

    `refresh(project)` recalcule les agrégats depuis le modèle interne.
    N'exécute aucun calcul métier (couche SOLVER ailleurs).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Tableau de bord")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {
            "nodes": _StatCard("Nœuds"),
            "columns": _StatCard("Poteaux"),
            "beams": _StatCard("Poutres"),
            "materials": _StatCard("Matériaux"),
            "gaps": _StatCard("Données manquantes"),
            "connectors": _StatCard("Logiciels connectés"),
            "checks": _StatCard("Vérifications exécutées"),
            "to_validate": _StatCard("Actions à valider"),
        }
        positions = [
            ("nodes", 0, 0), ("columns", 0, 1), ("beams", 0, 2),
            ("materials", 0, 3), ("gaps", 1, 0), ("connectors", 1, 1),
            ("checks", 1, 2), ("to_validate", 1, 3),
        ]
        for key, r, c in positions:
            grid.addWidget(self.cards[key], r, c)
        root.addLayout(grid)

        # Bandeau d'avertissement permanent (spec §20, §15.3)
        warn = QFrame()
        warn.setFrameShape(QFrame.Shape.StyledPanel)
        warn.setStyleSheet(
            "QFrame{background:#45475a;border-left:4px solid #f38ba8;"
            "border-radius:6px;padding:10px;}"
            "QLabel{color:#cdd6f4;}")
        wl = QVBoxLayout(warn)
        wt = QLabel(
            "Aucune conformité réglementaire n'est déclarée. Les vérifications "
            "BAEL/RPS nécessitent la validation d'un ingénieur compétent. "
            "Les articles ne sont pas encore vérifiés indépendamment.")
        wt.setWordWrap(True)
        wl.addWidget(wt)
        root.addWidget(warn)
        root.addStretch(1)

        self._project = None

    def refresh(self, project: Optional[object] = None,
                connector_count: int = 0,
                check_count: int = 0,
                to_validate_count: int = 0):
        """Met à jour les cartes depuis le modèle (aucun calcul ici)."""
        self._project = project
        if project is not None:
            c = project.counts()
            gaps = project.data_gaps()
            self.cards["nodes"].set(c.get("nodes", 0))
            self.cards["columns"].set(c.get("columns", 0))
            self.cards["beams"].set(c.get("beams", 0))
            self.cards["materials"].set(c.get("materials", 0))
            self.cards["gaps"].set(len(gaps),
                                   sub="à compléter" if gaps else "complet",
                                   color="#f38ba8" if gaps else "#a6e3a1")
        self.cards["connectors"].set(connector_count,
                                     sub="Robot/Revit détectés")
        self.cards["checks"].set(check_count)
        self.cards["to_validate"].set(to_validate_count,
                                      sub="validation ingénieur requise",
                                      color="#f9e2af")
