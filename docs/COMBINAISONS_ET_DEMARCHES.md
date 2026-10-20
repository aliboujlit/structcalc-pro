# STRUCTCALC PRO — Combinaisons, démarches et cas d'industrie

> Document **généré** par `tools/gen_combos_doc.py` depuis
> `structcalc/integration/interop/combinaisons.py` (source unique).
> La faisabilité **réelle** de chaque liaison est évaluée par le hub
> selon les capacités vérifiées — un refus est toujours motivé
> (spec §19/§20) : rien n'est présenté comme disponible sans preuve.

**Synthèse** : 6 logiciels — **30 sens dirigés** (A → B) — **15 paires réciproques** — **7 démarches** — **6 cas d'industrie**.

---

## 0. Les 6 logiciels et leur mission conçue

| Logiciel | Mission conçue | Opérations réelles |
|---|---|---|
| Revit 2027 | Conception BIM (modèle) | `read_model`, `write_model` |
| Robot Structural Analysis 2027 | Étude structurelle (charges + calcul + résultats) | `write_model`, `write_loads`, `read_results` |
| AutoCAD 2027 | Plans (DWG) | `read_model`, `write_model` |
| Civil 3D 2027 | Plans (DWG) | `read_model`, `write_model` |
| Navisworks Manage 2027 | Coordination (fichiers NWD) | `open_file`, `save_as`, `convert` |
| Advance Steel 2027 | Plans (DWG) | `read_model`, `write_model` |

---

## 1. Combinaisons dirigées — les 30 sens (A → B via pivot SC-*)

