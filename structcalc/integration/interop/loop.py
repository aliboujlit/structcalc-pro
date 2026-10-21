# -*- coding: utf-8 -*-
"""
integration/interop/loop.py — Planification d'une BOUCLE de logiciels.

Demande utilisateur (v2) : « choisir les logiciels à mettre en boucle en
cochant leurs cases » ET « chaque logiciel doit accomplir les missions
dont il est conçu ».

Deux couches, toutes deux DÉLIBÉRÉMENT sans Qt/COM (logique pure testable) :

  1. BOUCLE FERMÉE (plan_loop) : les logiciels cochés forment une chaîne
     fermée (dernier maillon -> premier maillon) via le pivot SC-* :

         Conception  --aller-->  Étude  --retour-->  Conception

  2. MISSIONS (SOFTWARE_MISSIONS + mission_legs) : chaque logiciel exerce
     la mission POUR LAQUELLE IL EST CONÇU, appuyée sur ses VRAIES méthodes
     (spec §19 — aucune fonction inventée) :

       - revit       : CONCEPTION BIM  -> read_model/write_model (add-in .NET)
       - robot       : ÉTUDE           -> write_model + write_loads + read_results
       - autocad     : PLANS           -> read/write DWG (nœuds/barres/dessins)
       - civil3d     : PLANS (DWG)     -> DWG de niveau dessin (objets C3D refusés)
       - advsteel    : PLANS ACIER     -> DWG via hôte acad.exe (AstorMain5 refusé)
       - navisworks  : COORDINATION    -> open_file/save_as/convert (fichiers NWD)

L'exécution réelle (hub + méthodes connecteur) est faite par l'appelant ou
par `exchange_plan` : ici on ne planifie jamais en mentant — une boucle
< 2 logiciels est REFUSÉE avec son motif ; une mission non exécutable est
RETOURNÉE avec son motif (jamais « réussie » à vide).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence, Tuple

# ----------------------------------------------------------------------
# Logiciels disponibles (= connecteurs du hub, spec §19)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SoftwareEntry:
    """Un logiciel cochable dans la GUI (clé = nom du connecteur du hub)."""
    name: str
    label: str
    hint: str


AVAILABLE_SOFTWARE: Tuple[SoftwareEntry, ...] = (
    SoftwareEntry(
        "revit", "Revit 2027",
        "Conception BIM — accès modèle via add-in .NET (Named Pipe)"),
    SoftwareEntry(
        "robot", "Robot Structural Analysis 2027",
        "Étude / calcul — COM vérifié (modèle, charges, résultats)"),
    SoftwareEntry(
        "autocad", "AutoCAD 2027",
        "Plans — COM vérifié (DWG lecture/écriture)"),
    SoftwareEntry(
        "civil3d", "Civil 3D 2027",
        "Topographie — DWG de niveau dessin (objets intelligents refusés)"),
    SoftwareEntry(
        "navisworks", "Navisworks Manage 2027",
        "Coordination — convertisseur de fichiers NWD (COM vérifié)"),
    SoftwareEntry(
        "advsteel", "Advance Steel 2027",
        "Charpente acier — DWG via hôte acad.exe partagé"),
)

SOFTWARE_NAMES: Tuple[str, ...] = tuple(s.name for s in AVAILABLE_SOFTWARE)
LABELS: Dict[str, str] = {s.name: s.label for s in AVAILABLE_SOFTWARE}

# ----------------------------------------------------------------------
# Rôles (choix utilisateur dans la GUI)
# ----------------------------------------------------------------------

ROLE_CONCEPTION = "conception"
ROLE_ETUDE = "etude"
ROLE_BOTH = "conception+etude"

ROLES: Tuple[str, ...] = (ROLE_CONCEPTION, ROLE_ETUDE, ROLE_BOTH)

ROLE_LABELS: Dict[str, str] = {
    ROLE_CONCEPTION: "Conception",
    ROLE_ETUDE: "Étude",
    ROLE_BOTH: "Conception + Étude",
}

# ----------------------------------------------------------------------
# MISSIONS — « chaque logiciel accomplit les missions dont il est conçu »
# ----------------------------------------------------------------------
# `designed_ops` = VRAIES méthodes du connecteur (vérifiées dans le code —
# aucune fonction inventée, spec §19). `note` = périmètre honnête.

MISSION_CONCEPTION = "conception_bim"
MISSION_ETUDE = "etude_calcul"
MISSION_PLANS = "plans_dwg"
MISSION_COORDINATION = "coordination_nwd"

MISSION_LABELS: Dict[str, str] = {
    MISSION_CONCEPTION: "Conception BIM (modèle)",
    MISSION_ETUDE: "Étude structurelle (charges + calcul + résultats)",
    MISSION_PLANS: "Plans (DWG)",
    MISSION_COORDINATION: "Coordination (fichiers NWD)",
}


@dataclass(frozen=True)
class SoftwareProfile:
    """Mission conçue d'un logiciel + ses opérations réelles."""
    name: str
    mission: str                    # clé MISSION_*
    designed_ops: Tuple[str, ...]   # méthodes réelles du connecteur
    transport: str                  # voie d'accès prouvée
    note: str                       # périmètre honnête (refus inclus)


