# -*- coding: utf-8 -*-
"""
Tests unitaires de model._iter_numbers (Robot, sans COM).

Régression vivante (live 19/10) : la villa avait une numérotation NON DENSE
— l'ancien supposé 1..N levait E_UNEXPECTED sur `Get(1)` inexistant alors
que GetAll().Count répondait (66 nœuds / 108 barres réels). Les numéros
doivent venir de la COLLECTION, jamais d'un supposé.
"""
import pytest

from structcalc.integration.robot.model import (
    _iter_numbers, import_nodes, import_bars, RobotModelError)


class _Coll:
    """Collection Robot factice (IRobotNumberCollection simplifiée)."""

    def __init__(self, numbers, expose="GetNumber"):
        self._numbers = list(numbers)
        self.Count = len(self._numbers)
        if expose == "GetNumber":
            self.GetNumber = lambda i: self._numbers[i - 1]  # 1-based
        elif expose == "Item":
            self.Item = lambda i: self._numbers[i - 1]


class _CollCall:
    """Variante dispatch appelable : coll(i)."""

    def __init__(self, numbers):
        self._numbers = list(numbers)
        self.Count = len(self._numbers)

    def __call__(self, i):
        return self._numbers[i - 1]


class _Server:
    def __init__(self, numbers, expose="GetNumber"):
        if expose == "call":
            self._coll = _CollCall(numbers)
        else:
            self._coll = _Coll(numbers, expose)

    def GetAll(self):
        return self._coll


def test_iter_numbers_real_numbers_not_dense():
    """Numéros NON denses (villa) : la collection donne les vrais numéros."""
    srv = _Server([101, 105, 210], expose="GetNumber")
    assert _iter_numbers(srv) == [101, 105, 210]


def test_iter_numbers_item_accessor():
    srv = _Server([7, 9], expose="Item")
    assert _iter_numbers(srv) == [7, 9]


def test_iter_numbers_callable_accessor():
    srv = _Server([42], expose="call")
    assert _iter_numbers(srv) == [42]


def test_iter_numbers_dense_fallback():
    """Sans aucun accesseur : repli historique 1..N (Phase 0)."""
    assert _iter_numbers(_Server([1, 2, 3], expose=None)) == [1, 2, 3]


def test_import_nodes_uses_real_numbers():
    """import_nodes doit appeler Get(numéro RÉEL), pas Get(position)."""

    class _Node:
        def __init__(self, x, y, z):
            self.X, self.Y, self.Z = x, y, z

    class _Nodes:
        def __init__(self):
            self._data = {101: _Node(0.0, 0.0, 0.0),
                          105: _Node(6.0, 0.0, 0.0)}
            self.asked = []

        def GetAll(self):
            return _Coll(sorted(self._data), expose="GetNumber")

        def Get(self, number):
            self.asked.append(number)
            if number not in self._data:
                raise RuntimeError(f"nœud {number} inexistant")
            return self._data[number]

    class _RC:
        is_project_open = True

        def __init__(self):
            self.structure = type("S", (), {})()
            self.structure.Nodes = _Nodes()

    rc = _RC()
    out = import_nodes(rc)
    assert [n["number"] for n in out] == [101, 105]
    assert rc.structure.Nodes.asked == [101, 105]   # Get(numéro réel)
    assert out[1]["x"] == 6.0


def test_import_nodes_typed_collection():
    """Binding TYPÉ (villa live) : coll.Get(i) renvoie l'objet IRobotNode."""

    class _INode:
        def __init__(self, number, x, y, z):
            self.Number, self.X, self.Y, self.Z = number, x, y, z

    class _CollTyped:
        def __init__(self, items):
            self._items = items
            self.Count = len(items)

        def Get(self, i):
            return self._items[i - 1]      # 1-based, objet direct

    class _Nodes:
        def __init__(self):
            self._coll = _CollTyped([_INode(2, 0.03, 0.0, 0.0),
                                     _INode(7, 3.77, 0.03, 2.8)])

        def GetAll(self):
            return self._coll

        def Get(self, number):             # ne doit PAS être utilisé
            raise AssertionError("voie typée : Get(numéro) interdit")

    class _RC:
        is_project_open = True

        def __init__(self):
            self.structure = type("S", (), {})()
            self.structure.Nodes = _Nodes()

    out = import_nodes(_RC())
    assert [n["number"] for n in out] == [2, 7]
    assert out[0]["x"] == 0.03 and out[1]["z"] == 2.8


def test_import_bars_typed_collection():
    """Voie typée barres : coll.Get(i) -> IRobotBar (Number/Start/End)."""

    class _IBar:
        def __init__(self, number, start, end):
            self.Number, self.StartNode, self.EndNode = number, start, end

    class _CollTyped:
        def __init__(self, items):
            self._items = items
            self.Count = len(items)

        def Get(self, i):
            return self._items[i - 1]

    class _Bars:
        def __init__(self):
            self._coll = _CollTyped([_IBar(1, 2, 3), _IBar(5, 10, 11)])

        def GetAll(self):
            return self._coll

        def Get(self, number):
            raise AssertionError("voie typée : Get(numéro) interdit")

    class _RC:
        is_project_open = True

        def __init__(self):
            self.structure = type("S", (), {})()
            self.structure.Bars = _Bars()

    out = import_bars(_RC())
    assert out == [{"number": 1, "start": 2, "end": 3},
                   {"number": 5, "start": 10, "end": 11}]


def test_require_project_raises():
    class _RC:
        is_project_open = False

    with pytest.raises(RobotModelError):
        import_nodes(_RC())
