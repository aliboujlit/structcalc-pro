# -*- coding: utf-8 -*-
"""
architectural_structural/validation_gate.py — Phase J (Module 71 §13).

Porte de validation avant diffusion. Contraint le passage d'un état de
diffusion au suivant selon les contrôles EXÉCUTÉS (§13).

États (DeliveryStatus, model_ext) :
  DRAFT → PRELIMINARY → UNDER_REVIEW → APPROVED_FOR_CALCULATION →
  CALCULATED → VERIFIED → VALIDATED_FOR_DELIVERY → SUPERSEDED

Règles absolues (§13) :
  - « Un calcul terminé ne suffit pas à rendre un plan exécutable. »
    → CALCULATED ne présage JAMAIS de la conformité ;
  - VALIDATED_FOR_DELIVERY exige les 4 contrôles (géométrique, analytique,
    réglementaire, documentaire) + conflits critiques traités ;
  - un document dont les contrôles obligatoires restent ouverts NE PEUT PAS
    être présenté comme définitif (§16.12).

100 % pur — testable unitairement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .model_ext import (
    ArchitecturalModel, DeliveryStatus,
    DELIVERY_TRANSITIONS,
)


# Les 4 contrôles de la Phase J (§13)
CONTROL_GEOMETRIC = "geometric"
CONTROL_ANALYTIC = "analytic"
CONTROL_REGULATORY = "regulatory"
CONTROL_DOCUMENTARY = "documentary"
ALL_CONTROLS = (CONTROL_GEOMETRIC, CONTROL_ANALYTIC,
                CONTROL_REGULATORY, CONTROL_DOCUMENTARY)


@dataclass
class GateResult:
    """Issue d'une demande de passage d'état."""
    allowed: bool
    from_status: str
    to_status: str
    missing_controls: List[str] = field(default_factory=list)
    blocking_conflicts: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "from": self.from_status,
                "to": self.to_status,
                "missing_controls": list(self.missing_controls),
                "blocking_conflicts": list(self.blocking_conflicts),
                "message": self.message}


@dataclass
class ValidationState:
    """
    État des contrôles pour un document/sujet (§13).

    Un contrôle passe à True UNIQUEMENT s'il a été exécuté et consigné ;
    il ne se déduit jamais d'un statut seul.
    """
    geometric: bool = False
    analytic: bool = False
    regulatory: bool = False
    documentary: bool = False
    controls_run: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def mark(self, control: str, done: bool = True,
             note: str = "") -> None:
        if control not in ALL_CONTROLS:
            raise ValueError(f"Contrôle inconnu : {control}")
        if control == CONTROL_GEOMETRIC:
            self.geometric = done
        elif control == CONTROL_ANALYTIC:
            self.analytic = done
        elif control == CONTROL_REGULATORY:
            self.regulatory = done
        elif control == CONTROL_DOCUMENTARY:
            self.documentary = done
        if done and control not in self.controls_run:
            self.controls_run.append(control)
        if note:
            self.notes.append(f"{control}: {note}")

    @property
    def completed(self) -> List[str]:
        out = []
        if self.geometric:
            out.append(CONTROL_GEOMETRIC)
        if self.analytic:
            out.append(CONTROL_ANALYTIC)
        if self.regulatory:
            out.append(CONTROL_REGULATORY)
        if self.documentary:
            out.append(CONTROL_DOCUMENTARY)
        return out

    @property
    def missing(self) -> List[str]:
        return [c for c in ALL_CONTROLS if c not in self.completed]


# ---------------------------------------------------------------------------
# Porte de validation
# ---------------------------------------------------------------------------

class ValidationGate:
    """
    Porte de validation d'un modèle Module 71.

    Contraindre `advance()` : refuse un passage si les prérequis ne sont pas
    satisfaits. NE promeut JAMAIS silencieusement (§13, §16.12).
    """

    def __init__(self, model: ArchitecturalModel):
        self.model = model
        # État des contrôles par drawing
        self._controls: Dict[str, ValidationState] = {}

    # -- Accès ------------------------------------------------------------
    def state_of(self, drawing_ref: str) -> ValidationState:
        if drawing_ref not in self._controls:
            self._controls[drawing_ref] = ValidationState()
        return self._controls[drawing_ref]

    def mark_control(self, drawing_ref: str, control: str,
                     done: bool = True, note: str = "") -> ValidationState:
        st = self.state_of(drawing_ref)
        st.mark(control, done, note)
        return st

    # -- Contrôle des prérequis -------------------------------------------
    def _blocking_conflicts(self) -> List[str]:
        """
        Conflits bloquants pour la diffusion : ceux qui ne sont PAS résolus
        ni rejetés (§13 « conflits critiques traités »).
        """
        terminal = {"VALIDATED_FOR_DELIVERY", "REJECTED"}
        return [c.sc_id for c in self.model.conflicts.values()
                if c.status not in terminal]

    def check_advance(self, drawing_ref: str,
                      to_status: DeliveryStatus) -> GateResult:
        """
        Évalue (sans appliquer) si un passage d'état est autorisé.

        Prérequis :
          - transition d'état autorisée (DELIVERY_TRANSITIONS) ;
          - pour VALIDATED_FOR_DELIVERY : les 4 contrôles faits + aucun
            conflit bloquant.
        """
        dr = self.model.drawings.get(drawing_ref)
        if dr is None:
            return GateResult(False, "?", to_status.value,
                              message=f"Plan inconnu : {drawing_ref}")
        frm = dr.status
        st = self.state_of(drawing_ref)

        # Transition structurelle autorisée ?
        if to_status.value not in DELIVERY_TRANSITIONS.get(frm.value, set()):
            return GateResult(
                False, frm.value, to_status.value,
                message=f"Transition {frm.value} -> {to_status.value} "
                        f"non autorisée (§13).")

        missing: List[str] = []
        blocking: List[str] = []

        # VALIDATED_FOR_DELIVERY exige les 4 contrôles (§13)
        if to_status == DeliveryStatus.VALIDATED_FOR_DELIVERY:
            missing = list(st.missing)
        # Toute diffusion au-delà de UNDER_REVIEW exige conflits traités
        advanced = {DeliveryStatus.APPROVED_FOR_CALCULATION,
                    DeliveryStatus.CALCULATED, DeliveryStatus.VERIFIED,
                    DeliveryStatus.VALIDATED_FOR_DELIVERY}
        if to_status in advanced:
            blocking = self._blocking_conflicts()

        ok = not missing and not blocking
        msg_parts = []
        if missing:
            msg_parts.append("contrôles manquants : " + ", ".join(missing))
        if blocking:
            msg_parts.append(f"{len(blocking)} conflit(s) non résolu(s)")
        if ok:
            msg_parts.append("prérequis satisfaits.")
        return GateResult(True if ok else False, frm.value, to_status.value,
                          missing_controls=missing,
                          blocking_conflicts=blocking,
                          message=" ; ".join(msg_parts))

    def advance(self, drawing_ref: str, to_status: DeliveryStatus,
                actor: str = "", reason: str = "") -> GateResult:
        """
        Applique le passage d'état SI autorisé ; sinon refuse SANS effet.
        Retourne le GateResult pour inspection/traçabilité (§15).
        """
        res = self.check_advance(drawing_ref, to_status)
        if not res.allowed:
            return res
        dr = self.model.drawings[drawing_ref]
        if not dr.transition(to_status, actor=actor, reason=reason):
            # transition refusée au niveau objet (double filet)
            res.allowed = False
            res.message += " ; transition refusée par l'objet Drawing."
            return res
        # Traçabilité (§15)
        self._trace(drawing_ref, actor, res.from_status,
                    to_status.value, reason)
        return res

    def _trace(self, drawing_ref, actor, frm, to, reason) -> None:
        rev_id = self.model.new_id("REVISION")
        from .model_ext import Revision
        rev = Revision(sc_id=rev_id, subject_ref=drawing_ref,
                       subject_kind="DRAWING",
                       version_from=0, version_to=0,
                       actor=actor, reason=reason or f"{frm} -> {to}")
        self.model.revisions[rev_id] = rev

    # -- Vue d'ensemble ---------------------------------------------------
    def delivery_readiness(self) -> Dict[str, dict]:
        """
        État de préparation de TOUS les plans (§13) : contrôle manquant et
        conflits bloquants visibles — jamais masqués.
        """
        out: Dict[str, dict] = {}
        blocking = self._blocking_conflicts()
        for did, dr in self.model.drawings.items():
            st = self.state_of(did)
            out[did] = {
                "status": dr.status.value,
                "controls_done": st.completed,
                "controls_missing": st.missing,
                "blocking_conflicts": blocking,
                "sections_provisional": list(dr.sections_provisional),
                "is_final": dr.status == DeliveryStatus.VALIDATED_FOR_DELIVERY,
                "can_be_presented_as_final": (
                    dr.status == DeliveryStatus.VALIDATED_FOR_DELIVERY
                    and not st.missing and not blocking),
            }
        return out