PROFILES: Dict[str, SoftwareProfile] = {
    "revit": SoftwareProfile(
        name="revit", mission=MISSION_CONCEPTION,
        designed_ops=("read_model", "write_model"),
        transport="add-in .NET (Named Pipe) / voies spec §6.2",
        note=("Mission : porter le modèle BIM de conception. Accès au "
              "modèle REFUSÉ sans add-in .NET chargé (motif explicite) — "
              "aucun faux accès prétendu.")),
    "robot": SoftwareProfile(
        name="robot", mission=MISSION_ETUDE,
        designed_ops=("write_model", "write_loads", "read_results"),
        transport="COM RobotOM (robotom.tlb, vérifié live)",
        note=("Mission : recevoir le modèle, appliquer les charges "
              "(write_loads), calculer et rapporter les résultats "
              "(read_results, unités contrôlées).")),
    "autocad": SoftwareProfile(
        name="autocad", mission=MISSION_PLANS,
        designed_ops=("read_model", "write_model"),
        transport="COM AutoCAD (vérifié live)",
        note=("Mission : produire/consulter les plans DWG (nœuds, barres, "
              "couches) — dessin de niveau géométrie.")),
    "civil3d": SoftwareProfile(
        name="civil3d", mission=MISSION_PLANS,
        designed_ops=("read_model", "write_model"),
        transport="DWG via hôte acad.exe (ProgIDs AeccX* inactivables)",
        note=("Mission : DWG topographique de niveau dessin ; les objets "
              "intelligents Civil 3D sont REFUSÉS (motif : .NET requis).")),
    "advsteel": SoftwareProfile(
        name="advsteel", mission=MISSION_PLANS,
        designed_ops=("read_model", "write_model"),
        transport="DWG via hôte acad.exe partagé",
        note=("Mission : plans charpente acier en DWG ; la sémantique "
              "AstorMain5 est REFUSÉE (coclasses non COM).")),
    "navisworks": SoftwareProfile(
        name="navisworks", mission=MISSION_COORDINATION,
        designed_ops=("open_file", "save_as", "convert"),
        transport="COM Navisworks (vérifié live DWG -> NWD)",
        note=("Mission : COORDINATION par conversion de fichiers "
              "(DWG/IFC -> NWD). Aucun accès modèle pivot : la conversion "
              "exige un chemin de fichier source (open_file/convert).")),
}


def mission_of(name: str) -> SoftwareProfile:
    """Profil de mission d'un logiciel ( KeyError si inconnu )."""
    return PROFILES[name]