| # | Sens | Ce qui circule (source) | Ce que la cible en fait (mission) | Démarche bureau d'études |
|---|---|---|---|---|
| 1 | **revit → robot** | le modèle BIM de conception (nœuds, barres, sections, matériaux, appuis) | l'importe comme modèle d'étude, applique les charges (`write_loads`) et rapporte les résultats (`read_results`) — mission Étude structurelle | Étude de calcul : vérification résistance/flèches/second ordre (BAEL/RPS) du modèle transmis |
| 2 | **revit → autocad** | le modèle BIM de conception (nœuds, barres, sections, matériaux, appuis) | le dessine en plan DWG (couches, mise en page) — mission Plans | Production des plans (coffrage, coffres, récolement, plans de fondation) à partir du modèle étudié |
| 3 | **revit → civil3d** | le modèle BIM de conception (nœuds, barres, sections, matériaux, appuis) | le reporte sur le fond topographique (implantation, axes) — mission Plans / site | Implantation : poser les axes et fondations sur le fond topographique/VRD du site |
| 4 | **revit → navisworks** | le modèle BIM de conception (nœuds, barres, sections, matériaux, appuis) | l'agrège en maquette NWD pour la coordination et la détection de conflits — mission Coordination (fichier) | Coordination pluridisciplinaire : agrégation NWD et détection de conflits (métrés, chevauchements) |
| 5 | **revit → advsteel** | le modèle BIM de conception (nœuds, barres, sections, matériaux, appuis) | le détaille en plan d'atelier acier — mission Plans acier | Détail d'atelier : profils, coupes, assemblages et nomenclature acier à partir du modèle étudié |
| 6 | **robot → revit** | le modèle d'étude + les charges + les résultats calculés (N, M, réactions, flèches, unités contrôlées) | l'intègre au modèle BIM (mise à jour des sections/appuis) — mission Conception BIM via add-in .NET | Retour d'étude vers le BIM : sections optimisées, appuis et observations d'ingénieur intégrés au modèle |
| 7 | **robot → autocad** | le modèle d'étude + les charges + les résultats calculés (N, M, réactions, flèches, unités contrôlées) | le dessine en plan DWG (couches, mise en page) — mission Plans | Production des plans (coffrage, coffres, récolement, plans de fondation) à partir du modèle étudié |
| 8 | **robot → civil3d** | le modèle d'étude + les charges + les résultats calculés (N, M, réactions, flèches, unités contrôlées) | le reporte sur le fond topographique (implantation, axes) — mission Plans / site | Implantation : poser les axes et fondations sur le fond topographique/VRD du site |
| 9 | **robot → navisworks** | le modèle d'étude + les charges + les résultats calculés (N, M, réactions, flèches, unités contrôlées) | l'agrège en maquette NWD pour la coordination et la détection de conflits — mission Coordination (fichier) | Coordination pluridisciplinaire : agrégation NWD et détection de conflits (métrés, chevauchements) |
| 10 | **robot → advsteel** | le modèle d'étude + les charges + les résultats calculés (N, M, réactions, flèches, unités contrôlées) | le détaille en plan d'atelier acier — mission Plans acier | Détail d'atelier : profils, coupes, assemblages et nomenclature acier à partir du modèle étudié |
| 11 | **autocad → revit** | le dessin DWG (génération de plans depuis le modèle : couches, géométrie, annotations) | l'intègre au modèle BIM (mise à jour des sections/appuis) — mission Conception BIM via add-in .NET | Retour d'étude vers le BIM : sections optimisées, appuis et observations d'ingénieur intégrés au modèle |
| 12 | **autocad → robot** | le dessin DWG (génération de plans depuis le modèle : couches, géométrie, annotations) | l'importe comme modèle d'étude, applique les charges (`write_loads`) et rapporte les résultats (`read_results`) — mission Étude structurelle | Étude de calcul : vérification résistance/flèches/second ordre (BAEL/RPS) du modèle transmis |
| 13 | **autocad → civil3d** | le dessin DWG (génération de plans depuis le modèle : couches, géométrie, annotations) | le reporte sur le fond topographique (implantation, axes) — mission Plans / site | Implantation : poser les axes et fondations sur le fond topographique/VRD du site |
| 14 | **autocad → navisworks** | le dessin DWG (génération de plans depuis le modèle : couches, géométrie, annotations) | l'agrège en maquette NWD pour la coordination et la détection de conflits — mission Coordination (fichier) | Coordination pluridisciplinaire : agrégation NWD et détection de conflits (métrés, chevauchements) |
| 15 | **autocad → advsteel** | le dessin DWG (génération de plans depuis le modèle : couches, géométrie, annotations) | le détaille en plan d'atelier acier — mission Plans acier | Détail d'atelier : profils, coupes, assemblages et nomenclature acier à partir du modèle étudié |
| 16 | **civil3d → revit** | le fond topographique / VRD en DWG (lignes de niveau, axes, terrain) | l'intègre au modèle BIM (mise à jour des sections/appuis) — mission Conception BIM via add-in .NET | Retour d'étude vers le BIM : sections optimisées, appuis et observations d'ingénieur intégrés au modèle |
| 17 | **civil3d → robot** | le fond topographique / VRD en DWG (lignes de niveau, axes, terrain) | l'importe comme modèle d'étude, applique les charges (`write_loads`) et rapporte les résultats (`read_results`) — mission Étude structurelle | Étude de calcul : vérification résistance/flèches/second ordre (BAEL/RPS) du modèle transmis |
| 18 | **civil3d → autocad** | le fond topographique / VRD en DWG (lignes de niveau, axes, terrain) | le dessine en plan DWG (couches, mise en page) — mission Plans | Production des plans (coffrage, coffres, récolement, plans de fondation) à partir du modèle étudié |
| 19 | **civil3d → navisworks** | le fond topographique / VRD en DWG (lignes de niveau, axes, terrain) | l'agrège en maquette NWD pour la coordination et la détection de conflits — mission Coordination (fichier) | Coordination pluridisciplinaire : agrégation NWD et détection de conflits (métrés, chevauchements) |
| 20 | **civil3d → advsteel** | le fond topographique / VRD en DWG (lignes de niveau, axes, terrain) | le détaille en plan d'atelier acier — mission Plans acier | Détail d'atelier : profils, coupes, assemblages et nomenclature acier à partir du modèle étudié |
| 21 | **navisworks → revit** | le fichier de coordination NWD (maquette agrégée de tous les corps de métier) | l'intègre au modèle BIM (mise à jour des sections/appuis) — mission Conception BIM via add-in .NET | Retour d'étude vers le BIM : sections optimisées, appuis et observations d'ingénieur intégrés au modèle |
| 22 | **navisworks → robot** | le fichier de coordination NWD (maquette agrégée de tous les corps de métier) | l'importe comme modèle d'étude, applique les charges (`write_loads`) et rapporte les résultats (`read_results`) — mission Étude structurelle | Étude de calcul : vérification résistance/flèches/second ordre (BAEL/RPS) du modèle transmis |
| 23 | **navisworks → autocad** | le fichier de coordination NWD (maquette agrégée de tous les corps de métier) | le dessine en plan DWG (couches, mise en page) — mission Plans | Production des plans (coffrage, coffres, récolement, plans de fondation) à partir du modèle étudié |
| 24 | **navisworks → civil3d** | le fichier de coordination NWD (maquette agrégée de tous les corps de métier) | le reporte sur le fond topographique (implantation, axes) — mission Plans / site | Implantation : poser les axes et fondations sur le fond topographique/VRD du site |
| 25 | **navisworks → advsteel** | le fichier de coordination NWD (maquette agrégée de tous les corps de métier) | le détaille en plan d'atelier acier — mission Plans acier | Détail d'atelier : profils, coupes, assemblages et nomenclature acier à partir du modèle étudié |
| 26 | **advsteel → revit** | les plans de charpente acier en DWG (profils, assemblages, détails d'atelier) | l'intègre au modèle BIM (mise à jour des sections/appuis) — mission Conception BIM via add-in .NET | Retour d'étude vers le BIM : sections optimisées, appuis et observations d'ingénieur intégrés au modèle |
| 27 | **advsteel → robot** | les plans de charpente acier en DWG (profils, assemblages, détails d'atelier) | l'importe comme modèle d'étude, applique les charges (`write_loads`) et rapporte les résultats (`read_results`) — mission Étude structurelle | Étude de calcul : vérification résistance/flèches/second ordre (BAEL/RPS) du modèle transmis |
| 28 | **advsteel → autocad** | les plans de charpente acier en DWG (profils, assemblages, détails d'atelier) | le dessine en plan DWG (couches, mise en page) — mission Plans | Production des plans (coffrage, coffres, récolement, plans de fondation) à partir du modèle étudié |
| 29 | **advsteel → civil3d** | les plans de charpente acier en DWG (profils, assemblages, détails d'atelier) | le reporte sur le fond topographique (implantation, axes) — mission Plans / site | Implantation : poser les axes et fondations sur le fond topographique/VRD du site |
| 30 | **advsteel → navisworks** | les plans de charpente acier en DWG (profils, assemblages, détails d'atelier) | l'agrège en maquette NWD pour la coordination et la détection de conflits — mission Coordination (fichier) | Coordination pluridisciplinaire : agrégation NWD et détection de conflits (métrés, chevauchements) |

Les 30 sens = **15 paires réciproques** (chaque paire dans les deux sens, garantie par le pivot SC-*).

---

## 2. Démarches (workflows de bureau d'études)

### Bâtiment complet — conception → étude → plans → retour

- **Clé** : `bati_complet`
- **Chaîne** : `Revit 2027 -> Robot Structural Analysis 2027 -> AutoCAD 2027 -> Revit 2027` (boucle fermée)
- **Objectif** : Cycle classique du bureau d'études structure BRISE : modèle BIM -> calcul -> plans -> retours d'étude dans le BIM.
- **Cas industrie** : Bâtiment (logements, tertiaire, équipements)
- **Note honnête** : Revit exige l'add-in .NET pour l'accès modèle ; add-in compilé/déployé (PIPE structcalc_revit prouvé live) ; sans lui, les jambages Revit sont refusés avec motif.
- **Jambages** : `revit→robot`, `robot→autocad`, `autocad→revit`

### Étude sans BIM — dessin → calcul → plans

- **Clé** : `etude_sans_bim`
- **Chaîne** : `AutoCAD 2027 -> Robot Structural Analysis 2027 -> AutoCAD 2027` (boucle fermée)
- **Objectif** : Processus historique des bureaux d'études : plan DWG existant -> modèle de calcul -> plans corrigés (câblage AutoCAD<->Robot prouvé live).
- **Cas industrie** : Bâtiment existant / réhabilitation / concours
- **Note honnête** : Paire réciproque AUTO<->ROBOT prouvée par tests live.
- **Jambages** : `autocad→robot`, `robot→autocad`

### Charpente acier — détail d'atelier ↔ calcul

- **Clé** : `charpente_acier`
- **Chaîne** : `Advance Steel 2027 -> Robot Structural Analysis 2027 -> Advance Steel 2027` (boucle fermée)
- **Objectif** : Hangar, plancher acier, passarelles : dessin d'atelier Advance Steel -> vérification de calcul Robot -> plans d'atelier corrigés.
- **Cas industrie** : Charpente métallique / industriel
- **Note honnête** : Advance Steel = DWG via hôte acad.exe partagé ; sémantique AstorMain5 refusée (non COM) — le transfert passe en DWG.
- **Jambages** : `advsteel→robot`, `robot→advsteel`

### Site & VRD — topographie → implantation → plans

- **Clé** : `site_vrd`
- **Chaîne** : `Civil 3D 2027 -> Revit 2027 -> Robot Structural Analysis 2027 -> AutoCAD 2027` (chemin ouvert)
- **Objectif** : Fond topographique Civil 3D -> positionnement des fondations dans le BIM -> étude -> plans d'implantation.
- **Cas industrie** : Lotissements, réseux, ouvrages de terrassement
- **Note honnête** : Civil 3D : DWG de niveau dessin (objets intelligents C3D refusés hors .NET) ; Revit : add-in .NET livré et prouvé (pipe structcalc_revit).
- **Jambages** : `civil3d→revit`, `revit→robot`, `robot→autocad`

### Coordination BIM — maquettes → NWD → retour conflits

- **Clé** : `coordination_bim`
- **Chaîne** : `Revit 2027 -> AutoCAD 2027 -> Navisworks Manage 2027 -> Revit 2027` (boucle fermée)
- **Objectif** : Coordination pluridisciplinaire : agréger maquette BIM et plans en NWD (Navisworks convertit les fichiers), traiter les conflits et rejeter les corrections au BIM.
- **Cas industrie** : Grand projet, coordination de corps d'état multiples
- **Note honnête** : Navisworks est un convertisseur de FICHIERS (open_file/convert, prouvé live DWG->NWD) : son jambage s'exécute avec un chemin de fichier source, sinon refus motivé.
- **Jambages** : `revit→autocad`, `autocad→navisworks`, `navisworks→revit`

### Charpente complète — BIM → calcul → détail acier

- **Clé** : `acier_complet`
- **Chaîne** : `Revit 2027 -> Robot Structural Analysis 2027 -> Advance Steel 2027 -> Revit 2027` (boucle fermée)
- **Objectif** : Structure métallique modélisée en BIM, étudiée sous BAEL, détaillée en atelier puis retours de montage.
- **Cas industrie** : Charpente métallique de bâtiment
- **Note honnête** : Add-in Revit .NET requis pour le maillon BIM.
- **Jambages** : `revit→robot`, `robot→advsteel`, `advsteel→revit`

### Boucle industrielle complète — les 6 logiciels en réseau

- **Clé** : `boucle_complete`
- **Chaîne** : `Revit 2027 -> Civil 3D 2027 -> Robot Structural Analysis 2027 -> Advance Steel 2027 -> AutoCAD 2027 -> Navisworks Manage 2027 -> Revit 2027` (boucle fermée)
- **Objectif** : Réseau réciproque total : tous les logiciels cochés tournent en boucle fermée via le pivot SC-*, chacun accomplissant sa mission conçue (retour auto sur le premier maillon).
- **Cas industrie** : Toute typologie (orchestration complète)
- **Note honnête** : 30 sens diriges disponibles ; la boucle n'en utilise qu'une chaîne ordonnée + retour.
- **Jambages** : `revit→civil3d`, `civil3d→robot`, `robot→advsteel`, `advsteel→autocad`, `autocad→navisworks`, `navisworks→revit`

---

## 3. Cas d'industrie (bureau d'études / technologies)

### Bâtiment (BRISE / logements / tertiaire)

- **Clé** : `bati`
- **Logiciels mobilisés** : Revit 2027 + Robot Structural Analysis 2027 + AutoCAD 2027 + Navisworks Manage 2027
- **Démarches** : `bati_complet`, `etude_sans_bim`, `coordination_bim`
- **Livrables** : Note de calcul BAEL ; Plans de coffrage ; Fiches de poteaux ; Maquette NWD coordonnée
- **Réalité technique** : AutoCAD<->Robot prouvé live ; Revit via add-in .NET compilé et déployé (PING + roundtrip pipe prouvés live) ; Navisworks conversion de fichiers prouvée live.

### Réhabilitation / diagnostic sur plans existants

- **Clé** : `rehabilitation`
- **Logiciels mobilisés** : AutoCAD 2027 + Robot Structural Analysis 2027
- **Démarches** : `etude_sans_bim`
- **Livrables** : Plan de situation coté ; Étude de reprise en élévation ; Rapport de conformité BAEL
- **Réalité technique** : Paire AutoCAD<->Robot réciproque et prouvée live.

### Charpente métallique / hangar industriel

- **Clé** : `charpente`
- **Logiciels mobilisés** : Advance Steel 2027 + Robot Structural Analysis 2027 + AutoCAD 2027
- **Démarches** : `charpente_acier`, `acier_complet`
- **Livrables** : Plans d'atelier ; Nomenclature d'acier ; Note de calcul BAEL 3 (acier)
- **Réalité technique** : Advance Steel en DWG via hôte partagé (AstorMain5 refusé motivé) ; Robot = étude prouvée live.

### Site, VRD & ouvrages de terrassement

- **Clé** : `site_vrd`
- **Logiciels mobilisés** : Civil 3D 2027 + AutoCAD 2027 + Robot Structural Analysis 2027
- **Démarches** : `site_vrd`
- **Livrables** : Plan topographique ; Plan d'implantation ; Calcul des ouvrages de soutènement
- **Réalité technique** : Civil 3D en DWG de niveau dessin (objets intelligents refusés motivé hors .NET) ; calcul = Robot.

### Coordination pluridisciplinaire (grand projet)

- **Clé** : `coordination`
- **Logiciels mobilisés** : Revit 2027 + AutoCAD 2027 + Civil 3D 2027 + Navisworks Manage 2027
- **Démarches** : `coordination_bim`, `bati_complet`
- **Livrables** : Maquette de coordination NWD ; Registre de conflits ; Comptes rendus de réunion
- **Réalité technique** : Navisworks = convertisseur NWD prouvé live ; conflits = fichiers, jamais inventés ; Revit via add-in .NET.

### Bureau d'études intégré (orchestration complète)

- **Clé** : `ingenierie_complete`
- **Logiciels mobilisés** : Revit 2027 + Robot Structural Analysis 2027 + AutoCAD 2027 + Civil 3D 2027 + Navisworks Manage 2027 + Advance Steel 2027
- **Démarches** : `boucle_complete`, `bati_complet`, `charpente_acier`, `site_vrd`
- **Livrables** : Dossier de calcul complet ; Tous plans ; Maquette coordonnée ; Synthèse des vérifications
- **Réalité technique** : Tous liens équipés d'un motif honnête : prouvés (AutoCAD, Robot, Navisworks), add-in compilé/déployé et prouvé live (Revit), DWG (Civil 3D, Advance Steel).

---

## 4. Lecture des faisabilités

| Statut affiché | Sens |
|---|---|
| `OK` | Route faisable selon capacités **vérifiées** (ex. AutoCAD ↔ Robot prouvé live) |
| `REFUS` + motif | Capacité absente/bloquée, **motif exact** affiché (ex. `revit.read_model=NOT_SUPPORTED` sans add-in .NET) |
| `—` | Même logiciel (route inutile) |

Voir l'onglet **Combinaisons** de l'interface (matrice vivante) et
`python tools/demo_loop_missions.py` pour la boucle avec missions.
