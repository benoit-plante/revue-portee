# 03 — Architecture

> **Statut** : version du 7 octobre 2026, validée par Benoit (pile technique : D-011; format de projet : D-012; licence : D-004 — voir le [journal](journal-des-decisions.md)). Une session de développement qui s'en écarte doit le signaler et le justifier dans sa demande de fusion.
> **Prérequis** : [02-exigences.md](02-exigences.md) (les identifiants `EF-…` et `ENF-…` y renvoient).

## 1. Vue d'ensemble

```
┌───────────────────────────────────────────────────────────────────────┐
│  Poste de l'utilisateur                                               │
│                                                                       │
│  Navigateur ──HTTP (127.0.0.1)──► revue_portee.web (FastAPI + HTMX)   │
│  Terminal  ─────────────────────► revue_portee.cli (Typer)            │
│                                         │                             │
│                         services applicatifs (cas d'usage)            │
│      ┌──────────┬──────────┬──────────┬──────────┬───────────┐        │
│      │ protocol │ search   │ collect  │ screening│ reporting │ …      │
│      └────┬─────┴────┬─────┴────┬─────┴────┬─────┴─────┬─────┘        │
│           │      domain (modèles, versionnement, impact, journal)     │
│           │          │          │          │           │              │
│      storage (dossier de projet : SQLite + fichiers bruts)            │
│                      │          │          │                          │
│               sources (connecteurs)    ai (couche d'abstraction)      │
└──────────────────────┼──────────────────────┼─────────────────────────┘
                       ▼                      ▼
      OpenAlex, PubMed, Crossref,     Anthropic (Claude) · classificateur
      Unpaywall, OAI-PMH (V2)         local (scikit-learn) · modèle local
                                      (API compatible Ollama/OpenAI, V3)
```

**Principes d'architecture**

1. **Le domaine ne dépend de rien d'externe.** Les modules `domain` ne connaissent ni la base de données, ni le web, ni les fournisseurs d'IA. Ils sont testables sans réseau ni disque.
2. **Ajout seulement.** Décisions, versions et journal ne sont jamais modifiés ni supprimés (ENF-TRA-02). L'« état courant » d'une référence est **calculé** à partir de ses décisions.
3. **Tout ce qui sort d'un appel externe est conservé brut** (réponses de modèles, pages d'API), puis interprété. On peut toujours réinterpréter sans rappeler (ENF-REP-02).
4. **Les normes sont des données** : listes PRISMA-ScR, gabarit de diagramme, correspondance OSF, tarifs des modèles sont des fichiers YAML versionnés dans `src/revue_portee/resources/`, avec leur source et leur date.
5. **Un connecteur par source, une implémentation par fournisseur d'IA**, derrière une interface commune.

## 2. Pile technique

