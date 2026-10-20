# -*- coding: utf-8 -*-
"""
integration/interop/combinaisons.py — Combinaisons, démarches et cas
d'industrie entre les logiciels Autodesk de STRUCTCALC PRO.

Demande utilisateur : « quelles sont toutes les combinaisons et démarches
possibles à produire entre les logiciels, avec les cas possibles dans cette
industrie de bureau des études et technologies ? »

Ce module inventorie TOUT, sans Qt/COM (logique pure testable) :

  1. PAIRES (combinaisons) : les 6x5 = 30 sens diriges A -> B (15 paires
     réciproques) — pour chacun : CE qui circule (mission de la source),
     CE QUE LA CIBLE en fait (sa mission conçue) et la DEMARCHE bureau
     d'études correspondante. La faisabilité RÉELLE reste évaluée par le
     hub (capacités vérifiées, refus motivé) — jamais prétendue ici.

  2. DEMARCHES (workflows) : chaînes ordonnées de logiciels réalisant un
     processus complet de bureau d'études (ex. : conception -> étude ->
     plans -> coordination). Chaque démarche expose ses jambages (legs)
     pour évaluation honnête par le hub.

  3. CAS D'INDUSTRIE : typologies de projets réels (bâtiment, charpente,
     site/VRD, coordination...) reliant logiciels + démarches.

Règles §19/§20 : aucune liaison n'est présentée comme disponible sans le
dire ; la faisabilité affichée vient des capacités vérifiées des
connecteurs (refus motivés inclus).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .loop import (
    AVAILABLE_SOFTWARE, SOFTWARE_NAMES, LABELS, PROFILES, MISSION_LABELS,
    mission_of,
)

# ----------------------------------------------------------------------
# Ce que CHAQUE logiciel fournit / accueille (missions conçues)
# ----------------------------------------------------------------------

#: Ce que la source MET DANS LE PIVOT (sa sortie métier).
PROVIDES: Dict[str, str] = {
    "revit": "le modèle BIM de conception (nœuds, barres, sections, "
             "matériaux, appuis)",
    "robot": "le modèle d'étude + les charges + les résultats calculés "
             "(N, M, réactions, flèches, unités contrôlées)",
    "autocad": "le dessin DWG (génération de plans depuis le modèle : "
               "couches, géométrie, annotations)",
    "civil3d": "le fond topographique / VRD en DWG (lignes de niveau, "
               "axes, terrain)",
    "advsteel": "les plans de charpente acier en DWG (profils, assemblages, "
                "détails d'atelier)",
    "navisworks": "le fichier de coordination NWD (maquette agrégée de "
                  "tous les corps de métier)",
}

#: Ce que la cible FAIT de ce qu'elle reçoit (sa mission conçue).
CONSUMES: Dict[str, str] = {
    "revit": "l'intègre au modèle BIM (mise à jour des sections/appuis) — "
             "mission Conception BIM via add-in .NET",
    "robot": "l'importe comme modèle d'étude, applique les charges "
             "(`write_loads`) et rapporte les résultats (`read_results`) — "
             "mission Étude structurelle",
    "autocad": "le dessine en plan DWG (couches, mise en page) — "
               "mission Plans",
    "civil3d": "le reporte sur le fond topographique (implantation, axes) — "
               "mission Plans / site",
    "advsteel": "le détaille en plan d'atelier acier — mission Plans acier",
    "navisworks": "l'agrège en maquette NWD pour la coordination et la "
                  "détection de conflits — mission Coordination (fichier)",
}


@dataclass(frozen=True)
class PairUse:
    """Une combinaison A -> B : ce qui circule, l'usage, la démarche."""
    source: str
    target: str
    transfer: str          # ce que la source fournit
    target_action: str     # ce que la cible en fait (mission conçue)
    use_case: str          # démarche de bureau d'études

    @property
    def key(self) -> Tuple[str, str]:
        return (self.source, self.target)

    @property
    def label(self) -> str:
        return f"{LABELS[self.source]} -> {LABELS[self.target]}"

    @property
    def sense(self) -> str:
        return f"{self.source} -> pivot -> {self.target}"

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target,
                "transfer": self.transfer, "target_action": self.target_action,
                "use_case": self.use_case}


