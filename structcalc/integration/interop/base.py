# -*- coding: utf-8 -*-
"""
integration/interop/base.py — Contrat commun d'interconnexion Autodesk.

Objectif (demande utilisateur) : tout logiciel Autodesk connecté aux autres,
et RÉCIPROQUEMENT.

Conception : architecture en ÉTOILE par pivot SC-* (le modèle interne
STRUCTCALC). Plutôt que N×N ponts directs (inassurables, §19), chaque
logiciel implémente UN seul pont vers/depuis le pivot :

    AutoCAD  --\\
    Civil3D  ----\\
    Robot    ------>  PIVOT (Project SC-*)  ------>  n'importe quel autre
    Revit    ----/         (provenance + statuts)
    Navis..  --/

L'échange réciproque A <-> B = A -> pivot -> B. Réciprocité garantie avec
N connecteurs seulement.

Règles :
  - aucune opération logicielle inventée (§19) : `capability_status()` est
    la source de vérité ;
  - une capacité NON vérifiée n'est jamais présentée comme disponible ;
  - la couche interop ne dépend d'aucun logiciel tiers (interfaces purs).
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Capacités et leur état
# ---------------------------------------------------------------------------

class Capability(str, enum.Enum):
    """Opération interopérable qu'un connecteur pourrait fournir."""
    DETECT = "detect"                # détection installation/version
    CONNECT = "connect"              # ouverture session COM/.NET
    READ_MODEL = "read_model"        # extraire le modèle -> pivot
    WRITE_MODEL = "write_model"      # pousser le pivot -> logiciel
    READ_RESULTS = "read_results"    # résultats de calcul
    WRITE_LOADS = "write_loads"      # charges / combinaisons
    READ_DRAWINGS = "read_drawings"  # documents graphiques
    WRITE_DRAWINGS = "write_drawings"


class CapabilityStatus(str, enum.Enum):
    """
    État HONNÊTE d'une capacité (§19).

    SUPPORTED         : vérifié par exécution/sonde réelle.
    PARTIAL           : couvre un sous-ensemble documenté.
    UNVERIFIED        : possible a priori, NON prouvé -> jamais présenté
                        comme disponible.
    NOT_IMPLEMENTED   : squelette volontaire (aucun code d'appel réel).
    NOT_SUPPORTED     : impossible par nature (ex. Revit sans COM modèle).
    """
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"

    @property
    def usable(self) -> bool:
        """True seulement si l'opération est réellement exécutable."""
        return self in (CapabilityStatus.SUPPORTED, CapabilityStatus.PARTIAL)


@dataclass(frozen=True)
class CapabilityReport:
    """Une capacité + son état + la preuve / la raison."""
    capability: Capability
    status: CapabilityStatus
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.status.usable

    def to_dict(self) -> dict:
        return {"capability": self.capability.value,
                "status": self.status.value,
                "usable": self.usable, "detail": self.detail}


# ---------------------------------------------------------------------------
# Détection d'installation (indépendante du transport)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Detection:
    """
    Résultat de détection d'un logiciel Autodesk (registre/processus).

    `installed` est une donnée ; `automatable` dépend du TRANSPORT réel
    (COM vs .NET) et n'est JAMAIS déduit de `installed`.
    """
    name: str
    installed: bool = False
    version: str = ""
    progs: List[str] = field(default_factory=list)     # ProgID COM trouvés
    transport: str = ""                                 # "com" | "dotnet" | "file"
    automatable: bool = False                           # transport COM/.NET réel
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "installed": self.installed,
                "version": self.version, "progs": list(self.progs),
                "transport": self.transport,
                "automatable": self.automatable, "detail": self.detail}


# ---------------------------------------------------------------------------
# Rapport d'opération (aucun faux succès)
# ---------------------------------------------------------------------------

@dataclass
class OpReport:
    """
    Retour d'une opération interop.

    `status` ∈ OK | PARTIAL | REFUSED | ERROR | NOT_IMPLEMENTED.
    Un REFUSED/ERROR/NOT_IMPLEMENTED n'est JAMAIS transformé en succès.
    """
    operation: str
    status: str = "OK"          # OK|PARTIAL|REFUSED|ERROR|NOT_IMPLEMENTED
    message: str = ""
    objects: Dict[str, int] = field(default_factory=dict)
    source: str = ""
    target: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def to_dict(self) -> dict:
        return {"operation": self.operation, "status": self.status,
                "message": self.message, "objects": dict(self.objects),
                "source": self.source, "target": self.target}