| Besoin | Choix (D-011) | Licence | Raison |
|---|---|---|---|
| Langage, gestion | Python ≥ 3.12, **uv** (décidé) | — | Décision prise |
| Serveur web | FastAPI + Uvicorn | MIT / BSD | Simple, typé, standard |
| Interface | Gabarits Jinja2 rendus côté serveur + **HTMX** (fichier statique vendu dans le dépôt) | BSD / BSD-2 | Aucune chaîne de compilation JavaScript; développement possible dans la VM avec Python seulement |
| Modèles de données | Pydantic v2 | MIT | Validation, schémas JSON pour les sorties structurées de l'IA |
| Stockage | SQLite (module standard) via SQLAlchemy 2.0 Core; migrations Alembic | MIT | Un seul fichier par projet, transactions, rapide jusqu'à des centaines de milliers de lignes |
| HTTP | httpx | BSD | Synchrone et asynchrone, facile à simuler |
| Ligne de commande | Typer | MIT | |
| RIS | Lecteur du projet (`sources/ris.py`, D-056) | — | Tolère les variantes des vrais exports et signale chaque enregistrement vide ou mal formé; rispy, envisagé au départ, n'est pas utilisé |
| Appariement approximatif | RapidFuzz | MIT | Dédoublonnage (D-062) |
| Classificateur rapide | scikit-learn | BSD | TF-IDF + régression logistique, étalonnage |
| Claude | SDK `anthropic` | MIT | Sorties structurées, mise en cache des invites, lots asynchrones |
| PDF → texte avec pages (V2) | PyMuPDF par défaut (compatible avec l'AGPL, D-004); pypdf ou pdfplumber en solution de rechange — choix confirmé par un essai comparatif à la tranche 2.1 | AGPL / BSD / MIT | Fiabilité de l'extraction avec pages |
| DOCX | python-docx | MIT | Protocole, section méthode |
| Diagramme de flux | Gabarit SVG paramétré (Jinja2), conversion PNG/PDF par CairoSVG (V2) | LGPL | Déterministe, pas de dépendance graphique lourde |
| Internationalisation | Babel (catalogues gettext) | BSD | ENF-LAN-03 |
| Client HTTP des connecteurs | httpx2 | BSD-3-Clause | Mandataire et certificats de l'environnement respectés (`trust_env`) |
| Tests | pytest, pytest-recording (VCR.py), respx, pytest-cov (coverage) | MIT / BSD / Apache-2.0 | Réponses enregistrées (ENF-QUA-01) : vcrpy pour `httpx`, mécanisme du projet pour `httpx2` (D-047); couverture et seuil de 90 % par paquet (ENF-QUA-04, D-023) |
| Qualité | ruff (vérification + formatage); mypy en mode strict (D-022) | MIT | ruff préinstallé; mypy vérifie la cohérence des types (ENF-QUA-03) |

**Règle** : toute nouvelle dépendance est ajoutée avec `uv add`, sa licence est vérifiée (ENF-LIC-01) et mentionnée dans la demande de fusion.

## 3. Organisation du code

```
revue-portee/
├── CLAUDE.md                     # instructions pour Claude Code
├── README.md
├── pyproject.toml                # créé au jalon 0
├── uv.lock
├── .claude/settings.json         # hook SessionStart (jalon 0)
├── docs/                         # rédigé dans Cowork
├── src/revue_portee/
│   ├── domain/                   # aucun import externe hors pydantic
│   │   ├── ids.py                # identifiants (ULID), codes de critères
│   │   ├── references.py         # Reference, Provenance, collectes, imports, Enrichment, merged (D-055)
│   │   ├── dedup.py              # DedupRun, DuplicatePair, PairDecision, DedupSettings (D-061)
│   │   ├── criteria.py           # CriteriaVersion, Criterion, différentiel
│   │   ├── changes.py            # ChangeType, CriterionChange, qualification (EF-VER-03)
│   │   ├── suggestions.py        # suggestions de l'IA pour le cadrage et leur décision
│   │   ├── protocol.py           # sections du protocole, listes de contrôle, enregistrement
│   │   ├── framing.py            # Framing, FramingVersion (question PCC versionnée)
│   │   ├── search.py             # blocs de concepts, termes, limites, articles clés, versions
│   │   ├── sensitivity.py        # test de sensibilité : articles manqués, bloc responsable (D-051)
│   │   ├── project.py            # Project, Reviewer
│   │   ├── screening.py          # Decision, CriterionAssessment, Stage, seuils, règle EF-SEL-07 (D-068),
│   │   │                         # tours, étalonnages, budget, tirage avec graine, langue (D-073)
│   │   ├── calibration.py        # étalonnage isotonique ou de Platt, seuil suggéré (D-072)
│   │   ├── impact.py             # analyse d'impact des cinq types de changement, échantillon des
│   │   │                         # clarifications (EF-VER-04, D-077, D-081)
│   │   ├── grid.py               # GridVersion, Field, ExtractionValue (V3)
│   │   ├── metrics.py            # matrice de confusion, accord, kappa, AC1, sensibilité, spécificité,
│   │   │                         # intervalles de Wilson, courbe seuil, désaccords par critère
│   │   └── journal.py            # JournalEntry, chaîne d'empreintes
│   ├── storage/
│   │   ├── project_folder.py     # création/ouverture du dossier de projet
│   │   ├── db.py, repositories/  # accès SQLite; écritures par ProjectFolder.write() (D-036)
│   │   ├── migrate.py, migrations/ # Alembic (migrations appliquées à l'ouverture)
│   │   ├── raw.py                # réponses brutes des modèles (brut/ia/) et des API (brut/sources/), gzip
│   │   └── archive.py            # tables lisibles (CSV, JSON lines), copie de la base, zip (EF-PRJ-04)
│   ├── sources/
│   │   ├── __init__.py           # interface SearchSource, fabrique des connecteurs
│   │   ├── http.py               # client httpx2, limiteur de débit, reprise, erreurs en français
│   │   ├── openalex.py, pubmed.py # comptes, appartenance, résolution d'articles, collecte paginée
│   │   │                         # (fetch); MeSH et serveur d'historique (PubMed, D-054)
│   │   ├── records.py            # FetchedRecord, FetchedPage : notices et pages renvoyées par fetch
│   │   ├── crossref.py           # notice d'un DOI (enrichissement, D-055)
│   │   ├── unpaywall.py          # (V2)
│   │   ├── ris.py                # lecteur RIS tolérant, reconnaissance de la base (D-056)
│   │   └── oai_pmh.py            # Érudit, HAL, dépôts (V2)
│   ├── protocol/                 # cas d'usage de l'étape 1 : cadrage, critères, notes du journal,
│   │                             # suggestions et qualification par l'IA (ai_assist.py), protocole
│   ├── search/                   # cas d'usage de l'étape 2 : versions de stratégie (strategies.py),
│   │                             # comptes, articles clés, sensibilité, descripteurs (runs.py),
│   │                             # suggestions de termes (suggestions.py); traducteurs (translate.py)
│   │                             # et comparateur d'équivalence syntaxique (equivalence.py)
│   ├── collect/                  # cas d'usage de la collecte : collectes reprenables (collection.py,
│   │                             # D-053), import RIS (imports.py), enrichissement Crossref (enrichment.py),
│   │                             # dédoublonnage (deduplication.py, D-061)
│   ├── dedup/                    # dédoublonnage, fonctions pures : normalize, matching (D-062),
│   │                             # groups (liens, groupes, référence principale), counts (D-064),
│   │                             # evaluation (rappel et précision sur un jeu annoté)
│   ├── screening/                # pilote : tirage, tri humain à l'aveugle (pilot.py, D-071), lot d'IA
│   │                             # plafonné et rejeu (ai_screening.py, D-069), budget et seuils
│   │                             # (settings.py), banc SYNERGY (benchmark.py, D-074); tri principal
│   │                             # et réconciliation (main.py, D-078, D-079, D-083), lots d'IA par
│   │                             # l'API Batches (batch_ai.py, D-080), analyse d'impact et
│   │                             # réévaluation (reassessment.py, D-081, D-082); rapports : diagramme
│   │                             # de flux (report.py), section méthode (methods.py), archive
│   │                             # publique ou complète (archive.py, D-092)
│   ├── ai/
│   │   ├── base.py               # TaskSpec, TaskInput/TaskOutput, TaskResult, AICallRecord, ModelProvider
│   │   ├── runner.py             # run_task : exécution indépendante du fournisseur
│   │   ├── settings.py           # configuration de l'IA du projet ([ia] de projet.toml, D-039)
│   │   ├── tasks/                # définition des tâches (entrées/sorties Pydantic)
│   │   ├── providers/            # anthropic.py, classifier.py, local.py, fake.py
│   │   ├── prompts/              # un dossier par gabarit : meta.yaml, system.md.j2, user.md.j2
│   │   └── costs.py              # estimation et coût réel par appel (plafonds : screening/, D-069)
│   ├── extraction/, synthesis/, stakeholders/   # V3, V3, V4
│   ├── reporting/                # fonctions pures : document neutre (rendus Markdown, DOCX), protocole,
│   │                             # nombres du diagramme (flow.py) et son rendu SVG (flow_svg.py, gabarit
│   │                             # Jinja2 dans templates/), section méthode (methods.py), notation des
│   │                             # nombres (formats.py); plus tard PRISMA-ScR
│   ├── config/                   # paramètres, secrets (seul point d'accès aux variables d'env.)
│   │   ├── secrets.py            # lecture des secrets (SecretStr), masquage des journaux
│   │   └── secret_scan.py        # détection de secrets dans des fichiers (tests/, archive)
│   ├── jobs/runner.py            # tâches de fond dans des fils du serveur (BackgroundJobs, D-059)
│   ├── web/                      # FastAPI : routes (app.py), lecture du formulaire de stratégie
│   │                             # (search_form.py), gabarits, statique (HTMX copié, D-033)
│   ├── cli/                      # Typer : nouveau, serve, verifier-journal, protocole, banc-synergy,
│   │                             # diagramme, methode, archive
│   ├── i18n/                     # catalogues Babel (locale/fr/…/messages.po), D-031
│   ├── clock.py, version.py      # heure UTC; version de l'outil et commit (D-034)
│   └── resources/                # YAML datés : tarifs (model_prices), IA par défaut (ai_defaults),
│                                 # protocol/ (Peters et al. 2022, formulaire OSF), reporting/ (gabarit
│                                 # du diagramme PRISMA 2020, validation de l'outil); plus tard PRISMA-ScR
└── tests/
    ├── conftest.py               # blocage du réseau, filtrage des cassettes, fixture http_cassette
    ├── recording.py              # cassettes httpx2 : rejeu et enregistrement filtré (D-047)
    ├── support.py                # utilitaires partagés (horloge déterministe, projet de test)
    ├── demo.py                   # projet de démonstration construit étape par étape (fixtures/demo/)
    ├── _plugins/                 # greffons pytest du projet (seuil de couverture par paquet)
    ├── unit/
    ├── integration/              # marqueur « integration », exclus par défaut
    ├── cassettes/                # réponses enregistrées, nettoyées
    └── fixtures/                 # stratégies de référence publiées (search/), jeu annoté du dédoublonnage
                                  # (dedup/, D-060), extraits d'exports RIS
                                  # réels nettoyés (ris/, D-057), petit jeu fictif du banc (synergy/),
                                  # décompte à la main du jeu de démonstration (demo/)
```

## 4. Format du dossier de projet

Un projet de revue est un **dossier** (extension conventionnelle `.revue`, ex. `ecoanxiete-enfants.revue/`) :

```
ecoanxiete-enfants.revue/
├── projet.toml           # métadonnées, version du format, configuration de l'IA ([ia], D-039)
├── revue.sqlite          # source de vérité (toutes les tables de la section 5)
├── brut/
│   ├── ia/AAAA/MM/<ai_call_id>.json.gz       # réponses brutes des modèles (ENF-TRA-03)
│   └── sources/<id>/page-0001.json.gz        # réponses brutes des API, une par requête : comptes et
│                                             # tests de sensibilité (search_run.id), vérifications MeSH,
│                                             # pages d'une collecte (collection_run.id), lots Crossref
├── imports/<sha256>.ris  # copie exacte de chaque fichier importé (D-056)
├── textes/               # PDF et texte extrait avec pages (V2)
├── etalonnage/           # modèles d'étalonnage sérialisés, par tour de pilote
└── exports/              # fichiers générés (diagramme, protocole, méthode, archives) — régénérables
```

- `projet.toml` contient `format_version` (ex. `"1.0"`). Toute ouverture d'un projet d'un format antérieur lance les migrations après **copie de sauvegarde** automatique.
- **Aucun secret** dans le dossier de projet (ENF-SEC-01). Les réviseurs IA y sont décrits par fournisseur et modèle, jamais par clé.
- `[ia]` de `projet.toml` : supervision (mode, taille du pilote, cible de sensibilité, étalonnage) et, pour chaque tâche, statut (`enabled` / `planned`), fournisseur, modèle, paramètres et sortie attendue. Valeurs initiales : `resources/ai_defaults.yaml`; un projet sans cette section reçoit ces valeurs.
- Le dossier est **autosuffisant** : copié ailleurs, il s'ouvre sans perte.
- **Archives** (EF-PRJ-04, ENF-REP-06, D-092), écrites dans `exports/archive-<publique|complete>-<date>.zip` :
  - l'archive **publique**, à déposer (OSF), contient les données lisibles sans l'outil (CSV et JSON lines dans `donnees/` : références sans résumé ni URL, dédoublonnage, tours, décisions, état du tri, réévaluations, appels à l'IA, critères, journal, nombres du diagramme), le diagramme et la section méthode, `etalonnage/`, `projet.toml` et un `LISEZMOI.md` qui explique comment recompter chaque nombre et vérifier la chaîne d'empreintes. Ni résumé, ni URL, ni réponse brute, ni base SQLite (droits d'auteur);
  - l'archive **complète**, privée, y ajoute une copie du dossier sans `textes/` (base, `brut/`, `imports/`) : elle se rouvre avec l'outil;
  - un secret trouvé dans les fichiers texte arrête l'export; chaque export est consigné au journal (`archive.exported`) avec l'empreinte SHA-256 du fichier.
- Le dossier n'est **pas** prévu pour être versionné dans git (SQLite binaire); la traçabilité est assurée par le journal interne.

## 5. Modèle de données

Tous les identifiants sont des **ULID** (triables par date), générés sans dépendance externe (D-025). Toutes les dates sont en UTC, ISO 8601. Les colonnes `*_json` contiennent du JSON validé par un modèle Pydantic.

Les règles d'ajout seulement sont imposées par des **déclencheurs SQLite** dans la migration, en plus du code (D-028). Toute écriture passe par `ProjectFolder.write()`, qui ouvre la transaction avec `BEGIN IMMEDIATE`, pour que deux requêtes simultanées ne puissent pas entrer en collision (D-036).

### 5.1 Projet, personnes, journal

| Table | Champs principaux | Notes |
|---|---|---|
| `project` | id, title, language, created_at, format_version | Une ligne |
| `reviewer` | id, kind (`human` / `ai`), display_name, role, ai_config_id (si IA), active | EF-PRJ-05 |
| `ai_config` | id, task, provider, model_requested, prompt_template_id, prompt_template_version, params_json, created_at | Configuration **demandée**, consignée à sa première utilisation (D-039); la version **effective** est dans `ai_call` |
| `journal_entry` | id, position (0, 1, 2…), created_at, actor_reviewer_id, entry_type, subject_type, subject_id, payload_json, summary_fr, prev_hash, hash, tool_version | Ajout seulement; chaque entrée inclut l'empreinte de la précédente (chaîne vérifiable, format D-029); `position` donne l'ordre de la chaîne |

Types d'entrées du journal (extrait) : `project.created`, `project.opened`, `framing.updated`, `framing.suggestions_received`, `framing.suggestion_reviewed`, `criteria.draft_started`, `criteria.draft_edited`, `criteria.draft_discarded`, `criteria.version_created`, `criteria.change_proposed`, `criteria.change_qualified`, `ai.config_recorded`, `ai.call_failed`, `ai.result_unusable`, `protocol.text_updated`, `impact.assessed`, `reassessment.completed`, `search.query_versioned`, `search.run_completed`, `search.key_articles_updated`, `search.sensitivity_checked`, `search.descriptors_checked`, `search.terms_suggested`, `search.term_suggestion_reviewed`, `collect.started`, `collect.page_stored`, `collect.completed`, `collect.failed`, `import.completed`, `enrich.completed`, `dedup.completed`, `dedup.pair_decided`, `pilot.started`, `screening.started`, `screening.members_added`, `screening.ai_batch_submitted`, `screening.reconciled`, `reassessment.started`, `reassessment.decided`, `screening.human_decided`, `screening.ai_decided`, `screening.ai_failed`, `screening.ai_batch_ended`, `reviewer.ai_recorded`, `calibration.fitted`, `thresholds.set`, `budget.set`, `budget.reached`, `ai_mode.enabled`, `protocol.registered`, `archive.exported`, `note.added`.

### 5.2 Critères versionnés

| Table | Champs principaux | Notes |
|---|---|---|
| `framing_version` | id, number, created_at, author_id, question, population, concept, context, secondary_questions_json, journal_entry_id | Cadrage PCC (EF-CAD-01), une version immuable par modification (D-030) |
| `criteria_version` | id, number (1, 2, 3…), parent_id, status (`draft` / `active` / `superseded`), created_at, activated_at, author_id, rationale, journal_entry_id, after_protocol_registration (bool) | Au plus un brouillon et une version `active` à la fois; immuable une fois sortie du brouillon (flux D-027) |
| `criterion` | version_id, code (stable : `P1`, `C2`, `CTX1`, `X3`…), pcc_element (`population` / `concept` / `context` / `other`), kind (`inclusion` / `exclusion`), text, guidance, examples_json, counterexamples_json, applies_to_stages | Le `code` reste le même d'une version à l'autre; `applies_to_stages` sera ajouté avec le tri |
| `criterion_code` | code, pcc_element, first_version_id, created_at | Registre en ajout seulement : un code n'est jamais réattribué, même s'il n'a existé que dans un brouillon (D-026) |
| `qualification_proposal` | id, draft_version_id, code, ai_call_id, change_type, confidence, rationale, after_json, created_at | Proposition de l'IA pour un critère modifié d'un brouillon; caduque si le critère change de nouveau (D-043) |
| `criterion_change` | id, from_version_id, to_version_id, code, change_type (`broadening` / `narrowing` / `clarification` / `added` / `removed`), proposed_by (`ai` / `human`), proposal_id, confirmed_by, created_at, journal_entry_id | EF-VER-03 : un type confirmé par l'humain pour chaque changement, à l'activation (D-043); la justification est celle de la version |
| `ai_suggestion` | id, ai_call_id, position, kind (`reformulation` / `secondary_question` / `population` / `concept` / `context`), text, rationale, created_at | Suggestions de l'IA pour le cadrage (EF-CAD-02) |
| `suggestion_review` | id, suggestion_id (unique), outcome (`accepted` / `modified` / `rejected`), final_text, reviewer_id, created_at, framing_version_id, journal_entry_id | Une décision humaine par suggestion; `framing_version_id` est la version créée, s'il y en a une (D-042) |
| `protocol_text_version` | id, number, created_at, author_id, sections_json, journal_entry_id | Texte libre du protocole par section, versionné (D-045) |
| `protocol_registration` | id, doi, registered_on, criteria_version_id, created_at, reviewer_id, journal_entry_id | Dépôt du protocole (EF-CAD-08); toute version de critères activée ensuite est un écart au protocole (D-044) |

### 5.3 Recherche et collecte

| Table | Champs principaux | Notes |
|---|---|---|
| `search_strategy_version` | id, number, created_at, author_id, rationale, strategy_json, journal_entry_id | La stratégie entière en JSON : blocs (code stable `B1`, `B2`…, libellé, élément PCC, rôle `include` / `exclude`, termes) et limites (années, langues) (D-048, D-049) |
| `query` | id, strategy_version_id, database (`pubmed`, `openalex`, `psycinfo_ebsco`), syntax_text, blocks_json, limits_text, warnings_json, generated_by, edited (bool), created_at | Une requête par base et par version, produite en même temps que la version; `blocks_json` : requête de chaque bloc seul; avertissements de traduction (D-050, D-052) |
| `search_run` | id, query_id, kind (`count` / `sensitivity`), executed_at, result_count, blocks_json, status, raw_dir, reviewer_id, journal_entry_id | Exécution d'une requête : nombre de résultats au total et par bloc (EF-REC-04) |
| `key_article_set_version` | id, number, created_at, author_id, articles_json, journal_entry_id | Articles clés (DOI, PMID ou titre), versionnés (EF-REC-05) |
| `sensitivity_check` | id, search_run_id, key_article_set_version_id, found, indexed, outcomes_json | Résultat par article : identifiant dans la base, retrouvé ou non, blocs responsables (D-051) |
| `descriptor_check` | id, created_at, vocabulary, heading, found, official_heading, descriptor_ui, raw_dir, reviewer_id, journal_entry_id | Vérification d'un descripteur MeSH par E-utilities (EF-REC-02) |
| `term_suggestion` | id, ai_call_id, strategy_version_id, position, block_code, kind (`free_term` / `descriptor`), line, rationale, created_at | Termes proposés par l'IA (tâche `suggest_terms`), dans la syntaxe des termes (D-049) |
| `term_suggestion_review` | id, suggestion_id (unique), outcome, final_line, reviewer_id, created_at, strategy_version_id, journal_entry_id | Décision humaine; `strategy_version_id` : version créée par l'ajout du terme (D-042) |
| `collection_run` | id, query_id, database, query_text, started_at, reviewer_id, journal_entry_id | Collecte de tous les enregistrements d'une requête; au plus une ouverte par base (D-053) |
| `collection_page` | run_id, number, announced, record_count, new_references, next_cursor, raw_path, created_at, journal_entry_id | Une page enregistrée avec ses références, dans une transaction : l'unité de reprise (D-053) |
| `collection_end` | run_id (unique), status (`completed` / `failed`), announced, collected, discrepancy, error, ended_at, journal_entry_id | Fin d'une collecte : nombre collecté comparé au nombre annoncé, écart expliqué (EF-COL-01) |
| `import_file` | id, filename, sha256 (unique), format, database_declared, imported_at, record_count, issues_json, reviewer_id, journal_entry_id | Fichier RIS importé une seule fois; enregistrements vides ou mal formés listés dans `issues_json` (D-056) |

Toutes ces tables sont en ajout seulement (déclencheurs, migrations 0003 et 0004). La table `concept_block` envisagée au départ est remplacée par `strategy_json` (D-048). La collecte n'utilise pas `search_run`, réservé aux comptes et aux tests de sensibilité (écart, D-053).

### 5.4 Références, provenance, doublons

| Table | Champs principaux | Notes |
|---|---|---|
| `reference` | id, title, abstract, authors_json, year, container_title, volume, issue, pages, doi, pmid, openalex_id, language, doc_type, url, created_at | Champs normalisés, enregistrés tels que reçus et jamais modifiés (D-055); `oa_url` viendra avec Unpaywall (V2) |
| `provenance` | id, reference_id, source (`openalex` / `pubmed` / `ris`; plus tard `oai`, `manual`), original_id, collection_run_id, import_file_id, query_id, page, created_at | EF-COL-05; plusieurs par référence; `page` : page brute (collecte) ou position de l'enregistrement (import); un identifiant d'origine au plus une fois par collecte |
| `enrichment` | id, reference_id, source (`crossref`), fields_json, raw_dir, created_at, journal_entry_id | Champs manquants trouvés par Crossref; vide si le DOI est inconnu; la référence fusionnée est calculée (D-055) |
| `dedup_run` | id, created_at, reviewer_id, settings_json (seuils, version des règles), reference_count, automatic_pairs, review_pairs, journal_entry_id | Une exécution du dédoublonnage (EF-COL-06, D-062) |
| `duplicate_pair` | id, run_id, reference_a_id, reference_b_id (a < b), kind (`identifier` / `fuzzy` / `version`), rule, score, proposal (`duplicate` / `review`), details_json | Paires trouvées par une exécution, avec les raisons d'un examen humain (D-062, D-063) |
| `pair_decision` | id, reference_a_id, reference_b_id, pair_id, outcome (`duplicate` / `not_duplicate`), reviewer_id, note, created_at, journal_entry_id | Décision d'une personne; la dernière compte, dans l'ordre du journal (EF-COL-07) |

Toutes ces tables sont en ajout seulement (migrations 0004 et 0005). Les liens en vigueur, les groupes et la référence principale sont **calculés** à partir de la dernière exécution et des décisions; la table `duplicate_link` envisagée au départ est remplacée (écart, D-061).

### 5.5 Sélection

| Table | Champs principaux | Notes |
|---|---|---|
| `screening_round` | id, number, stage (`title_abstract` / `full_text`), kind (`pilot` / `main` / `reassessment`; plus tard `audit_sample`), criteria_version_id, seed, sample_size, created_at, reviewer_id, journal_entry_id | Un tour de pilote (tranche 1.6), le tri principal ou une réévaluation (tranche 1.7). Ni `closed_at` ni `metrics_json` : les métriques se recalculent à partir des décisions |
| `round_member` | round_id, position, reference_id | Références d'un tour, dans l'ordre tiré avec la graine consignée (EF-SEL-01, D-083); les références ajoutées au tri principal se placent à la suite |
| `decision` | id, reference_id, stage, round_id, reviewer_id, reviewer_kind, value (`include` / `exclude` / `uncertain`), confidence_raw (probabilité d'inclusion, D-065), confidence_calibrated, rationale, criteria_cited_json, per_criterion_json, model_decision, thresholds_json, calibration_id, criteria_version_id, language, context (`independent` / `reconciliation` / `reassessment` / `audit`), blinded, supersedes_decision_id, ai_call_id, tool_version, created_at, journal_entry_id | **Ajout seulement.** Contient tous les champs d'ENF-TRA-01 directement ou via `ai_call`; des contraintes `CHECK` imposent les champs d'une décision de l'IA et interdisent un appel de modèle sur une décision humaine (ENF-TRA-05); le modèle du domaine exige en plus un critère cité pour une exclusion humaine (EF-SEL-12) |
| `calibration_model` | id, round_id, ai_config_id, method (`isotonic` / `platt` / `none`), calibration_json, artifact_path, fitted_on_n, created_at, journal_entry_id | EF-SEL-05, D-072 |
| `threshold_setting` | id, stage, exclude_below, include_above, target_sensitivity, justification, based_on_round_id, calibration_id, reviewer_id, created_at, journal_entry_id | EF-SEL-09; le dernier réglage dans l'ordre du journal est en vigueur, sinon les valeurs par défaut (D-066) |
| `ai_batch` | id, round_id, task, criteria_version_id, provider, provider_batch_id, item_ids_json, estimate, created_at, reviewer_id, journal_entry_id | Lot envoyé à l'API Batches du fournisseur, avec la version des critères donnée au modèle (D-080) |
| `ai_batch_end` | batch_id, screened, failed_json, spent, created_at, journal_entry_id | Fin d'un lot, une fois tous ses résultats consignés; un lot sans fin est encore à suivre |
| `impact_assessment` | id, from_version_id, to_version_id, main_round_id, changes_json (références touchées par changement), touched_count, reassessment_round_id, seed, sampled, created_at, reviewer_id, journal_entry_id | EF-VER-04/05; la fin de la réévaluation est une entrée du journal (`reassessment.completed`) |

Tables des tranches 1.6 et 1.7 en ajout seulement (déclencheurs, migrations 0006 et 0007). Écarts de la tranche 1.7 : `ai_batch` et `ai_batch_end` ajoutées; `impact_assessment` garde l'impact complet dans `changes_json` et n'a ni `reassessment_mode` (un seul mode en V1 : l'IA puis la vérification humaine) ni `status`. La migration 0007 ajoute aussi des index pour le passage à la référence suivante, dont un index sur expression (`ix_decision_priority`) que SQLite ne permet pas de comparer au modèle. Écarts de la tranche 1.6 : `round_member` ajoutée; `decision` gagne `model_decision`, `thresholds_json`, `calibration_id` et `language`; `screening_round` perd `closed_at` et `metrics_json`; `threshold_setting` ne porte plus `ai_config_id`, l'étalonnage étant lié à sa configuration.

**État courant** d'une référence à une étape (vue calculée, `screening/main.py`) : en V1, la dernière décision humaine, dans l'ordre du journal, parmi les décisions indépendantes (pilote compris quand la version des critères est la même, D-078), de réconciliation et de réévaluation. Une décision IA seule ne déterminera l'état courant que si le mode d'exclusion assistée (EF-SEL-11, V2) est actif et que la décision dépasse le seuil.

**Désaccord** (D-079) : l'humain et l'IA sont en désaccord quand l'un conserve la référence (inclure ou incertain) et l'autre l'exclut. La file de réconciliation contient les désaccords sans décision de réconciliation.

### 5.6 Appels aux modèles

| Table | Champs principaux |
|---|---|
| `ai_call` | id, ai_config_id, task, item_id, provider, model_requested, **model_returned** (identifiant exact renvoyé par l'API; vide si l'API n'a renvoyé aucun modèle), provider_request_id, prompt_template_id, prompt_template_version, prompt_sha256, params_json, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_estimate, currency, latency_ms, batch_id, response_path, status, error_code, created_at |
| `budget_setting` | id, limit_amount, currency, reviewer_id, created_at, journal_entry_id |

Un appel fait dans un lot porte l'identifiant du lot chez le fournisseur (`batch_id`) et son coût au tarif des lots. `budget_setting` est en ajout seulement : le dernier réglage est en vigueur, et la dépense se calcule à partir de `ai_call.cost_estimate`. Le plafond de lot est un paramètre du lot, consigné à la fin du lot (écart à la table `budget` prévue, qui portait un `spent_amount` modifiable, D-069).

### 5.7 Texte complet, études, extraction (V2–V3)

| Table | Champs principaux |
|---|---|
| `fulltext_document` | id, reference_id, origin (`unpaywall` / `upload`), sha256, path, page_count, text_path, page_map_path, status (`obtained` / `not_found` / `not_retrievable`) |
| `study` | id, label, created_at |
| `study_reference` | study_id, reference_id, role (`primary` / `secondary`), decided_by |
| `grid_version`, `grid_field`, `grid_field_change` | Mêmes principes que les critères : code stable, type, définition, consignes, choix permis, qualification des changements |
| `extraction_value` | id, study_id, field_code, grid_version_id, value_json, quote, page, reviewer_id, reviewer_kind, status (`proposed` / `validated` / `corrected` / `rejected`), supersedes_id, ai_call_id, created_at |

### 5.8 Consultation (V4)

`stakeholder` (nom, rôle, organisation — rien d'autre, EF-CON-03), `lay_summary` (version, texte, révisé par), `stakeholder_comment` (auteur, cible, texte, date, suite donnée).

## 6. Couche d'abstraction des modèles

### 6.1 Concepts

- **Tâche** (`ai/tasks/`) : ce qu'on demande, indépendamment du modèle. Chaque tâche définit un schéma d'entrée et un **schéma de sortie Pydantic**. Tâches prévues :
  - `screen_reference` (V1) : référence + version des critères → évaluation par critère, décision, confiance, justification;
  - `qualify_criterion_change` (V1) : ancien et nouveau texte → type de changement;
  - `suggest_terms` (V1) : bloc de concepts → synonymes, descripteurs candidats;
  - `suggest_pcc` (V1) : question → éléments PCC et reformulations;
  - `screen_fulltext` (V2), `group_reports` (V2), `extract_fields` (V3), `summarize_for_lay_audience` (V4).
- **Fournisseur** (`ai/providers/`) : comment on exécute une tâche avec un moteur donné.
- **Réviseur IA** (`ai_config`) : couple tâche + fournisseur + modèle + gabarit d'invite + paramètres.

### 6.2 Interface (esquisse, à implémenter en anglais)

```python
class TaskResult(BaseModel, Generic[OutputT]):
    output: OutputT                 # validated structured output
    raw_confidence: float | None
    call: AICallRecord              # provider, model_returned, tokens, cost, prompt hash, response path…

class ModelProvider(Protocol):
    name: str
    def supports(self, task: TaskSpec) -> bool: ...
    def estimate_cost(self, task: TaskSpec, inputs: Sequence[TaskInput]) -> CostEstimate: ...
    def run(self, task: TaskSpec, inputs: Sequence[TaskInput]) -> Iterator[TaskResult]: ...
```

Les services applicatifs ne connaissent que `ModelProvider` et `TaskSpec`. Le choix du fournisseur se fait par la configuration du projet.

### 6.3 Fournisseurs prévus

| Fournisseur | Tâches | Confiance | Justification | Version |
|---|---|---|---|---|
| `FakeProvider` | Toutes | Fixée par le test | Fixe | Jalon 0 — **seul fournisseur utilisé dans les tests automatisés** |
| `AnthropicProvider` (Claude) | Toutes | Confiance déclarée par le modèle, éventuellement agrégée sur plusieurs échantillons, puis étalonnée | Oui, avec citation et critère | V1 |
| `ClassifierProvider` (scikit-learn, local) | `screen_reference` seulement | Probabilité étalonnée | **Non** (au plus : termes les plus influents); doit être signalé dans la section méthode | V2 |
| `LocalLLMProvider` (API HTTP compatible Ollama ou OpenAI, sur `localhost`) | Toutes, selon le modèle | Comme Claude | Oui | V3 |

Le **nom exact du modèle** n'est jamais codé en dur : il vient de la configuration du projet. Le fichier `resources/model_prices.yaml` (daté) donne les tarifs connus.

`AnthropicProvider` (tranche 1.2, D-037) : sortie structurée selon le schéma de la tâche, revalidée par Pydantic; instructions mises en cache; replis côté serveur activables (`fallbacks`); chaque appel produit un `AICallRecord` complet et la réponse brute. Seul ce module importe le SDK `anthropic` (test d'architecture). Les services reçoivent une fabrique de fournisseurs (`ProviderFactory`) construite depuis `[ia]`; les tests y substituent `FakeProvider`.

### 6.4 Invites

- Gabarits Jinja2 dans `ai/prompts/<id>/` : `meta.yaml` (`id`, `version`, `task`, `changelog`), `system.md.j2` (instructions fixes, préfixe mis en cache) et `user.md.j2` (entrée de la tâche). Modifier un gabarit = incrémenter sa version. L'empreinte SHA-256 consignée porte sur les deux parties rendues.
- Gabarits livrés à la tranche 1.2 : `suggest_pcc` et `qualify_criterion_change` (version 1).
- **Structure de l'invite de tri** : instructions fixes → critères de la version en vigueur (avec exemples et contre-exemples) → référence. Les deux premiers blocs forment un **préfixe stable** qui profite de la mise en cache des invites (ENF-COU-04).
- Deux stratégies configurables, à comparer dans l'étude de validation : **un appel par référence** évaluant tous les critères (par défaut, moins coûteux) ou **un appel par critère** (Vembye et al., 2025).
- Sortie **structurée** (schéma JSON) : pour chaque critère, `status` (`met` / `not_met` / `cannot_tell`), `evidence_quote`; puis `decision`, `confidence`, `rationale`, `decisive_criteria`.
- **Règle codée en dur, pas laissée au modèle** : si un critère d'inclusion est `cannot_tell` et aucun critère n'est `not_met`, la décision est au minimum `uncertain` (EF-SEL-07).

### 6.5 Confiance et étalonnage

1. **Score brut** : probabilité d'inclusion déclarée par le modèle (D-065); option : proportion de *k* exécutions concordantes (auto-cohérence), au prix de *k* fois le coût.
2. **Étalonnage** après chaque tour de pilote : régression isotonique (ou Platt si peu de données) du score brut vers la probabilité observée que l'humain inclue; sérialisée dans `etalonnage/`, référencée par `calibration_model`.
3. **Seuils** appliqués sur la probabilité étalonnée quand un étalonnage est en vigueur, sinon sur la probabilité brute; la valeur de l'IA s'en déduit, puis la règle EF-SEL-07 s'applique (D-068). Le seuil d'exclusion suggéré est le plus élevé qui garde la sensibilité du pilote au moins égale à la cible (D-072); la courbe seuil → sensibilité / charge évitée est présentée à l'équipe (EF-SEL-03, EF-SEL-05).
4. **Limite assumée** : avec peu d'inclusions dans le pilote, l'estimation de la sensibilité est imprécise; l'outil affiche l'intervalle de confiance (méthode de Wilson ou exacte) et refuse le mode d'exclusion assistée si la borne inférieure est sous la cible (EF-SEL-11).

### 6.6 Coûts

`ai/costs.py` estime le coût avant chaque lot (jetons d'entrée estimés × tarif, instructions au tarif d'écriture en cache, + sortie attendue : D-040), vérifie le plafond, enregistre le coût réel par appel et arrête proprement au plafond (ENF-COU-01 à 03). Depuis la tranche 1.6, le plafond du projet et celui du lot sont vérifiés avant chaque appel, nouvelles tentatives comprises (D-069). L'appel se fait hors transaction d'écriture; il est consigné dans sa propre transaction, puis son résultat est exploité (D-041). Depuis la tranche 1.7, le tri principal et la réévaluation passent par l'API de traitement par lots du fournisseur (`BatchProvider`, D-080) : tarif des lots dans `model_prices.yaml` (`batch_factor`), au plus 5 000 requêtes par lot, estimation réservée avant chaque lot en comptant les lots encore en cours, collecte qui reprend sans payer deux fois.

## 7. Analyse d'impact (fonctionnalité distinctive)

Algorithme de `domain/impact.py` (fonction pure, entièrement testée) :

```
entrée : version A, version B, changements qualifiés, décisions courantes
pour chaque changement (code, type) :
    broadening    → références dont l'état courant est « exclure » ET qui citent ce code
    narrowing     → références dont l'état courant est « inclure » ou « incertain »
                    (option : seulement celles où l'IA a jugé ce critère « met » faiblement)
    clarification → références qui citent ce code (réévaluation par échantillon proposée)
    added         → toutes les références encore actives à l'étape concernée
    removed       → références exclues UNIQUEMENT pour ce code
sortie : ensemble des références touchées, par changement et au total, avec explication
```

Mise en œuvre de la tranche 1.7 (D-077, D-081, D-082) :

- l'état courant est la dernière décision humaine (§5.5); les références pas encore triées ne sont pas touchées, puisqu'elles seront triées avec la nouvelle version; une référence « encore active » est une référence conservée (inclure ou incertain); l'option sur la restriction n'est pas offerte;
- les versions activées pendant le tri sont analysées une à une, dans l'ordre;
- une clarification est réévaluée sur un échantillon de 20 % des références qu'elle seule touche (au moins 20), tiré avec une graine consignée, ou sur toutes au choix de la personne;
- la réévaluation crée un `screening_round` de type `reassessment` avec la nouvelle version : l'IA trie de nouveau les références (par lots), la personne ne vérifie que celles où l'IA ferait passer de « conserver » à « exclure » ou l'inverse; sa décision remplace la précédente (`supersedes_decision_id`), qui demeure;
- le journal consigne pour chaque changement les versions, le type, la justification de la version, le nombre de références touchées et réévaluées (`impact.assessed`), puis le résultat de la réévaluation (`reassessment.completed`).

Le diagramme de flux en rend compte par une note sur la case « Références triées » (D-091), et la section méthode, changement par changement (tranche 1.8).

## 8. Connecteurs de sources

- Interface `SearchSource` (tranche 1.3) : `count(query)`, `among(query, ids)` (lesquels de ces identifiants la requête retrouve, par lots), `resolve(article)` (identifiant d'un article clé dans la base). Les services reçoivent une fabrique (`SourceFactory`); les tests y substituent des connecteurs qui rejouent des réponses enregistrées. Un connecteur ferme le client HTTP qu'il a créé.
- Collecte (tranche 1.4, interface `Collector` de `collect/collection.py`) : `fetch(query, cursor) -> FetchedPage` donne une page de notices déjà normalisées (`FetchedRecord`), le nombre annoncé et le curseur de la page suivante (`None` à la fin); `cursor` vaut `None` pour la première page. OpenAlex : curseur de l'API, pages de 200. PubMed : serveur d'historique, pages de 200, au plus 10 000 notices par recherche (D-054). Le cas d'usage (`collect/collection.py`) enregistre chaque page avec son curseur, ce qui rend la collecte reprenable (D-053).
- Crossref (`sources/crossref.py`) : `work(doi)` donne la notice d'un DOI (ou `None` s'il est inconnu) et la réponse brute; enrichissement par lots de 100, au plus trois requêtes simultanées (D-055).
- **Limiteur de débit** par source, paramétré selon les conditions de 2026 (voir [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026)) : OpenAlex (clé requise, suivi de l'allocation quotidienne), PubMed (3 ou 10 requêtes/s, `tool` et `email`), Crossref (pool « poli », concurrence ≤ 3), Unpaywall (`email`).
- Nouvelle tentative avec attente exponentielle sur 429, 5xx, délais dépassés et connexions coupées en cours de réponse; arrêt propre et message clair en français si le **domaine est bloqué par la liste réseau** de l'environnement, si l'accès est refusé ou si la réponse est illisible (`SourceError`, `sources/http.py`).
- PubMed : `tool=revue-portee` et `email` (adresse de contact lue par `config/secrets.py`); vérification des descripteurs par `esearch` puis `esummary` sur la base `mesh`. OpenAlex : filtres de l'API `works` (D-050). PsycINFO (EBSCOhost) n'a pas d'API publique : la requête est produite pour être exécutée dans l'interface.
- Chaque page brute est conservée dans `brut/sources/`.
- Bases sans API (PsycINFO EBSCOhost ou Ovid, CINAHL, ERIC, SocINDEX, Scopus, Web of Science, Érudit) : import de fichiers RIS (`sources/ris.py`, `collect/imports.py`, D-056).

## 9. Interface web

- Rendu côté serveur, HTMX pour les interactions partielles (tri au clavier sans recharger la page).
- Pages V1 : tableau de bord du projet (étape courante, nombres, coûts), cadrage PCC et critères (avec historique et différentiel), stratégie de recherche et test de sensibilité, collecte et imports, doublons à confirmer, pilote (tri à l'aveugle puis tableau d'étalonnage), tri principal, réconciliation, analyse d'impact, journal, exports.
- Pages livrées à la tranche 1.1 : « Cadrage », « Critères » (version en vigueur, brouillon, versions, différentiel) et « Journal » (entrées, notes, vérification de la chaîne).
- Ajouts de la tranche 1.3 : page « Recherche » : blocs de concepts éditables et limites; requêtes de chaque base avec leurs avertissements; nombre de résultats au total et par bloc (PubMed, OpenAlex); vérification des descripteurs MeSH; articles clés et test de sensibilité; suggestions de termes par l'IA; historique des versions. Le protocole décrit la stratégie et donne les requêtes à l'annexe II.
- Ajouts de la tranche 1.8 : page « Rapports » : nombres et diagramme de flux calculés à partir des données (provisoire tant qu'il reste quelque chose à faire, D-090); téléchargement du diagramme (SVG) et de l'ébauche de section méthode (DOCX, Markdown), en français et en anglais; écriture de l'archive publique ou complète, et téléchargement des archives écrites (seuls fichiers servis depuis `exports/`).
- Ajouts de la tranche 1.7 : pages « Tri » : avancement (références, décisions, désaccords); tri de la référence suivante sans voir l'IA, entièrement au clavier (`i`, `d`, `e`, `1` à `9`, `p`, D-084), dans l'ordre tiré ou par priorité selon la probabilité d'inclusion (EF-SEL-10); lots d'IA estimés, lancés et suivis en arrière-plan; réconciliation des désaccords, seule page où la justification de l'IA est visible; analyse d'impact d'une nouvelle version et page de réévaluation. Passage à la référence suivante mesuré sous 200 ms sur 50 000 références (ENF-PER-01).
- Ajouts de la tranche 1.6 : page « Pilote » : budget d'IA du projet; tirage d'un échantillon avec graine; tri de la référence suivante sans voir l'IA (D-071), avec critères cités et note; estimation du coût puis lot d'IA en arrière-plan, sous un plafond de lot; table des décisions, où l'IA n'apparaît qu'après la décision humaine, avec son évaluation par critère et ses citations; table d'étalonnage (accord, kappa, AC1, sensibilité et spécificité avec intervalles, matrice de confusion, désaccords par critère, courbe seuil); ajustement de l'étalonnage et réglage des seuils avec justification.
- Ajouts de la tranche 1.5 : page « Doublons » : nombres du diagramme par source (D-064); exécution en arrière-plan avec seuils réglables; paires à examiner côte à côte, différences signalées, raisons d'un examen humain; groupes de doublons avec leur référence principale et leurs liens, chacun annulable; paires gardées séparées, de nouveau regroupables.
- Ajouts de la tranche 1.4 : page « Collecte » : collecte de chaque requête OpenAlex et PubMed, état mis à jour toutes les 2 secondes, reprise d'une collecte ouverte, écart entre nombre annoncé et collecté; import de fichiers RIS avec la base déclarée et la liste des enregistrements écartés; enrichissement par Crossref; nombre de références par source.
- Ajouts de la tranche 1.2 : suggestions de l'IA sur « Cadrage » (accepter, modifier, refuser); qualification des changements sur « Critères », avec proposition facultative de l'IA; page « Protocole » (téléchargement Markdown et DOCX en français et en anglais, enregistrement OSF, état des éléments de Peters et al., texte libre). Tout appel à l'IA passe par une page d'estimation du coût, puis une confirmation (ENF-COU-01).
- Navigation avec `hx-boost`; les réponses 4xx et 5xx sont affichées (configuration `htmx-config`), car l'application renvoie ses erreurs de formulaire comme des pages complètes (D-033). Les formulaires fonctionnent aussi sans JavaScript.
- Chaînes d'interface dans le catalogue Babel de `i18n/` (D-031).
- **Sécurité locale** (D-032) : chaque formulaire porte un jeton propre au processus du serveur; les en-têtes `Host` autres que `127.0.0.1` ou `localhost`, et les en-têtes `Origin` étrangers sur les écritures, sont refusés (requêtes intersites, DNS rebinding).
- **Tâches de fond** (`jobs/runner.py`) : chaque tâche longue (collecte, enrichissement, dédoublonnage, lot d'IA du pilote, suivi des lots du tri et de la réévaluation) s'exécute dans un fil du processus du serveur, au plus une par clé. Son état est ce qu'elle a enregistré dans le projet; une tâche arrêtée avec le serveur se reprend en la relançant (ENF-PER-04). Pas de file persistée ni de reprise automatique au redémarrage (écart, D-059). Pas de Celery ni de Redis.

## 10. Sécurité et secrets

- `config/secrets.py` est le **seul** module qui lit les variables d'environnement sensibles (un test d'architecture l'impose); il renvoie des `SecretStr` (Pydantic) dont la représentation est masquée.
  - Clé Anthropic : `REVUE_PORTEE_ANTHROPIC_KEY`, à défaut `ANTHROPIC_API_KEY` (D-020); toutes les valeurs définies sont enregistrées pour le masquage.
  - `CONTACT_EMAIL` : obligatoire. `OPENALEX_API_KEY` : facultative pour le code, qui ne l'envoie que si elle est définie (D-021); elle doit être définie sur un poste local, car OpenAlex l'exige (D-013), alors que dans l'environnement infonuagique le mandataire réseau l'ajoute aux requêtes (D-085).
  - Une variable obligatoire absente lève `MissingSecretError`, avec un message en français qui nomme la variable sans jamais afficher de valeur.
- **Masquage des journaux** (ENF-SEC-03, D-024) : `install_secret_redaction()`, appelée au démarrage de chaque point d'entrée, installe une fabrique d'entrées de journal (`logging.setLogRecordFactory`) qui masque chaque entrée dès sa création. Elle couvre ainsi tous les gestionnaires, y compris ceux configurés plus tard (uvicorn). Un filtre `logging` sur les gestionnaires sert de seconde protection.
  - Sont masqués les valeurs de secrets chargées et les motifs de clés connus (`sk-ant-…`, en-têtes `Authorization` / `x-api-key`, `api_key`, paramètres `api_key` / `email` / `mailto`), dans le message, les arguments, les traces d'exception et les piles d'appels.
  - La forme des entrées (`msg`, `args`) est conservée tant qu'aucun secret n'y figure, et le masquage ne lève jamais d'exception.
  - Limite : un gestionnaire qui rend lui-même les exceptions à partir de `record.exc_info` (par exemple `RichHandler`) contourne le masquage des traces; ne pas en utiliser.
- Les cassettes de test sont enregistrées avec filtrage des en-têtes (`x-api-key`, `authorization`) et des paramètres (`api_key`, `email`, `mailto`), remplacés par `DUMMY` et `contact@example.org`. Elles sont ensuite vérifiées par un test qui cherche des motifs de secrets dans `tests/` (`config/secret_scan.py`, ENF-SEC-04), selon la règle des valeurs fictives de D-017. Ce test signale le fichier, la ligne et le type de fuite, jamais la valeur.
- Le serveur écoute sur `127.0.0.1` (ENF-SEC-06).

## 11. Tests

| Type | Où | Réseau | Lancement |
|---|---|---|---|
| Unitaires (domaine, métriques, impact, dédoublonnage, diagramme) | `tests/unit/` | Non | `uv run pytest` |
| Bout en bout sur le jeu de démonstration (diagramme, section méthode, archive recomptée sans l'outil) | `tests/unit/screening/`, `tests/demo.py` | Non | `uv run pytest` |
| Connecteurs avec réponses enregistrées | `tests/unit/sources/` + `tests/cassettes/` | Non (mode lecture seule des cassettes) | `uv run pytest` |
| Services avec `FakeProvider` | `tests/unit/` | Non | `uv run pytest` |
| Intégration réelle (API de sources, Claude) | `tests/integration/`, marqueur `integration` | **Oui** | `uv run pytest -m integration` — **volontairement seulement** |
| Performance de tri sur SYNERGY (sous-ensemble) | `tests/benchmarks/` (V1, tranche 7) | Oui (modèle) | Manuel, résultats consignés |

`pyproject.toml` configure `addopts` avec `-m "not integration"` et `--record-mode=none` (cassettes en lecture seule), et `tests/conftest.py` bloque le réseau pour tout test non marqué `integration` (D-016) : aucun test ordinaire ne peut atteindre le réseau. Seule l'adresse de bouclage 127.0.0.1 reste ouverte, car la boucle asyncio s'y connecte sous Windows, et les variables de mandataire (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`) sont retirées pendant ces tests (D-086). Pour enregistrer une cassette : `uv run pytest -m integration --record-mode=once`, puis nettoyage et vérification anti-secrets. Les tests des connecteurs `httpx2` portent le marqueur `cassette` (D-047) : ils rejouent `tests/cassettes/<module>/<test>.json`; `uv run pytest <test> --record-mode=once` enregistre une cassette absente contre le vrai service, sur autorisation de Benoit. Avant d'être écrites, les réponses sont réduites à ce dont les tests ont besoin (`trim_body` : résumés tronqués, courriels masqués, références citées retirées, D-058). Les exports RIS réels sont versionnés comme extraits nettoyés, octets conservés (D-057).

**Couverture** (ENF-QUA-04, D-023) : chaque exécution de `pytest` mesure la couverture de `revue_portee`, branches comprises (pytest-cov). Le greffon `tests/_plugins/coverage_gate.py` fait échouer la suite si l'un des paquets `domain`, `dedup` ou `reporting` est sous 90 %, chacun séparément. Le seuil n'est vérifié que sur la suite complète, et se règle dans `pyproject.toml` (`coverage_gate_packages`, `coverage_gate_fail_under`).

**Vérifications avant fusion** (ENF-QUA-03) : `ruff check`, `ruff format --check`, `mypy` et `pytest`, exécutées aussi par la CI GitHub (`.github/workflows/ci.yml`, Python 3.12 et 3.13). ruff ignore `docs/` et les fichiers `*.md` (D-019).

## 12. Évolution vers une version hébergée (V4 ou plus tard)

Le découpage domaine / stockage / web permet de remplacer SQLite par PostgreSQL et d'ajouter l'authentification sans toucher au domaine. Points à prévoir dès maintenant : identifiants ULID (pas d'entiers auto-incrémentés liés à un fichier), aucun état global dans le processus web, réviseurs identifiés dans toutes les tables. La licence AGPL (recommandée) imposerait alors de publier le code de la version hébergée.
