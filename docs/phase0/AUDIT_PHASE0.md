# STRUCTCALC PRO — Phase 0 : Audit technique

> **Statut de la phase** : EN COURS / TERMINÉE (voir §9 Synthèse)
> **Règle appliquée** : aucune intégration n'est déclarée acquise sans vérification
> **Dernière mise à jour** : Phase 0

---

## 1. Inventaire de l'environnement

### 1.1 Système et runtime

| Composant | Valeur vérifiée | Source |
|---|---|---|
| OS | Microsoft Windows 10 Professionnel — Build **19045** | `Win32_OperatingSystem` |
| Architecture | 64-bit (AMD64) | — |
| Python | **3.12.10** (`MSC v.1943 64 bit`) | `sys.version` |
| Emplacement Python | `C:\Users\Admin\AppData\Local\Programs\Python\Python312` | `sys.executable` |
| .NET Framework | **4.8** (4.8.09037 / 4.8.04084) | Registre NDP |

### 1.2 Dépendances Python présentes

| Paquet | Version | Rôle dans STRUCTCALC PRO |
|---|---|---|
| PyQt6 | 6.11.0 (Qt 6.11.0, sip 13.11.1) | Couche GUI |
| numpy | 1.26.4 | Algèbre linéaire, sections |
| scipy | 1.16.0 | Calculs numériques, recherche d'armatures |
| openpyxl | 3.1.5 | Export XLSX |
| pytest | 8.4.2 | Tests unitaires / non-régression |
| pywin32 | installé en Phase 0 | Pont COM vers Robot |
| comtypes | 1.4.17 | Pont COM typé (RobotOM) |

> **Constat corrigé** : `pywin32` et `comtypes` étaient **absents** au démarrage
> de l'audit (seul `pywin32-ctypes`, simple utilitaire PyInstaller, était
> présent). Ils ont été installés. **Sans eux, aucun pont COM n'est possible.**
> C'est désormais une dépendance explicite du projet.

### 1.3 Compatibilité Python 3.12

- PyQt6 6.11, numpy, scipy, openpyxl, pytest : **confirmés chargés** sous 3.12.
- pywin32 / comtypes : **confirmés fonctionnels** sous 3.12 (sondage Robot réussi).
- Aucun blocage identifié sur le runtime.

---

## 2. Inventaire des logiciels Autodesk installés

| Logiciel | Version | Dossier constaté | Statut |
|---|---|---|---|
| **Robot Structural Analysis Professional** | 2027 | `...\Autodesk\Robot Structural Analysis Professional 2027` | Installé — **connecté (Phase 0)** |
| **Revit** | 2027 | `...\Autodesk\Revit 2027` | Installé — API .NET présente |
| **AutoCAD** | 2027 | `...\Autodesk\AutoCAD 2027` | Installé — COM AutoCAD 26 |
| Navisworks Manage | 2027 | `...\Autodesk\Navisworks Manage 2027` | Installé |
| Civil 3D (Object Enabler) | 2027 | présent | Object Enabler détecté |
| Robot Structural Analysis | — | clé registre `HKLM\SOFTWARE\Autodesk\Robots` vide | Version via API |

---

## 3. Analyse de l'interface Robot (priorité spec §5)

### 3.1 Mécanisme d'automatisation identifié

| Élément | Constat vérifié |
|---|---|
| ProgID COM | **`Robot.Application`** — **instançiation RÉUSSIE** |
| Version COM (`app.Version`) | **27.0** |
| Version interne (`app.ProgramVersion`) | **40.0.0.12707** |
| TypeLib | `Exe\robotom.tlb` (1 536 Ko) — **charge via comtypes** |
| Interop .NET | `Exe\Interop.RobotOM.dll` (1 848 Ko) |
| Autres interops | `Interop.IDbRootLib.dll`, `robwinInterop.dll` |
| Coclasses exposées | **573** |

**Conclusion** : l'automatisation passe par l'API **RobotOM** (COM/TypeLib),
consommable depuis Python via `comtypes` (binding typé) ou `pywin32`
(binding dynamique). Le SDK Autodesk est livré sur le poste.

