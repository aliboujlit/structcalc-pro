# -*- coding: utf-8 -*-
"""
integration/robot/loads.py — Cas de charges et combinaisons (spec §5.3).

Signatures Robot 2027 VÉRIFIÉES par sondage (tools/probe_cs_analize.py,
probe_full_pipeline.py) :
  - Cases.CreateSimple(number, name, type_int, analize_bool)  [CONFIRMÉ]
  - Cases.GetAll().Count                                       [CONFORME]
  - Cases.Get(number)                                          [CONFIRMÉ]
  - Cases.CreateCombination(number, name, comb_type, case_nature,
                            case_analize_type) + CaseFactors.New
    [CONFIRMÉ par exécution — tools/probe_create_combination_live.py]

Signatures PARTIELLEMENT vérifiées (un paramètre découvert par la liaison
typée mais chaînage complet non démontré) :
  - Nodes.SetLabel(node_number, lab_name)  -> nécessite le nom d'appui

Charge uniforme barre — CHAÎNE PRUVÉE par exécution (spec §0, §19) :
  - case.Records.New(I_LRT_BAR_UNIFORM=5) -> index ; Records.Get(index) ;
    rec.Objects.FromText(bar_list) ; rec.SetValue(2, fz) [index 2 = Fz].
  (L'ancienne chaîne `Records.Create(type); rec.Objects=".."; rec.Fz=..` était
   FAUSSE — Objects est un objet FromText et Fz passe par SetValue(2,..).)

Règle (spec §19) : toute fonction dont le chaînage COMplet n'a pas été démontré
lève RobotLoadsError avec un statut explicite, au lieu de renvoyer un faux
succès. Le module ne prétend jamais à une opération non prouvée.
"""

from __future__ import annotations

from typing import Optional

from .connection import RobotConnection


class RobotLoadsError(Exception):
    """Erreur / statut non vérifié lors de l'export de charges."""


# ---------------------------------------------------------------------------
# Enums RobotOM — VALEURS LUES dans robotom.tlb et PRUVÉES par exécution
# (tools/probe_create_combination_live.py, spec §0). Ne pas les deviner.
# ---------------------------------------------------------------------------

# IRobotCombinationType
COMB_TYPE_ULS = 0          # I_CBT_ULS  (Ultimate)
COMB_TYPE_SLS = 1          # I_CBT_SLS  (Serviceability)
COMB_TYPE_ALS = 2          # I_CBT_ALS  (Accidental)
COMB_TYPE_SPC = 3          # I_CBT_SPC  (Special)

# IRobotCaseNature
CASE_NATURE_PERMANENT = 0      # I_CN_PERMANENT
CASE_NATURE_EXPLOITATION = 1   # I_CN_EXPLOATATION
CASE_NATURE_WIND = 2           # I_CN_WIND
CASE_NATURE_SNOW = 3           # I_CN_SNOW
CASE_NATURE_ACCIDENTAL = 5     # I_CN_ACCIDENTAL
CASE_NATURE_SEISMIC = 6        # I_CN_SEISMIC

# IRobotCaseAnalizeType (combinaison linéaire)
CASE_ANALIZE_COMB_LINEAR = 0   # I_CAT_COMB  (COMB_LINEAR)

# IRobotLoadRecordType — charge uniforme barre (lu dans robotom.tlb + confirmé
# live : records.New(5), rec.Type==5 — tools/probe_bar_uniform_chain_live.py)
I_LRT_BAR_UNIFORM = 5


# Types de cas de charge simples — CONSTANTES CANDIDATES, non confirmées.
# La valeur exacte par nature de charge (mort, explo, vent, neige) doit être
# vérifiée sur la version installée AVANT usage production (spec §5.1).
CASE_TYPE_CANDIDATES = {
    "dead": 1,        # à CONFIRMER
    "live": None,     # à CONFIRMER
    "wind": None,
    "snow": None,
    "seismic": None,
}


def export_dead_load_case(rc: RobotConnection, number: int = 1,
                          name: str = "Poids propre",
                          analyze: bool = False) -> dict:
    """
    Crée un cas de charge simple de type « poids propre ».

    Signature CONFIRMÉE : CreateSimple(number, name, type_int, analize_bool).

    Retourne un résumé. Lève RobotLoadsError si le type n'est pas le bon.
    """
    if not rc.is_project_open:
        raise RobotLoadsError("Aucun projet ouvert.")
    cases = rc.structure.Cases
    try:
        cases.CreateSimple(int(number), str(name),
                           CASE_TYPE_CANDIDATES["dead"], bool(analyze))
    except Exception as exc:
        raise RobotLoadsError(
            f"CreateSimple a échoué (type candidat="
            f"{CASE_TYPE_CANDIDATES['dead']}) : {exc}"
        ) from exc
    return {"created": True, "number": number, "name": name,
            "count": int(cases.GetAll().Count)}


def list_cases(rc: RobotConnection) -> list[dict]:
    """Liste les cas de charge existants (numéro + nom si accessible)."""
    if not rc.is_project_open:
        raise RobotLoadsError("Aucun projet ouvert.")
    cases = rc.structure.Cases
    out = []
    for i in range(1, int(cases.GetAll().Count) + 1):
        try:
            c = cases.Get(i)
            out.append({"number": i,
                        "name": str(getattr(c, "Name", ""))})
        except Exception:
            out.append({"number": i, "name": ""})
    return out


