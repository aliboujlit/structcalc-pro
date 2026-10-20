# -*- coding: utf-8 -*-
"""
integration/software_status.py — État LIVE des logiciels Autodesk : LEDs du
GUI (vert = connecté VÉRIFIÉ, rouge = non connecté) + relance par les MÊMES
programmes (demande utilisateur v1.3 : détection au lancement, relance par
les exécutables réels).

Règles (spec §19) :
  - VERT = le connecteur STRUCTCALC peut s'attacher MAINTENANT sans rien
    lancer : GetActiveObject (ROT), ou processus déjà actif quand
    l'attachement Dispatch est PRUVÉ (v1.2.5 : dispatch sans lancement,
    sans seconde fenêtre — vérifié live), ou pipe add-in vivant (Revit) ;
  - ROUGE = non connecté — le motif exact est porté dans `detail` ;
  - la détection NE LANCE JAMAIS rien et reste non bloquante
    (tasklist + GetActiveObject + sonde pipe ctypes) ;
  - `launch()` relance un logiciel manquant par SON exécutable réel
    (processus visible), uniquement s'il n'est pas déjà actif.

Revit n'a PAS de COM : seul compte le Named Pipe de l'add-in STRUCTCALC
(honnêteté stricte — un Revit « ouvert sans add-in » reste ROUGE).
Civil 3D et Advance Steel partagent l'hôte acad.exe : leur LED reflète le
transport hôte avec le détail explicite (aucune prétention au vertical).
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess
from typing import Dict, List, Tuple

_log = logging.getLogger("structcalc.integration.software_status")

# (clé, libellé, image processus)
APPS: List[Tuple[str, str, str]] = [
    ("robot", "Robot Structural Analysis", "robot.exe"),
    ("autocad", "AutoCAD", "acad.exe"),
    ("civil3d", "Civil 3D (hôte AutoCAD)", "acad.exe"),
    ("advsteel", "Advance Steel (hôte AutoCAD)", "acad.exe"),
    ("revit", "Revit (+ add-in STRUCTCALC)", "Revit.exe"),
    ("navisworks", "Navisworks Manage", "Roamer.exe"),
]

_ACAD_EXE = r"C:\Program Files\Autodesk\AutoCAD 2027\acad.exe"
_REVIT_GLOB = r"C:\Program Files\Autodesk\Revit *\Revit.exe"
_NW_GLOB = r"C:\Program Files\Autodesk\Navisworks *\Roamer.exe"


def _running(image: str) -> bool:
    """Vrai si un processus de cette image tourne (tasklist, sans lancement)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True, text=True, timeout=10).stdout.lower()
        return image.lower() in out
    except Exception:
        return False


def _rot(prog_id: str) -> bool:
    """Vrai si une instance COM est déjà dans le ROT (GetActiveObject —
    ne lance JAMAIS rien, échec rapide)."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            win32com.client.GetActiveObject(prog_id)
            return True
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        return False


def _revit_pipe() -> bool:
    from ..detector_stub import revit_addin_alive
    return bool(revit_addin_alive())


def _newest(glob_pattern: str) -> str:
    hits = sorted(glob.glob(glob_pattern))
    return hits[-1] if hits else ""


def exe_for(key: str) -> str:
    """Exécutable RÉEL du produit (registre/glob) — '' si introuvable."""
    if key == "robot":
        try:
            from .robot.connection import RobotConnection
            return RobotConnection._exe_path()
        except Exception:
            return ""
    if key in ("autocad", "civil3d", "advsteel"):
        return _ACAD_EXE if os.path.isfile(_ACAD_EXE) else _newest(
            r"C:\Program Files\Autodesk\AutoCAD *\acad.exe")
    if key == "revit":
        return _newest(_REVIT_GLOB)
    if key == "navisworks":
        return _newest(_NW_GLOB)
    return ""


def status_all() -> List[Dict[str, object]]:
    """
    Statut LIVE des 6 logiciels — une entrée par logiciel :
    {key, label, running, connected, exe, detail}.
    `connected` = VÉRIFIÉ (règles du module) ; jamais supposé.
    """
    out: List[Dict[str, object]] = []
    acad_running = _running("acad.exe")
    for key, label, image in APPS:
        running = acad_running if image == "acad.exe" else _running(image)
        exe = exe_for(key)
        installed = bool(exe and os.path.isfile(exe))
        connected = False
        detail = ""

        if key == "robot":
            if running:
                connected = True
                detail = ("actif — attachement direct PRUVÉ (Dispatch sans "
                          "lancement, v1.2.5)" + (" ; dans le ROT"
                          if _rot("Robot.Application") else ""))
            else:
                detail = "fermé (robot.exe absent)"
        elif key in ("autocad", "civil3d", "advsteel"):
            if running:
                connected = True
                rot = _rot("AutoCAD.Application")
                detail = ("actif — attachement direct PRUVÉ" + (" ; dans le ROT"
                          if rot else ""))
                if key != "autocad":
                    detail += (" ; transport = hôte AutoCAD partagé "
                               "(acad.exe) — le vertical partage "
                               "l'exécutable")
            else:
                detail = "fermé (acad.exe absent)"
        elif key == "revit":
            if _revit_pipe():
                connected = True
                detail = "add-in STRUCTCALC actif (pipe vivant)"
            elif running:
                detail = ("Revit actif MAIS add-in STRUCTCALC non détecté "
                          "(pipe muet) — non connecté")
            else:
                detail = "fermé"
        elif key == "navisworks":
            rot = _rot("Navisworks.Application")
            if rot or running:
                connected = True
                detail = ("actif — attachement COM prouvé"
                          + (" ; dans le ROT" if rot else ""))
            else:
                detail = "fermé (Roamer.exe absent)"

        if not installed and not running:
            detail = "non installé (introuvable) — " + detail
        out.append({"key": key, "label": label, "running": bool(running),
                    "connected": bool(connected), "exe": exe,
                    "detail": detail})
    n = sum(1 for s in out if s["connected"])
    _log.info("software_status : %s/%s logiciel(s) connecté(s) "
              "(vert = attachement vérifié sans lancement)", n, len(out))
    return out


def launch_missing(keys: List[str] | None = None) -> List[Tuple[str, bool, str]]:
    """
    Relance les logiciels demandés (par défaut : tous non connectés) par
    LEUR exécutable réel — processus visible, aucun silent start. Un
    logiciel déjà actif n'est jamais relancé (double instance interdite).
    """
    results: List[Tuple[str, bool, str]] = []
    statuses = {s["key"]: s for s in status_all()}
    for key, label, _image in APPS:
        if keys is not None and key not in keys:
            continue
        st = statuses[key]
        if st["connected"]:
            continue
        if st["running"]:
            results.append((key, False,
                            f"{label} : déjà actif mais non connecté — "
                            f"{st['detail']}"))
            continue
        exe = str(st["exe"] or "")
        if not exe or not os.path.isfile(exe):
            results.append((key, False, f"{label} : exécutable introuvable — "
                                        "relance impossible"))
            continue
        try:
            subprocess.Popen([exe])      # fenêtre visible — jamais caché
            _log.info("software_status : lancement de %s (%s)", label, exe)
            results.append((key, True, f"{label} : lancé par {exe}"))
        except Exception as exc:
            results.append((key, False, f"{label} : lancement impossible "
                                        f"({exc})"))
    return results
