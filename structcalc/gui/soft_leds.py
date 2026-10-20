# -*- coding: utf-8 -*-
"""
gui/soft_leds.py — Panneau LEDs des logiciels connectés (demande v1.3).

VERT = connecté VÉRIFIÉ (attachement possible sans lancement) ;
ROUGE = non connecté — le motif exact est affiché (jamais de vert supposé).
Boutons : « Actualiser » (re-détection live) et « Démarrer les manquants »
(relance par les exécutables RÉELS de chaque produit, processus visibles,
puis re-détection différée — un démarrage à froid prend ~30-60 s).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from ..integration.software_status import launch_missing, status_all

_GREEN = "#a6e3a1"
_RED = "#f38ba8"


class SoftwareLedPanel(QWidget):
    """6 LEDs (un par logiciel) + relance des manquants."""

    log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        title = QLabel("Logiciels connectés  (vert = attachement vérifié — "
                       "rouge = non connecté)")
        title.setStyleSheet("font-weight: bold;")
        root.addWidget(title)

        for key in ("robot", "autocad", "civil3d", "advsteel", "revit",
                    "navisworks"):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setFixedWidth(20)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel("")
            name.setFixedWidth(240)
            state = QLabel("en attente de détection…")
            state.setStyleSheet("color: #a6acb4;")
            row.addWidget(dot)
            row.addWidget(name)
            row.addWidget(state, stretch=1)
            root.addLayout(row)
            self._rows[key] = (dot, name, state)

        btns = QHBoxLayout()
        self._btn_refresh = QPushButton("Actualiser")
        self._btn_refresh.clicked.connect(self.refresh)
        self._btn_launch = QPushButton("Démarrer les logiciels manquants")
        self._btn_launch.clicked.connect(self.launch_missing)
        btns.addWidget(self._btn_refresh)
        btns.addWidget(self._btn_launch)
        btns.addStretch(1)
        root.addLayout(btns)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self):
        """Détection live (aucun lancement) puis peinture des LEDs."""
        try:
            rows = status_all()
        except Exception as exc:
            self.log.emit(f"Détection impossible : {exc}")
            return
        n = 0
        for st in rows:
            dot, name, state = self._rows[st["key"]]
            name.setText(str(st["label"]))
            if st["connected"]:
                n += 1
                dot.setStyleSheet(f"color: {_GREEN}; font-size: 18px;")
                state.setStyleSheet(f"color: {_GREEN};")
                state.setText(f"connecté — {st['detail']}")
            else:
                dot.setStyleSheet(f"color: {_RED}; font-size: 18px;")
                state.setStyleSheet("color: #f38ba8;")
                state.setText(f"non connecté — {st['detail']}")
        self.log.emit(f"LEDs : {n}/{len(rows)} logiciel(s) connecté(s).")

    def launch_missing(self):
        """Relance les logiciels manquants par leurs exécutables réels,
        puis re-détection différée (démarrage à froid 30-60 s)."""
        try:
            results = launch_missing()
        except Exception as exc:
            self.log.emit(f"Relance impossible : {exc}")
            return
        if not results:
            self.log.emit("Relance : rien à lancer (tout est déjà connecté).")
            return
        for _key, ok, msg in results:
            self.log.emit(("Relance — " if ok else "Relance refusée — ") + msg)
        for ms in (5000, 15000, 40000):
            QTimer.singleShot(ms, self.refresh)