# Démarches bureau d'études par CIBLE (ce qu'on en fait concrètement)
_USE_CASE_BY_TARGET: Dict[str, str] = {
    "robot": ("Étude de calcul : vérification résistance/flèches/second "
              "ordre (BAEL/RPS) du modèle transmis"),
    "autocad": ("Production des plans (coffrage, coffres, récolement, plans "
                "de fondation) à partir du modèle étudié"),
    "revit": ("Retour d'étude vers le BIM : sections optimisées, appuis et "
              "observations d'ingénieur intégrés au modèle"),
    "civil3d": ("Implantation : poser les axes et fondations sur le fond "
                "topographique/VRD du site"),
    "advsteel": ("Détail d'atelier : profils, coupes, assemblages et nomenclature "
                 "acier à partir du modèle étudié"),
    "navisworks": ("Coordination pluridisciplinaire : agrégation NWD et "
                   "détection de conflits (métrés, chevauchements)"),
}


def all_pairs() -> List[PairUse]:
    """Les 30 combinaisons diriges A -> B (A != B) — enumeration complete."""
    out: List[PairUse] = []
    for src in SOFTWARE_NAMES:
        for tgt in SOFTWARE_NAMES:
            if src == tgt:
                continue
            out.append(PairUse(
                source=src, target=tgt,
                transfer=PROVIDES[src],
                target_action=CONSUMES[tgt],
                use_case=_USE_CASE_BY_TARGET[tgt]))
    return out


def pair_use(source: str, target: str) -> PairUse:
    """Combinaison dirigee (KeyError si logiciel inconnu)."""
    for p in all_pairs():
        if p.source == source and p.target == target:
            return p
    raise KeyError(f"combinaison inconnue : {source} -> {target}")


def reciprocal_pairs_count() -> int:
    """15 paires réciproques (30 sens / 2)."""
    n = len(SOFTWARE_NAMES)
    return n * (n - 1) // 2


# ----------------------------------------------------------------------
# DEMARCHES (workflows de bureau d'études)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Workflow:
    """Une démarche complète : chaîne ordonnée de logiciels."""
    key: str
    name: str
    chain: Tuple[str, ...]       # ordre d'exécution des maillons
    objective: str               # but du processus
    industry_case: str           # typologie de projet
    loop: bool = True            # True = boucle fermée (retour au 1er)
    notes: str = ""

    @property
    def chain_labels(self) -> str:
        sep = " -> "
        labels = [LABELS[n] for n in self.chain]
        # Ferme la chaine seulement si elle n'est pas deja refermee
        if self.loop and len(self.chain) > 1 \
                and self.chain[-1] != self.chain[0]:
            labels.append(labels[0])
        return sep.join(labels)

    @property
    def legs(self) -> List[Tuple[str, str]]:
        """Jambages (source, cible) dans l'ordre, boucle fermée si loop.
        Une chaine deja refermee (fin == debut) n'est pas refermee 2 fois."""
        seq = list(self.chain)
        if self.loop and len(seq) > 1 and seq[-1] != seq[0]:
            seq = seq + [seq[0]]
        return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "chain": list(self.chain),
                "objective": self.objective, "industry_case": self.industry_case,
                "loop": self.loop, "chain_labels": self.chain_labels,
                "legs": [list(l) for l in self.legs], "notes": self.notes}


