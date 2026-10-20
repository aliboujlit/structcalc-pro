# -*- coding: utf-8 -*-
"""
main.py — Point d'entree STRUCTCALC PRO.

Lance l'application PyQt6. Aucune operation COM lourde au demarrage :
la connexion Robot est declenchee a la demande (menu Integrations).

Le numero de version provient de structcalc/version.py (source unique).

Usage :
    python main.py                 # lance l'interface
    python main.py --selftest      # autotest (ecrit structcalc_selftest.txt)
"""

import os
import sys
import tempfile


def _selftest_path() -> str:
    return os.path.join(tempfile.gettempdir(), "structcalc_selftest.txt")


def _selftest() -> int:
    """
    Autotest du bundle (utile une fois compile en .exe) : verifie imports,
    version, plan de boucle, et instanciation de la fenetre principale.
    Resultat ecrit dans %TEMP%\\structcalc_selftest.txt (SELFTEST=PASS/FAIL).
    """
    import traceback

    lines = []
    try:
        from structcalc.version import VERSION_STRING, version_title
        lines.append(f"version={VERSION_STRING}")
        lines.append(f"title={version_title()}")

        # Couche logique boucle (sans COM)
        from structcalc.integration.interop.loop import (
            Selection, plan_loop, ROLE_CONCEPTION, ROLE_ETUDE)
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        assert plan.ok, plan.error
        assert len(plan.steps) == 2
        lines.append(f"plan_boucle=OK ({len(plan.steps)} etapes)")

        # Couche rapport (openpyxl/reportlab)
        import structcalc.reporting.exports  # noqa: F401
        lines.append("exports=OK")

        # Couche regulation (sans PyQt6)
        from structcalc.regulation.bael91r99 import columns  # noqa: F401
        lines.append("bael=OK")

        # GUI : instanciation reelle de la fenetre
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv[:1])
        from structcalc.gui.main_window import MainWindow
        win = MainWindow()
        tabs = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert "Boucle logiciels" in tabs, tabs
        win.close()
        lines.append(f"fenetre=OK ({len(tabs)} onglets)")

        lines.append("SELFTEST=PASS")
        code = 0
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("SELFTEST=FAIL")
        code = 1

    try:
        with open(_selftest_path(), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError:
        pass
    return code


def main() -> int:
    # Mode autotest (verification du .exe compile) avant toute UI
    if "--selftest" in sys.argv:
        return _selftest()

    # Vérifier PyQt6 avant d'importer l'UI (message propre sinon)
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("ERREUR : PyQt6 n'est pas installe.")
        print("         Installez-le : pip install PyQt6")
        return 1

    from structcalc.version import APP_NAME, __version__, VERSION_STRING
    from structcalc.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME} v{VERSION_STRING}")
    app.setApplicationVersion(__version__)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
