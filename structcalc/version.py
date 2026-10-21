# -*- coding: utf-8 -*-
"""
version.py — Numéro de version unique de STRUCTCALC PRO.

Source de vérité unique pour :
  - la barre de titre de la fenêtre principale ;
  - la boîte « À propos » ;
  - le numéro de version embarqué dans le .exe (version_info.txt) ;
  - le nom du fichier exécutable (STRUCTCALC_PRO_<version>.exe).

Règle : toute bump de version se fait ICI (et miroir dans version_info.txt).
"""

from __future__ import annotations

APP_NAME = "STRUCTCALC PRO"
APP_SUBTITLE = "Orchestrateur d'ingénierie structurelle"

# Version publique (format semver)
__version__ = "1.5.0"
VERSION_STRING = __version__

# Composants pour le numéro de version Windows (.exe) : (major, minor, patch, build)
VERSION_INFO = (1, 5, 0, 0)

# Métadonnées pour version_info.txt / ressources PE
VERSION_COMPANY = "STRUCTCALC"
VERSION_COPYRIGHT = "Copyright © STRUCTCALC 2026"
VERSION_FILEDESCRIPTION = "STRUCTCALC PRO — Orchestrateur d'ingénierie structurelle"
VERSION_INTERNALNAME = "STRUCTCALC_PRO"
VERSION_ORIGINALFILENAME = "STRUCTCALC_PRO.exe"


def version_title() -> str:
    """Titre affiché : « STRUCTCALC PRO v1.0.0 — … »."""
    return f"{APP_NAME} v{__version__} — {APP_SUBTITLE}"


def about_text() -> str:
    """Texte de la boîte « À propos » (avec version)."""
    return (
        f"{APP_NAME} v{__version__}\n"
        f"{APP_SUBTITLE}\n\n"
        "Python 3.12 / PyQt6 — architecture CORE / SCOPE / SOLVER /\n"
        "REGULATION / INTEGRATION / GUI / REPORTING.\n\n"
        "Aucune conformité réglementaire n'est déclarée sans validation\n"
        "d'ingénieur compétent (spec §20). Les articles BAEL/RPS restent\n"
        "marqués A_VALIDER tant que non vérifiés indépendamment."
    )