WORKFLOWS: Tuple[Workflow, ...] = (
    Workflow(
        key="bati_complet",
        name="Bâtiment complet — conception → étude → plans → retour",
        chain=("revit", "robot", "autocad", "revit"),
        objective=("Cycle classique du bureau d'études structure BRISE : "
                   "modèle BIM -> calcul -> plans -> retours d'étude dans "
                   "le BIM."),
        industry_case="Bâtiment (logements, tertiaire, équipements)",
        notes=("Revit exige l'add-in .NET pour l'accès modèle ; add-in "
               "compilé/déployé (PIPE structcalc_revit prouvé live) ; sans "
               "lui, les jambages Revit sont refusés avec motif.")),
    Workflow(
        key="etude_sans_bim",
        name="Étude sans BIM — dessin → calcul → plans",
        chain=("autocad", "robot", "autocad"),
        objective=("Processus historique des bureaux d'études : plan DWG "
                   "existant -> modèle de calcul -> plans corrigés "
                   "(câblage AutoCAD<->Robot prouvé live)."),
        industry_case="Bâtiment existant / réhabilitation / concours",
        notes="Paire réciproque AUTO<->ROBOT prouvée par tests live."),
    Workflow(
        key="charpente_acier",
        name="Charpente acier — détail d'atelier ↔ calcul",
        chain=("advsteel", "robot", "advsteel"),
        objective=("Hangar, plancher acier, passarelles : dessin d'atelier "
                   "Advance Steel -> vérification de calcul Robot -> "
                   "plans d'atelier corrigés."),
        industry_case="Charpente métallique / industriel",
        notes=("Advance Steel = DWG via hôte acad.exe partagé ; sémantique "
               "AstorMain5 refusée (non COM) — le transfert passe en DWG.")),
    Workflow(
        key="site_vrd",
        name="Site & VRD — topographie → implantation → plans",
        chain=("civil3d", "revit", "robot", "autocad"),
        objective=("Fond topographique Civil 3D -> positionnement des "
                   "fondations dans le BIM -> étude -> plans d'implantation."),
        industry_case="Lotissements, réseux, ouvrages de terrassement",
        loop=False,
        notes=("Civil 3D : DWG de niveau dessin (objets intelligents C3D "
               "refusés hors .NET) ; Revit : add-in .NET livré et prouvé "
               "(pipe structcalc_revit).")),
    Workflow(
        key="coordination_bim",
        name="Coordination BIM — maquettes → NWD → retour conflits",
        chain=("revit", "autocad", "navisworks", "revit"),
        objective=("Coordination pluridisciplinaire : agréger maquette BIM "
                   "et plans en NWD (Navisworks convertit les fichiers), "
                   "traiter les conflits et rejeter les corrections au BIM."),
        industry_case="Grand projet, coordination de corps d'état multiples",
        notes=("Navisworks est un convertisseur de FICHIERS (open_file/"
               "convert, prouvé live DWG->NWD) : son jambage s'exécute avec "
               "un chemin de fichier source, sinon refus motivé.")),
    Workflow(
        key="acier_complet",
        name="Charpente complète — BIM → calcul → détail acier",
        chain=("revit", "robot", "advsteel", "revit"),
        objective=("Structure métallique modélisée en BIM, étudiée sous "
                   "BAEL, détaillée en atelier puis retours de montage."),
        industry_case="Charpente métallique de bâtiment",
        notes="Add-in Revit .NET requis pour le maillon BIM."),
    Workflow(
        key="boucle_complete",
        name="Boucle industrielle complète — les 6 logiciels en réseau",
        chain=("revit", "civil3d", "robot", "advsteel", "autocad",
               "navisworks"),
        objective=("Réseau réciproque total : tous les logiciels "
                   "cochés tournent en boucle fermée via le pivot SC-*, "
                   "chacun accomplissant sa mission conçue "
                   "(retour auto sur le premier maillon)."),
        industry_case="Toute typologie (orchestration complète)",
        notes="30 sens diriges disponibles ; la boucle n'en utilise qu'une "
              "chaîne ordonnée + retour."),
)