# ---------------------------------------------------------------------------
# Connecteur abstrait
# ---------------------------------------------------------------------------

class InteropError(Exception):
    """Erreur d'interopérabilité (transport absent, capacité refusée...)."""


class AutodeskConnector(abc.ABC):
    """
    Pont UNIVERSEL d'un logiciel Autodesk vers/depuis le pivot SC-*.

    Sous-classes : Robot, AutoCAD, Civil3D, Revit, Navisworks...

    Un connecteur fournit :
      - `detect()`       : détection installation + transport réel ;
      - `capabilities()` : matrix honnête (§19) ;
      - `read_model()`   : logiciel -> pivot ;
      - `write_model()`  : pivot -> logiciel.

    Les opérations non supportées LÈVENT `InteropError` avec la raison
    explicite (jamais de résultat silencieusement vide).
    """

    #: identifiant stable du logiciel (clé de registre interop)
    name: str = "abstract"
    #: libellé affichable
    label: str = ""

    # -- Détection --------------------------------------------------------
    @abc.abstractmethod
    def detect(self) -> Detection:
        """Détecte installation/version/transport. Ne lève pas si absent."""

    @property
    def available(self) -> bool:
        """True si le transport réel permet la session (COM/.NET actif)."""
        return self.detect().automatable

    @property
    def connected(self) -> bool:
        """
        État de session courant. Par défaut non connecté ; les connecteurs
        concrets surchargent. Sert au hub pour éviter de re-connecter.
        """
        return False

    # -- Capacités --------------------------------------------------------
    @abc.abstractmethod
    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        """Matrix complète des Capacities -> CapabilityReport (§19)."""

    def can(self, cap: Capability) -> bool:
        """True si la capacité est réellement exécutable (SUPPORTED/PARTIAL)."""
        rep = self.capabilities().get(cap)
        return bool(rep and rep.usable)

    def status_of(self, cap: Capability) -> CapabilityStatus:
        rep = self.capabilities().get(cap)
        return rep.status if rep else CapabilityStatus.NOT_IMPLEMENTED

    # -- Session ----------------------------------------------------------
    def connect(self, timeout: float = 60.0) -> "AutodeskConnector":
        """Établit la session. Sans implémentation -> REFUSED explicite."""
        raise InteropError(
            f"[{self.name}] connect() non implémenté : aucune session "
            f"n'est ouverte (§19, aucun faux succès).")

    def disconnect(self) -> None:
        """Ferme la session. Fermeture par défaut sans sauvegarde (§5.4)."""
        return None

    # -- Ponts vers/depuis le pivot --------------------------------------
    @abc.abstractmethod
    def read_model(self, project: Any) -> OpReport:
        """
        Extrait le modèle du logiciel vers le pivot `project` (Project SC-*).
        Doit renseigner `objects` (compteurs) + traçabilité des statuts.
        """

    @abc.abstractmethod
    def write_model(self, project: Any) -> OpReport:
        """
        Pousse le pivot `project` dans le logiciel.
        Doit tracer la provenance (§4.3) des objets écrits.
        """

    def read_results(self, project: Any) -> OpReport:
        """Surchargeable. Par défaut : capacité refusée si non supportée."""
        return self._refuse(Capability.READ_RESULTS)

    def write_loads(self, project: Any) -> OpReport:
        return self._refuse(Capability.WRITE_LOADS)

    # -- Refus explicite --------------------------------------------------
    def _refuse(self, cap: Capability) -> OpReport:
        rep = self.capabilities().get(cap)
        st = rep.status if rep else CapabilityStatus.NOT_IMPLEMENTED
        detail = rep.detail if rep else "capacité inconnue"
        return OpReport(
            operation=cap.value, status="REFUSED", source=self.name,
            message=f"[{self.name}] {cap.value} refusé ({st.value}) : "
                    f"{detail}")

    def __repr__(self) -> str:  # pragma: no cover - débogage
        return f"<{type(self).__name__} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Livraison d'un connecteur : état courant (optionnel, pour boutons GUI)
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """État d'une session connecteur (affichage GUI, sans faux positif)."""
    name: str
    connected: bool = False
    project_open: bool = False
    last_operation: str = ""
    last_status: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "connected": self.connected,
                "project_open": self.project_open,
                "last_operation": self.last_operation,
                "last_status": self.last_status}
