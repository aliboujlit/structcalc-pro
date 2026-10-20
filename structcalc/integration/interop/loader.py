# -*- coding: utf-8 -*-
"""
interop/loader.py — Chargement d'un fichier projet dans le pivot SC-*.

Demande utilisateur (v1.2) : « je veux que STRUCTCALC PRO lance le projet
Plan-villa avec son workflow entier » — point d'entrée GUI « Projet >
Ouvrir… » qui alimente le modèle interne :

  - .rtd (Robot)   : connexion Robot -> GARDE « un projet étranger déjà
                     ouvert » (règle §5.4 : jamais fermer/modifier ce qui
                     ne nous appartient pas) -> ouverture du .rtd ->
                     read_model -> fermeture SANS sauvegarde — et UNIQUEMENT
                     le projet que NOUS venons d'ouvrir ;
  - .dwg (AutoCAD) : connexion -> si le document est DÉJÀ ouvert, il est
                     réutilisé en LECTURE SEULE (ni réouvert ni fermé) ;
                     sinon ouverture puis fermeture sans save en fin de
                     lecture — encore une fois, seulement ce que nous avons
                     ouvert -> read_model ciblé sur le document ;
  - autre suffixe  : REFUS explicite (format non pris en charge).

Règles absolues :
  - aucune donnée inventée : 0 objet lu = 0 objet rapporté (un plan
    architectural sans calques SC_* reste honnêtement à 0) ;
  - aucun faux succès : chaque exception devient un résultat REFUS/ERROR
    explicite — jamais levée, jamais masquée ;
  - chaque message porte l'identité de la source (nom de fichier) et les
    compteurs RÉELS du pivot après lecture.

Testable sans COM : les classes connecteur sont injectables (robot_cls /
autocad_cls) — voir tests/unit/test_loader.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional


@dataclass
class LoadResult:
    """Issue honnête d'un chargement de fichier projet."""
    ok: bool
    project: Any = None                    # Project SC-* rempli (None si échec)
    source: str = ""                       # "Robot (.rtd)" / "AutoCAD (.dwg)"
    status: str = ""                       # "OK" | "PARTIAL" (lecture complète/partielle)
    counts: Dict[str, int] = field(default_factory=dict)
    message: str = ""                      # message honnête complet


def _counts_line(project: Any) -> str:
    """Compteurs réels du pivot, sans jamais inventer un objet."""
    c = project.counts()
    return (f"{c['nodes']} nœud(s), {c['columns']} poteau(x), "
            f"{c['beams']} barre(s), {c['slabs']} dalle(s), "
            f"{c['walls']} mur(s), {c['supports']} appui(s)")


# ---------------------------------------------------------------------------
# Robot (.rtd)
# ---------------------------------------------------------------------------

def _load_rtd(path: Path, robot_cls: Callable[[], Any],
              timeout: float) -> LoadResult:
    from ...core.model import Project

    try:
        conn = robot_cls()
    except Exception as exc:
        return LoadResult(False, source="Robot (.rtd)",
                          message=f"REFUS — connecteur Robot indisponible : {exc}")
    rc = None
    opened = False
    try:
        conn.connect(timeout=timeout)
        rc = conn.rc
        if rc.is_project_open and not rc.opened_by_us:
            return LoadResult(
                False, source="Robot (.rtd)",
                message="REFUS — un projet Robot est déjà ouvert et il "
                        "n'a pas été ouvert par STRUCTCALC (session "
                        "étrangère) : règle §5.4, aucun projet existant "
                        "n'est fermé ni modifié. Fermez-le dans Robot puis "
                        "relancez.")
        rc.open_project(str(path))
        opened = True
        project = Project(sc_id="SC-PROJECT-000001", name=path.stem)
        project.source_file = str(path)   # porté pour coordination (NWD)
        rep = conn.read_model(project)
        status = getattr(rep, "status", "ERROR")
        if status not in ("OK", "PARTIAL"):
            return LoadResult(
                False, source="Robot (.rtd)",
                message=f"REFUS — lecture du modèle Robot refusée : "
                        f"{getattr(rep, 'message', '')}")
        counts = project.counts()
        if status == "PARTIAL":
            # Lecture partielle : chargée ce qui a pu l'être, avec le motif
            # détaillé — JAMAIS présenté comme une lecture complète.
            msg = (f"Modèle Robot PARTIELLEMENT chargé depuis « {path.name} » "
                   f"({status}) : {_counts_line(project)} — détails : "
                   f"{getattr(rep, 'message', '')}")
        else:
            msg = (f"Modèle Robot chargé depuis « {path.name} » : "
                   f"{_counts_line(project)} — identifiants SC-* attribués "
                   f"(table de correspondance Robot conservée).")
        return LoadResult(True, project=project, source="Robot (.rtd)",
                          status=status, counts=counts, message=msg)
    except Exception as exc:
        return LoadResult(False, source="Robot (.rtd)",
                          message=f"ERREUR — lecture du .rtd impossible : {exc}")
    finally:
        if opened and rc is not None:
            # Fermeture SANS sauvegarde — et uniquement notre projet.
            try:
                rc.close_project(save=False)
            except Exception:
                pass
        try:
            conn.disconnect()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# AutoCAD (.dwg)
