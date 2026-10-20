# -*- coding: utf-8 -*-
"""
tests/unit/test_revit_compatibility.py — Tests de la fiche Revit (spec §6, §7.3).

Vérifie l'honnêteté du connecteur : il ne prétend JAMAIS lire un modèle BIM
sans add-in .NET, et expose une fiche de compatibilité complète.
"""

from structcalc.integration.revit.connection import RevitConnection


def test_compatibility_fiche_complete():
    rc = RevitConnection()
    f = rc.compatibility()
    assert f["logiciel"] == "Autodesk Revit"
    assert f["com_available"] is False
    assert f["pilotage_python_direct"] is False
    assert len(f["voies_integration"]) >= 4
    assert "add-in" in f["statut"].lower() or "add-in" in f["statut"]


def test_model_access_is_honestly_denied_without_addin():
    """Règle §19 : aucun faux accès au modèle sans add-in."""
    rc = RevitConnection()
    st = rc.model_access_status()
    assert st["model_readable"] is False
    assert "add-in" in st["reason"].lower()


def test_no_com_pretension():
    rc = RevitConnection()
    assert rc.compatibility()["com_available"] is False
