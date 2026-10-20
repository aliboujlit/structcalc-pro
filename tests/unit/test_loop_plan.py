# -*- coding: utf-8 -*-
"""
Tests du planificateur de BOUCLE de logiciels (interop/interop/loop.py).

Couvre la demande utilisateur : cocher les logiciels (ex. Revit + Robot
en conception/études) et obtenir une boucle FERMÉE planifiée — ou un refus
EXPLICITE (aucun logiciel, un seul, rôle invalide, doublon, inconnu).

Aucun Qt / aucun COM : logique pure (spec §17.2 esprit de non-régression).
"""

from __future__ import annotations

import pytest

from structcalc.integration.interop.loop import (
    AVAILABLE_SOFTWARE, SOFTWARE_NAMES, LABELS,
    ROLE_CONCEPTION, ROLE_ETUDE, ROLE_BOTH, ROLES,
    ROLE_LABELS, Selection, LoopStep, LoopPlan,
    plan_loop, describe_plan, _phase_label,
)


class TestCatalogue:
    def test_six_autodesk_software_available(self):
        # 6 connecteurs = le hub interop (Revit, Robot, AutoCAD, Civil 3D,
        # Navisworks, Advance Steel)
        assert len(AVAILABLE_SOFTWARE) == 6

    def test_names_match_hub_connectors(self):
        assert set(SOFTWARE_NAMES) == {
            "revit", "robot", "autocad", "civil3d",
            "navisworks", "advsteel"}

    def test_labels_unique_and_non_empty(self):
        assert len(set(LABELS.values())) == 6
        assert all(LABELS.values())

    def test_three_roles_declared(self):
        assert set(ROLES) == {ROLE_CONCEPTION, ROLE_ETUDE, ROLE_BOTH}
        assert set(ROLE_LABELS) == set(ROLES)


class TestRefusExplicites:
    """Chaque refus porte son MOTIF (jamais un succès à vide)."""

    def test_empty_selection_refused(self):
        plan = plan_loop([])
        assert plan.ok is False
        assert "Aucun logiciel coché" in plan.error
        assert plan.steps == []

    def test_single_software_refused(self):
        plan = plan_loop([Selection("robot", ROLE_BOTH)])
        assert plan.ok is False
        assert "Un seul logiciel" in plan.error
        assert "Robot" in plan.error  # le motif nomme le logiciel

    def test_unknown_software_refused(self):
        plan = plan_loop([
            Selection("robot"), Selection("sketchup")])
        assert plan.ok is False
        assert "inconnu" in plan.error
        assert plan.missing == ["sketchup"]

    def test_invalid_role_refused(self):
        plan = plan_loop([
            Selection("robot", "bidon"), Selection("revit")])
        assert plan.ok is False
        assert "Rôle invalide" in plan.error
        assert "robot=bidon" in plan.error

    def test_duplicate_refused(self):
        plan = plan_loop([
            Selection("robot"), Selection("robot"), Selection("revit")])
        assert plan.ok is False
        assert "Doublon" in plan.error
        assert "robot" in plan.error