def mission_legs(target: str) -> Tuple[str, ...]:
    """
    Actions de mission que le RECEVEUR doit accomplir APRÈS avoir reçu le
    modèle (transport déjà couvert par l'étape A -> pivot -> B).

    - Conception / Plans : write_model EST la mission (aucune action
      supplémentaire — le transport l'exécute déjà, honnêtement) ;
    - Étude (Robot)      : appliquer les charges + rapporter les résultats ;
    - Coordination (NW)  : conversion de fichiers (exige un chemin source).
    """
    m = PROFILES[target].mission
    if m == MISSION_ETUDE:
        return ("Appliquer les charges (write_loads)",
                "Calculer et rapporter les résultats (read_results)")
    if m == MISSION_COORDINATION:
        return ("Convertir le fichier de coordination (open_file/convert "
                "-> NWD)",)
    return ()  # conception / plans : la mission = le transport lui-même


def _phase_label(src_role: str, tgt_role: str) -> str:
    """Libellé de l'étape — jamais de jargon inventé, lecture directe."""
    def is_c(role): return role in (ROLE_CONCEPTION, ROLE_BOTH)
    def is_e(role): return role in (ROLE_ETUDE, ROLE_BOTH)
    sc, se = is_c(src_role), is_e(src_role)
    tc, te = is_c(tgt_role), is_e(tgt_role)
    if sc and te and not (se and tc):
        return "Conception -> Étude (aller)"
    if se and tc and not (sc and te):
        return "Étude -> Conception (retour)"
    if sc and tc and not (se or te):
        return "Conception (chaîne)"
    if se and te and not (sc or tc):
        return "Étude (chaîne)"
    return "Conception + Étude (boucle fermée)"


# ----------------------------------------------------------------------
# Sélection / plan
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    """Un logiciel coché avec son rôle."""
    name: str
    role: str = ROLE_BOTH


@dataclass(frozen=True)
class LoopStep:
    """Une étape de la boucle : source -> pivot -> target (+ mission cible)."""
    order: int
    source: str
    target: str
    phase: str            # libellé honnête de l'étape
    source_label: str = ""
    target_label: str = ""
    target_mission: str = ""   # mission conçue du RECEVEUR

    @property
    def sense(self) -> str:
        return f"{self.source} -> pivot -> {self.target}"

    def to_dict(self) -> dict:
        return {"order": self.order, "source": self.source,
                "target": self.target, "phase": self.phase,
                "target_mission": self.target_mission, "sense": self.sense}


@dataclass
class LoopPlan:
    """Résultat de planification. `ok=False` => `error` contient le motif."""
    ok: bool
    error: str = ""
    order: List[str] = field(default_factory=list)
    steps: List[LoopStep] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error, "order": list(self.order),
                "missing": list(self.missing),
                "steps": [s.to_dict() for s in self.steps]}


def plan_loop(selections: Sequence[Selection]) -> LoopPlan:
    """
    Construit le plan de boucle fermée à partir des logiciels cochés.

    Refus EXPLICITES (jamais de succès à vide) :
      - aucun logiciel coché ;
      - un seul logiciel (une boucle exige >= 2 maillons) ;
      - logiciel inconnu / rôle invalide ;
      - doublon.
    """
    if not selections:
        return LoopPlan(
            ok=False,
            error="Aucun logiciel coché : la boucle nécessite au moins "
                  "2 logiciels (cochez leurs cases).")

    if len(selections) == 1:
        only = LABELS.get(selections[0].name, selections[0].name)
        return LoopPlan(
            ok=False,
            error=f"Un seul logiciel coché ({only}) : une boucle nécessite "
                  "au moins 2 maillons — cochez un second logiciel.")

    unknown = [s.name for s in selections if s.name not in LABELS]
    if unknown:
        return LoopPlan(
            ok=False,
            error="Logiciel(s) inconnu(s) : " + ", ".join(unknown),
            missing=unknown)

    bad_roles = [f"{s.name}={s.role}" for s in selections
                 if s.role not in ROLES]
    if bad_roles:
        return LoopPlan(
            ok=False,
            error="Rôle invalide (attendu : " + " | ".join(ROLES) + ") : "
                  + ", ".join(bad_roles))

    names = [s.name for s in selections]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        return LoopPlan(
            ok=False,
            error="Doublon de logiciel coché : " + ", ".join(dupes))

    role_of: Dict[str, str] = {s.name: s.role for s in selections}

    # Ordre de boucle : conception d'abord (maillon de départ), puis étude.
    # L'ordre déclaré est préservé à l'intérieur de chaque groupe.
    conception_first = [s.name for s in selections
                        if s.name in PROFILES
                        and s.role in (ROLE_CONCEPTION, ROLE_BOTH)]
    etude_rest = [s.name for s in selections
                  if s.name in PROFILES
                  and s.role not in (ROLE_CONCEPTION, ROLE_BOTH)]
    order = conception_first + etude_rest

    def make_step(i: int, src: str, tgt: str) -> LoopStep:
        return LoopStep(
            order=i + 1, source=src, target=tgt,
            phase=_phase_label(role_of[src], role_of[tgt]),
            source_label=LABELS[src], target_label=LABELS[tgt],
            target_mission=MISSION_LABELS[PROFILES[tgt].mission])

    # Étapes : chaîne consécutive + retour fermant (dernier -> premier)
    steps: List[LoopStep] = [
        make_step(i, order[i], order[i + 1]) for i in range(len(order) - 1)]
    steps.append(make_step(len(order) - 1, order[-1], order[0]))

    return LoopPlan(ok=True, order=order, steps=steps)