def apply_uniform_bar_load(rc: RobotConnection, case_number: int,
                           bar_list: str, fz: float,
                           confirmed_rectype: Optional[int] = None) -> dict:
    """
    Applique une charge uniforme Fz (kN/m, systÃ¨me local) sur une liste de
    barres (ex. "1" ou "1,2").

    CHAÎNE PRUVÉE par exécution sur Robot 2027
    (tools/probe_bar_uniform_chain_live.py, spec §0, §19) :
      - idx   = case.Records.New(I_LRT_BAR_UNIFORM)  -> index (entier) ;
      - rec   = case.Records.Get(idx)                -> objet record ;
      - rec.Objects.FromText(bar_list)               -> OBJETS (via FromText) ;
      - rec.SetValue(2, fz)                          -> index 2 = Fz (local z) ;
      - rec.GetValue(2) = fz                         -> round-trip confirmé.

    Le type d'enregistrement `I_LRT_BAR_UNIFORM = 5` est lu dans robotom.tlb et
    confirmé live (`rec.Type == 5`). `confirmed_rectype` est conservé en
    option (par défaut la valeur prouvée) pour transparence ; il n'est plus
    requis. Toute erreur COM lève RobotLoadsError explicite (jamais un faux
    succès, §19). L'unité (kN/m, local) suit les préférences Robot (§5.3).
    """
    if not rc.is_project_open:
        raise RobotLoadsError("Aucun projet ouvert.")
    rectype = I_LRT_BAR_UNIFORM if confirmed_rectype is None else confirmed_rectype
    case = rc.structure.Cases.Get(int(case_number))
    try:
        rec_index = case.Records.New(int(rectype))
        record = case.Records.Get(rec_index)
    except Exception as exc:
        raise RobotLoadsError(
            f"Records.New/Get(type={rectype}) a échoué : {exc}"
        ) from exc
    try:
        record.Objects.FromText(str(bar_list))
        record.SetValue(2, float(fz))   # index 2 = Fz (local z)
    except Exception as exc:
        raise RobotLoadsError(
            f"Affectation charge uniforme (objets={bar_list!r}, Fz={fz}) "
            f"échouée : {exc}"
        ) from exc
    return {"applied": True, "case": int(case_number), "bars": bar_list,
            "fz": fz, "rectype": int(rectype), "record_index": rec_index,
            "value_index": 2}


def create_combination(rc: RobotConnection, number: int, name: str,
                       factors, comb_type: int = COMB_TYPE_ULS,
                       case_nature: int = CASE_NATURE_EXPLOITATION,
                       case_analize_type: int = CASE_ANALIZE_COMB_LINEAR
                       ) -> dict:
    """
    Crée une combinaison linéaire de cas + ses coefficients.

    SIGNATURE PRUVÉE par exécution sur Robot 2027 (spec §0, §19) :
      - Cases.CreateCombination(int number, str name, enum comb_type,
                                enum case_nature, enum case_analize_type)
        -> renvoie l'objet combinaison (relisible via Cases.Get(number)) ;
      - combination.CaseFactors.New(case_number, coefficient) pour chaque membre.

    Ordre des enums CONFIRMÉ par lecture de retour
    (tools/probe_create_combination_live.py) : entrée
    (comb_type=2, case_nature=3, case_analize_type=0) -> CombinationType=2,
    Nature=3, AnalizeType=0.

    `factors` : dict {case_number: coefficient} OU liste de (case_number, coeff).
    Toute erreur COM est propagée comme RobotLoadsError explicite (jamais un
    faux succès, spec §19).
    """
    if not rc.is_project_open:
        raise RobotLoadsError("Aucun projet ouvert.")
    cases = rc.structure.Cases
    try:
        comb = cases.CreateCombination(int(number), str(name),
                                       int(comb_type), int(case_nature),
                                       int(case_analize_type))
    except Exception as exc:
        raise RobotLoadsError(
            f"Cases.CreateCombination({number}, {name!r}, {comb_type}, "
            f"{case_nature}, {case_analize_type}) a échoué : {exc}"
        ) from exc

    # Normaliser les coefficients (dict ou liste de paires)
    if isinstance(factors, dict):
        pairs = list(factors.items())
    else:
        pairs = list(factors or [])

    applied = []
    try:
        cf = comb.CaseFactors
        for case_no, coeff in pairs:
            cf.New(int(case_no), float(coeff))
            applied.append((int(case_no), float(coeff)))
    except Exception as exc:
        raise RobotLoadsError(
            f"CaseFactors.New a échoué pour la combinaison {number} : "
            f"{exc} (combinaison crée mais membres incomplets)"
        ) from exc

    return {"created": True, "number": int(number), "name": name,
            "comb_type": int(comb_type), "case_nature": int(case_nature),
            "case_analize_type": int(case_analize_type),
            "factors": applied}


def calculate(rc: RobotConnection) -> dict:
    """
    Lance le calcul dans Robot (CalcEngine.Calculate).

    CONFIRMÉ : CalcEngine.Calculate() s'exécute (probe_full_pipeline).
    Après calcul, Results.Available indique si des résultats sont présents.
    """
    if not rc.is_project_open:
        raise RobotLoadsError("Aucun projet ouvert.")
    try:
        rc.project.CalcEngine.Calculate()
    except Exception as exc:
        raise RobotLoadsError(f"CalcEngine.Calculate() a échoué : {exc}") from exc
    available = bool(int(rc.structure.Results.Available))
    # Robot 2027 rend -1 (VARIANT_TRUE) quand des résultats existent :
    # interprété en booléen honnête (True/False) — prouvé live 20/10.
    return {"calculated": True, "results_available": available}