class TestPlanConforme:
    def test_revit_robot_conception_etude(self):
        """Exemple utilisateur : Revit (conception) + Robot (étude)."""
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        assert plan.ok is True
        assert plan.order == ["revit", "robot"]  # conception d'abord
        # 2 maillons -> 1 aller + 1 retour (boucle fermée)
        assert len(plan.steps) == 2
        aller = plan.steps[0]
        assert (aller.source, aller.target) == ("revit", "robot")
        assert aller.phase == "Conception -> Étude (aller)"
        retour = plan.steps[1]
        assert (retour.source, retour.target) == ("robot", "revit")
        assert retour.phase == "Étude -> Conception (retour)"

    def test_closing_step_returns_to_first(self):
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("autocad", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        assert plan.ok is True
        last = plan.steps[-1]
        assert last.source == "robot"      # dernier maillon
        assert last.target == "revit"      # referme sur le premier
        assert last.order == 3

    def test_conception_group_comes_first(self):
        plan = plan_loop([
            Selection("robot", ROLE_ETUDE),
            Selection("navisworks", ROLE_ETUDE),
            Selection("revit", ROLE_CONCEPTION),
        ])
        assert plan.order[0] == "revit"
        assert plan.order[1:] == ["robot", "navisworks"]

    def test_both_role_counts_as_conception_start(self):
        plan = plan_loop([
            Selection("civil3d", ROLE_BOTH),
            Selection("robot", ROLE_ETUDE),
        ])
        assert plan.order[0] == "civil3d"

    def test_all_six_software_chain(self):
        sel = [Selection(n, ROLE_BOTH) for n in SOFTWARE_NAMES]
        plan = plan_loop(sel)
        assert plan.ok is True
        # chaîne complète + retour final = 6 étapes
        assert len(plan.steps) == 6
        assert plan.steps[-1].target == plan.order[0]

    def test_step_count_is_n_for_n_maillons(self):
        for n in range(2, 7):
            sel = [Selection(name) for name in SOFTWARE_NAMES[:n]]
            plan = plan_loop(sel)
            assert len(plan.steps) == n, f"n={n}"


class TestPhases:
    def test_conception_vers_etude(self):
        assert _phase_label(ROLE_CONCEPTION, ROLE_ETUDE) == \
            "Conception -> Étude (aller)"

    def test_etude_vers_conception(self):
        assert _phase_label(ROLE_ETUDE, ROLE_CONCEPTION) == \
            "Étude -> Conception (retour)"

    def test_both_vers_both(self):
        assert _phase_label(ROLE_BOTH, ROLE_BOTH) == \
            "Conception + Étude (boucle fermée)"

    def test_conception_chaine(self):
        assert _phase_label(ROLE_CONCEPTION, ROLE_CONCEPTION) == \
            "Conception (chaîne)"


class TestAffichage:
    def test_describe_ok_plan_mentions_sense(self):
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        txt = describe_plan(plan)
        assert "Boucle fermée" in txt
        assert "2 échanges" in txt
        assert "-> pivot" not in txt  # le libellé lisible, pas le détail
        assert "retour" in txt

    def test_describe_refused_plan_shows_reason(self):
        txt = describe_plan(plan_loop([]))
        assert txt.startswith("Boucle impossible")
        assert "Aucun logiciel coché" in txt

    def test_step_to_dict_roundtrip(self):
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        d = plan.steps[0].to_dict()
        assert d["source"] == "revit"
        assert d["target"] == "robot"
        assert "pivot" in d["sense"]
        # plan -> dict complet
        pd = plan.to_dict()
        assert pd["ok"] is True and len(pd["steps"]) == 2


class TestPlanInvalideDict:
    def test_plan_loop_error_carried_in_dict(self):
        plan = plan_loop([])
        d = plan.to_dict()
        assert d["ok"] is False
        assert "Aucun logiciel" in d["error"]
        assert d["steps"] == []


# ----------------------------------------------------------------------
# MISSIONS — « chaque logiciel accomplit les missions dont il est conçu »
# ----------------------------------------------------------------------


class TestMissions:
    def test_all_six_software_have_a_mission_profile(self):
        from structcalc.integration.interop.loop import PROFILES
        assert set(PROFILES) == set(SOFTWARE_NAMES)

    def test_designed_ops_are_real_connector_methods(self):
        """Les opérations déclarées = VRAIES méthodes des connecteurs
        (spec §19 — aucune fonction inventée). On vérifie par introspection."""
        import inspect
        from structcalc.integration.interop import (
            RobotConnector, AutoCADConnector, Civil3DConnector,
            AdvanceSteelConnector, RevitConnector, NavisworksConnector,
        )
        import structcalc.integration.interop.loop as L
        classes = {
            "revit": RevitConnector, "robot": RobotConnector,
            "autocad": AutoCADConnector, "civil3d": Civil3DConnector,
            "advsteel": AdvanceSteelConnector,
            "navisworks": NavisworksConnector,
        }
        for name, cls in classes.items():
            prof = L.PROFILES[name]
            assert prof.designed_ops, name
            for op in prof.designed_ops:
                assert hasattr(cls, op), f"{name}.{op} invente !"

    def test_robot_mission_is_etude_with_two_actions(self):
        from structcalc.integration.interop.loop import (
            mission_legs, MISSION_ETUDE, mission_of)
        assert mission_of("robot").mission == MISSION_ETUDE
        legs = mission_legs("robot")
        assert len(legs) == 2
        assert any("write_loads" in l for l in legs)
        assert any("read_results" in l for l in legs)

    def test_navisworks_mission_is_coordination_file_conversion(self):
        from structcalc.integration.interop.loop import (
            mission_legs, MISSION_COORDINATION, mission_of)
        assert mission_of("navisworks").mission == MISSION_COORDINATION
        legs = mission_legs("navisworks")
        assert len(legs) == 1
        assert "NWD" in legs[0] or "convert" in legs[0]

    def test_revit_mission_is_conception_bim(self):
        from structcalc.integration.interop.loop import (
            mission_of, MISSION_CONCEPTION, mission_legs)
        assert mission_of("revit").mission == MISSION_CONCEPTION
        # write_model EST la mission : aucune action supplémentaire
        assert mission_legs("revit") == ()

    def test_cad_tools_mission_is_plans(self):
        from structcalc.integration.interop.loop import (
            mission_of, MISSION_PLANS, mission_legs)
        for name in ("autocad", "civil3d", "advsteel"):
            assert mission_of(name).mission == MISSION_PLANS
            assert mission_legs(name) == ()

    def test_step_carries_target_mission(self):
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        aller = plan.steps[0]
        assert aller.target == "robot"
        assert "tudes" in aller.target_mission or "Étude" in aller.target_mission
        retour = plan.steps[1]
        assert retour.target == "revit"
        assert "Conception" in retour.target_mission

    def test_describe_plan_lists_missions_per_maillon(self):
        from structcalc.integration.interop.loop import describe_plan
        plan = plan_loop([
            Selection("revit", ROLE_CONCEPTION),
            Selection("robot", ROLE_ETUDE),
        ])
        txt = describe_plan(plan)
        # Missions annoncées par maillon + legs de mission Robot
        assert "Missions de chaque maillon" in txt
        assert "write_loads" in txt and "read_results" in txt
        assert "Robot" in txt and "Revit" in txt
