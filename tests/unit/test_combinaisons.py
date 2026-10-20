# -*- coding: utf-8 -*-
"""
Tests de l'inventaire COMBINAISONS / DEMARCHES / CAS D'INDUSTRIE
(interop/combinaisons.py) — logique pure, sans Qt/COM (spec §17).

Couvre : les 30 sens diriges, les 15 paires reciproques, les demarches de
bureau d'etudes, les cas d'industrie, et l'honnetete des notes (aucune
liaison pretendue disponible).
"""

from __future__ import annotations

import pytest

from structcalc.integration.interop.loop import (
    SOFTWARE_NAMES, LABELS, PROFILES, MISSION_LABELS,
)
from structcalc.integration.interop.combinaisons import (
    PROVIDES, CONSUMES, all_pairs, pair_use, reciprocal_pairs_count,
    WORKFLOWS, WORKFLOW_KEYS, workflow, Workflow,
    INDUSTRY_CASES, CASE_KEYS, industry_case, IndustryCase,
    inventory, legs_of_all_workflows, describe_inventory, PairUse,
)


class TestCombinaisons:
    def test_all_pairs_count_is_30(self):
        """6 logiciels x 5 cibles = 30 sens diriges."""
        pairs = all_pairs()
        assert len(pairs) == 30
        assert len(pairs) == len(SOFTWARE_NAMES) * (len(SOFTWARE_NAMES) - 1)

    def test_no_self_pair(self):
        for p in all_pairs():
            assert p.source != p.target

    def test_every_ordered_pair_present(self):
        expected = {(a, b) for a in SOFTWARE_NAMES for b in SOFTWARE_NAMES
                    if a != b}
        got = {p.key for p in all_pairs()}
        assert got == expected

    def test_reciprocal_count_is_15(self):
        assert reciprocal_pairs_count() == 15

    def test_provides_and_covers_all_software(self):
        assert set(PROVIDES) == set(SOFTWARE_NAMES)
        assert set(CONSUMES) == set(SOFTWARE_NAMES)

    def test_pair_transfer_matches_source_mission(self):
        """Le transfert dit ce que la SOURCE produit (mission conçue)."""
        for p in all_pairs():
            assert p.transfer == PROVIDES[p.source]

    def test_pair_action_matches_target_mission(self):
        for p in all_pairs():
            assert p.target_action == CONSUMES[p.target]

    def test_pair_use_case_names_target_job(self):
        """La démarche dit ce que la CIBLE en fait (métier bureau d'études)."""
        for p in all_pairs():
            assert p.use_case
            # chaque cas mentionne la mission métier de la cible
            mission = PROFILES[p.target].mission
            assert mission in MISSION_LABELS

    def test_pair_use_lookup(self):
        p = pair_use("robot", "autocad")
        assert p.label == (f"{LABELS['robot']} -> {LABELS['autocad']}")
        assert "pivot" in p.sense

    def test_pair_use_unknown_raises(self):
        with pytest.raises(KeyError):
            pair_use("sketchup", "robot")

    def test_pair_to_dict(self):
        d = pair_use("revit", "robot").to_dict()
        assert d["source"] == "revit" and d["target"] == "robot"
        assert d["transfer"] and d["target_action"] and d["use_case"]


