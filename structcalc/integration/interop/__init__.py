# -*- coding: utf-8 -*-
"""
integration/interop/__init__.py — Hub d'interconnexion RÉCIPROQUE Autodesk.

Demande utilisateur : « tout logiciel Autodesk peut se connecter avec les
autres, et de façon RÉCIPROQUE entre eux ».

Architecture retenue : ÉTOILE par pivot SC-* (le modèle interne STRUCTCALC).

    AutoCAD  ──┐                              ┌── Robot (résultats/charges)
    Civil 3D ──┤                              │
    Revit ─────┼──►  PIVOT (Project SC-*)  ◄──┤
    (refus     │      IDs stables SC-*        └── n'importe quel autre
     direct)   │      provenance + statuts
               └──►

Pour N logiciels, N connecteurs donnent les N×N sens d'échange :

    A --read--> PIVOT --write--> B     (A vers B)
    B --read--> PIVOT --write--> A     (B vers A)

La réciprocité est garantie PAR CONSTRUCTION, sans écrire N² ponts directs
(inassurables, spec §19 « aucune API inventée »).

Connecteurs (statut HONNÊTE) :
  - robot      : COM vérifié Phase 0/2 — modèle + résultats + charges partielles
  - autocad    : COM vérifié par sonde — DWG lecture/écriture (sans texte)
  - civil3d    : hérite d'AutoCAD (hôte acad.exe partagé) — DWG de niveau
                 dessin ; objets intelligents Civil 3D REFUSÉS (.NET requis,
                 ProgIDs AeccX* inactivables en externe)
  - advsteel   : hérite d'AutoCAD (hôte acad.exe partagé, l'instance active
                 EST Advance Steel) — DWG de niveau dessin ; sémantique acier
                 AstorMain5 REFUSÉE (coclasses non enregistrées en COM, §19)
  - revit      : .NET seulement, AUCUN COM modèle -> pont direct REFUSÉ,
                 motif explicite (voies §6.2 recommandées à la place)
  - navisworks : COM VÉRIFIÉ (Navisworks.Document.24) — OpenFile/SaveAs :
                 convertisseur de FICHIERS de coordination (DWG/IFC -> NWD) ;
                 géométrie via pivot REFUSÉE (aucun membre COM de modèle, §19)

Garanties :
  - une capacité non vérifiée n'est JAMAIS présentée comme disponible ;
  - un échec/refus est TOUJOURS retourné avec son motif (jamais de faux succès).
"""

from .base import (
    AutodeskConnector,
    Capability,
    CapabilityReport,
    CapabilityStatus,
    Detection,
    InteropError,
    OpReport,
    SessionState,
)
from .hub import (
    ExchangeResult,
    InteropHub,
    RouteUnavailability,
)
from .autocad import AutoCADConnector, AutoCADConnectionError
from .robot import RobotConnector
from .revit import RevitConnector
from .civil3d import Civil3DConnector
from .navisworks import NavisworksConnector, NavisworksConnectionError
from .advsteel import AdvanceSteelConnector

__all__ = [
    # contrat
    "AutodeskConnector",
    "Capability",
    "CapabilityReport",
    "CapabilityStatus",
    "Detection",
    "InteropError",
    "OpReport",
    "SessionState",
    # hub
    "InteropHub",
    "ExchangeResult",
    "RouteUnavailability",
    # connecteurs
    "AutoCADConnector",
    "AutoCADConnectionError",
    "RobotConnector",
    "RevitConnector",
    "Civil3DConnector",
    "NavisworksConnector",
    "NavisworksConnectionError",
    "AdvanceSteelConnector",
    # raccourci : hub pré-enregistré (sans connexion)
    "default_hub",
]


def default_hub() -> InteropHub:
    """
    Hub avec les 6 connecteurs Autodesk enregistrés (aucune connexion ouverte).

    Le appelant décide quand connecter (aucun logiciel n'est lancé au import).
    """
    hub = InteropHub()
    for conn in (RobotConnector(), AutoCADConnector(), Civil3DConnector(),
                 AdvanceSteelConnector(), RevitConnector(),
                 NavisworksConnector()):
        hub.register(conn)
    return hub
