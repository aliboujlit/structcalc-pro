# -*- coding: utf-8 -*-
"""
tests/unit/test_dossier.py — Dossier de rendu (spec §15.3).

Vérifie que le dossier produit pour l'architecte : (a) existe réellement
(MD + PDF + XLSX), (b) n'invente aucun objet (0 poteau = 0 fiche + index
qui le dit), (c) n'affirme aucune conformité non vérifiée, (d) n'élève
jamais d'exception.
"""

import os

from structcalc.core.model import Project
from structcalc.reporting.dossier import build_dossier


def _p_with_column(sc_id="SC-PROJECT-000001"):
    p = Project(sc_id=sc_id, name="Immeuble")
    n1 = p.new_node(0.0, 0.0, 0.0)
    n2 = p.new_node(0.0, 3.0, 0.0)
    p.new_column(n1.sc_id, n2.sc_id, name="P1")
    return p


def test_dossier_writes_summary_fiche_and_formats(tmp_path):
    """Dossier complet : résumé + fiche poteau, en MD, XLSX et PDF."""
    p = _p_with_column()
    out = tmp_path / "dossier"
    files = build_dossier(p, str(out))
    names = [os.path.basename(f) for f in files]
    assert "resume_etude.md" in names, names
    assert any(n.startswith("fiche_poteau_") and n.endswith(".md")
               for n in names), names
    assert "LISEZ-MOI.txt" in names, names
    assert any(n.endswith(".xlsx") for n in names), names
    assert any(n.endswith(".pdf") for n in names), names
    # les fichiers annoncés existent RÉELLEMENT sur disque
    for f in files:
        assert os.path.isfile(f), f


def test_dossier_summary_never_claims_unverified_conformity(tmp_path):
    p = _p_with_column()
    out = tmp_path / "d2"
    build_dossier(p, str(out))
    md = (out / "resume_etude.md").read_text(encoding="utf-8")
    assert "conformit" in md.lower()          # le sujet est abordé…
    assert "Aucune conformité" in md or "à valider" in md.lower()


def test_dossier_no_column_no_fiche_and_index_says_it(tmp_path):
    """0 poteau = 0 fiche, et l'index l'écrit noir sur blanc."""
    p = Project(sc_id="SC-PROJECT-000002", name="Villa")
    p.new_node(0.0, 0.0, 0.0)
    out = tmp_path / "d3"
    files = build_dossier(p, str(out))
    names = [os.path.basename(f) for f in files]
    assert not any(n.startswith("fiche_poteau") for n in names), names
    idx = (out / "LISEZ-MOI.txt").read_text(encoding="utf-8")
    assert "aucun poteau" in idx
    assert "rien n'est invente" in idx or "rien n'est inventé" in idx


def test_dossier_includes_coherence_when_provided(tmp_path):
    p = Project(sc_id="SC-PROJECT-000003", name="RAS")
    p.new_node(0.0, 0.0, 0.0)
    out = tmp_path / "d4"
    files = build_dossier(p, str(out),
                          coherence_md="# Constats\n- donnée manquante\n")
    names = [os.path.basename(f) for f in files]
    assert "rapport_coherence.md" in names, names
    body = (out / "rapport_coherence.md").read_text(encoding="utf-8")
    assert "donnée manquante" in body


def test_dossier_never_raises_and_creates_nested_dir(tmp_path):
    """Jamais d'exception : dossier profond créé, projet minimal accepté."""
    p = Project(sc_id="SC-PROJECT-000004", name="Vide")
    files = build_dossier(p, str(tmp_path / "a" / "b" / "c"))
    assert files, "au minimum le résumé + l'index"