### 3.2 Documentation et SDK livrés

Dossier `...\Robot Structural Analysis Professional 2027\SDK\` :

- `Robot API.pdf` (**21,9 Mo** — référence complète)
- `Robot API.chm` (7,1 Mo — aide contextuelle)
- `Getting Started Guide Robot API.pdf`
- `Robot API SteelDesign.pdf`
- `How To Create Add-In extension.pdf`
- Exemples : `Samples\RobotSDKSample_Steel`, templates RCUAPI
- Projets add-in C# / VB.NET prêts (`Add-In\MyAddin*`)

> La **vérification documentaire** de chaque méthode d'échange doit s'appuyer
> sur `Robot API.pdf` / `.chm`, pas sur la supposition.

### 3.3 Arbre API réellement accessible (sondé)

**`app.Project` — 38 membres** (liste exhaustive sondée) :

```
ActiveModel, AxisMngr, Backgrounds, CalcEngine, Close, ComponentMngr,
ConcrReinfEngine, Connections, DimServer, ExtFileName, ExtFileParams,
FileInsertParams, FileName, InsertExtFile, IsActive, Name, New,
NewFromTemplate, Open, OpenExtFile, Preferences, PrintEngine,
ReadExtFileParams, Save, SaveAs, SaveAsExtFile, SaveToFormat,
Structure, Type, UniqueId, ViewMngr   (+ méthodes IUnknown/IDispatch)
```

**Points d'API critiques vérifiés** (pièges relevés par sondage) :

| Supposition naïve | Réalité vérifiée | Source de la vérité |
|---|---|---|
| `Project.Model` | **N'existe pas** (ni en binding dynamique, ni typé) | sondage + SDK |
| `Project.ActiveModel` = serveur modèle | **Non** : méthode renvoyant une *enum* (type de modèle actif) | TypeLib |
| accès modèle | **`Project.Structure`** | code SDK officiel (`Robot.cs`, `Class1.cs`) |
| `serveur.Count` | **Non** : `serveur.GetAll().Count` | SDK |
| `serveur.Item(id)` | **Non** : `serveur.Get(id)` | SDK |
| `Project.New()` sans argument | **Échec** « nombre de paramètres non valide » | sondage |
| ouverture projet | **`Project.New(type)`** — ex. `New(1)` = `I_PT_FRAME_2D` | sondage + TypeLib |
| sections / matériaux | via **`Structure.Labels.GetAvailableNames(I_LT_*)`** | SDK |
| fermeture | **`Project.Close()`** sans argument | sondage |

> Toute première implémentation naïve se tromperait sur au moins trois de ces
> points. Ils sont la valeur principale de cette Phase 0.

**Coclasses RobotOM par domaine fonctionnel** (extraction sur 573 types) :

| Domaine | Types | Couverture spec |
|---|---|---|
| Appuis / Liaisons | 125 | §5.3 appuis, liaisons, relâchements |
| Structure / Objets | 54 | §5.3 nœuds, barres, coques, voiles |
| Béton / Armatures | 37 | §10 poteaux, §11 BAEL/RPS |
| Calcul / Modal | 35 | §5.3 résultats, modes propres |
| Résultats | 34 | §5.3 efforts, réactions, déplacements |
| Charges / Cas | 18 | §5.3 cas de charges, combinaisons |
| Sections / Matériaux | 18 | §5.3 sections, matériaux |
| Géométrie / Axes | 4 | axes, systèmes |

> La couverture déclarée ci-dessus est une **présomption de disponibilité**
> basée sur la présence des coclasses. Elle doit être **confirmée objet par
> objet** en Phase 2 (chaque échange testé sur modèle de test).

### 3.4 Serveurs d'objets ciblés (à confirmer en Phase 2)

Les serveurs attendus sur `ActiveModel` pour les échanges bidirectionnels :
`Bars`, `Nodes`, `Cases`, `Combos`, `Materials`, `Sections`, `Stories`,
`AnalysisResults`, `Supports`, `Shells`, `CalcEngine`, `ConcrReinfEngine`.

> Le sondage de l'arbre `ActiveModel.*` a échoué tant qu'**aucun projet
> n'était ouvert** (`IsActive = 0`). L'ouverture d'un projet est un préalable
> obligatoire à toute exploration ou écriture du modèle — voir §5 « Ouverture
> de projet », en cours de résolution.

---

## 4. Analyse de l'intégration Revit (priorité spec §6)

| Élément | Constat vérifié |
|---|---|
| Revit installé | 2027 |
| API .NET | `RevitAPI.dll` (33,2 Mo), `RevitAPIUI.dll` (3,3 Mo) |
| API IFC | `RevitAPIIFC.dll` |
| API structure | `RevitAPISteel.dll` |
| Résultats structurels | `StructuralAnalysisResults.dll` |
| Add-in Robot dédié dans `AddIns` | **Aucun détecté** |
| Mécanisme | **.NET uniquement — pas de COM comme Robot** |

**Conséquence (conforme à la spec §6.2 et §6.3)** : Revit ne peut pas être
piloté « comme une bibliothèque Python ordinaire ». Les voies à étudier, dans
l'ordre de préférence de la spec :

1. **Intégration native Revit–Robot** — à privilégier si elle couvre le besoin
   (évite de reconstruire un mécanisme existant). *À vérifier sur 2027.*
2. **Fichiers intermédiaires (SMXX)** — format d'échange structurel
   Revit↔Robot. *Compatibilité 2027 à confirmer.*
3. **Extension Revit .NET** — add-in développé, respectant l'environnement
   d'exécution et les transactions Revit (jamais comme lib Python directe).
4. **Échange structuré interne documenté** — via format interne STRUCTCALC.

> Aucune de ces voies n'est déclarée opérationnelle en Phase 0.

---

## 5. Preuve de connexion Robot (livrable spec §0)

**Opération réalisée et reproductible** :

```
win32com.client.Dispatch("Robot.Application")  →  OK
app.Version        → 27.0
app.ProgramVersion → 40.0.0.12707
app.Project        → objet IRobotProject, 38 membres
```

- Sondes écrites dans `structcalc_pro/tools/probe_robot*.py`.
- Résultats JSON : `robot_probe_result.json`, `robot_api_tree.json`, …
- **Fermeture propre** vérifiée : `Project.Close(False)` / `app.Quit()`.
- **Aucun fichier projet modifié ou enregistré** lors des sondes.

**Limite de cette preuve** : la connexion et la lecture de l'arbre `Project`
sont démontrées. La **création/lecture d'objets du modèle** (nœuds, barres,
charges, résultats) n'est **pas encore démontrée** — elle conditionne la
Phase 2 et dépend de la résolution de l'ouverture de projet (`§ ci-dessous`).

### 5.1 Résolution : ouverture de projet et opération réelle

**Démonstration finale validée** (`tools/probe_structure_final.py`) :

```
win32com.client.Dispatch("Robot.Application")   -> Robot 40.0.0.12707
proj.New(1)                                     -> IsActive = -1 (projet ouvert)
S = proj.Structure                              -> serveur de modèle
S.Nodes.Create(1, 0,0,0) ; S.Nodes.Create(2, 4,0,0)
S.Bars.Create(1, 1, 2)
S.Nodes.GetAll().Count -> 2      (attendu 2)  [OK]
S.Bars.GetAll().Count  -> 1      (attendu 1)  [OK]
S.Nodes.Get(1) -> X=0 Y=0 Z=0                 [OK]
S.Bars.Get(1)  -> Start=1 End=2               [OK]
S.Labels.GetAvailableNames(21) -> 3 sections   [OK]
proj.Close()                                   -> sans sauvegarde
```

**Contrôles de cohérence : TOUS OK.** C'est la **première opération réelle,
documentée et reproductible** exigée par la spec (§0, §21).

**Serveurs réellement présents sur `Project.Structure`** (sondés) :

| Serveur | État | Membres métier notables |
|---|---|---|
| `Nodes` | OK (34) | Create, Get, GetAll, Delete, SetLabel, GetCalcSupport |
| `Bars` | OK (46) | Create, Get, GetAll, SetLabel, SetStructuralType, GetElemsData |
| `Cases` | OK (31) | CreateSimple, CreateCombination, GetAll |
| `Labels` | OK (25) | GetAvailableNames, SetLabel |
| `Selections` | OK (15) | Create, CreateFull |
| `Results` | OK (19) | Nodes.Reactions, Nodes.Displacements (à confirmer Phase 2) |
| `Combos` | **absent** | combinaisons via `Cases.CreateCombination` |
| `Materials` / `Sections` | **absent** | via `Labels` |
| `Stories` | **absent** | géré autrement (à documenter) |

**Méthodes de calcul observées dans le SDK** : `Project.CalcEngine.Calculate()`,
résultats via `Structure.Results.Nodes.Reactions.Value(n, case)` /
`.Displacements.Value(n, case)` — à valider en Phase 2 sur modèle chargé.

---

## 6. Schéma d'architecture (cible)

```
                 ┌─────────────────────────────────────────────┐
                 │                 GUI (PyQt6)                 │
                 │  projet · modèle · intégrations · calculs   │
                 └───────────────────────┬─────────────────────┘
                                         │ (aucune formule ici)
   ┌─────────────┬───────────────┬───────┴────────┬───────────────┬────────────┐
   │   SCOPE     │    SOLVER     │  REGULATION    │  INTEGRATION  │  REPORTING │
   │ périmètre   │ descente      │ BAEL 91 r99    │ Robot ▸◂      │ notes calc │
   │ variantes   │ combinaisons  │ RPS 2011       │ Revit         │ fiches     │
   │ hypothèses  │ poteaux       │ statuts        │ AutoCAD       │ XLSX/PDF   │
   └──────┬──────┴───────┬───────┴────────┬───────┴───────┬───────┴──────┬─────┘
          │              │                │               │              │
   ┌──────┴──────────────┴────────────────┴───────────────┴──────────────┴─────┐
   │                    CORE — modèle interne (sans dépendre de Qt/COM)        │
   │  Project · Building · Storey · Node · Column · Beam · Slab · Wall         │
   │  Material · CrossSection · Support · LoadCase · LoadCombination           │
   │  AnalysisModel · AnalysisResult · DesignCheck · Revision · Issue          │
   │  + statuts (PROVIDED/IMPORTED/…) + identifiants SC-* + provenance         │
   └───────────────────────────────────────────────────────────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              │   SQLite (projets)    │
                              │   JSON (échange)      │
                              └───────────────────────┘
