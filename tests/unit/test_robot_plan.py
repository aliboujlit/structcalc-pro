# -*- coding: utf-8 -*-
"""
tests/unit/test_robot_plan.py — Plan du modèle Robot (v1.3) : collecte
COMPLÈTE (niveaux, cas, charges, sections, matériaux, appuis, barres
classées poteau/poutre) + vérification d'identité `apply_plan` + intégration
`read_model` (classification + merge dans le pivot, arrêt AVANT mutation en
cas de dérive).

Aucun COM : fausses structures mimant EXACTEMENT les membres RÉELLEMENT
vérifiés en live (tools/probe_plan_elements_live.py, 20/10/2026). Les
membres absents lèvent AttributeError comme en réel -> avertissement
honnête, jamais d'invention (spec §6/§19).
"""

from types import SimpleNamespace

import pytest

from structcalc.core.model import Project
from structcalc.integration.interop import plan as planmod
from structcalc.integration.interop.robot import RobotConnector
from structcalc.integration.robot.connection import RobotConnection


# ---------------------------------------------------------------------------
# Faux COM (membres RÉELS du sondage live)
# ---------------------------------------------------------------------------

class FakeStorey:
    def __init__(self, name, level, height):
        self.Name, self.Level, self.Height = name, level, height


class FakeColl:
    """Collection d'objets (GetAll()) : Count + Get(i) — comme RobotOM."""

    def __init__(self, items):
        self.Count = len(items)
        self._i = list(items)

    def Get(self, i):
        return self._i[i - 1]


class FakeStoreys:
    def __init__(self, storeys):
        self._s = list(storeys)

    def __len__(self):
        return len(self._s)

    def Get(self, idx):
        return self._s[idx - 1]


class FakeRec:
    def __init__(self, rtype, desc, objects="", value=None):
        self.Type, self.Description = rtype, desc
        self._value = value
        self.Objects = SimpleNamespace(ToText=lambda: objects)

    def GetValue(self, _idx):
        return self._value


class FakeRecs:
    def __init__(self, recs):
        self.Count = len(recs)
        self._r = list(recs)

    def Get(self, i):
        return self._r[i - 1]


class FakeCase:
    def __init__(self, number, name, nature, recs=None):
        self.Number, self.Name, self.Nature = number, name, nature
        self._recs = recs


class FakeCases:
    def __init__(self, cases):
        self._c = list(cases)

    def GetAll(self):
        return FakeColl(self._c)

    def Get(self, i):
        return self._c[i - 1]


class FakeNames:
    """IRobotNamesArray : Count/Get(i) — forme RÉELLE sondée 20/10
    (l'itération Python lève « This object does not support
    enumeration » : elle est donc IMPOSSIBLE ici, comme en live)."""

    def __init__(self, items):
        self.Count = len(items)
        self._n = list(items)

    def Get(self, i):
        return self._n[i - 1]

    def __iter__(self):
        raise TypeError("This object does not support enumeration")


class FakeLabels:
    def __init__(self, names):
        self._n = names

    def GetAvailableNames(self, ltype):
        return FakeNames(self._n.get(ltype, []))


class FakeBar:
    def __init__(self, number, start, end, sec="", mat=""):
        self.Number, self.StartNode, self.EndNode = number, start, end
        self._sec, self._mat = sec, mat

    def GetLabelName(self, ltype):
        # Comme en live : label absent -> com_error « No label »
        name = {planmod.LT_BAR_SECTION: self._sec,
                planmod.LT_BAR_MATERIAL: self._mat}.get(ltype, "")
        if not name:
            raise Exception("Robot.Bar - No label")
        return name


class FakeBars:
    def __init__(self, bars, types):
        self._b = list(bars)
        self._t = dict(types)

    def GetAll(self):
        return FakeColl(self._b)

    def Get(self, i):
        return self._b[i - 1]

    def GetStructuralType(self, number):
        return self._t[number]


class FakeNode:
    def __init__(self, number, x=0.0, y=0.0, z=0.0, sup=""):
        self.Number, self.X, self.Y, self.Z = number, x, y, z
        self._sup = sup

    def GetLabelName(self, _t):
        # Comme en live (20/10) : nœud SANS appui -> com_error « No label »
        if not self._sup:
            raise Exception("Robot.Structure.Node.1 Robot.Node - No label")
        return self._sup


