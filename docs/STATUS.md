# STRUCTCALC PRO — État d'avancement

> **Règle absolue (spec §0, §20) :** aucun calcul n'est présenté comme conforme
> tant que sa méthode, ses coefficients, ses hypothèses et ses limites de
> validité ne sont pas vérifiés. Aucune fonction n'est présentée comme
> opérationnelle sans preuve. Ce document sépare explicitement **PRUVÉ** /
> **EN COURS** / **NON IMPLÉMENTÉ**.

Dernière mise à jour : 2026-10-20 (v1.3.0 — LEDs, plan du modèle complet, Navisworks en boucle)

---

## 0ter. v1.3.0 (20/10/2026) — LEDs, TOUS les éléments structurels, Navisworks en boucle

Demandes utilisateur : détection au lancement + relance par les mêmes
programmes ; Navisworks réellement intégré à la boucle ; tous les éléments
structurels repris ; LEDs vert/rouge dans le programme.

| Apport | État réel (preuve) |
|---|---|
| **LEDs des 6 logiciels** (onglet Connecteurs) — vert = attachement **VÉRIFIÉ** sans lancement, rouge = motif exact affiché | `integration/software_status.py` : tasklist + GetActiveObject (ROT) + sonde pipe Revit — **aucun lancement** dans la détection ; boutons « Actualiser » et « Démarrer les logiciels manquants » (exécutables RÉELS, processus visibles, jamais de double instance) ; tests `test_software_status.py` (7) + `test_gui_smoke.py` (2) |
| **Détection au lancement** du GUI + relance par les MÊMES programmes | `MainWindow` : refresh LEDs au démarrage (`QTimer` 400 ms) ; Relance : robot.exe (registre), acad.exe, Revit.exe, Roamer.exe (Navisworks 2027 installé — vérifié) |
| **Plan du modèle Robot COMPLET** (niveaux, cas de charge, charges, sections, matériaux, appuis, **barres classées poteau/poutre**) | `integration/interop/plan.py` — **aucune API inventée** : membres RÉELLEMENT sondés en live 20/10 (`tools/probe_plan_elements_live.py`) + enums lues dans `robotom.tlb` : `I_OST_COLUMN=2/BEAM=1/GIRDER=6` (`Bars.GetStructuralType`), `I_CN_*` (`case.Nature`), `I_LT_BAR_SECTION=3/BAR_MATERIAL=8/NODE_SUPPORT=0` (`Labels.GetAvailableNames`), `IRobotSimpleCase.Records` via **rejeu dynamique** (wrapper typé `IRobotCase` n'expose pas `Records` — constaté live) |
| **Valeurs de charges honnêtes** | `GetValue(2)`=Fz **seullement** pour `I_LRT_BAR_UNIFORM` (index VÉRIFIÉ, chaîne prouvée loads.py) ; tout autre type -> valeur **MANQUANTE** (jamais devinée), la description réelle Robot reste dans `ref` ; nouveau conteneur core `Project.loads` (classe `Load`) |
| **`apply_plan` : vérification d'identité Robot↔Plan** | diff nul requis (niveaux, cas, charges, sections, matériaux, appuis, barres classées) — **AUCUNE écriture Robot** ; dérive -> REFUSED motivé ; `read_model` arrête **avant toute mutation** du pivot (testé) |
| **Navisworks RÉELLEMENT dans la boucle** | mission `coordination_nwd` : conversion `source_file` (pivot) → **`.nwd`** via `convert()` (chaîne OpenFile→SaveAs **prouvée live** DWG→NWD) ; sans fichier source réel : refus motivé (spec §6) ; le chargeur porte `project.source_file` ; la chaîne villa convertit `Plan-villa.dwg` → `Plan-villa.nwd` (copié au dossier) |
| **Correctif live Robot** `connect()` | Dispatch immédiat après lancement direct → `CO_E_SERVER_EXEC_FAILURE` (constaté 20/10) : ajout d'une **boucle d'attente/retry** (2 s, jusqu'au timeout) pour l'attachement et `attach_only` |

Tests : **351 passed** (327 + 24 : `test_robot_plan.py` 9, `test_software_status.py` 7,
`test_loop_coordination.py` 5, `test_gui_smoke.py` +3 dont LEDs).

---

## 0bis. Session live 2026-10-19 (v1.2.5) — 4 défauts trouvés et corrigés

Déroulé live de la chaîne complète (Plan-villa.dwg → étude villa Robot →
Revit → boucle 6 logiciels → dossier) après redémarrage de la machine :

| Défaut observé (live) | Cause racine (prouvée) | Correctif |
|---|---|---|
| Lecture modèle villa → `E_UNEXPECTED` alors que `GetAll().Count` répond (66/108) | **Double bug** : `_iter_numbers` supposait une numérotation dense 1..N (villa : nœuds à partir de 2, barres 1, 2, 5…) **et** le dispatch dynamique pywin32 ne sait pas lire les collections Robot (membre `Get` = propriété indexée → sous-objet COM au lieu d'un numéro) | **Binding typé RobotOM** généré depuis le FICHIER `robotom.tlb` (`_ensure_typed_binding()`, le registre TypeLib est incomplet) : `coll.Get(i)` renvoie `IRobotNode`/`IRobotBar` — import villa **66 nœuds + 108 barres en 1,3 s** vérifié live ; repli dynamique conservé (`model.import_nodes/import_bars` voie typée d'abord) |
| Robot : `CO_E_SERVER_EXEC_FAILURE` au démarrage à froid | Lancement uniquement via COM/SCM (invisible) — Robot met des minutes à s'enregistrer | **Lancement direct visible** de `robot.exe` (registre LocalServer32, args retirés) puis **attachement `Dispatch`** (single-instance, vérifié live : 0 seconde fenêtre) ; `attach_only` profite de l'attachement si robot.exe tourne |
| AutoCAD « L'appel a été rejeté par l'appelé » | Palette « Références externes » (xref manquante) laissée par une session précédente → service COM saturé | Instances nettoyées — AutoCAD repart propre ; timeouts par défaut portés à 180 s (froid) |
| Add-in Revit refusé : fenêtre « Outils externes - AddInId dupliqué » | Notre `AddInId` factice `a1b2c3d4-…` **collidait** avec RevitPythonShell | AddInId unique `da6d1f72-cdc4-4303-92d1-c5da20ff0758` → **add-in chargé, pipe vivant** (manifeste `%APPDATA%\Autodesk\Revit\Addins\2027\StructCalcAddin.addin`) |

**Verdict live final (19/10 12:02)** : étape 1 plan OK (honnête : 0 objet
structurel) ; étape 2 villa **ADOPTÉE** (ouverte par la session GUI) →
lecture 66/108 OK + 11 cas + **CALCUL OK + 66 réactions réelles** ;
étape 3 add-in vivant (refus honnête « aucun document .rvt actif » —
mise à jour seule, §6.3) ; **boucle 6/12** (robot→autocad→civil3d→advsteel
visibles + refus motivés Navisworks/Revit) ; dossier MD/PDF/XLSX + DWG.
Nouveau : `RobotConnection.adopt_live_project()` réutilisé par la chaîne
quand la villa est déjà ouverte (étude sans fermeture ni sauvegarde, §5.4).

---

---

## 1. Synthèse des tests

| Suite | Commande | Résultat |
|---|---|---|
| Unitaires (CORE, mapping, réglementaire, solver, reporting, GUI, **interop**, **boucle + missions + combinaisons**, **chargeur de projet v1.2**, **cohérence v1.2**, **adoption Robot**, **dossier architecte**, **import modèle typé**, **plan du modèle Robot v1.3**, **LEDs logiciels v1.3**, **mission Navisworks v1.3**) | `python -m pytest tests/unit -q` | **351 passed** |
| Intégration Robot (round-trip modèle) | `python -m pytest -m robot tests/integration_robot/test_model_roundtrip.py -v` | **2 passed** |
| Intégration Robot (charges + résultats, Phase 2) | `python -m pytest -m robot tests/integration_robot/test_loads_results.py -v` | **5 passed** |
| Intégration **interop réciproque** Robot ↔ AutoCAD | `python -m pytest -m robot tests/integration_robot/test_interop_exchange.py -v` | **3 passed** |
| **Total intégration Robot** (10 tests, 3 fichiers) | `python -m pytest -m robot tests/integration_robot -v` | **10 passed** |

Scripts de vérification :
- `python tools/verify_interop_hub.py` — matrice de routes + paires réciproques (aucun lancement).
- `python tools/verify_interop_live.py` — aller-retour réel Project ↔ AutoCAD (DWG AC1018, géométrie identique).
- `python tools/verify_navisworks_live.py` — pont réel AutoCAD(DWG) → Navisworks → **NWD** (préuve live du convertisseur).
- `python tools/probe_nw_saveas.py` — borne `.nwd` OK / `.nwc` échec (SaveAs Navisworks).
- `python main.py --selftest` — autotest applicatif (version, plan de boucle, exports, fenêtre) → `%TEMP%\structcalc_selftest.txt`.
- `python tools/verify_test_projects.py "<projet.dwg>"` — **vérification LIVE 9 phases** sur les projets réels de l'utilisateur (inventaire, lecture .rtd Robot, ouverture/lecture DWG + gardes anti-faux-succès, échanges avec contrôle de compteurs, conversion NWD, sonde Revit, matrice hub, boucle 6 logiciels) — **sujet DWG paramétrable en argument** (ex. `Plan-villa.dwg`) ; rapport `\_structcalc_sortie/verification_report.txt`.
- `python tools/build_exe.py` — compilation du `.exe` autonome avec n° de version embarqué + vérification automatique du binaire.
- `python tools/demo_loop_missions.py` — boucle Revit<->Robot avec missions par maillon (refus motivés sans logiciel ouvert).
- `python tools/gen_combos_doc.py` — regénère `docs/COMBINAISONS_ET_DEMARCHES.md` depuis le code (source unique).

> Les suites `robot` lancent le vrai Robot 2027 : exécuter **séquentiellement**,
> jamais en parallèle des unitaires. `addopts = -m 'not robot'` les exclut par
> défaut.

---

## 2. Couche par couche

### CORE — **PRUVÉ et testé**
- `ids.py` (`IdAllocator`, `make_id`, `parse_id`) — identifiants stables `SC-*-000124`.
- `status.py` (`DataStatus`, `RegulatoryStatus`, transitions) — `ASSUMED→VALIDATED`
  jamais silencieux ; `VERIFICATION_NON_IMPLEMENTE` ne compte jamais comme passage.
- `tracked.py` (`TrackedValue`, `Provenance`, `validate_assumption`).
- `model.py` (`Project`, `Node`, `Column`, `Material`, `CrossSection`, `ExternalRef`,
  `counts()`, `data_gaps()`).
- `store.py` (`ProjectStore` SQLite : tables `objects` + `external_refs`).
- **Sans dépendance** PyQt6 / Robot / Revit (spec §3.1).

### INTEGRATION / Robot — **PRUVÉ (priorité haute)**
- `connection.py` : `RobotApplication` via COM/TypeLib `robotom.tlb` (comtypes).
- `model.py` : export/import nœuds + barres, `verify_transfer`.
- `loads.py` (Phase 2) :
  - **Prouvé** : `Cases.CreateSimple(number, name, type_int, analize_bool)` ;
    `CalcEngine.Calculate()` ; `Results.Available`.
  - **Froid / refus explicite (spec §19)** : `create_combination` (non démontré),
    `apply_uniform_bar_load` (type d'enregistrement non confirmé).
- `results.py` (Phase 2) :
  - **Prouvé** : `Results.Nodes.Reactions.Value(node, case)` (structure),
    `Results.Nodes.Displacements`, `Results.Bars.Forces.Value(bar, case, point)`.
  - Lecture **refusée** tant que `Results.Available == 0` (pas de fausses valeurs).
  - **Unités non encore contrôlées** (spec §5.3) — à faire.
- `mapping.py` : table `SC-* ↔ Robot`, ambiguïtés signalées, orphelins **jamais**
  supprimés (spec §4.1, §13).

### INTEGRATION / Revit — **ADD-IN .NET COMPILÉ, DÉPLOYÉ ET PROUVÉ LIVE**
- `connection.py` : détection, fiche de compatibilité — **accès modèle = False sans add-in** (spec §6.3, §19).
- **Add-in .NET** (`StructCalcAddin/`) : 
  - `IExternalApplication` avec ruban (Lire modèle, Écrire modèle, Statut Pipe, Arrêter Pipe)
  - **Serveur Named Pipe** (`NamedPipeServer`) : protocole NDJSON, commandes PING/READ_MODEL/WRITE_MODEL/GET_ELEMENTS/APPLY_CHANGES
  - DTOs JSON (`ElementDto`) : nœuds, barres, sections, matériaux, appuis, charges, armatures
  - Commandes `ReadModelCommand` / `WriteModelCommand` : extraction/appl. modèle dans transaction Revit
  - `ModelExtractor` : BoundaryConditions fixities, cas de charge via NatureId, poteaux/poutres distingués (StructuralType)
  - `ChangesApplier` : transaction unique, Rebar.CreateFromCurves (signature vérifiée), refus motivés (appuis, armatures latérales)
  - `RevitApiDispatcher` : IExternalEventHandler + ExternalEvent, timeout honnête ~15 s
- **Client Python** (`integration/interop/revit_addin_client.py`) : connect, ping, read_model, apply_changes
- **Connecteur Python** (`integration/interop/revit.py`) : sonde PING dynamique (cache TTL), capacités retournables (PARTIAL si pipe actif, NOT_SUPPORTED si absent + motif d'action), import pivot avec IDs SC-NODE-V*/SC-BEAM-V*/SC-COLUMN-V*, refus d'écriture sans mappage (aucun identifiant inventé)
- **Test live** (`tools/live_test_revit_addin.py`) : vérification PING + READ_MODEL + refus écriture sans mappage
- **Déploiement** ("tools/deploy_revit_addin.py") : compilation .NET + copie .addin + DLL + Newtonsoft.Json vers `%APPDATA%\Autodesk\Revit\Addins\2027\`
- **Réciprocité** : Revit <-> STRUCTCALC via pipe (pas de COM, pas de port réseau, fiable local). **Prouvé live : PING + roundtrip READ_MODEL.**

### INTEGRATION / interop — **PRUVÉ (réciprocité Autodesk)**
Architecture **en étoile par pivot SC-\*** : plutôt que N×N ponts directs
(inassurables, §19), chaque logiciel n'a qu'UN pont vers/depuis le pivot.
L'échange réciproque `A ↔ B` = `A -> pivot -> B` puis `B -> pivot -> A`.

La réciprocité est donc garantie **par construction** avec N connecteurs.

- `base.py` : contrat commun (`AutodeskConnector`, `Capability`,
  `CapabilityStatus`, `Detection`, `OpReport`). Une capacité n'est `usable`
  que si `SUPPORTED` ou `PARTIAL` — `UNVERIFIED` / `NOT_IMPLEMENTED` /
  `NOT_SUPPORTED` comptent comme **non disponibles** (§19).
- `autocad.py` — **PRUVÉ par exécution réelle** (AutoCAD 2027, `acad.exe`) :
  - attach (`GetActiveObject`/`Dispatch` + **backoff** : `Dispatch` peut lever
    `CO_E_SERVER_EXEC_FAILURE` tant que le serveur s'enregistre) ;
  - **`_active()` durci (18/10/2026)** : la validité exige `app.Name`
    **et** `app.Documents.Count` — une instance dégradée qui ne résout plus
    `Documents` (`<unknown>.Count`) n'est **jamais** acceptée (cause réelle
    des rejets `com_error` en chaîne observés live) ; repli `Dispatch(ProgID)`
    **seulement si un `acad.exe` tourne déjà** (rattachement à l'objet
    mono-instance, aucun lancement involontaire — helper
    `_acad_process_running()`) ;
  - `Documents.Add/Open` (Open exige un **retry** : `CALL_REJECTED` tant que le
    document n'est pas chargé) ;
  - `AddLine` / `AddLightWeightPolyline` avec **points en `VARIANT`**
    (`VT_ARRAY|VT_R8`) — la forme tuple échoue ;
  - `ent.Layer` (get/set), `ent.Handle`, `ent.Delete()`, `layers.Add/Item` ;
  - `SaveAs` avec **codes vérifiés : 24 = AC1018, 12 = AC1015** (les autres
    codes lèvent « Argument incorrect ») ;
  - **Non vérifié → jamais appelé** : `AddText`/`AddMText` (toutes formes
    échouent), `ItemByRef(Handle)` (inexistant → parcours de `ModelSpace`).
- `robot.py` — **PRUVÉ** : traduit le pivot vers les dict neutres de
  `integration/robot/model.py` (voies Phase 0). Tables de correspondance
  `SC-NODE-* ↔ numéro Robot` dense. Combinaisons toujours refusées
  (`create_combination` non vérifié, §19).
- `civil3d.py` — **PRUVÉ (partiel), diagnostic CORRIGÉ** : Civil 3D 2027
  installé. Contre un diagnostic initial erroné (« aucun ProgID `Aecc` » — le
  premier scan exigeait le préfixe exact `Aecc.` et ratait `AeccX...`), les
  ProgIDs **existent bel et bien** (`AeccXUiLand.AeccApplication.13.9`,
  `AeccDocument`, `AeccXUiPipe...`, serveurs Inproc `AeccXUiLand.dll`), **mais
  échouent à l'activation externe** (`0x8007007E`, y compris avec
  `os.add_dll_directory` sur `C3D\`+racine AutoCAD) : contexte en-processus
  Civil 3D (add-in .NET) requis. Hérite donc de l'hôte AutoCAD (même
  `acad.exe`) pour le DWG de niveau dessin ; les **objets intelligents**
  (alignements, surfaces, corridors, réseaux) sont **refusés motivés** (§19).
- `revit.py` — **HONNÊTE** : installé mais `automatable=False` (aucun COM
  modèle ; les clés `Revit.*` sont des associations de fichiers).
  `read_model`/`write_model` retournent `NOT_IMPLEMENTED` avec le motif
  (voies §6.2 recommandées : natif Revit↔Robot, SMXX, add-in .NET).
- `advsteel.py` — **PRUVÉ (partiel), hérite AutoCAD** : Advance Steel 2027
  (l'instance AutoCAD active EST Advance Steel, hôte `acad.exe` partagé).
  La TLB `ADVS\AstorMain5.tlb` (325 Ko, 986 symboles) expose le VRAI modèle
  objet acier (`AdvanceSteelApplication`, `Beam`, `Bolt`, `AstUI`…) **mais ses
  coclasses ont un CLSID non enregistré** (`REGDB_E_CLASSNOTREG`, « Classe non
  enregistrée ») → sémantique acier **non pilotable en COM externe**. Accès
  DWG de niveau dessin via l'hôte commun (PARTIAL) ; `read_steel_objects` /
  `write_steel_objects` = **refus motivé** (§19).
- `navisworks.py` — **PRUVÉ par exécution live** (`tools/verify_navisworks_live.py`,
  `Navisworks Manage 2027`) :
  - **14 ProgID** au registre : `Navisworks.Document(.24)` (Local → `Roamer.exe`)
    + famille `NavisworksIntegratedAPI.*` (Inproc `lcodieD.dll`). Seul
    `Navisworks.Document.24` est **sûr** ; les coclasses **Inproc plantent en
    natif** au Dispatch externe → jamais touchées.
  - surface COM **réellement exposée** (sondes `probe_nw_step`/`probe_nw_discover`,
    bibliothèque de types `roamer.tlb` vide) : `Visible`, `OpenFile(path)`,
    `SaveAs(path)` — **rien d'autre** (pas de membre de modèle, §19).
  - **prouvé live** : `connect` (~20 s) → `OpenFile(dwg AutoCAD)` → `SaveAs(.nwd)`
    → **fichier NWD produit**. Borne vérifiée : **`.nwd` OK, `.nwc` échoue**
    (`Failed to save document` — le `.nwc` est un *cache*, pas une cible SaveAs).
  - rôle réel = **convertisseur de fichiers de coordination** ; géométrie via
    pivot `read_model`/`write_model` = **`NOT_SUPPORTED` motivé** (§19).
- `hub.py` : registre (clé dupliquée = conflit explicite), `routes()` (matrice
  N×N avec motif si non faisable), `reciprocal_pairs()`, `exchange()`
  (`success=False` + `step_failed` = `read`/`write` en cas d'échec, jamais de
  faux succès).
- **Paires réciproques réelles** : `autocad ↔ robot`, `autocad ↔ civil3d`,
  `civil3d ↔ robot`, `advsteel ↔ robot`, `advsteel ↔ autocad`,
  `advsteel ↔ civil3d` (**6 paires**). Revit : **0 échange direct** (motif
  fourni). Navisworks : **0 route de géométrie** via pivot (COM sans membre de
  modèle) mais **nœud de coordination fonctionnel** (conversion DWG→NWD prouvée).

### REGULATION — **CADRE PRUVÉ ; articles NON vérifiés (notes enrichies)**
- `base.py` : `Regulation`, `Article`, `VerificationResult` — statut par défaut
  `VERIFICATION_NON_IMPLEMENTE`.
- `bael91r99/columns.py` : compression centrale, élancement, armatures min/max,
  fcd/fyd, **flexion composée** (diagramme d'interaction) + **second ordre**
  (amplification nominale) — §10.3/§11.3 **IMPLÉMENTÉS** (A_VALIDER tant que
  `verified=False`, jamais « Conforme » silencieux). Cas de référence (§17.2).
  **Notes enrichies** : γc=1.5/γs=1.15 CONFIRMÉS ; coef. 0.6, η=0.85, λ=0.8, ε_cu=0.0035,
  ρ_max=4% CANDIDATS — à confronter au fascicule officiel.
- `bael91r99/interaction.py` : diagramme N/M par compatibilité des déformations
  (bloc λ=0,8/η=0,85, ε_cu **paramétrés** §3.4) + `second_order_moment`.
  **Correctif unités** : conversion MPa·cm²→kN **explicite** (`K_MPA_CM2_TO_KN=10`)
  — un bug `/1000` sous-estimait les efforts d'un **facteur 100** (§5.3).
- `rps2011/seismic.py` : classification de site, spectre (forme générique),
  paramètres. **Notes enrichies** : classes S1..S4 confirmées ; coefficients S/Tc/Td
  candidats ; γI (1.0/1.2/1.4), q (selon système) à confirmer. Analyse modale,
  dérives, torsion, ductilité **non implémentés** (spec §11.3).

> ⚠️ **Aucun article BAEL/RPS n'est confirmé contre l'édition officielle.**
> Les statuts restent `A_VALIDER` / `VERIFICATION_NON_IMPLEMENTE` tant que
> l'ingénieur n'a pas confronté chaque formule au texte réglementaire.

### SOLVER — **PRUVÉ et testé**
- `column_design.py` : `ColumnDesigner.search()` — étapes 1-10 de la spec §10.4.
  Génération → géométrie → élancement → compression → armatures → classement
  explicite (critères visibles) → `requires_global_reanalysis()`. Ne code
  **aucune** formule réglementaire (appelle REGULATION).
- `loads.py` : **descente de charges + combinaisons internes** (§9).
  `apply_combination` lit les coefficients dans `LoadCombination` (§9.2, jamais
  codés en dur) ; `line_load_from_area` / `point_load_from_area` (§9) prennent
  la géométrie de répartition en ENTRÉE (jamais déduite, §4.2) ; un cas sans
  valeur est signalé manquant (pas un zéro silencieux). Tests §17.2.

### REPORTING — **PRUVÉ et testé**
- `column_report.py` : fiche de poteau (§15.2), résumé de projet (§15.3).
  Affiche les statuts honnêtes, données manquantes, avertissement permanent.
  Ne transforme **jamais** une étude incomplète en document conforme.
- `exports.py` : exports **XLSX** (openpyxl) et **PDF** (reportlab) §15.3.
  Parseur Markdown commun → la sortie exportée est **identique** à l'affichage
  (source de vérité unique, aucun statut masqué). Bibliothèque absente ⇒
  erreur explicite (jamais de faux succès).

### GUI (PyQt6) — **PRUVÉ (fumée) et testé**
- `main_window.py` : 9 menus (§14.1), 5 espaces de travail (§14.2),
  tableau de bord (§14.3), QThread pour opérations longues (§14.4).
- **v1.2 — workflow « lancer le projet »** :
  - `Projet > Ouvrir…` → `integration/interop/loader.py` (`load_project_file`)
    charge un `.rtd` (Robot) ou `.dwg` (AutoCAD) dans le pivot SC-* — gardes
    §5.4 : projet Robot étranger = **refus motivé** ; document déjà ouvert =
    réutilisé en **lecture seule** (jamais fermé/modifié) ; fermeture sans save
    **uniquement** ce que le programme a ouvert ; 0 objet lu = 0 rapporté ;
    lecture `PARTIAL` = chargé **+ dévoilé** (`LoadResult.status` + détails du
    motif dans le message — jamais présenté comme un plein succès).
  - `Modèle > Vérifier la cohérence` → `core/coherence.py` : géométrie,
    références de nœuds, `data_gaps()` (§4.2), valeurs ASSUMED listées (§4.5) —
    **aucune conformité déclarée** (§20).
  - `Intégrations > Workflow complet` (menu + bouton barre d'outils) →
    échanges de la boucle selon les cases cochées, puis constats de cohérence,
    rapport Markdown dans l'onglet Rapports (`_WorkflowThread`, §14.4).
  - Threads dédiés `_ObjThread` / `_WorkflowThread` ; smoke offscreen OK.
- `dashboard.py` : cartes d'agrégats + bandeau d'avertissement (§20).
- `detector_stub.py` : détection légère (registre/dossiers + **sonde du Named
  Pipe add-in Revit**, sans COM lourd) — **libellés alignés sur la réalité
  v1.2** : AutoCAD = câblé/live (l'ancien libellé « non câblé (Phase 7) » était
  périmé), Revit = prêt **uniquement** si l'add-in répond sur `structcalc_revit`
  (PARTIAL : mise à jour, jamais création), Robot = câblé/live ; §20 rappelé.
- **Aucune formule dans l'UI** (§14.6) — testé.

### REPORTING / entry point
- `main.py` : `python main.py` lance l'application.

---

## 2bis. Flowchart de projet global

`docs/FLOWCHART.md` — chaîne complète du dossier architectural au document
validé, avec l'intégration du **Module 71 (Architectural-to-Structural
Formwork Engine)** : portes de validation, dépendances inter-modules et mapping
vers le code existant. Le Module 71 est **implémenté** dans
`structcalc/architectural_structural/` (15 sous-modules + `model_ext`),
couvert par `tests/unit/test_module71_reference.py` et
`tests/unit/test_module71_pipeline.py`. Vérification de bout en bout :
`python tools/verify_module71_pipeline.py`.

Reste **non branché** (statut explicite, §19) : les adaptateurs d'import
Revit/IFC/DWG/PDF retournent `ADAPTER_NOT_IMPLEMENTED` — seules les données
structurées (`RawGeometryImporter`) sont opérationnelles ; le vrai échange
Robot (COM) reste porté par `integration/robot`.

---

## 3. Livrables Phase 0 (audité)
- `docs/phase0/AUDIT_PHASE0.md` : environnement, API vérifiées + pièges,
  architecture, arborescence, protocole de tests, risques, plan.
- Outils de sondage `tools/*.py` + résultats JSON.

---

## 4. Reste à faire (priorisé)

| # | Tâche | Blocage / note |
|---|---|---|
| 1 | **Confirmer les articles BAEL 91 r99** contre l'édition officielle → passer `verified=True` | Requiert le texte réglementaire ; condition pour tout « Conforme » |
| 2 | Confirmer les coefficients **RPS 2011** (site, spectre) | Idem |
| 3 | ~~Robot : **combinaisons** (`Cases.CreateCombination`)~~ | **FAIT** — signature prouvée statiquement (`robotom.tlb`, `IRobotCaseServer(int,str,enum,enum,enum)`) + **live Robot 2027** (`tools/probe_create_combination_live.py`) : ordre `(number, name, comb_type, case_nature, case_analize_type)` confirmé par lecture de retour, `CaseFactors.New` membre ajouté. `loads.create_combination` implémenté |
| 4 | ~~Robot : **type d'enregistrement** charge barre uniforme~~ | **FAIT + BUG CORRIGÉ** — `I_LRT_BAR_UNIFORM=5` (TLB + live), chaîne prouvée `Records.New(5)`→`Get(idx)`→`Objects.FromText(list)`→`SetValue(2, fz)`. L'ancienne chaîne (`Create`/`rec.Objects=`/`rec.Fz=`) était **fausse** (Objects = objet FromText ; Fz = SetValue(2,..)) |
| 5 | ~~Robot : **contrôle des unités** des résultats (§5.3)~~ | **FAIT** — `results.get_result_units` lit `Preferences.Units.Get(type).Name` (pruvé live `tools/probe_units_live.py` : force=kN, moment=kN, disp=cm, length=m, stress=MN) et **attache** les unités réelles à chaque réaction/déplacement (unité illisible = None, jamais supposée) |
| 6 | ~~Robot : **effets du 2e ordre** + **flexion composée** (diagramme d'interaction)~~ | **FAIT côté réglementaire** — `bael91r99/interaction.py` (diagramme N/M + amplification 2ᵉ ordre), tests §17.2. Reste : câbler les **résultats Robot** (N, M) en entrée |
| 7 | Descente de charges + combinaisons internes (couche SOLVER) | **FAIT** — `solver/loads.py` (`apply_combination` lit `LoadCombination.factors` §9.2 ; descente surfacique→ligne/point §9 ; cas manquant signalé, géométrie = entrée §4.2) |
| 8 | **Revit** : vérifier intégration native 2027 / SMXX, ou add-in .NET pont | §6.2 |
| 9 | ~~Exports **XLSX/PDF** du reporting~~ | **FAIT** — `reporting/exports.py` (parseur Markdown commun → openpyxl/reportlab ; source de vérité unique, statuts honnêtes préservés, lib absente = erreur explicite) |
| ~~10~~ | ~~AutoCAD / Civil 3D connecteurs~~ | **FAIT** — `integration/interop/` (AutoCAD COM prouvé, Civil 3D = hôte DWG + refus objets .NET) |
| ~~11~~ | ~~Connecteur Navisworks + corrections~~ | **FAIT** — `navisworks.py` (COM prouvé live DWG→NWD) ; **corrigé** : diagnostic Civil 3D (ProgIDs `AeccX*` existent mais inactivables en externe) + **bug import** `autocad.py` (`..core`→`...core`, poutres/dalles non créées à la lecture) |
| ~~12~~ | ~~Connecteur Advance Steel~~ | **FAIT** — `advsteel.py` (hérite AutoCAD, DWG de niveau dessin) ; sémantique acier `AstorMain5` refusée motivée (coclasses non enregistrées en COM externe, §19) |
| ~~13~~ | ~~Add-in **Revit .NET** (pont Named Pipe)~~ | **FAIT (squelette complet)** — `StructCalcAddin/` (IExternalApplication, ruban Lire/Écrire modèle, serveur NDJSON, DTOs Node/Bar/Section/Material/Rebar, commandes transaction) + client Python `interop/revit_addin_client.py` + déploiement `tools/deploy_revit_addin.py`. **COMPILÉ (0 erreur, net10.0-windows) + DÉPLOYÉ + PROUVÉ LIVE (18/10/2026)** : PING/NDJSON + roundtrip READ_MODEL prouvés via `tools/live_test_revit_addin.py` (refus « Aucun document Revit actif » = preuve du canal) ; connecteur Python `revit.py` à sonde PING dynamique (capacités PARTIAL/NOT_SUPPORTED retournables) ; 13 tests déterministes `tests/unit/test_revit_addin_pipe.py` (serveur mocké byte-mode) |
| ~~14~~ | ~~GUI **Boucle logiciels** (cases à cocher) + **missions par logiciel**~~ | **FAIT** — `gui/loop_tab.py` : 6 logiciels cochables, rôle Conception / Étude / les deux, plan de **boucle fermée** (`interop/loop.py`, logique pure testée : 31 tests). **« Chaque logiciel accomplit les missions dont il est conçu »** (`PROFILES` + `mission_legs`) : Robot = `write_loads` + `read_results` (étude), AutoCAD/Civil 3D/Advance Steel = plans DWG, Navisworks = coordination NWD (refus motivé sans chemin de fichier), Revit = modèle BIM (refus motivé sans add-in). Exécution réciproque via hub en QThread (§14.4), chaque refus affiché avec son motif (jamais de faux succès). Démo : `python tools/demo_loop_missions.py` |
| ~~15~~ | ~~**N° de version** + livrable **.exe**~~ | **FAIT** — `structcalc/version.py` (source unique, actuellement **v1.2.0** : titre, À propos, statut, selftest) miroir `version_info.txt` (ressource PE) ; build `tools/build_exe.py` / spec `build/STRUCTCALC_PRO_1.2.0.spec` (PyInstaller onefile windowed) → `dist/STRUCTCALC_PRO_1.2.0.exe` + autotest `--selftest` du binaire compilé (**PASS**, version PE 1.2.0 vérifiée) |
| ~~16~~ | ~~**Combinaisons / démarches / cas d'industrie** complets~~ | **FAIT** — `interop/combinaisons.py` : **30 sens dirigés** (missions source + cible + démarche bureau d'études), **7 démarches** (bâtiment BIM, sans BIM, charpente acier, site/VRD, coordination NWD, acier complet, boucle 6 logiciels), **6 cas d'industrie** (bâtiment, réhabilitation, charpente, site/VRD, coordination, bureau intégré). Doc générée `docs/COMBINAISONS_ET_DEMARCHES.md` (`tools/gen_combos_doc.py`), onglet GUI **Combinaisons** (matrice 6×6 évaluée par le hub : OK/REFUS+motif, démarches, cas). 32 tests logique pure |
| ~~17~~ | ~~**v1.2 : lancer un projet (Plan-villa) + workflow complet + vérifications**~~ | **FAIT** — `Projet > Ouvrir…` (`integration/interop/loader.py`, **12 tests** : gardes §5.4, lecture seule pour document ouvert, aucun faux succès, **PARTIAL dévoilé** via `LoadResult.status`), `Modèle > Vérifier la cohérence` + `Intégrations > Workflow complet` (`core/coherence.py`, 14 tests) ; smoke offscreen OK ; détection **corrigée** (libellés AutoCAD/Revit alignés sur la réalité, sonde pipe add-in) ; `_active()` AutoCAD **durci** (validation `Documents.Count` + repli `Dispatch` rattachement-only) ; script vérification : `PARTIAL` rendu en **PARTIAL** (jamais reformulé en REFUS/OK) ; **308 tests PASS**, selftest PASS, `dist/STRUCTCALC_PRO_1.2.0.exe` (PE 1.2.0) ; vérification live 9 phases relancée sur `Plan-villa.dwg` (sujet paramétrable) |

---

## 5. Protocole de vérification

```bash
# Unitaires (rapide, sans Robot)
python -m pytest tests/unit -q

# Intégration Robot (lance le vrai Robot — séquentiellement)
python -m pytest -m robot tests/integration_robot -v
```

Toute nouvelle vérification réglementaire doit fournir (spec §17.2) :
1. la référence exacte (titre, édition, article) ;
2. l'équation transcrite ;
3. un **cas de référence** avec calcul manuel ;
4. un test de non-régression.