```

**Règle de dépendance** : `CORE` ne dépend ni de PyQt6, ni de Robot, ni de
Revit. `INTEGRATION` dépend de `CORE` et des ponts COM/.NET, jamais l'inverse.

---

## 7. Arborescence cible du dépôt

```
structcalc_pro/
├── docs/
│   └── phase0/                  # audits, fiches compatibilité
├── tools/                       # sondes Phase 0 (audit, non productif)
│   ├── probe_robot.py
│   ├── probe_robot_early.py
│   ├── probe_new_win32.py
│   └── *.json                   # résultats d'audit
├── structcalc/
│   ├── core/                    # modèle interne (indépendant)
│   │   ├── model.py             # Project, Node, Column, Beam…
│   │   ├── ids.py               # générateurs SC-*
│   │   ├── status.py            # statuts de données
│   │   └── store.py             # persistance SQLite
│   ├── scope/                   # périmètre d'étude, variantes
│   ├── solver/                  # descente de charges, combinaisons
│   ├── regulation/
│   │   ├── base.py              # registre référentiel
│   │   ├── bael91r99/
│   │   └── rps2011/
│   ├── integration/
│   │   ├── base.py              # interface d'adaptateur
│   │   └── robot/
│   │       ├── connection.py    # connexion/fermeture
│   │       ├── api.py           # helpers RobotOM typés
│   │       ├── import_model.py
│   │       ├── export_model.py
│   │       ├── export_loads.py
│   │       ├── import_results.py
│   │       ├── mapping.py       # SC-* ↔ Robot
│   │       ├── synchronization.py
│   │       └── validation.py
│   ├── reporting/
│   └── gui/                     # PyQt6
├── tests/
│   ├── unit/
│   ├── reference/               # cas de référence réglementaires
│   └── integration_robot/       # modèles de test Robot
├── pyproject.toml
└── README.md
```

---

## 8. Protocole de test minimal (Phase 0 → Phase 2)

**Jeu de modèles Robot de test** (spec §17.3), à créer et valider un à un :

| # | Modèle | Objet vérifié |
|---|---|---|
| T1 | 1 barre libre | connexion, création nœud+barre, relecture |
| T2 | Poutre + charge connue | efforts calculés vs valeur théorique |
| T3 | Portique simple | appuis, combinaisons, réactions |
| T4 | Multi-étages | stories, transfert vertical, résultats |
| T5 | Multi-matériaux/sections | mapping matériaux et sections |
| T6 | Cas + combinaisons | export charges, concomitance |

**Critère de réussite d'un transfert** (spec §20) : objet présent des deux côtés,
identifiant correspondant, unités contrôlées, valeur vérifiée.

**Problématique de test** : les sondes ouvrent l'UI Robot, incompatible avec un
pytest parallèle. Prévoir des **doubles de test** clairement identifiés
(spec §19) pour l'unit-test, et des tests d'intégration séquentiels et isolés.

---

## 9. Risques techniques identifiés

| # | Risque | Impact | Atténuation |
|---|---|---|---|
| R1 | ~~`Project.New()` : signature inconnue~~ **RÉSOLU** | — | `New(type)` ex. `New(1)` ; accès via `Structure` (doc SDK + sondage) |
| R2 | Pilotage Robot = UI ouverte (pas de headless) | Tests parallèles difficiles | Doubles de test + sérialisation des tests COM |
| R3 | Revit : API .NET, pas de COM | Pas de pilotage Python direct | Intégration native, SMXX, ou add-in .NET |
| R4 | Correspondance SC-* ↔ Robot non garantie | Perte de mapping | Table de correspondance + validation post-transfert |
| R5 | Suppression vs objet non exporté | Suppression accidentelle | Aucune suppression sans règle explicite (spec §5.4) |
| R6 | Double comptage des charges | Résultat faux | Contrôles d'équilibre + provenance (spec §9.1) |
| R7 | Version 2027 = API récente | Doc/ exemples antérieurs non valides | Vérification sur la version installée uniquement |
| R8 | BAEL/RPS transcrits sans preuve | Non-conformité réglementaire | Tests de référence + statut VÉRIFICATION_NON_IMPLÉMENTÉE |

---

## 10. Synthèse Phase 0

### Acquis vérifiés
- Environnement compatible : Windows 10, Python 3.12, PyQt6, numpy, scipy.
- **Connexion Robot 2027 établie** via `Robot.Application` (COM/RobotOM).
- **Première opération réelle validée** : création + relecture de nœuds et
  barres dans Robot, fermeture sans sauvegarde (contrôles de cohérence OK).
- Arbre API cartographié ; accès modèle par **`Project.Structure`**.
- Pièges d'API identifiés et documentés (`GetAll()`, `Get()`, `New(type)`).
- Documentation + SDK Robot livrés et localisés.
- Revit 2027 : API .NET identifiée, voies d'intégration listées.

### Non acquis (ne pas déclarer opérationnel)
- Charges, combinaisons, résultats (efforts, réactions, déplacements).
- Tous échanges bidirectionnels complets (mapping SC-* ↔ Robot).
- Intégration Revit, AutoCAD, Civil 3D.
- Toute conformité réglementaire BAEL/RPS.

### Prochaine action (Phase 1 + Phase 2)
1. **Phase 1** : `core/model.py` (objets SC-*) + `ids.py` + SQLite + tests.
2. **Phase 2** : monter les sondes vers un vrai module
   `integration/robot/{connection,import_model,export_model}.py` en
   réutilisant les chemins API vérifiés, puis étendre aux charges et
   résultats sur les modèles de test T2–T6.