class FakeNodes:
    def __init__(self, nodes, supports):
        self._n = list(nodes)
        self._s = dict(supports)

    def GetAll(self):
        return FakeColl(self._n)

    def Get(self, i):
        return self._n[i - 1]

    def HasCalcSupport(self, number):
        return self._s.get(number, False)


class FakeStructure:
    """Serveur Project.Structure — un membre n'existe QUE si fourni
    (AttributeError comme en réel -> avertissement honnête)."""

    def __init__(self, storeys=(), cases=(), labels=None, bars=None,
                 bar_types=None, nodes=(), supports=None):
        if storeys:
            self.Storeys = FakeStoreys(storeys)
        if cases:
            self.Cases = FakeCases(cases)
        if labels is not None:
            self.Labels = FakeLabels(labels)
        if bars is not None:
            self.Bars = FakeBars(bars, bar_types or {})
        if nodes:
            self.Nodes = FakeNodes(nodes, supports or {})


class FakeProject:
    def __init__(self, structure, name="Projet Villa avec sous sol"):
        self.Structure = structure
        self.FileName = name
        self.IsActive = True


def _conn(structure, name="Projet Villa avec sous sol"):
    """RobotConnection sans COM (champs posés à la main, comme test_robot_adopt)."""
    rc = RobotConnection()
    rc._connected = True
    proj = FakeProject(structure, name)
    rc._app = SimpleNamespace(Project=proj)
    rc._project = proj          # project.Structure lisible via rc.structure
    return rc


def _villa_structure():
    """Villa type : 2 niveaux, 3 cas, 3 barres (1 poteau), nœuds non denses."""
    cases = [
        FakeCase(1, "PERM1", 0, [FakeRec(5, "Fz=-5 kN/m", "1,2", -5.0),
                                 FakeRec(3, "force ponctuelle", "3")]),
        FakeCase(2, "EXPL1", 1, [FakeRec(5, "Fz=-8 kN/m", "5", -8.0)]),
        FakeCase(3, "ELU", 1),
    ]
    bars = [FakeBar(1, 2, 3, "C R30x30", mat="Béton C25/30"),
            FakeBar(2, 3, 4, "C R25x30", mat="Béton C25/30"),
            FakeBar(5, 2, 4, "", mat="Béton C25/30")]
    bar_types = {1: planmod.OST_COLUMN, 2: planmod.OST_BEAM,
                 5: planmod.OST_BEAM}
    # Nœud 2 : appui par LABEL réel (« Encastrement ») — voie primaire
    # v1.3.1 ; nœud 4 : voie secondaire HasCalcSupport (signal complémentaire).
    nodes = [FakeNode(2, 0.0, 0.0, 0.0, sup="Encastrement"),
             FakeNode(3, 6.0, 0.0, 3.0),
             FakeNode(4, 6.0, 5.0, 3.0)]
    return FakeStructure(
        storeys=[FakeStorey("RDC", 0.0, 3.0), FakeStorey("R+1", 3.0, 3.0)],
        cases=cases,
        labels={planmod.LT_BAR_SECTION: ["C R30x30", "C R25x30"],
                planmod.LT_BAR_MATERIAL: ["Béton C25/30"],
                planmod.LT_NODE_SUPPORT: ["Encastrement"]},
        bars=bars, bar_types=bar_types,
        nodes=nodes, supports={4: True})


@pytest.fixture
def records(monkeypatch):
    """Pont COM des records (IRobotLoadRecordMngr) -> manager factice."""
    def _fake(case):
        recs = getattr(case, "_recs", None)
        return FakeRecs(recs) if recs else None
    monkeypatch.setattr(planmod, "_records_mngr", _fake)
    return _fake


# ---------------------------------------------------------------------------
# Collecte complète
# ---------------------------------------------------------------------------

