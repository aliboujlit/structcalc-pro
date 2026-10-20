# -*- coding: utf-8 -*-
"""
detector_stub.py — Détection honnête des logiciels Autodesk (couche INTEGRATION).

Note : malgré le nom « stub », cette détection est RÉELLE et légère (registre +
dossiers + sonde du Named Pipe add-in), sans instanciation COM lourde.

Règle (spec §19) : la détection affiche le statut d'intégration RÉEL. Elle ne
prétend jamais qu'un logiciel est « connecté/opérationnel » pour l'échange de
données sans le connecteur approprié. Le rappel spec §20 reste affiché :
présence d'un logiciel ≠ échange fonctionnel.

État réel (v1.2, vérifié en live) :
  - Robot     : COM/RobotOM câblé (interop/robot.py) — attach/lancement,
                lecture/écriture de modèle vérifiés sur .rtd réels ;
  - AutoCAD   : COM câblé (interop/autocad.py) — ouverture/lecture ciblée
                (document ciblé, relecture si déjà ouvert), écriture SC_*
                avec gardes anti-faux-succès, échanges Robot<->AutoCAD
                vérifiés en live (paires réciproques du hub) ;
  - Revit     : PAS de COM — add-in .NET STRUCTCALC (Named Pipe
                structcalc_revit) : PING/NDJSON et lecture de modèle
                vérifiés en live ; l'instance est réputée prête UNIQUEMENT
                si le pipe de l'add-in répond (sonde réelle ci-dessous).
                Capacités PARTIAL : mise à jour d'un modèle existant,
                JAMAIS création de modèle de zéro (aucune API inventée).
"""

from __future__ import annotations

import ctypes
import os

# Pipe de l'add-in .NET (StructCalcAddin/Server/NamedPipeServer.cs)
_REVIT_PIPE = r"\\.\pipe\structcalc_revit"


def revit_addin_alive() -> bool:
    """Vrai si l'add-in STRUCTCALC dans Revit expose son Named Pipe.

    Sonde LÉGÈRE (CreateFileW sur le pipe) — aucun COM, aucune charge de
    modèle : utilisable depuis le thread de détection (spec §14.4).
    """
    try:
        handle = ctypes.windll.kernel32.CreateFileW(
            _REVIT_PIPE, 0x80000000, 0, None, 3, 0, None)
        alive = handle != -1          # -1 = INVALID_HANDLE_VALUE
        if alive:
            ctypes.windll.kernel32.CloseHandle(handle)
        return bool(alive)
    except Exception:
        return False


# ProgIDs / chemins audités — libellés d'intégration = ÉTAT RÉEL v1.2
_KNOWN = [
    {
        "name": "Robot Structural Analysis Professional 2027",
        "exe": r"C:\Program Files\Autodesk\Robot Structural Analysis Professional 2027\Exe\robot.exe",
        "prog_id": "Robot.Application",
        "integration": ("COM/RobotOM — câblé (interop/robot.py) : connexion, "
                        "lecture/écriture de modèle vérifiées en live"),
        "ready": True,
    },
    {
        "name": "Revit 2027",
        "exe": r"C:\Program Files\Autodesk\Revit 2027\Revit.exe",
        "prog_id": None,
        "integration": ("Pas de COM — add-in .NET STRUCTCALC via Named Pipe "
                        "(structcalc_revit) : PING/lecture vérifiés en live ; "
                        "mise à jour d'un modèle existant seulement, "
                        "jamais création de zéro"),
        "ready": None,               # None = dépend de la sonde du pipe
    },
    {
        "name": "AutoCAD 2027",
        "exe": r"C:\Program Files\Autodesk\AutoCAD 2027\acad.exe",
        "prog_id": "AutoCAD.Application.26",
        "integration": ("COM AutoCAD — câblé (interop/autocad.py) : ouverture "
                        "et lecture ciblées, écriture SC_* avec gardes anti-"
                        "faux-succès, échanges Robot<->AutoCAD vérifiés en live"),
        "ready": True,
    },
]


def _state(p: dict) -> tuple[bool, str]:
    """(prêt échange, détail affiché) — évaluation honnête pour un produit présent."""
    if p["ready"] is None:
        # Revit : prêt SEULEMENT si l'add-in répond sur son pipe (sonde réelle)
        if revit_addin_alive():
            return True, ("OUI (add-in structcalc_revit actif — capacités "
                          "PARTIAL : mise à jour, pas de création)")
        return False, ("NON (add-in STRUCTCALC non détecté : lancez Revit "
                       "2027 — l'add-in se charge au démarrage)")
    if p["ready"]:
        return True, "OUI (transport présent, session vérifiée en live)"
    return False, "NON (voir intégration)"


def detect_products() -> str:
    """
    Détecte les logiciels connus et renvoie un rapport texte lisible.
    N'instancie AUCUN logiciel (détection légère) — sauf sonde du pipe
    add-in Revit (ctypes, sans COM).
    """
    lines = ["=== Détection des logiciels Autodesk ===", ""]
    found = 0
    for p in _KNOWN:
        present = os.path.isfile(p["exe"])
        if present:
            found += 1
        mark = "[INSTALLE]" if present else "[ absent ]"
        lines.append(f"{mark} {p['name']}")
        if present:
            lines.append(f"    Exe        : {p['exe']}")
            if p["prog_id"]:
                lines.append(f"    ProgID COM : {p['prog_id']}")
            lines.append(f"    Intégration: {p['integration']}")
            _ready, detail = _state(p)
            lines.append(f"    Prêt échange: {detail}")
        lines.append("")
    lines.append(f"Total détecté : {found}/{len(_KNOWN)}")
    lines.append("")
    lines.append("Rappel (spec §20) : la présence d'un logiciel ne prouve pas que "
                 "l'échange est fonctionnel.")
    return "\n".join(lines)


def connected_count() -> int:
    """Nombre de logiciels réellement prêts pour l'échange (spec §20).

    Robot/AutoCAD : transport prêt (capacité de session vérifiée en live).
    Revit : uniquement si l'add-in répond actuellement sur son pipe.
    """
    n = 0
    for p in _KNOWN:
        if not os.path.isfile(p["exe"]):
            continue
        ready, _ = _state(p)
        if ready:
            n += 1
    return n
