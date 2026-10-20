# -*- coding: utf-8 -*-
"""
architectural_structural/robot_exchange_coordinator.py — Phase E (Module 71 §8).

Coordonne l'échange contrôlé avec Robot Structural Analysis en appuyant sur
`integration/robot` (déjà éprouvé en Phase 0/2) — sans dupliquer son code.

Contrôles de retour avant d'ACCEPTER les résultats (§8.3) :
  1. modèle analysé = version envoyée ;
  2. éléments/sections correctement associés ;
  3. unités cohérentes ;
  4. charges/combinaisons attendues présentes ;
  5. calcul sans erreur bloquante ;
  6. résultats associés aux bons SC-ID ;
  7. données manquantes/non concordantes SIGNALÉES.

Règle (§8.3) : la disponibilité des opérations dépend des API réelles. Ce
module NE FAIT JAMAIS semblant : il retourne des statuts explicites (§19).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .model_ext import ArchitecturalModel, AnalysisModel, AnalysisResult


@dataclass
class ExchangeCheck:
    """Résultat d'un contrôle de retour (§8.3)."""
    index: int                # 1..7
    label: str
    passed: Optional[bool]    # None = non vérifiable (statut explicite)
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.passed is True

    def to_dict(self) -> dict:
        return {"index": self.index, "label": self.label,
                "passed": self.passed, "detail": self.detail,
                "status": ("OK" if self.passed is True
                           else "FAIL" if self.passed is False
                           else "NOT_CHECKABLE")}


@dataclass
class ExchangeReport:
    """Rapport d'échange Robot (§8)."""
    sent: bool = False
    received: bool = False
    model_ref: str = ""
    model_version: int = 0
    checks: List[ExchangeCheck] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed is True for c in self.checks)

    @property
    def any_failed(self) -> bool:
        return any(c.passed is False for c in self.checks)

    @property
    def accepted(self) -> bool:
        """Résultats acceptés UNIQUEMENT si tous les contrôles passent (§8.3)."""
        return (self.sent and self.received and not self.errors
                and self.all_passed)

    def to_dict(self) -> dict:
        return {"sent": self.sent, "received": self.received,
                "model_ref": self.model_ref,
                "model_version": self.model_version,
                "checks": [c.to_dict() for c in self.checks],
                "errors": list(self.errors),
                "all_passed": self.all_passed, "accepted": self.accepted}


# Les 7 contrôles de la §8.3 (libellés exacts)
CHECK_LABELS = {
    1: "Le modèle analysé correspond à la version envoyée",
    2: "Les éléments et sections sont correctement associés",
    3: "Les unités sont cohérentes",
    4: "Les charges et combinaisons attendues sont présentes",
    5: "Le calcul a abouti sans erreur bloquante",
    6: "Les résultats importés sont associés aux bons SC-ID",
    7: "Les données manquantes ou non concordantes sont signalées",
}


def preflight_send(model: ArchitecturalModel,
                   analysis_model_ref: str) -> ExchangeReport:
    """
    Contrôle AVANT export (§8.1) : vérifie que le modèle analytique est
    exploitable (nœuds + éléments + au moins un appui). Signale le manque
    d'appuis sans l'inventer.
    """
    rep = ExchangeReport()
    am = model.analysis_models.get(analysis_model_ref)
    if am is None:
        rep.errors.append(f"Modèle analytique inconnu : {analysis_model_ref}")
        return rep
    rep.model_ref = am.sc_id
    rep.model_version = am.version

    if not am.node_ids:
        rep.errors.append("Modèle analytique sans nœud — export impossible.")
    if not am.member_ids:
        rep.errors.append("Modèle analytique sans élément barre — export "
                          "impossible.")
    if not am.support_ids:
        rep.errors.append("Aucun appui défini — modèle non calculable tel quel "
                          "(§8.1 appuis/liaisons requis).")

    rep.checks.append(ExchangeCheck(
        1, CHECK_LABELS[1], True,
        f"Envoi du modèle {am.sc_id} v{am.version} (version tracée)."))
    rep.sent = not rep.errors
    return rep


def receive_results(model: ArchitecturalModel,
                    analysis_model_ref: str,
                    raw_results: Optional[Dict[str, Any]],
                    expected_software: str = "Robot",
                    units: Optional[Dict[str, str]] = None,
                    missing_data: Optional[Sequence[str]] = None,
                    ) -> ExchangeReport:
    """
    Réception + 7 contrôles de retour (§8.3).

    `raw_results` : dict brut {reactions, bar_forces, displacements} ou None
    (aucun résultat => contrôle 5/6 échouent, jamais des valeurs inventées).

    L'AnalysisResult n'est créé QUE si les contrôles passent ; sinon les
    erreurs sont rapportées (§8.3 « avant d'accepter les résultats »).
    """
    rep = receive_and_validate(model, analysis_model_ref, raw_results,
                               expected_software, units, missing_data)
    return rep