def test_collect_plan_complete(records):
    plan = planmod.collect_plan(_conn(_villa_structure()))
    assert plan.plan_id == "SC-PLAN-Projet-Villa-avec-sous-sol"
    assert [st.name for st in plan.storeys.values()] == ["RDC", "R+1"]
    assert plan.storeys["SC-STOREY-1"].level.value == 0.0
    kinds = {lc.name: lc.kind for lc in plan.load_cases.values()}
    assert kinds == {"PERM1": "dead", "EXPL1": "live", "ELU": "live"}
    # charges : valeurs RÉELLES pour bar_uniform (index 2 vérifié),
    # MANQUANT pour les autres types (jamais deviné, spec §19)
    uniforms = [ld for ld in plan.loads.values() if ld.kind == "bar_uniform"]
    assert [ld.value.value for ld in uniforms] == [-5.0, -8.0]
    assert all(ld.unit == "kN/m" for ld in uniforms)
    other = [ld for ld in plan.loads.values()
             if ld.kind == "bar_force_concentrated"]
    assert other and other[0].value.is_missing
    assert "force ponctuelle" in other[0].ref      # description réelle Robot
    assert set(plan.sections) == {"C R30x30", "C R25x30"}
    assert set(plan.materials) == {"Béton C25/30"}
    # v1.3.1 : voie primaire = label nœud 2 (« Encastrement ») ;
    # voie secondaire = HasCalcSupport nœud 4 — les DEUX sont réels.
    assert set(plan.supports) == {2, 4}
    assert plan.supports[2].name == "Encastrement"  # nom de label RÉEL
    assert "GetLabelName" in plan.supports[2].notes
    assert "HasCalcSupport" in plan.supports[4].notes
    assert plan.bar_types[1] == (planmod.OST_COLUMN, "C R30x30")
    # matériau PORTÉ par chaque barre (GetLabelName(8)) — v1.3.1
    assert plan.bar_materials == {1: "Béton C25/30", 2: "Béton C25/30",
                                  5: "Béton C25/30"}
    assert "PORTÉ" in plan.materials["Béton C25/30"].notes
    assert plan.counts == {"storeys": 2, "load_cases": 3, "loads": 3,
                           "sections": 2, "materials": 1, "supports": 2,
                           "bars": 3, "columns": 1, "beams": 2}
    assert plan.warnings == []


def test_collect_plan_material_porte_meme_hors_labels(records):
    """Matériau PORTÉ par une barre mais absent de la table de labels ->
    il entre quand même dans le pivot (réel, jamais inventé)."""
    st = _villa_structure()
    st.Labels = FakeLabels({planmod.LT_BAR_SECTION: ["C R30x30"],
                            planmod.LT_BAR_MATERIAL: [],
                            planmod.LT_NODE_SUPPORT: []})
    st.Bars = FakeBars([FakeBar(1, 2, 3, "C R30x30", mat="BETON25")],
                       {1: planmod.OST_COLUMN})
    plan = planmod.collect_plan(_conn(st))
    assert set(plan.materials) == {"BETON25"}
    assert plan.bar_materials == {1: "BETON25"}
    assert "PORTÉ" in plan.materials["BETON25"].notes


def test_label_names_count_get_meme_si_iteration_interdite():
    """IRobotNamesArray : Count/Get lu même quand l'iteration est interdite
    (constat live : « This object does not support enumeration »)."""
    class Names:
        Count = 2

        def Get(self, i):
            return ["Encastrement", "Rotule"][i - 1]

        def __iter__(self):
            raise TypeError("This object does not support enumeration")

    assert planmod._label_names(Names()) == ["Encastrement", "Rotule"]
    assert planmod._label_names(["liste", "test"]) == ["liste", "test"]


def test_collect_plan_partial_structure_warns_never_invents(records):
    """Serveurs manquants -> avertissements honnêtes, données présentes lues."""
    st = FakeStructure(cases=[FakeCase(1, "PERM1", 0)])
    plan = planmod.collect_plan(_conn(st, name=""))
    assert len(plan.load_cases) == 1
    assert plan.warnings                          # storeys/labels/bars/nodes
    assert plan.counts["sections"] == 0           # 0 inventé
    assert plan.plan_id.startswith("SC-PLAN-R")   # nom absent -> id stable


# ---------------------------------------------------------------------------
# apply_plan : vérification d'identité (aucune écriture)
# ---------------------------------------------------------------------------

