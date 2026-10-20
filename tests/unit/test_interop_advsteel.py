# -*- coding: utf-8 -*-
"""
tests/unit/test_interop_advsteel.py — Connecteur Advance Steel (hérite AutoCAD).

Faits vérifiés (probe_advsteel.py / probe_advsteel_activate.py) sur Advance
Steel 2027 : hôte acad.exe partagé (DWG de niveau dessin accessible) ; modèle
objet AstorMain5 (AdvanceSteelApplication/Beam/Bolt/AstUI) avec coclasses NON
enregistrées en COM externe -> sémantique acier REFUSÉE (§19).

Ces tests n'utilisent AUCUN logiciel : on vérifie la matrice de capacités
honnête et les refus explicites de la sémantique AstorMain5.
"""

from __future__ import annotations

from structcalc.integration.interop import (
    AdvanceSteelConnector, Capability, CapabilityStatus, default_hub,
)


def test_detect_structural():
    det = AdvanceSteelConnector().detect()
    assert det.name == "advsteel"
    assert det.transport == "com"
    assert isinstance(det.automatable, bool)


def test_capabilities_dwg_partial_semantic_refused():
    caps = AdvanceSteelConnector().capabilities()
    # DWG de niveau dessin : PARTIAL (hérité AutoCAD, via hôte commun)
    assert caps[Capability.READ_MODEL].status is CapabilityStatus.PARTIAL
    assert caps[Capability.WRITE_MODEL].status is CapabilityStatus.PARTIAL
    assert caps[Capability.CONNECT].status is CapabilityStatus.SUPPORTED
    # charges : refusées (AstorMain5 non exposé)
    assert caps[Capability.WRITE_LOADS].status is CapabilityStatus.NOT_SUPPORTED


def test_steel_objects_refused_not_ok():
    """Sémantique AstorMain5 : REFUS explicite (motif non vide, §19)."""
    c = AdvanceSteelConnector()
    r_read = c.read_steel_objects()
    r_write = c.write_steel_objects()
    assert r_read.ok is False
    assert r_write.ok is False
    assert r_read.status == "NOT_IMPLEMENTED"
    assert "AstorMain5" in r_read.message
    assert "advsteel" in r_read.message


def test_inherits_autocad_dwg_capability():
    """Advance Steel partage l'hôte AutoCAD : DWG échangeable (réciproque)."""
    hub = default_hub()
    m = hub.routes()
    # advsteel <-> robot faisable (lecture/écriture DWG via hôte commun)
    assert m["advsteel"]["robot"]["feasible"] is True
    assert m["robot"]["advsteel"]["feasible"] is True