def receive_and_validate(model: ArchitecturalModel,
                         analysis_model_ref: str,
                         raw_results: Optional[Dict[str, Any]],
                         expected_software: str,
                         units: Optional[Dict[str, str]],
                         missing_data: Optional[Sequence[str]],
                         ) -> ExchangeReport:
    """Implémentation des 7 contrôles (§8.3)."""
    rep = ExchangeReport()
    am = model.analysis_models.get(analysis_model_ref)
    if am is None:
        rep.errors.append(f"Modèle analytique inconnu : {analysis_model_ref}")
        return rep
    rep.model_ref = am.sc_id
    rep.model_version = am.version
    rep.sent = True

    # Contrôle 5 : erreur bloquante de calcul
    calc_error = (raw_results or {}).get("calc_error", "")
    # Contrôle 1 : version du modèle analysé == version envoyée
    returned_version = (raw_results or {}).get("model_version")
    if returned_version is None:
        c1 = (None, "Version du modèle non retournée par le calcul.")
    elif int(returned_version) == am.version:
        c1 = (True, f"v{returned_version} conforme à la version envoyée.")
    else:
        c1 = (False, f"v{returned_version} != v{am.version} envoyée.")
    rep.checks.append(ExchangeCheck(1, CHECK_LABELS[1], c1[0], c1[1]))

    # Contrôle 2 : éléments/sections associés
    members_expected = set(am.member_ids)
    members_returned = set((raw_results or {}).get("member_ids", []) or [])
    if raw_results is None:
        c2 = (None, "Aucun résultat retourné.")
    elif members_expected and members_returned <= members_expected:
        c2 = (True, f"{len(members_returned)} éléments associés.")
    else:
        c2 = (False, "Éléments retournés non conformes au modèle envoyé.")
    rep.checks.append(ExchangeCheck(2, CHECK_LABELS[2], c2[0], c2[1]))

    # Contrôle 3 : unités cohérentes
    if not units:
        c3 = (None, "Unités non fournies — contrôle impossible (§8.3).")
    elif units.get("force") and units.get("length"):
        c3 = (True, f"force={units['force']}, length={units['length']}.")
    else:
        c3 = (False, "Unités incomplètes.")
    rep.checks.append(ExchangeCheck(3, CHECK_LABELS[3], c3[0], c3[1]))

    # Contrôle 4 : charges/combinaisons présentes
    combos = (raw_results or {}).get("combinations", None)
    if combos is None:
        c4 = (None, "Combinaisons non renseignées.")
    elif combos:
        c4 = (True, f"{len(combos)} combinaison(s) présente(s).")
    else:
        c4 = (False, "Aucune combinaison attendue présente.")
    rep.checks.append(ExchangeCheck(4, CHECK_LABELS[4], c4[0], c4[1]))

    # Contrôle 5 : pas d'erreur bloquante
    if raw_results is None:
        c5 = (False, "Aucun résultat (calcul absent ou échoué).")
    elif calc_error:
        c5 = (False, f"Erreur de calcul : {calc_error}")
    else:
        c5 = (True, "Aucune erreur bloquante signalée.")
    rep.checks.append(ExchangeCheck(5, CHECK_LABELS[5], c5[0], c5[1]))

    # Contrôle 6 : résultats associés aux bons SC-ID
    if raw_results is None:
        c6 = (None, "Aucun résultat à associer.")
    else:
        bad = [k for k in (raw_results.get("reactions", {}) or {})
               if k not in set(am.node_ids)]
        if bad:
            c6 = (False, f"SC-ID inconnus dans les réactions : {bad[:3]}")
        else:
            c6 = (True, "Réactions rattachées aux SC-ID du modèle.")
    rep.checks.append(ExchangeCheck(6, CHECK_LABELS[6], c6[0], c6[1]))

    # Contrôle 7 : données manquantes signalées (jamais masquées)
    missing = list(missing_data or [])
    if missing:
        c7 = (True, f"{len(missing)} donnée(s) manquante(s) signalée(s) : "
                    + ", ".join(missing[:5]))
    else:
        c7 = (True, "Aucune donnée manquante signalée.")
    rep.checks.append(ExchangeCheck(7, CHECK_LABELS[7], c7[0], c7[1]))

    rep.received = raw_results is not None

    # Création de l'AnalysisResult UNIQUEMENT si accepté (§8.3)
    if rep.accepted:
        _store_result(model, am, raw_results, expected_software)
    else:
        # L'erreur de calcul brute est remontée pour traçabilité (§8.3.5)
        if calc_error:
            rep.errors.append(f"Erreur de calcul bloquante : {calc_error}")
        failed = [c.label for c in rep.checks if c.passed is False]
        if failed:
            rep.errors.append("Contrôles de retour échoués : "
                              + " | ".join(failed))
    return rep


def _store_result(model: ArchitecturalModel, am: AnalysisModel,
                  raw: Dict[str, Any], software: str) -> AnalysisResult:
    import datetime as _dt
    rid = model.new_id("RESULT")
    res = AnalysisResult(
        sc_id=rid, name=f"Résultats {software} {am.sc_id} v{am.version}",
        model_ref=am.sc_id, model_version=am.version,
        software=software, available=True, outdated=False,
        reactions=raw.get("reactions", {}),
        bar_forces=raw.get("bar_forces", {}),
        displacements=raw.get("displacements", {}),
        calc_error="", imported_at=_dt.datetime.now().isoformat(
            timespec="seconds"))
    model.analysis_results[rid] = res
    am_ref = am
    return res