def test_apply_plan_identique_ok(records):
    rc = _conn(_villa_structure())
    plan = planmod.collect_plan(rc)
    rep = planmod.apply_plan(rc, plan)
    assert rep.ok and rep.status == "OK"
    assert "aucune écriture" in rep.message.lower()


def test_apply_plan_refuse_storey_drift(records):
    st = _villa_structure()
    rc = _conn(st)
    plan = planmod.collect_plan(rc)
    st.Storeys._s.append(FakeStorey("R+2", 6.0, 3.0))   # Robot a changé
    rep = planmod.apply_plan(rc, plan)
    assert rep.status == "REFUSED" and "Niveaux" in rep.message


def test_apply_plan_refuse_load_value_drift(records):
    st = _villa_structure()
    rc = _conn(st)
    plan = planmod.collect_plan(rc)
    st.Cases._c[0]._recs[0]._value = -9.0               # valeur modifiée
    rep = planmod.apply_plan(rc, plan)
    assert rep.status == "REFUSED" and "Charges" in rep.message


def test_apply_plan_refuse_section_drift(records):
    st = _villa_structure()
    rc = _conn(st)
    plan = planmod.collect_plan(rc)
    st.Labels._n[planmod.LT_BAR_SECTION].append("HEA200")
    rep = planmod.apply_plan(rc, plan)
    assert rep.status == "REFUSED" and "Sections" in rep.message


# ---------------------------------------------------------------------------
# read_model : classification + merge + arrêt avant mutation
# ---------------------------------------------------------------------------

def test_read_model_classifies_and_merges_plan(records):
    rc = _conn(_villa_structure())
    conn = RobotConnector()
    conn._rc = rc
    project = Project(sc_id="SC-PROJECT-000001", name="villa")
    rep = conn.read_model(project)
    assert rep.status == "OK"
    c = project.counts()
    assert c["nodes"] == 3 and c["columns"] == 1 and c["beams"] == 2
    assert c["sections"] == 2 and c["materials"] == 1 and c["supports"] == 2
    assert c["load_cases"] == 3 and c["loads"] == 3 and c["storeys"] == 2
    col = next(iter(project.columns.values()))
    assert col.section == "SC-SEC-C R30x30"          # section RÉELLE liée
    assert col.material == "SC-MAT-Béton C25/30"      # matériau PORTÉ lié
    assert "SC-SUPPORT-R2" in project.supports       # appui nœud 2 (non dense)
    assert "SC-SUPPORT-R4" in project.supports       # voie HasCalcSupport
    for sec in project.sections.values():            # dims JAMAIS inventées
        assert sec.b.is_missing and sec.h.is_missing


def test_read_model_plan_drift_stops_before_mutation(records):
    """Dérive pendant la lecture -> REFUSED et AUCUNE mutation du pivot."""
    st = _villa_structure()
    base = st.Labels
    calls = {"n": 0}

    class Drifting(FakeLabels):
        def GetAvailableNames(self, ltype):
            calls["n"] += 1
            names = list(base._n.get(ltype, []))
            if ltype == planmod.LT_BAR_SECTION and calls["n"] > 2:
                names.append("C R40x40")     # apparaît au 2e relevé
            return names

    st.Labels = Drifting(base._n)
    conn = RobotConnector()
    conn._rc = _conn(st)
    project = Project(sc_id="SC-PROJECT-000001", name="villa")
    rep = conn.read_model(project)
    assert rep.status == "REFUSED"
    assert project.beams == {} and project.columns == {} and project.nodes == {}


def test_read_model_without_plan_servers_still_imports(records):
    """Structure minimale (faux ancien) : le modèle s'importe, plan vide."""
    st = FakeStructure()
    st.Bars = FakeBars([FakeBar(1, 1, 2)], {1: planmod.OST_UNDEFINED})
    st.Nodes = FakeNodes([FakeNode(1, 0, 0, 0), FakeNode(2, 1, 0, 0)], {})
    conn = RobotConnector()
    conn._rc = _conn(st, name="")
    project = Project(sc_id="SC-PROJECT-000001", name="vide")
    rep = conn.read_model(project)
    assert rep.status in ("OK", "PARTIAL")
    assert project.counts()["beams"] == 1            # non classée -> poutre
    assert project.counts()["columns"] == 0