WORKFLOW_KEYS: Tuple[str, ...] = tuple(w.key for w in WORKFLOWS)


def workflow(key: str) -> Workflow:
    for w in WORKFLOWS:
        if w.key == key:
            return w
    raise KeyError(f"démarche inconnue : {key!r} (connues : {WORKFLOW_KEYS})")


# ----------------------------------------------------------------------
# CAS D'INDUSTRIE (typologies de bureau d'études)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class IndustryCase:
    """Typologie de projet : logiciels mobilisés + démarches + réalités."""
    key: str
    name: str
    software: Tuple[str, ...]        # logiciels mobilisés
    workflows: Tuple[str, ...]       # clés WORKFLOWS utilisées
    deliverables: Tuple[str, ...]    # livrables du bureau d'études
    reality: str                     # état honnête des liens

    @property
    def software_labels(self) -> str:
        return " + ".join(LABELS[s] for s in self.software)

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name,
                "software": list(self.software),
                "workflows": list(self.workflows),
                "deliverables": list(self.deliverables),
                "reality": self.reality}


INDUSTRY_CASES: Tuple[IndustryCase, ...] = (
    IndustryCase(
        key="bati",
        name="Bâtiment (BRISE / logements / tertiaire)",
        software=("revit", "robot", "autocad", "navisworks"),
        workflows=("bati_complet", "etude_sans_bim", "coordination_bim"),
        deliverables=("Note de calcul BAEL", "Plans de coffrage",
                      "Fiches de poteaux", "Maquette NWD coordonnée"),
        reality=("AutoCAD<->Robot prouvé live ; Revit via add-in .NET "
                 "compilé et déployé (PING + roundtrip pipe prouvés live) ; "
                 "Navisworks conversion de fichiers prouvée live.")),
    IndustryCase(
        key="rehabilitation",
        name="Réhabilitation / diagnostic sur plans existants",
        software=("autocad", "robot"),
        workflows=("etude_sans_bim",),
        deliverables=("Plan de situation coté", "Étude de reprise en élévation",
                      "Rapport de conformité BAEL"),
        reality="Paire AutoCAD<->Robot réciproque et prouvée live."),
    IndustryCase(
        key="charpente",
        name="Charpente métallique / hangar industriel",
        software=("advsteel", "robot", "autocad"),
        workflows=("charpente_acier", "acier_complet"),
        deliverables=("Plans d'atelier", "Nomenclature d'acier",
                      "Note de calcul BAEL 3 (acier)"),
        reality=("Advance Steel en DWG via hôte partagé (AstorMain5 refusé "
                 "motivé) ; Robot = étude prouvée live.")),
    IndustryCase(
        key="site_vrd",
        name="Site, VRD & ouvrages de terrassement",
        software=("civil3d", "autocad", "robot"),
        workflows=("site_vrd",),
        deliverables=("Plan topographique", "Plan d'implantation",
                      "Calcul des ouvrages de soutènement"),
        reality=("Civil 3D en DWG de niveau dessin (objets intelligents "
                 "refusés motivé hors .NET) ; calcul = Robot.")),
    IndustryCase(
        key="coordination",
        name="Coordination pluridisciplinaire (grand projet)",
        software=("revit", "autocad", "civil3d", "navisworks"),
        workflows=("coordination_bim", "bati_complet"),
        deliverables=("Maquette de coordination NWD",
                      "Registre de conflits", "Comptes rendus de réunion"),
        reality=("Navisworks = convertisseur NWD prouvé live ; conflits = "
                 "fichiers, jamais inventés ; Revit via add-in .NET.")),
    IndustryCase(
        key="ingenierie_complete",
        name="Bureau d'études intégré (orchestration complète)",
        software=tuple(SOFTWARE_NAMES),
        workflows=("boucle_complete", "bati_complet", "charpente_acier",
                   "site_vrd"),
        deliverables=("Dossier de calcul complet", "Tous plans",
                      "Maquette coordonnée", "Synthèse des vérifications"),
        reality=("Tous liens équipés d'un motif honnête : prouvés (AutoCAD,"
                 " Robot, Navisworks), add-in compilé/déployé et prouvé live"
                 " (Revit), DWG (Civil 3D, Advance Steel).")),
)

