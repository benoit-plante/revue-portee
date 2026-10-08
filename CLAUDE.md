# CLAUDE.md — revue-portee

Lis ce fichier en entier au début de chaque session. Il est court; les détails sont dans `docs/`.

## Le projet

**revue-portee** : logiciel libre (Python) qui accompagne une équipe de recherche dans une revue de portée (*scoping review*) selon la méthode **JBI** et la norme **PRISMA-ScR**, avec l'IA comme **second réviseur traçable**. Fonctionnalité distinctive : critères d'inclusion et grille d'extraction **versionnés**, avec **analyse d'impact** des changements et réévaluation. V1 = application **web locale** (FastAPI, interface en français) + ligne de commande; **un réviseur humain + l'IA**.

Projet personnel de Benoit Plante (dépôt **public** `benoit-plante/revue-portee`, rendu public le 2026-10-07 : tout ce qui est poussé, historique compris, est visible de tous). Benoit révise chaque demande de fusion.

## À lire selon la tâche

| Avant de… | Lire |
|---|---|
| Toute tâche | `docs/04-feuille-de-route.md` (trouver la tranche en cours et ses critères d'acceptation) |
| Écrire une fonctionnalité | `docs/02-exigences.md` (identifiants `EF-…`, `ENF-…`) |
| Créer un module, une table, un connecteur, un fournisseur d'IA | `docs/03-architecture.md` |
| Faire un choix non prévu | `docs/journal-des-decisions.md` (décisions prises et proposées) |
| Toucher au tri par l'IA, aux seuils, à l'étalonnage | `docs/05-plan-de-validation.md` et `docs/01-etat-de-l-art.md` §4 |
| Comprendre le pourquoi | `docs/00-vision.md` |

## Principes non négociables

1. **Aucune exclusion entièrement automatique** sans étalonnage préalable (essai pilote) et vérification humaine d'un échantillon. En V1 : aucune exclusion par l'IA seule.
2. **Traçabilité complète** : chaque décision enregistre type de réviseur (humain/IA), identité, modèle et **version exacte renvoyée par l'API**, confiance, justification, critères cités, date UTC, version des critères ou de la grille, version du gabarit d'invite (ENF-TRA-01). Rien n'est modifié ni supprimé : on ajoute.
3. **Alignement RAISE et PRISMA-ScR.**
4. **Couche d'abstraction des modèles** : les services ne connaissent que `ModelProvider` / `TaskSpec`; jamais de nom de modèle codé en dur.
5. **Aucune donnée de participants** : seulement de la littérature publiée.

## Conventions

- **Code, identifiants, commentaires, docstrings, messages de commit : anglais.** Documentation et interface : **français** (guillemets « », espace insécable avant `:` `;` `?` `!` dans l'interface). Chaînes d'interface externalisées (Babel, D-031) :
  - dans le code, `gettext as _` (interface) ou `french` (résumés `summary_fr` du journal), importés de `revue_portee.i18n`; dans les gabarits, `{{ _("…") }}`; identifiants de message **en anglais**;
  - après tout ajout ou changement de message, mettre à jour puis traduire le catalogue `src/revue_portee/i18n/locale/fr/LC_MESSAGES/messages.po` (commandes dans `babel.cfg`); `tests/unit/test_i18n.py` échoue s'il manque une traduction.
- Disposition `src/revue_portee/`, tests dans `tests/`. Le module `domain/` n'importe rien d'externe hors Pydantic.
- Typage complet, vérifié par **mypy en mode strict** (D-022); Pydantic v2 pour les modèles; fonctions pures pour les calculs (métriques, impact, dédoublonnage, diagramme).
- Cas d'usage dans des modules par étape (`protocol/` pour l'étape 1, puis `search/`, `screening/`…). Toute écriture dans un projet passe par `with folder.write() as connection:` (`BEGIN IMMEDIATE`, D-036), et chaque action consigne son entrée de journal dans la même transaction. Ne jamais modifier ni supprimer une ligne en ajout seulement : la base le refuse (déclencheurs, D-028).
- Dans les chaînes d'interface du code, utiliser de vraies espaces insécables (U+00A0); ruff les autorise (D-018). ruff ignore `docs/` et les fichiers `*.md` (D-019) : ne pas lancer d'autre formateur sur la documentation.
- Appels à l'IA : un cas d'usage affiche d'abord le coût (`protocol.ai_assist.preview`), puis appelle `run_and_record` après confirmation; chaque appel est consigné dans sa propre transaction avec sa réponse brute (D-041). Noms de modèles et paramètres seulement dans `resources/ai_defaults.yaml` et `[ia]` de `projet.toml`; tarifs datés dans `resources/model_prices.yaml`; gabarits d'invite dans `ai/prompts/<id>/` (modifier un gabarit = incrémenter sa version **et** ajouter son entrée dans `docs/08-journal-des-gabarits.md` : motif, données de mise au point, versions essayées, données de test mises de côté, appels réels; un test l'exige). Seul `ai/providers/anthropic.py` importe le SDK `anthropic`.
- Appels aux API bibliographiques : seulement par `sources/` (client `httpx2` de `sources/http.py` : limiteur de débit, nouvelles tentatives, `SourceError` en français); les services reçoivent une fabrique de connecteurs (`SourceFactory`) et conservent chaque réponse brute dans `brut/sources/` avant d'en consigner le résultat. Les requêtes sont produites par `search/translate.py` à partir des blocs de concepts : ne pas écrire de requête à la main dans le code.
- Collecte et import (`collect/`) : une page collectée s'enregistre avec ses références, leurs provenances et son entrée de journal dans une seule transaction, après sa réponse brute (D-053); une référence n'est jamais modifiée, l'enrichissement Crossref s'ajoute dans `enrichment` (D-055). Les tâches longues de l'interface passent par `jobs/runner.py` (`BackgroundJobs`) et doivent pouvoir reprendre en étant relancées (D-059).
- Dédoublonnage : règles pures dans `dedup/`, cas d'usage dans `collect/deduplication.py`. Rien n'est supprimé : les liens, les groupes et la référence principale se calculent à partir de la dernière exécution et des décisions (D-061). Toute modification des règles d'appariement incrémente `ALGORITHM_VERSION` (`domain/dedup.py`), et `tests/unit/dedup/test_benchmark.py` doit rester au-dessus des cibles (D-062).
- Tri (`screening/`) : décisions en ajout seulement; une nouvelle décision sur la même référence remplace la précédente (`supersedes_decision_id`). La valeur de l'IA se déduit de la probabilité d'inclusion et des seuils en vigueur, puis de la règle EF-SEL-07 (`domain/screening.py`, D-065, D-068) : ne jamais la prendre telle quelle du modèle. L'aveugle passe par `PilotState.visible_ai` (D-071). Le plafond du projet et celui du lot se vérifient avant chaque appel, nouvelles tentatives comprises (D-069). Modifier le gabarit `screen_reference` = incrémenter sa version et relancer le banc SYNERGY. Tri principal et réévaluation (`screening/main.py`, `reassessment.py`) : l'état courant est la dernière décision humaine; un désaccord oppose « conserver » à « exclure » (D-079); l'IA n'est montrée qu'à la réconciliation et à la vérification d'une réévaluation. Lots d'IA seulement par `screening/batch_ai.py` (API Batches, D-080) : estimation réservée avant chaque lot, collecte qui reprend sans repayer. Le passage à la référence suivante doit rester sous 200 ms sur 50 000 références (`tests/unit/web/test_screening_performance.py`) : pas de calcul sur toutes les références dans ce chemin.
- Rapports (tranche 1.8) : les nombres du diagramme se calculent à chaque export à partir des données (`reporting/flow.py`, fonctions pures), jamais saisis; libellés du gabarit dans `resources/reporting/prisma_2020_flow.yaml`. Section méthode : faits tirés du projet, marqueurs « À compléter » pour ce que seule l'équipe peut écrire (D-093). Archive publique sans résumé, URL, réponse brute ni base (D-092) : tout nombre ajouté au diagramme doit pouvoir se recompter à partir d'elle (`tests/unit/screening/test_archive.py`). Le jeu de démonstration (`tests/demo.py`, `tests/fixtures/demo/README.md`) sert de décompte à la main.
- Toute nouvelle dépendance : `uv add <paquet>`, vérifier sa licence (pas de licence non commerciale ni « sans dérivé »), la mentionner dans la demande de fusion. Licence du projet : **AGPL-3.0-or-later** (D-004); dépendances compatibles seulement.
- Toute fonction qui produit un nombre déclaré (diagramme, accord, sensibilité) a un test sur un cas calculé à la main.

## Git et flux de travail

- Ne jamais committer sur `main`. Une branche par tranche : `tranche/<version>.<n>-<nom-court>` (ex. `tranche/1.3-requetes`).
- Demande de fusion : tranche visée, exigences couvertes (identifiants), critères d'acceptation cochés, nouvelles dépendances et licences, décisions proposées pour le journal, ce qui n'a pas été fait.
- **Ne pas modifier `docs/`** (rédigé dans Cowork), sauf : créer ou alimenter `docs/resultats/` quand une tranche le prévoit. Proposer tout autre changement de documentation dans la demande de fusion.
- Écart à `docs/03-architecture.md` : le signaler et le justifier dans la demande de fusion.

## Environnement de développement

Claude Code tourne **sur le poste de Benoit** depuis le 2026-10-08 (D-085); l'environnement infonuagique reste possible (voir plus bas). Le dépôt est le même dans les deux cas : installation par `uv`, tests sans réseau, secrets lus par `config/secrets.py`.

### Poste local (par défaut)

- macOS, Linux ou Windows (natif ou WSL). Prérequis : Python 3.12 ou plus récent, **uv** et Git dans le `PATH`; `gh` (connecté au compte de Benoit) pour ouvrir les demandes de fusion. Les fichiers persistent d'une session à l'autre : après un changement de `uv.lock`, lancer `uv sync`.
- Le **hook SessionStart** de `.claude/settings.json` (ci-dessous) s'exécute aussi en local et installe les dépendances (`uv sync --frozen`).
- **Réseau libre** : aucune liste ne bloque plus les domaines. Les tests ordinaires restent coupés du réseau (D-016). Tout appel réel (tests d'intégration, cassettes, banc SYNERGY, API Anthropic) reste **sur demande explicite de Benoit**, et toute nouvelle source (Érudit, theses.fr, HAL, dépôts OAI-PMH…) lui est **signalée** avant d'être utilisée (méthode, licence).
- Variables, définies par Benoit dans le profil de son shell ou dans `env` de `.claude/settings.local.json` (non versionné), **jamais** dans un fichier du dépôt; ne jamais créer ni modifier ces fichiers de réglages personnels :
  - `REVUE_PORTEE_ANTHROPIC_KEY` : clé d'API Anthropic du projet. Ne **pas** définir `ANTHROPIC_API_KEY` dans le shell : Claude Code pourrait s'en servir pour s'authentifier et facturer les sessions de développement sur la clé du projet (D-020); le code ne la lit qu'à défaut;
  - `CONTACT_EMAIL` : adresse de contact transmise aux API bibliographiques;
  - `OPENALEX_API_KEY` : **nécessaire** sur le poste, car OpenAlex l'exige et aucun mandataire ne l'ajoute (D-013); le code ne l'envoie que si elle est définie (D-021).
- Données de travail **hors du dépôt**, par exemple dans `~/revue-portee-donnees/` : jeux SYNERGY (CSV), réponses brutes du banc (`*.brut.jsonl`), projets `.revue` d'essai, captures d'écran. Le dépôt est public : ne jamais y déplacer ces fichiers.

### Environnement infonuagique (encore possible)

- VM **Ubuntu 24.04 neuve à chaque session**; Python, **uv**, pytest, ruff préinstallés. Rien ne persiste hors du dépôt.
- **Réseau limité à une liste** : `api.openalex.org`, `eutils.ncbi.nlm.nih.gov`, `api.crossref.org`, `api.unpaywall.org`, `api.anthropic.com`, `dataverse.nl` et `objectstore.surf.nl` (données SYNERGY, D-075) + registres de paquets. Toute nouvelle source exige que **Benoit ajoute son domaine** dans les réglages : ne pas contourner, le signaler.
- Mêmes variables, définies dans les réglages de l'environnement, sauf `OPENALEX_API_KEY` : le mandataire réseau ajoute lui-même la clé aux requêtes vers `api.openalex.org`, et la variable est absente (D-021).
- `CLAUDE_CODE_REMOTE=true` indique une session infonuagique si une différence de comportement est nécessaire.

### Dans les deux cas

- Si une variable obligatoire manque, le code échoue proprement avec un message clair en français qui nomme la variable.
- Dépendances installées par le **hook SessionStart** de `.claude/settings.json` (en place depuis le jalon 0), qui doit rester idempotent et rapide :

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv sync --frozen" }
        ]
      }
    ]
  }
}
```

## Secrets — règles absolues

- **Ne jamais afficher, journaliser, imprimer, écrire dans un fichier ni committer** la valeur de `REVUE_PORTEE_ANTHROPIC_KEY`, `ANTHROPIC_API_KEY`, `OPENALEX_API_KEY`, `CONTACT_EMAIL` ou de toute autre clé. Pas de `echo $REVUE_PORTEE_ANTHROPIC_KEY`, pas de `env`/`printenv` sans filtre, pas de valeur dans un message d'erreur, une exception, un `repr`, une cassette de test ou un dossier de projet.
- Pour vérifier qu'une variable existe : `test -n "$REVUE_PORTEE_ANTHROPIC_KEY" && echo "défini"`.
- Seul `src/revue_portee/config/secrets.py` lit ces variables (`get_secret`, `get_optional_secret`, `configured_secrets`; valeurs en `SecretStr`). Un test d'architecture l'impose.
- Tout point d'entrée (ligne de commande, serveur web) appelle `install_secret_redaction()` au démarrage : les secrets chargés et les motifs de clés connus sont alors masqués dans toutes les entrées de journal, dès leur création (D-024). Ne pas ajouter de gestionnaire qui rend lui-même les exceptions à partir de `record.exc_info` (par exemple `RichHandler`) : il contournerait le masquage des traces.
- Cassettes de test : filtrer `x-api-key`, `authorization`, `api_key`, `email`, `mailto` **avant** de les committer, en les remplaçant par `DUMMY` (clés, en-têtes) et `contact@example.org` (adresses). `tests/conftest.py` applique déjà ce filtrage à l'enregistrement.
- Le test anti-secrets de `tests/` n'accepte que des valeurs visiblement fictives : marqueurs `DUMMY`, `FAKE`, `REDACTED`, `example`…, ou domaines réservés (`example.org`, `.test`, `.invalid`) (D-017). Dans un test, construire toute chaîne qui ressemble à un secret par concaténation **explicite** (`"sk-" + "ant-"`, `"api_" + "key"`) : ruff fusionne les concaténations implicites.

## Tests

- Les tests ordinaires **n'appellent jamais les vraies API** : réponses enregistrées (pytest-recording, mode lecture seule) et `FakeProvider` pour l'IA. Le réseau leur est bloqué : toute tentative de connexion échoue (D-016), sauf vers 127.0.0.1, dont la boucle asyncio a besoin sous Windows; les variables de mandataire (`HTTPS_PROXY`…) leur sont retirées.
- Les tests qui appellent de vrais services portent le marqueur `@pytest.mark.integration`, sont exclus par défaut et ne sont lancés **que sur demande explicite de Benoit** (ils coûtent et consomment des quotas).
- Enregistrer une nouvelle cassette = appel volontaire au vrai service, **sur autorisation de Benoit**, puis nettoyage et vérification anti-secrets :
  - cassettes vcrpy (`httpx`) : `uv run pytest -m integration --record-mode=once`;
  - connecteurs `httpx2` (PubMed, OpenAlex) : tests marqués `cassette`, fixture `http_cassette` (`tests/recording.py`, D-047), cassettes dans `tests/cassettes/<module>/<test>.json`; `uv run pytest <fichier ou test> --record-mode=once` enregistre seulement les cassettes absentes (supprimer une cassette pour la réenregistrer).
- Exports RIS réels (`tests/fixtures/ris/`) : seulement des **extraits** nettoyés, octets conservés (`.gitattributes` : `-text`) : résumés tronqués, courriels masqués, identifiants d'abonnement neutralisés; jamais l'export complet (D-057). Les réponses des cassettes `httpx2` sont réduites à l'enregistrement par `trim_body` (D-058).
- Jeu annoté du dédoublonnage (`tests/fixtures/dedup/`) : métadonnées seulement, jamais de résumés, d'URL ni de numéros d'accès (D-060).
- Banc SYNERGY (`revue-portee banc-synergy`) : appelle le vrai modèle, donc **seulement sur demande de Benoit**, avec un plafond. Les CSV des jeux et les réponses brutes restent hors du dépôt; seuls les rapports chiffrés et les critères (`docs/resultats/synergy/`) sont versionnés (D-074, D-075).
- Utilitaires partagés dans `tests/support.py` : horloge déterministe (`make_clock`), projet de test (`new_project`), accès SQLite direct (`raw_sqlite`), fabrique de `FakeProvider` par tâche pour les services et l'interface (`fake_factory`).
- **Couverture** : `uv run pytest` mesure la couverture (branches comprises) et **échoue** si l'un des paquets `domain`, `dedup` ou `reporting` est sous 90 % (D-023). Le seuil n'est vérifié que sur la suite complète : un fichier seul, `-k`, `-m` ou `--lf` l'ignorent, avec un avertissement. Réglages dans `pyproject.toml` (`coverage_gate_packages`, `coverage_gate_fail_under`).

## Commandes

```bash
uv sync                              # installer / mettre à jour l'environnement
uv run pytest                        # tests (sans réseau, sans intégration), couverture et seuil de 90 %
uv run pytest -m integration         # tests d'intégration — seulement sur demande
uv run pytest tests/unit/search --record-mode=once   # enregistre les cassettes absentes — seulement sur demande
uv run ruff check . && uv run ruff format --check .   # avant chaque commit
uv run ruff format .                 # formater
uv run mypy                          # vérification des types (mode strict)
uv add <paquet> / uv add --dev <paquet>
uv run revue-portee --version        # ligne de commande
uv run revue-portee nouveau ma-revue --titre "…" --reviseur "…"   # crée ma-revue.revue/
uv run revue-portee serve ma-revue   # interface web sur http://127.0.0.1:8000/
uv run revue-portee verifier-journal ma-revue   # vérifie la chaîne d'empreintes (lecture seule)
uv run revue-portee protocole ma-revue --langue fr   # écrit protocole-fr.md et .docx dans exports/
uv run revue-portee diagramme ma-revue   # diagramme de flux du tri (SVG, fr et en) dans exports/
uv run revue-portee methode ma-revue     # ébauche de section méthode sur l'IA au tri (md et docx, fr et en)
uv run revue-portee archive ma-revue [--complete]   # archive publique (ou complète, privée) dans exports/
uv run revue-portee retenues ma-revue    # références retenues pour le texte intégral (RIS et CSV) dans exports/
```

Avant de proposer une demande de fusion : `ruff check`, `ruff format --check`, `mypy` et `pytest` (seuil de couverture compris) doivent passer. La CI GitHub (`.github/workflows/ci.yml`) les exécute sous Python 3.12 et 3.13.

## Si tu es bloqué

Ne devine pas une décision de méthode (critères, seuils, règles d'exclusion, licence, nouvelle source) : écris l'hypothèse retenue dans la demande de fusion ou pose la question à Benoit.