# ---------------------------------------------------------------------------

def _doc_identity(doc: Any) -> str:
    """Nom/chemin exploitable d'un document AutoCAD (jamais d'exception)."""
    try:
        full = str(doc.FullName or "")
    except Exception:
        full = ""
    try:
        name = str(doc.Name or "")
    except Exception:
        name = "?"
    return full or name


def _load_dwg(path: Path, autocad_cls: Callable[..., Any],
              timeout: float) -> LoadResult:
    from ...core.model import Project
    from .autocad import find_doc_by_path

    try:
        conn = autocad_cls(attach_only=False)
    except Exception as exc:
        return LoadResult(
            False, source="AutoCAD (.dwg)",
            message=f"REFUS — connecteur AutoCAD indisponible : {exc}")
    doc = None
    opened = False
    try:
        conn.connect(timeout=timeout)
        doc = find_doc_by_path(conn.app, str(path))
        if doc is not None:
            doc_note = (f"document DÉJÀ ouvert réutilisé en LECTURE SEULE : "
                        f"{_doc_identity(doc)} (ni réouvert, ni fermé)")
        else:
            doc = conn.open_document(str(path))
            opened = True
            doc_note = f"document ouvert par STRUCTCALC : {_doc_identity(doc)}"
        project = Project(sc_id="SC-PROJECT-000001", name=path.stem)
        project.source_file = str(path)   # porté pour coordination (NWD)
        rep = conn.read_model(project, document=doc)
        status = getattr(rep, "status", "ERROR")
        if status not in ("OK", "PARTIAL"):
            return LoadResult(
                False, source="AutoCAD (.dwg)",
                message=f"REFUS — lecture AutoCAD refusée : "
                        f"{getattr(rep, 'message', '')}")
        counts = project.counts()
        note_zero = ""
        if sum(counts.values()) == 0:
            note_zero = (" — 0 objet structurel SC_* trouvé : c'est un plan "
                         "sans objets STRUCTCALC (aucun objet n'est inventé)")
        if status == "PARTIAL":
            # Lecture partielle assumée et affichée — jamais un faux plein.
            msg = (f"Modèle PARTIELLEMENT chargé depuis « {path.name} » "
                   f"({status}) : {_counts_line(project)}{note_zero} — "
                   f"{doc_note} — détails : {getattr(rep, 'message', '')}")
        else:
            msg = (f"Modèle chargé depuis « {path.name} » via AutoCAD : "
                   f"{_counts_line(project)}{note_zero} — {doc_note}.")
        return LoadResult(True, project=project, source="AutoCAD (.dwg)",
                          status=status, counts=counts, message=msg)
    except Exception as exc:
        return LoadResult(
            False, source="AutoCAD (.dwg)",
            message=f"ERREUR — lecture du .dwg impossible : {exc}")
    finally:
        if opened and doc is not None:
            # Fermeture sans save — uniquement le document que NOUS avons
            # ouvert (un document pré-existant reste ouvert, intact).
            try:
                conn.close_document(doc, save=False)
            except Exception:
                pass
        try:
            conn.disconnect()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def load_project_file(path: Any, *,
                      robot_cls: Optional[Callable[[], Any]] = None,
                      autocad_cls: Optional[Callable[..., Any]] = None,
                      timeout: float = 90.0) -> LoadResult:
    """
    Charge un fichier projet (.rtd Robot / .dwg AutoCAD) dans le pivot SC-*.

    Ne lève JAMAIS d'exception : tout échec est un LoadResult(ok=False) avec
    le motif explicite. Les classes connecteur sont injectables (tests).
    """
    p = Path(str(path))
    if not p.exists():
        return LoadResult(False,
                          message=f"REFUS — fichier introuvable : {p}")
    suffix = p.suffix.lower()
    if suffix == ".rtd":
        if robot_cls is None:
            from .robot import RobotConnector   # import paresseux (COM)
            robot_cls = RobotConnector
        return _load_rtd(p, robot_cls, timeout)
    if suffix == ".dwg":
        if autocad_cls is None:
            from .autocad import AutoCADConnector   # import paresseux (COM)
            autocad_cls = AutoCADConnector
        return _load_dwg(p, autocad_cls, timeout)
    return LoadResult(
        False,
        message=f"REFUS — format non pris en charge : "
                f"« {p.suffix or p.name} » (attendu : .rtd Robot ou "
                f".dwg AutoCAD).")
