# -*- coding: utf-8 -*-
"""
tests/unit/test_robot_units.py — Contrôle des unités des résultats (spec §5.3).

Teste `get_result_units` et l'attachement des unités aux résultats avec un
FAUX connecteur — AUCUNE connexion Robot/COM. La preuve live est dans
tools/probe_units_live.py (force=kN, moment=kN, displacement=cm, ...).

Règle §5.3 : une unité non lisible est None (INCONNUE), jamais supposée.
"""

import pytest

from structcalc.integration.robot.results import (
    RobotResultsError,
    get_result_units,
    import_reactions,
    UNIT_FORCE,
    UNIT_MOMENT,
    UNIT_DISPLACEMENT,
    UNIT_STRUCTURE_DIMENSION,
    UNIT_STRESS,
)


class FakeUnitData:
    def __init__(self, name):
        self.Name = name


class FakeUnitsServer:
    def __init__(self, mapping, fail=False):
        self.mapping = mapping
        self.fail = fail

    def Get(self, utype):
        if self.fail:
            raise RuntimeError("unit read failure")
        return FakeUnitData(self.mapping.get(utype))


class FakePrefs:
    def __init__(self, units):
        self.Units = units


class FakeProject:
    def __init__(self, units):
        self.Preferences = FakePrefs(units)


class FakeReaction:
    """Forme RÉELLE sondée live 20/10 : membres MAJUSCULES (TLB 27)."""
    FX, FY, FZ, MX, MY, MZ = 1.0, 2.0, 3.0, 0.1, 0.2, 0.3


class FakeReactions:
    def Value(self, node, case):
        return FakeReaction()


class FakeNodes:
    Reactions = FakeReactions()


class FakeResults:
    Available = 1
    Nodes = FakeNodes()


class FakeStructure:
    Results = FakeResults()


class FakeRC:
    def __init__(self, mapping=None, units_fail=False, is_open=True):
        self.is_project_open = is_open
        self.project = FakeProject(FakeUnitsServer(mapping or {}, fail=units_fail))
        self.structure = FakeStructure()


# mapping typique Robot 2027 (probe live)
MAPPING = {
    UNIT_FORCE: "kN",
    UNIT_MOMENT: "kN",
    UNIT_DISPLACEMENT: "cm",
    UNIT_STRUCTURE_DIMENSION: "m",
    UNIT_STRESS: "MN",
}


def test_get_result_units_reads_robot_names():
    rc = FakeRC(MAPPING)
    units = get_result_units(rc)
    assert units["force"] == "kN"
    assert units["moment"] == "kN"
    assert units["displacement"] == "cm"
    assert units["length"] == "m"
    assert units["stress"] == "MN"


def test_unreadable_unit_is_none_not_assumed():
    """Une unité que Robot ne fournit pas -> None (INCONNUE), jamais devinée."""
    rc = FakeRC({UNIT_FORCE: "kN"})   # displacement absent -> None
    units = get_result_units(rc)
    assert units["force"] == "kN"
    assert units["displacement"] is None


def test_all_units_unreadable_all_none():
    rc = FakeRC({}, units_fail=True)
    units = get_result_units(rc)
    assert all(v is None for v in units.values())


def test_closed_project_raises():
    rc = FakeRC(MAPPING, is_open=False)
    with pytest.raises(RobotResultsError):
        get_result_units(rc)


def test_reactions_attach_real_units():
    """Les réactions importées portent l'unité FORCE/MOMENT réelle (§5.3)."""
    rc = FakeRC(MAPPING)
    reacs = import_reactions(rc, case_number=1, node_numbers=[1])
    assert reacs[0]["units"] == {"force": "kN", "moment": "kN"}
    assert reacs[0]["Fx"] == 1.0


def test_reactions_membres_majuscules_tlb27():
    """Live 20/10 : IRobotReactionData (TLB 27) expose FX/FY/FZ/MX/MY/MZ en
    MAJUSCULES. L'ancienne lecture `Fx` levait une AttributeError AVALÉE et
    retournait None partout (réactions vides -> combinaisons vides ->
    dimensionnement non exécutable). Doit lire les VRAIES valeurs."""
    rc = FakeRC(MAPPING)
    r = import_reactions(rc, case_number=1, node_numbers=[1])[0]
    assert (r["Fx"], r["Fy"], r["Fz"]) == (1.0, 2.0, 3.0)
    assert (r["Mx"], r["My"], r["Mz"]) == (0.1, 0.2, 0.3)


def test_reactions_fallback_casse_historique():
    """Repli : l'ancienne casse Fx/Fy... (autres générations TLB) est
    toujours lue (fallback documenté dans _comp)."""
    class FakeReactionLow:
        Fx, Fy, Fz, Mx, My, Mz = 1.5, 2.5, 3.5, 0.4, 0.5, 0.6

    class FakeReactionsLow:
        def Value(self, node, case):
            return FakeReactionLow()

    class FakeNodesLow:
        Reactions = FakeReactionsLow()

    class FakeResultsLow:
        Available = 1
        Nodes = FakeNodesLow()

    class FakeStructureLow:
        Results = FakeResultsLow()

    class FakeRCLow:
        is_project_open = True
        project = FakeProject(FakeUnitsServer(dict(MAPPING)))
        structure = FakeStructureLow()

    r = import_reactions(FakeRCLow(), case_number=1, node_numbers=[1])[0]
    assert (r["Fx"], r["Fz"], r["Mz"]) == (1.5, 3.5, 0.6)


def test_reactions_membres_absents_none_jamais_invente():
    """Objet retour SANS aucun membre connu -> composantes None (donnée
    manquante), JAMAIS une valeur inventée (spec §19)."""
    class FakeReactionVide:
        pass

    class FakeReactionsVide:
        def Value(self, node, case):
            return FakeReactionVide()

    class FakeNodesVide:
        Reactions = FakeReactionsVide()

    class FakeResultsVide:
        Available = 1
        Nodes = FakeNodesVide()

    class FakeStructureVide:
        Results = FakeResultsVide()

    class FakeRCVide:
        is_project_open = True
        project = FakeProject(FakeUnitsServer(dict(MAPPING)))
        structure = FakeStructureVide()

    r = import_reactions(FakeRCVide(), case_number=1, node_numbers=[1])[0]
    assert all(r[k] is None
               for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz"))