CASE_KEYS: Tuple[str, ...] = tuple(c.key for c in INDUSTRY_CASES)


def industry_case(key: str) -> IndustryCase:
    for c in INDUSTRY_CASES:
        if c.key == key:
            return c
    raise KeyError(f"cas industrie inconnu : {key!r} (connus : {CASE_KEYS})")


# ----------------------------------------------------------------------
# Evaluation honnete (faite par l'appelant avec le hub)
# ----------------------------------------------------------------------


@dataclass
class ComboInventory:
    """Inventaire complet pour affichage GUI / documentation."""
    pairs: List[PairUse] = field(default_factory=list)
    workflows: List[Workflow] = field(default_factory=list)
    cases: List[IndustryCase] = field(default_factory=list)

    @property
    def n_senses(self) -> int:
        return len(self.pairs)

    @property
    def n_reciprocal(self) -> int:
        return reciprocal_pairs_count()


def inventory() -> ComboInventory:
    """Tout l'inventaire : 30 sens, 7 démarches, 6 cas d'industrie."""
    return ComboInventory(pairs=all_pairs(),
                          workflows=list(WORKFLOWS),
                          cases=list(INDUSTRY_CASES))


def legs_of_all_workflows() -> List[Tuple[str, str, str]]:
    """Tous les jambages (workflow, source, cible) pour évaluation hub."""
    out: List[Tuple[str, str, str]] = []
    for w in WORKFLOWS:
        for s, t in w.legs:
            out.append((w.key, s, t))
    return out


def describe_inventory() -> str:
    """Listing complet texte (docs + journal GUI)."""
    inv = inventory()
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("STRUCTCALC PRO — COMBINAISONS, DEMARCHES ET CAS D'INDUSTRIE")
    lines.append("=" * 72)
    lines.append(
        f"{len(SOFTWARE_NAMES)} logiciels -> {inv.n_senses} sens diriges, "
        f"{inv.n_reciprocal} paires reciproques, "
        f"{len(WORKFLOWS)} demarches, {len(INDUSTRY_CASES)} cas d'industrie.")
    lines.append("")
    lines.append("--- 1. COMBINAISES DIRIGEES (A -> B via pivot SC-*) ---")
    for p in inv.pairs:
        lines.append(f"* {p.label}")
        lines.append(f"    circule : {p.transfer}")
        lines.append(f"    la cible : {p.target_action}")
        lines.append(f"    demarche : {p.use_case}")
    lines.append("")
    lines.append("--- 2. DEMARCHES (workflows bureau d'etudes) ---")
    for w in inv.workflows:
        lines.append(f"* [{w.key}] {w.name}")
        lines.append(f"    chaine : {w.chain_labels}")
        lines.append(f"    but : {w.objective}")
        lines.append(f"    cas : {w.industry_case}")
        if w.notes:
            lines.append(f"    note honnete : {w.notes}")
    lines.append("")
    lines.append("--- 3. CAS D'INDUSTRIE ---")
    for c in inv.cases:
        lines.append(f"* [{c.key}] {c.name}")
        lines.append(f"    logiciels : {c.software_labels}")
        lines.append(f"    demarches : {', '.join(c.workflows)}")
        lines.append(f"    livrables : {', '.join(c.deliverables)}")
        lines.append(f"    realite : {c.reality}")
    lines.append("")
    lines.append("NOTE : la faisabilite REELLE de chaque jambage est evaluee")
    lines.append("par le hub selon les capacites verifiees (refus motives).")
    return "\n".join(lines)