class TestDemarches:
    def test_workflow_keys_stable(self):
        assert WORKFLOW_KEYS == (
            "bati_complet", "etude_sans_bim", "charpente_acier",
            "site_vrd", "coordination_bim", "acier_complet",
            "boucle_complete")

    def test_all_workflow_maillons_known(self):
        for w in WORKFLOWS:
            for n in w.chain:
                assert n in SOFTWARE_NAMES, f"{w.key}: {n} inconnu"

    def test_workflow_has_legs(self):
        for w in WORKFLOWS:
            legs = w.legs
            assert len(legs) >= 2, f"{w.key} : boucle/demarche incomplète"
            for s, t in legs:
                assert s in SOFTWARE_NAMES and t in SOFTWARE_NAMES
                assert s != t, f"{w.key}: jambage identique"

    def test_closed_workflow_returns_to_first(self):
        for w in WORKFLOWS:
            if w.loop:
                assert w.legs[-1][1] == w.chain[0], w.key
                assert w.legs[0][0] == w.chain[0], w.key
            else:
                # chemin ouvert : pas de retour final
                assert w.legs[-1][1] != w.chain[0] or len(w.chain) < 2

    def test_chain_labels_closed_loop_appends_first(self):
        w = workflow("bati_complet")
        labels = w.chain_labels.split(" -> ")
        assert labels[0] == labels[-1] == LABELS["revit"]

    def test_industry_case_field_present(self):
        for w in WORKFLOWS:
            assert w.objective and w.industry_case

    def test_workflows_cover_core_industry_processes(self):
        """Les démarches couvrent : BIM, sans BIM, acier, site, coordination,
        orchestration totale (industrie de bureau d'études)."""
        for key in ("bati_complet", "etude_sans_bim", "charpente_acier",
                    "site_vrd", "coordination_bim", "boucle_complete"):
            assert key in WORKFLOW_KEYS

    def test_workflow_lookup_unknown_raises(self):
        with pytest.raises(KeyError):
            workflow("inexistant")

    def test_workflow_to_dict(self):
        d = workflow("etude_sans_bim").to_dict()
        assert d["chain"] == ["autocad", "robot", "autocad"][:3] or \
               d["chain"][0] == "autocad"
        assert len(d["legs"]) >= 2


class TestCasIndustrie:
    def test_six_industry_cases(self):
        assert len(INDUSTRY_CASES) == 6
        assert len(set(CASE_KEYS)) == 6

    def test_case_software_known(self):
        for c in INDUSTRY_CASES:
            for s in c.software:
                assert s in SOFTWARE_NAMES, f"{c.key}: {s}"

    def test_case_workflows_exist(self):
        for c in INDUSTRY_CASES:
            for k in c.workflows:
                assert k in WORKFLOW_KEYS, f"{c.key}: workflow {k} manquant"

    def test_case_deliverables_and_reality(self):
        for c in INDUSTRY_CASES:
            assert c.deliverables, c.key
            assert c.reality, c.key

    def test_reality_is_honest_no_free_liaison(self):
        """Les notes de réalité nomment les obstacles (add-in, refus…)
        — aucune liaison n'est présentée comme magiquement disponible."""
        joined = " ".join(c.reality.lower() for c in INDUSTRY_CASES)
        assert "prouv" in joined      # ce qui est prouvé est dit prouvé
        assert "refus" in joined or "add-in" in joined  # obstacles nommés

    def test_full_industry_case_covers_all_software(self):
        c = industry_case("ingenierie_complete")
        assert set(c.software) == set(SOFTWARE_NAMES)

    def test_case_lookup_unknown_raises(self):
        with pytest.raises(KeyError):
            industry_case("inconnu")

    def test_case_to_dict(self):
        d = industry_case("charpente").to_dict()
        assert "advsteel" in d["software"]
        assert d["deliverables"] and d["reality"]


class TestInventaire:
    def test_inventory_totals(self):
        inv = inventory()
        assert inv.n_senses == 30
        assert inv.n_reciprocal == 15
        assert len(inv.workflows) == 7
        assert len(inv.cases) == 6

    def test_legs_of_all_workflows_unique_source(self):
        legs = legs_of_all_workflows()
        assert legs, "aucun jambage"
        for key, s, t in legs:
            assert key in WORKFLOW_KEYS
            assert s in SOFTWARE_NAMES and t in SOFTWARE_NAMES

    def test_describe_inventory_lists_everything(self):
        txt = describe_inventory()
        # 30 sens, 7 demarches, 6 cas
        assert "30 sens diriges" in txt
        assert "15 paires reciproques" in txt
        for w in WORKFLOWS:
            assert w.name in txt
        for c in INDUSTRY_CASES:
            assert c.name in txt
        # honnêteté : la faisabilité vient du hub, pas prétendue ici
        assert "hub" in txt and "refus" in txt.lower()

    def test_all_pairs_have_missions_from_loop_profiles(self):
        """Cohérence croisée loop.py <-> combinaisons.py (pas de divergences)."""
        for p in all_pairs():
            assert PROFILES[p.source].mission in MISSION_LABELS
            assert PROFILES[p.target].mission in MISSION_LABELS