def describe_plan(plan: LoopPlan) -> str:
    """Texte d'aperçu du plan (affiché dans la GUI avant exécution)."""
    if not plan.ok:
        return f"Boucle impossible : {plan.error}"
    lines = [f"Boucle fermée — {len(plan.order)} logiciels, "
             f"{len(plan.steps)} échanges réciproques (via pivot SC-*) :"]
    for st in plan.steps:
        lines.append(f"  {st.order}. {st.source_label} -> {st.target_label}"
                     f"   [{st.phase}]")
        legs = mission_legs(st.target)
        if legs:
            for leg in legs:
                lines.append(f"       + mission {st.target_label} : {leg}")
    lines.append("  (Dernière étape = retour : la boucle se referme sur le "
                 "premier logiciel.)")
    lines.append("Missions de chaque maillon (« chacun fait ce pour quoi il "
                 "est conçu ») :")
    for name in plan.order:
        prof = PROFILES[name]
        lines.append(f"  - {LABELS[name]} : {MISSION_LABELS[prof.mission]} "
                     f"[{', '.join(prof.designed_ops)}]")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Exécution (hub réel + missions des connecteurs)
# ----------------------------------------------------------------------


def _mission_rows(hub, target: str, project: Any,
                  transport_ok: bool, transport_msg: str,
                  order: int) -> List[dict]:
    """
    Exécute la MISSION du receveur après l'étape de transport.

    N'utilise QUE les méthodes réelles du connecteur (PROFILES.designed_ops).
    Un refus/échec est retourné tel quel (motif d'origine conservé).
    """
    prof = PROFILES[target]
    rows: List[dict] = []
    mlabel = MISSION_LABELS[prof.mission]

    def row(action: str, ok: bool, msg: str) -> dict:
        return {"order": order, "source": target, "target": target,
                "phase": f"Mission {mlabel}", "action": action,
                "success": ok, "message": msg, "step_failed": ""}

    if prof.mission == MISSION_ETUDE:
        # Robot : charges puis résultats — méthodes COM prouvées (Phase 2)
        if not transport_ok:
            rows.append(row(
                "write_loads + read_results", False,
                f"Mission non exécutée : le transport du modèle vers "
                f"{LABELS[target]} a échoué/refusé ({transport_msg})."))
            return rows
        conn = hub.get(target)
        try:
            r_loads = conn.write_loads(project)
            rows.append(row(
                "write_loads", bool(r_loads.ok),
                f"Charges appliquées via {prof.transport}"
                if r_loads.ok else
                f"write_loads refusé/échoué ({r_loads.status}) : "
                f"{r_loads.message}"))
        except Exception as exc:
            rows.append(row("write_loads", False,
                            f"write_loads en échec : {exc}"))
        try:
            r_res = conn.read_results(project)
            rows.append(row(
                "read_results", bool(r_res.ok),
                "Résultats rapportés (unités contrôlées)"
                if r_res.ok else
                f"read_results refusé/échoué ({r_res.status}) : "
                f"{r_res.message}"))
        except Exception as exc:
            rows.append(row("read_results", False,
                            f"read_results en échec : {exc}"))
        return rows

    if prof.mission == MISSION_COORDINATION:
        # Navisworks : convertisseur de fichiers RÉEL (OpenFile -> SaveAs
        # NWD — chaîne VÉRIFIÉE live, DWG -> NWD). La conversion exige un
        # chemin source : le pivot porte `source_file` (fichier d'origine,
        # ex. plan DWG). Sans fichier réel : REFUS motivé (spec §6 — aucun
        # chemin inventé).
        src = str(getattr(project, "source_file", "") or "")
        if not src or not os.path.isfile(src):
            rows.append(row(
                "open_file/convert -> NWD", False,
                "Mission coordination : aucun fichier source RÉEL porté par "
                "le pivot (`source_file` vide ou introuvable) — conversion "
                "NWD refusée (aucun chemin inventé, spec §6). Renseignez "
                "project.source_file (ex. plan DWG) pour activer la "
                "conversion."))
            return rows
        conn = hub.get("navisworks")
        try:
            conn.connect()          # attache Roamer (visible si lancement)
        except Exception as exc:
            rows.append(row("open_file/convert -> NWD", False,
                            f"Connexion Navisworks impossible : {exc}"))
            return rows
        target_nwd = os.path.splitext(src)[0] + ".nwd"
        try:
            r_conv = conn.convert(src, target_nwd)
            rows.append(row(
                "open_file/convert -> NWD", bool(r_conv.ok),
                f"{os.path.basename(src)} -> {os.path.basename(target_nwd)} : "
                + (r_conv.message or r_conv.status)))
        except Exception as exc:
            rows.append(row("open_file/convert -> NWD", False,
                            f"convert en échec : {exc}"))
        return rows

    # Conception BIM / Plans DWG : la mission EST l'étape de transport
    # (write_model du receveur) — on la qualifie honnêtement.
    if transport_ok:
        rows.append(row(
            "write_model", True,
            f"Mission accomplie par l'étape de transport : modèle poussé "
            f"dans {LABELS[target]} ({prof.transport}). {prof.note}"))
    else:
        rows.append(row(
            "write_model", False,
            f"Mission bloquée : le transport vers {LABELS[target]} a "
            f"échoué/refusé ({transport_msg}). {prof.note}"))
    return rows


