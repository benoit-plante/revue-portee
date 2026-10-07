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
| RIS | rispy | MIT | Analyseur RIS maintenu; enveloppé pour tolérer les variantes |
| Appariement approximatif | RapidFuzz | MIT | Dédoublonnage |
| Classificateur rapide | scikit-learn | BSD | TF-IDF + régression logistique, étalonnage |
| Claude | SDK `anthropic` | MIT | Sorties structurées, mise en cache des invites, lots asynchrones |
| PDF → texte avec pages (V2) | PyMuPDF par défaut (compatible avec l'AGPL, D-004); pypdf ou pdfplumber en solution de rechange — choix confirmé par un essai comparatif à la tranche 2.1 | AGPL / BSD / MIT | Fiabilité de l'extraction avec pages |
| DOCX | python-docx | MIT | Protocole, section méthode |
| Diagramme de flux | Gabarit SVG paramétré (Jinja2), conversion PNG/PDF par CairoSVG (V2) | LGPL | Déterministe, pas de dépendance graphique lourde |
| Internationalisation | Babel (catalogues gettext) | BSD | ENF-LAN-03 |
| Tests | pytest, pytest-recording (VCR.py), respx, pytest-cov (coverage) | MIT / BSD / Apache-2.0 | Réponses enregistrées (ENF-QUA-01); couverture et seuil de 90 % par paquet (ENF-QUA-04, D-023) |
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
│   │   ├── references.py         # Reference, Provenance, normalisation DOI/titre
│   │   ├── criteria.py           # CriteriaVersion, Criterion, CriterionChange
│   │   ├── framing.py            # Framing, FramingVersion (question PCC versionnée)
│   │   ├── project.py            # Project, Reviewer
│   │   ├── decisions.py          # Decision, ReviewerRef, Stage, état courant
│   │   ├── impact.py             # analyse d'impact des changements (EF-VER-04)
│   │   ├── grid.py               # GridVersion, Field, ExtractionValue (V3)
│   │   ├── metrics.py            # accord, kappa, AC1, sensibilité, WSS…
│   │   └── journal.py            # JournalEntry, chaîne d'empreintes
│   ├── storage/
│   │   ├── project_folder.py     # création/ouverture du dossier de projet
│   │   ├── db.py, repositories/  # accès SQLite; écritures par ProjectFolder.write() (D-036)
│   │   ├── migrate.py, migrations/ # Alembic (migrations appliquées à l'ouverture)
│   │   └── archive.py            # export autonome (EF-PRJ-04)
│   ├── sources/
│   │   ├── base.py               # interface Source, limiteur de débit, reprise
│   │   ├── openalex.py, pubmed.py, crossref.py, unpaywall.py
│   │   ├── ris.py                # import RIS
│   │   └── oai_pmh.py            # Érudit, HAL, dépôts (V2)
│   ├── protocol/                 # cas d'usage de l'étape 1 : cadrage, critères, notes du journal
│   ├── search/                   # blocs de concepts, traducteurs par base, test de sensibilité
│   ├── dedup/                    # dédoublonnage
│   ├── screening/                # pilote, échantillonnage, réconciliation, seuils
│   ├── ai/
│   │   ├── base.py               # TaskSpec, TaskInput/TaskOutput, TaskResult, AICallRecord, ModelProvider
│   │   ├── runner.py             # run_task : exécution indépendante du fournisseur
│   │   ├── tasks/                # définition des tâches (entrées/sorties Pydantic)
│   │   ├── providers/            # anthropic.py, classifier.py, local.py, fake.py
│   │   ├── prompts/              # gabarits d'invite versionnés (*.md.j2 + métadonnées)
│   │   ├── calibration.py        # étalonnage de la confiance
│   │   └── costs.py              # estimation, plafonds, suivi
│   ├── extraction/, synthesis/, stakeholders/   # V3, V3, V4
│   ├── reporting/                # diagramme, protocole, section méthode, PRISMA-ScR
│   ├── config/                   # paramètres, secrets (seul point d'accès aux variables d'env.)
│   │   ├── secrets.py            # lecture des secrets (SecretStr), masquage des journaux
│   │   └── secret_scan.py        # détection de secrets dans des fichiers (tests/, archive)
│   ├── jobs/                     # tâches de fond persistantes
│   ├── web/                      # FastAPI : routes (app.py), gabarits, statique (HTMX copié, D-033)
│   ├── cli/                      # Typer : nouveau, serve, verifier-journal
│   ├── i18n/                     # catalogues Babel (locale/fr/…/messages.po), D-031
│   ├── clock.py, version.py      # heure UTC; version de l'outil et commit (D-034)
│   └── resources/                # YAML : PRISMA-ScR, gabarit diagramme, OSF, tarifs
└── tests/
    ├── conftest.py               # blocage du réseau, filtrage des cassettes
    ├── support.py                # utilitaires partagés (horloge déterministe, projet de test)
    ├── _plugins/                 # greffons pytest du projet (seuil de couverture par paquet)
    ├── unit/
    ├── integration/              # marqueur « integration », exclus par défaut
    ├── cassettes/                # réponses enregistrées, nettoyées
    └── fixtures/                 # RIS réels anonymisés, petits jeux SYNERGY
```

## 4. Format du dossier de projet

Un projet de revue est un **dossier** (extension conventionnelle `.revue`, ex. `ecoanxiete-enfants.revue/`) :

```
ecoanxiete-enfants.revue/
├── projet.toml           # métadonnées, version du format, paramètres (seuils, plafonds, réviseurs IA)
├── revue.sqlite          # source de vérité (toutes les tables de la section 5)
├── brut/
│   ├── ia/AAAA/MM/<ai_call_id>.json.gz       # réponses brutes des modèles (ENF-TRA-03)
│   └── sources/<search_run_id>/page-0001.json.gz
├── imports/<sha256>.ris  # copie exacte de chaque fichier importé
├── textes/               # PDF et texte extrait avec pages (V2)
├── etalonnage/           # modèles d'étalonnage sérialisés, par tour de pilote
└── exports/              # fichiers générés (diagramme, protocole, méthode, CSV) — régénérables
```

- `projet.toml` contient `format_version` (ex. `"1.0"`). Toute ouverture d'un projet d'un format antérieur lance les migrations après **copie de sauvegarde** automatique.
- **Aucun secret** dans le dossier de projet (ENF-SEC-01). Les réviseurs IA y sont décrits par fournisseur et modèle, jamais par clé.
- Le dossier est **autosuffisant** : copié ailleurs, il s'ouvre sans perte. L'archive OSF (EF-PRJ-04) est ce dossier sans `textes/` (droits d'auteur), plus des exports CSV/JSON lisibles sans l'outil.
- Le dossier n'est **pas** prévu pour être versionné dans git (SQLite binaire); la traçabilité est assurée par le journal interne.

## 5. Modèle de données

Tous les identifiants sont des **ULID** (triables par date), générés sans dépendance externe (D-025). Toutes les dates sont en UTC, ISO 8601. Les colonnes `*_json` contiennent du JSON validé par un modèle Pydantic.

Les règles d'ajout seulement sont imposées par des **déclencheurs SQLite** dans la migration, en plus du code (D-028). Toute écriture passe par `ProjectFolder.write()`, qui ouvre la transaction avec `BEGIN IMMEDIATE`, pour que deux requêtes simultanées ne puissent pas entrer en collision (D-036).

### 5.1 Projet, personnes, journal

| Table | Champs principaux | Notes |
|---|---|---|
| `project` | id, title, language, created_at, format_version | Une ligne |
| `reviewer` | id, kind (`human` / `ai`), display_name, role, ai_config_id (si IA), active | EF-PRJ-05 |
| `ai_config` | id, provider, model_requested, task, prompt_template_id, prompt_template_version, params_json, created_at | Configuration **demandée**; la version **effective** est dans `ai_call` |
| `journal_entry` | id, position (0, 1, 2…), created_at, actor_reviewer_id, entry_type, subject_type, subject_id, payload_json, summary_fr, prev_hash, hash, tool_version | Ajout seulement; chaque entrée inclut l'empreinte de la précédente (chaîne vérifiable, format D-029); `position` donne l'ordre de la chaîne |

Types d'entrées du journal (extrait) : `project.created`, `project.opened`, `framing.updated`, `criteria.draft_started`, `criteria.draft_edited`, `criteria.draft_discarded`, `criteria.version_created`, `criteria.change_qualified`, `impact.assessed`, `reassessment.completed`, `search.query_versioned`, `search.run_completed`, `import.completed`, `dedup.completed`, `pilot.round_completed`, `thresholds.set`, `ai_mode.enabled`, `protocol.registered`, `note.added`, `budget.reached`.

### 5.2 Critères versionnés

| Table | Champs principaux | Notes |
|---|---|---|
| `framing_version` | id, number, created_at, author_id, question, population, concept, context, secondary_questions_json, journal_entry_id | Cadrage PCC (EF-CAD-01), une version immuable par modification (D-030) |
| `criteria_version` | id, number (1, 2, 3…), parent_id, status (`draft` / `active` / `superseded`), created_at, activated_at, author_id, rationale, journal_entry_id, after_protocol_registration (bool) | Au plus un brouillon et une version `active` à la fois; immuable une fois sortie du brouillon (flux D-027) |
| `criterion` | version_id, code (stable : `P1`, `C2`, `CTX1`, `X3`…), pcc_element (`population` / `concept` / `context` / `other`), kind (`inclusion` / `exclusion`), text, guidance, examples_json, counterexamples_json, applies_to_stages | Le `code` reste le même d'une version à l'autre; `applies_to_stages` sera ajouté avec le tri |
| `criterion_code` | code, pcc_element, first_version_id, created_at | Registre en ajout seulement : un code n'est jamais réattribué, même s'il n'a existé que dans un brouillon (D-026) |
| `criterion_change` | id, from_version_id, to_version_id, code, change_type (`broadening` / `narrowing` / `clarification` / `added` / `removed`), proposed_by (IA ou humain), confirmed_by, rationale | EF-VER-03 (à venir avec l'analyse d'impact) |

### 5.3 Recherche et collecte

| Table | Champs principaux |
|---|---|
| `search_strategy_version` | id, number, created_at, author_id, rationale |
| `concept_block` | strategy_version_id, code, label, pcc_element, terms_json (termes libres, descripteurs avec vocabulaire, langue, statut vérifié) |
| `query` | id, strategy_version_id, database (`openalex`, `pubmed`, `psycinfo_ebsco`, …), syntax_text, generated_by, edited (bool) |
| `search_run` | id, query_id, executed_at, result_count, status, raw_dir |
| `import_file` | id, filename, sha256, format, database_declared, imported_at, record_count, warnings_json |
| `key_article` | id, identifier (DOI/PMID/titre), note — pour le test de sensibilité |
| `sensitivity_check` | id, query_id, executed_at, found_json, missing_json, recall |

### 5.4 Références, provenance, doublons

| Table | Champs principaux | Notes |
|---|---|---|
| `reference` | id, title, abstract, authors_json, year, container_title, volume, issue, pages, doi, pmid, openalex_id, language, doc_type, url, oa_url | Champs normalisés |
| `provenance` | id, reference_id, source (`openalex` / `pubmed` / `ris` / `oai` / `manual`), search_run_id, import_file_id, original_id, raw_pointer | EF-COL-05; plusieurs par référence |
| `duplicate_link` | id, primary_reference_id, duplicate_reference_id, method (`doi` / `pmid` / `fuzzy` / `manual`), score, decided_by_reviewer_id, created_at, active | Réversible : désactiver un lien en crée un nouveau état (EF-COL-07) |

### 5.5 Sélection

| Table | Champs principaux | Notes |
|---|---|---|
| `screening_round` | id, stage (`title_abstract` / `full_text`), kind (`pilot` / `main` / `reassessment` / `audit_sample`), criteria_version_id, sample_seed, sample_size, created_at, closed_at, metrics_json | Un tour de pilote, le tri principal, une réévaluation, un échantillon de vérification |
| `decision` | id, reference_id, stage, round_id, reviewer_id, reviewer_kind, value (`include` / `exclude` / `uncertain`), confidence_raw, confidence_calibrated, rationale, criteria_cited_json, per_criterion_json, criteria_version_id, context (`independent` / `reconciliation` / `reassessment` / `audit`), blinded, supersedes_decision_id, ai_call_id, tool_version, created_at | **Ajout seulement.** Contient tous les champs d'ENF-TRA-01 directement ou via `ai_call` |
| `calibration_model` | id, round_id, ai_config_id, method (`isotonic` / `platt` / `none`), artifact_path, fitted_on_n, created_at | EF-SEL-05 |
| `threshold_setting` | id, stage, ai_config_id, exclude_below, include_above, target_sensitivity, justification, based_on_round_id, created_at | EF-SEL-09 |
| `impact_assessment` | id, from_version_id, to_version_id, change_ids_json, affected_reference_ids_json, affected_count, reassessment_mode, reassessment_round_id, status | EF-VER-04/05 |

**État courant** d'une référence à une étape (vue calculée) : la dernière décision de réconciliation si elle existe; sinon, en V1, la décision humaine indépendante; une décision IA seule ne détermine l'état courant que si le mode d'exclusion assistée (EF-SEL-11) est actif et que la décision dépasse le seuil.

### 5.6 Appels aux modèles

| Table | Champs principaux |
|---|---|
| `ai_call` | id, ai_config_id, provider, model_requested, **model_returned** (identifiant exact renvoyé par l'API), provider_request_id, prompt_template_id, prompt_template_version, prompt_sha256, params_json, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_estimate, currency, latency_ms, batch_id, response_path, status, error_code, created_at |
| `budget` | id, scope (`project` / `batch`), limit_amount, currency, spent_amount, updated_at |

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

### 6.4 Invites

- Gabarits Jinja2 dans `ai/prompts/`, chacun avec un fichier de métadonnées (`id`, `version`, `task`, `changelog`). Modifier un gabarit = incrémenter sa version.
- **Structure de l'invite de tri** : instructions fixes → critères de la version en vigueur (avec exemples et contre-exemples) → référence. Les deux premiers blocs forment un **préfixe stable** qui profite de la mise en cache des invites (ENF-COU-04).
- Deux stratégies configurables, à comparer dans l'étude de validation : **un appel par référence** évaluant tous les critères (par défaut, moins coûteux) ou **un appel par critère** (Vembye et al., 2025).
- Sortie **structurée** (schéma JSON) : pour chaque critère, `status` (`met` / `not_met` / `cannot_tell`), `evidence_quote`; puis `decision`, `confidence`, `rationale`, `decisive_criteria`.
- **Règle codée en dur, pas laissée au modèle** : si un critère d'inclusion est `cannot_tell` et aucun critère n'est `not_met`, la décision est au minimum `uncertain` (EF-SEL-07).

### 6.5 Confiance et étalonnage

1. **Score brut** : confiance déclarée par le modèle; option : proportion de *k* exécutions concordantes (auto-cohérence), au prix de *k* fois le coût.
2. **Étalonnage** après chaque tour de pilote : régression isotonique (ou Platt si peu de données) du score brut vers la probabilité observée que l'humain inclue; sérialisée dans `etalonnage/`, référencée par `calibration_model`.
3. **Seuils** appliqués sur la confiance étalonnée; la courbe seuil → sensibilité / charge évitée est présentée à l'équipe (EF-SEL-03, EF-SEL-05).
4. **Limite assumée** : avec peu d'inclusions dans le pilote, l'estimation de la sensibilité est imprécise; l'outil affiche l'intervalle de confiance (méthode de Wilson ou exacte) et refuse le mode d'exclusion assistée si la borne inférieure est sous la cible (EF-SEL-11).

### 6.6 Coûts

`ai/costs.py` estime le coût avant chaque lot (jetons d'entrée estimés × tarif + sortie moyenne observée), vérifie le plafond, enregistre le coût réel par appel et arrête proprement au plafond (ENF-COU-01 à 03). L'API de traitement par lots du fournisseur est utilisée pour les lots non urgents quand elle est offerte.

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

La réévaluation crée un `screening_round` de type `reassessment`; les nouvelles décisions pointent vers la nouvelle version des critères; les anciennes demeurent. Le diagramme de flux et la section méthode rendent compte des réévaluations.

## 8. Connecteurs de sources

- Interface `Source` : `count(query)`, `fetch(query) -> Iterator[RawRecord]` (paginé, reprenable), `normalize(raw) -> Reference`.
- **Limiteur de débit** par source, paramétré selon les conditions de 2026 (voir [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026)) : OpenAlex (clé requise, suivi de l'allocation quotidienne), PubMed (3 ou 10 requêtes/s, `tool` et `email`), Crossref (pool « poli », concurrence ≤ 3), Unpaywall (`email`).
- Nouvelle tentative avec attente exponentielle sur 429 et 5xx; arrêt propre et message clair en français si le **domaine est bloqué par la liste réseau** de l'environnement.
- Chaque page brute est conservée dans `brut/sources/`.

## 9. Interface web

- Rendu côté serveur, HTMX pour les interactions partielles (tri au clavier sans recharger la page).
- Pages V1 : tableau de bord du projet (étape courante, nombres, coûts), cadrage PCC et critères (avec historique et différentiel), stratégie de recherche et test de sensibilité, collecte et imports, doublons à confirmer, pilote (tri à l'aveugle puis tableau d'étalonnage), tri principal, réconciliation, analyse d'impact, journal, exports.
- Pages livrées à la tranche 1.1 : « Cadrage », « Critères » (version en vigueur, brouillon, versions, différentiel) et « Journal » (entrées, notes, vérification de la chaîne).
- Navigation avec `hx-boost`; les réponses 4xx et 5xx sont affichées (configuration `htmx-config`), car l'application renvoie ses erreurs de formulaire comme des pages complètes (D-033). Les formulaires fonctionnent aussi sans JavaScript.
- Chaînes d'interface dans le catalogue Babel de `i18n/` (D-031).
- **Sécurité locale** (D-032) : chaque formulaire porte un jeton propre au processus du serveur; les en-têtes `Host` autres que `127.0.0.1` ou `localhost`, et les en-têtes `Origin` étrangers sur les écritures, sont refusés (requêtes intersites, DNS rebinding).
- **Tâches de fond** (`jobs/`) : file persistée dans SQLite, exécutée par un fil de travail dans le processus du serveur; reprise au redémarrage (ENF-PER-04). Pas de Celery ni de Redis.

## 10. Sécurité et secrets

- `config/secrets.py` est le **seul** module qui lit les variables d'environnement sensibles (un test d'architecture l'impose); il renvoie des `SecretStr` (Pydantic) dont la représentation est masquée.
  - Clé Anthropic : `REVUE_PORTEE_ANTHROPIC_KEY`, à défaut `ANTHROPIC_API_KEY` (D-020); toutes les valeurs définies sont enregistrées pour le masquage.
  - `CONTACT_EMAIL` : obligatoire. `OPENALEX_API_KEY` : facultative, car le mandataire réseau de l'environnement infonuagique l'ajoute aux requêtes (D-021).
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
| Connecteurs avec réponses enregistrées | `tests/unit/sources/` + `tests/cassettes/` | Non (mode lecture seule des cassettes) | `uv run pytest` |
| Services avec `FakeProvider` | `tests/unit/` | Non | `uv run pytest` |
| Intégration réelle (API de sources, Claude) | `tests/integration/`, marqueur `integration` | **Oui** | `uv run pytest -m integration` — **volontairement seulement** |
| Performance de tri sur SYNERGY (sous-ensemble) | `tests/benchmarks/` (V1, tranche 7) | Oui (modèle) | Manuel, résultats consignés |

`pyproject.toml` configure `addopts` avec `-m "not integration"` et `--record-mode=none` (cassettes en lecture seule), et `tests/conftest.py` bloque le réseau pour tout test non marqué `integration` (D-016) : aucun test ordinaire ne peut atteindre le réseau. Pour enregistrer une cassette : `uv run pytest -m integration --record-mode=once`, puis nettoyage et vérification anti-secrets.

**Couverture** (ENF-QUA-04, D-023) : chaque exécution de `pytest` mesure la couverture de `revue_portee`, branches comprises (pytest-cov). Le greffon `tests/_plugins/coverage_gate.py` fait échouer la suite si l'un des paquets `domain`, `dedup` ou `reporting` est sous 90 %, chacun séparément. Le seuil n'est vérifié que sur la suite complète, et se règle dans `pyproject.toml` (`coverage_gate_packages`, `coverage_gate_fail_under`).

**Vérifications avant fusion** (ENF-QUA-03) : `ruff check`, `ruff format --check`, `mypy` et `pytest`, exécutées aussi par la CI GitHub (`.github/workflows/ci.yml`, Python 3.12 et 3.13). ruff ignore `docs/` et les fichiers `*.md` (D-019).

## 12. Évolution vers une version hébergée (V4 ou plus tard)

Le découpage domaine / stockage / web permet de remplacer SQLite par PostgreSQL et d'ajouter l'authentification sans toucher au domaine. Points à prévoir dès maintenant : identifiants ULID (pas d'entiers auto-incrémentés liés à un fichier), aucun état global dans le processus web, réviseurs identifiés dans toutes les tables. La licence AGPL (recommandée) imposerait alors de publier le code de la version hébergée.
