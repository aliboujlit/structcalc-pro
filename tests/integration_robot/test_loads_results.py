# -*- coding: utf-8 -*-
"""
tests/integration_robot/test_loads_results.py — Phase 2 : charges + résultats.

Ces tests ouvrent un VRAI Robot 2027 (marqueur `robot`, exécution séquentielle).

Vérifie ce qui a été PROUVÉ en Phase 2 :
  - Cases.CreateSimple(number, name, type_int, analize_bool)  [signature confirmée]
  - CalcEngine.Calculate()                                     [confirmé]
  - Results.Available                                          [confirmé]
  - Results.Nodes.Reactions.Value(node, case)                  [structure confirmée]

Ce qui n'est PAS démontré lève une erreur explicite (spec §19) :
  - combinaisons (create_combination)
  - charge barre uniforme sans confirmed_rectype

Lance :
    python -m pytest -m robot tests/integration_robot/test_loads_results.py -v
"""

import pytest

pytestmark = pytest.mark.robot

from structcalc.integration.robot.connection import (
    RobotConnection, RobotConnectionError, PROJECT_TYPE_FRAME_2D,
)
from structcalc.integration.robot import loads, results
from structcalc.core.status import RegulatoryStatus


@pytest.fixture
def rc():
    """Connexion Robot + projet 2D jetable, fermé sans sauvegarde."""
    try:
        conn = RobotConnection()
        conn.connect()
        conn.open_project(PROJECT_TYPE_FRAME_2D)
    except RobotConnectionError as exc:
        pytest.skip(f"Robot indisponible : {exc}")
    yield conn
    try:
        conn.close_project()
    except Exception:
        pass
    conn.disconnect()


def test_create_simple_dead_load_case(rc):
    """Signature CONFIRMÉE : CreateSimple(number, name, type, analize)."""
    rep = loads.export_dead_load_case(rc, number=1, name="Poids propre",
                                      analyze=False)
    assert rep["created"] is True
    assert rep["count"] >= 1
    # Liste cohérente
    cases = loads.list_cases(rc)
    assert any(c["number"] == 1 for c in cases)


def test_calculate_runs_and_reports_availability(rc):
    """CalcEngine.Calculate() s'exécute et Results.Available est lisible."""
    rep = loads.calculate(rc)
    assert rep["calculated"] is True
    assert isinstance(rep["results_available"], int)
    # Sans appuis/charges valides -> Available peut rester 0 (explicite)
    assert rep["results_available"] >= 0


def test_reactions_require_available_results(rc):
    """Tant qu'aucun résultat n'est disponible, la lecture est REFUSÉE
    (spec §19 : pas de fausses valeurs)."""
    if results.results_available(rc):
        pytest.skip("Résultats disponibles : autre scénario à tester.")
    with pytest.raises(results.RobotResultsError):
        results.import_reactions(rc, case_number=1)


def test_uniform_bar_load_is_cold_without_confirmed_type(rc):
    """Spec §19 : charge barre sans type confirmé -> erreur explicite,
    JAMAIS un faux succès."""
    loads.export_dead_load_case(rc, number=1)
    with pytest.raises(loads.RobotLoadsError) as ei:
        loads.apply_uniform_bar_load(rc, case_number=1, bar_list="1", fz=-10.0)
    assert "NON CONFIRMÉ" in str(ei.value)


def test_combination_is_explicitly_not_implemented(rc):
    """Spec §5.3/§19 : combinaisons non démontrées -> statut explicite."""
    with pytest.raises(loads.RobotLoadsError) as ei:
        loads.create_combination(rc, number=10, name="ULS",
                                 factors={1: 1.35})
    assert "NON IMPLÉMENTÉ" in str(ei.value) or "non démontrés" in str(ei.value)