def exchange_plan(plan: LoopPlan, project: Any,
                  connect: bool = True, hub: Any = None) -> List[dict]:
    """
    Exécute le plan via le hub et accomplit les MISSIONS de chaque maillon.

    Pour chaque étape A -> B :
      1. transport du modèle (hub.exchange : A.read_model -> B.write_model) ;
      2. mission du RECEVEUR B (PROFILES) avec ses VRAIES méthodes :
         - Étude (Robot) : write_loads puis read_results ;
         - Plans/Conception : write_model EST la mission (qualifiée) ;
         - Coordination (Navisworks) : CONVERTISSEUR DE FICHIERS (DWG -> NWD),
           PAS un nœud pivot. Exige un DWG source réel.

    `hub` : hub OPTIONNEL. Permet de réutiliser la session qui a ouvert le
    modèle source (ex. le .rtd ouvert par le connecteur Robot du hub —
    `opened_by_us=True` -> Robot accepte alors lecture ET écriture dans CE
    projet, fermé sans sauvegarde ensuite, §5.4). Sans hub, un hub neuf est
    créé (comportement historique).

    HONNÊTETÉ : chaque ligne renvoie `success` + `message` ISSUS du hub ou
    des OpReports des connecteurs ; un refus s'affiche tel quel, jamais
    reformulé en succès.
    """
    if hub is None:
        from . import default_hub  # import paresseux (COM jamais au démarrage)
        hub = default_hub()

    if not plan.ok:
        return [{"order": 0, "source": "", "target": "", "phase": "",
                 "success": False, "message": f"Plan invalide : {plan.error}"}]

    out: List[dict] = []
    for st in plan.steps:
        # --- CAS SPÉCIAL : Navisworks comme cible (convertisseur fichiers) ---
        if st.target == "navisworks":
            # Navisworks n'est PAS un nœud pivot : il consomme un FICHIER DWG
            # produit par le maillon source (autocad/civil3d/revit via DWG).
            # On exporte le pivot vers un DWG temporaire, puis on convertit.
            out.extend(_exchange_to_navisworks(
                hub, st, project, connect))
            continue

        # --- CAS GÉNÉRAL : échange pivot standard (A.read -> B.write) ---
        # Navisworks ne doit JAMAIS être source (pas de read_model pivot).
        if st.source == "navisworks":
            out.append({
                "order": st.order, "source": st.source, "target": st.target,
                "phase": st.phase, "action": "Transport modèle",
                "success": False,
                "message": ("Navisworks ne peut pas être source d'un échange pivot "
                            "(READ_MODEL non supporté) — étape ignorée."),
                "step_failed": "read"})
            continue

        try:
            res = hub.exchange(st.source, st.target, project,
                               connect=connect)
            ok, msg = bool(res.success), res.message
            failed = res.step_failed
        except Exception as exc:
            ok, msg, failed = False, f"ERREUR MOTEUR D'ÉCHANGE : {exc}", "read"
        out.append({
            "order": st.order,
            "source": st.source,
            "target": st.target,
            "phase": st.phase,
            "action": "Transport modèle (read_model -> write_model)",
            "success": ok,
            "message": msg,
            "step_failed": failed,
        })
        # Mission propre du receveur — « chacun fait ce pour quoi il est conçu »
        try:
            out.extend(_mission_rows(hub, st.target, project, ok, msg,
                                     st.order))
        except Exception as exc:  # jamais de crash muet
            out.append({
                "order": st.order, "source": st.target, "target": st.target,
                "phase": f"Mission {MISSION_LABELS[PROFILES[st.target].mission]}",
                "action": "mission", "success": False,
                "message": f"ERREUR MISSION : {exc}", "step_failed": "mission"})
    return out


def _exchange_to_navisworks(hub, st, project: Any,
                            connect: bool) -> List[dict]:
    """
    Échange spécial vers Navisworks : convertisseur de FICHIERS (DWG -> NWD).

    1. Produit un DWG depuis le maillon source (autocad/civil3d/revit)
       en écrivant le pivot dans un DWG temporaire.
    2. Appelle navisworks.convert(dwg_path, nwd_path).
    3. Signale le NWD comme livrable.
    """
    import tempfile
    import os

    out = []
    order = st.order
    source_name = st.source
    target_name = "navisworks"
    phase = st.phase

    # 1. Choisir un exportateur DWG selon le maillon source
    # Seuls les connecteurs capables d'écrire un VRAI DWG (COM AutoCAD vérifié)
    dwg_exporters = ["autocad", "civil3d", "advsteel"]
    exporter_name = None
    if source_name in dwg_exporters:
        exporter_name = source_name
    elif "autocad" in hub.names:
        exporter_name = "autocad"  # fallback vers AutoCAD (toujours dispo)
    elif "civil3d" in hub.names:
        exporter_name = "civil3d"
    else:
        out.append({
            "order": order, "source": source_name, "target": target_name,
            "phase": phase, "action": "Export DWG pour Navisworks",
            "success": False,
            "message": (f"Aucun exportateur DWG disponible pour {source_name} "
                        f"(dispo : {', '.join(dwg_exporters)})"),
            "step_failed": "write"})
        return out

    # 2. Fichier DWG temporaire
    with tempfile.NamedTemporaryFile(suffix=".dwg", delete=False) as tmp:
        dwg_path = tmp.name
    nwd_path = os.path.splitext(dwg_path)[0] + ".nwd"

    try:
        # 2a. Connecter l'exportateur DWG
        exporter = hub.get(exporter_name)
        if connect and not exporter.connected:
            try:
                exporter.connect()
            except Exception as exc:
                out.append({
                    "order": order, "source": source_name, "target": target_name,
                    "phase": phase, "action": f"Connexion {LABELS[exporter_name]}",
                    "success": False,
                    "message": f"Connexion {exporter_name} échouée : {exc}",
                    "step_failed": "connect"})
                return out

        # 2b. Écrire le pivot dans le DWG temporaire (write_model)
        # Le connecteur AutoCAD/Civil3D/AdvSteel écrit dans son document actif.
        # On utilise write_model avec out_path pour SaveAs.
        # NOTE : L'API actuelle n'a pas out_path sur write_model.
        # On écrit dans le document actif, puis SaveAs via l'exportateur.
        # L'exportateur AutoCAD a _last_doc et save_document.
        try:
            rep_write = exporter.write_model(project)
            if not rep_write.ok:
                out.append({
                    "order": order, "source": source_name, "target": target_name,
                    "phase": phase, "action": f"Export DWG ({exporter_name})",
                    "success": False,
                    "message": f"write_model {exporter_name} refusé : {rep_write.message}",
                    "step_failed": "write"})
                return out
            # SaveAs le document actif vers dwg_path
            if hasattr(exporter, "_last_doc") and exporter._last_doc:
                exporter.save_document(exporter._last_doc, dwg_path)
            else:
                out.append({
                    "order": order, "source": source_name, "target": target_name,
                    "phase": phase, "action": f"Export DWG ({exporter_name})",
                    "success": False,
                    "message": "Aucun document actif après write_model — SaveAs impossible",
                    "step_failed": "write"})
                return out
        except Exception as exc:
            out.append({
                "order": order, "source": source_name, "target": target_name,
                "phase": phase, "action": f"Export DWG ({exporter_name})",
                "success": False,
                "message": f"Export DWG échoué : {exc}",
                "step_failed": "write"})
            return out

        # 3. Convertir DWG -> NWD via Navisworks
        out.append({
            "order": order, "source": source_name, "target": target_name,
            "phase": phase, "action": f"Export DWG ({LABELS[exporter_name]})",
            "success": True,
            "message": f"Modèle exporté vers {os.path.basename(dwg_path)}",
            "step_failed": ""})

        nw = hub.get("navisworks")
        try:
            if connect and not nw.connected:
                nw.connect()
        except Exception as exc:
            out.append({
                "order": order, "source": source_name, "target": target_name,
                "phase": phase, "action": "Connexion Navisworks",
                "success": False,
                "message": f"Connexion Navisworks échouée : {exc}",
                "step_failed": "connect"})
            return out

        try:
            rep_conv = nw.convert(dwg_path, nwd_path)
            ok = rep_conv.ok
            msg = rep_conv.message or rep_conv.status
        except Exception as exc:
            ok, msg = False, f"convert Navisworks échoué : {exc}"

        out.append({
            "order": order, "source": source_name, "target": target_name,
            "phase": phase, "action": "Convert DWG -> NWD (Navisworks)",
            "success": ok,
            "message": (f"{os.path.basename(dwg_path)} -> "
                        f"{os.path.basename(nwd_path)} : {msg}"),
            "step_failed": "" if ok else "write"})

        # 4. Mission coordination (livrable NWD)
        if ok:
            out.append({
                "order": order, "source": target_name, "target": target_name,
                "phase": f"Mission {MISSION_LABELS[PROFILES[target_name].mission]}",
                "action": "Livrable coordination NWD",
                "success": True,
                "message": f"Fichier de coordination produit : {nwd_path}",
                "step_failed": ""})
        else:
            out.append({
                "order": order, "source": target_name, "target": target_name,
                "phase": f"Mission {MISSION_LABELS[PROFILES[target_name].mission]}",
                "action": "Livrable coordination NWD",
                "success": False,
                "message": f"Échec conversion : {msg}",
                "step_failed": "mission"})

    finally:
        # Nettoyage DWG temporaire (on garde le NWD comme livrable)
        try:
            if os.path.exists(dwg_path):
                os.remove(dwg_path)
        except Exception:
            pass

    return out
