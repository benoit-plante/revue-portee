# CLAUDE.md — revue-portee

Lis ce fichier en entier au début de chaque session. Il est court; les détails sont dans `docs/`.

## Le projet

**revue-portee** : logiciel libre (Python) qui accompagne une équipe de recherche dans une revue de portée (*scoping review*) selon la méthode **JBI** et la norme **PRISMA-ScR**, avec l'IA comme **second réviseur traçable**. Fonctionnalité distinctive : critères d'inclusion et grille d'extraction **versionnés**, avec **analyse d'impact** des changements et réévaluation. V1 = application **web locale** (FastAPI, interface en français) + ligne de commande; **un réviseur humain + l'IA**.

Projet personnel de Benoit Plante (dépôt privé `benoit-plante/revue-portee`). Benoit révise chaque demande de fusion.

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
- Toute nouvelle dépendance : `uv add <paquet>`, vérifier sa licence (pas de licence non commerciale ni « sans dérivé »), la mentionner dans la demande de fusion. Licence du projet : **AGPL-3.0-or-later** (D-004); dépendances compatibles seulement.
- Toute fonction qui produit un nombre déclaré (diagramme, accord, sensibilité) a un test sur un cas calculé à la main.

## Git et flux de travail

- Ne jamais committer sur `main`. Une branche par tranche : `tranche/<version>.<n>-<nom-court>` (ex. `tranche/1.3-requetes`).
- Demande de fusion : tranche visée, exigences couvertes (identifiants), critères d'acceptation cochés, nouvelles dépendances et licences, décisions proposées pour le journal, ce qui n'a pas été fait.
- **Ne pas modifier `docs/`** (rédigé dans Cowork), sauf : créer ou alimenter `docs/resultats/` quand une tranche le prévoit. Proposer tout autre changement de documentation dans la demande de fusion.
- Écart à `docs/03-architecture.md` : le signaler et le justifier dans la demande de fusion.

## Environnement infonuagique

- VM **Ubuntu 24.04 neuve à chaque session**; Python, **uv**, pytest, ruff préinstallés. Rien ne persiste hors du dépôt.
- **Réseau limité à une liste** : `api.openalex.org`, `eutils.ncbi.nlm.nih.gov`, `api.crossref.org`, `api.unpaywall.org` + registres de paquets. Toute nouvelle source (Érudit, theses.fr, HAL, dépôts OAI-PMH…) exige que **Benoit ajoute son domaine** dans les réglages : ne pas contourner, le signaler.
- Variables disponibles :
  - `REVUE_PORTEE_ANTHROPIC_KEY` : clé d'API Anthropic du projet. `ANTHROPIC_API_KEY` est lue seulement à défaut, car elle peut servir à l'authentification de la session Claude Code elle-même (D-020);
  - `CONTACT_EMAIL` : adresse de contact transmise aux API bibliographiques;
  - `OPENALEX_API_KEY` : **facultative**. Dans l'environnement infonuagique, le mandataire réseau ajoute lui-même la clé aux requêtes vers `api.openalex.org`, et la variable est absente (D-013, D-021).
- Si une variable obligatoire manque, le code échoue proprement avec un message clair en français qui nomme la variable.
- Dépendances installées par le **hook SessionStart** de `.claude/settings.json` (en place depuis le jalon 0) :

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

  Le hook doit être idempotent et rapide. `CLAUDE_CODE_REMOTE=true` indique une session infonuagique si une différence de comportement est nécessaire.

## Secrets — règles absolues

- **Ne jamais afficher, journaliser, imprimer, écrire dans un fichier ni committer** la valeur de `REVUE_PORTEE_ANTHROPIC_KEY`, `ANTHROPIC_API_KEY`, `OPENALEX_API_KEY`, `CONTACT_EMAIL` ou de toute autre clé. Pas de `echo $REVUE_PORTEE_ANTHROPIC_KEY`, pas de `env`/`printenv` sans filtre, pas de valeur dans un message d'erreur, une exception, un `repr`, une cassette de test ou un dossier de projet.
- Pour vérifier qu'une variable existe : `test -n "$REVUE_PORTEE_ANTHROPIC_KEY" && echo "défini"`.
- Seul `src/revue_portee/config/secrets.py` lit ces variables (`get_secret`, `get_optional_secret`, `configured_secrets`; valeurs en `SecretStr`). Un test d'architecture l'impose.
- Tout point d'entrée (ligne de commande, serveur web) appelle `install_secret_redaction()` au démarrage : les secrets chargés et les motifs de clés connus sont alors masqués dans toutes les entrées de journal, dès leur création (D-024). Ne pas ajouter de gestionnaire qui rend lui-même les exceptions à partir de `record.exc_info` (par exemple `RichHandler`) : il contournerait le masquage des traces.
- Cassettes de test : filtrer `x-api-key`, `authorization`, `api_key`, `email`, `mailto` **avant** de les committer, en les remplaçant par `DUMMY` (clés, en-têtes) et `contact@example.org` (adresses). `tests/conftest.py` applique déjà ce filtrage à l'enregistrement.
- Le test anti-secrets de `tests/` n'accepte que des valeurs visiblement fictives : marqueurs `DUMMY`, `FAKE`, `REDACTED`, `example`…, ou domaines réservés (`example.org`, `.test`, `.invalid`) (D-017). Dans un test, construire toute chaîne qui ressemble à un secret par concaténation **explicite** (`"sk-" + "ant-"`, `"api_" + "key"`) : ruff fusionne les concaténations implicites.

## Tests

- Les tests ordinaires **n'appellent jamais les vraies API** : réponses enregistrées (pytest-recording, mode lecture seule) et `FakeProvider` pour l'IA. Le réseau leur est bloqué : toute tentative de connexion échoue (D-016).
- Les tests qui appellent de vrais services portent le marqueur `@pytest.mark.integration`, sont exclus par défaut et ne sont lancés **que sur demande explicite de Benoit** (ils coûtent et consomment des quotas).
- Enregistrer une nouvelle cassette = test d'intégration lancé volontairement (`uv run pytest -m integration --record-mode=once`), puis nettoyage et vérification anti-secrets.
- Utilitaires partagés dans `tests/support.py` : horloge déterministe (`make_clock`), projet de test (`new_project`), accès SQLite direct (`raw_sqlite`).
- **Couverture** : `uv run pytest` mesure la couverture (branches comprises) et **échoue** si l'un des paquets `domain`, `dedup` ou `reporting` est sous 90 % (D-023). Le seuil n'est vérifié que sur la suite complète : un fichier seul, `-k`, `-m` ou `--lf` l'ignorent, avec un avertissement. Réglages dans `pyproject.toml` (`coverage_gate_packages`, `coverage_gate_fail_under`).

## Commandes

```bash
uv sync                              # installer / mettre à jour l'environnement
uv run pytest                        # tests (sans réseau, sans intégration), couverture et seuil de 90 %
uv run pytest -m integration         # tests d'intégration — seulement sur demande
uv run ruff check . && uv run ruff format --check .   # avant chaque commit
uv run ruff format .                 # formater
uv run mypy                          # vérification des types (mode strict)
uv add <paquet> / uv add --dev <paquet>
uv run revue-portee --version        # ligne de commande
uv run revue-portee nouveau ma-revue --titre "…" --reviseur "…"   # crée ma-revue.revue/
uv run revue-portee serve ma-revue   # interface web sur http://127.0.0.1:8000/
uv run revue-portee verifier-journal ma-revue   # vérifie la chaîne d'empreintes (lecture seule)
```

Avant de proposer une demande de fusion : `ruff check`, `ruff format --check`, `mypy` et `pytest` (seuil de couverture compris) doivent passer. La CI GitHub (`.github/workflows/ci.yml`) les exécute sous Python 3.12 et 3.13.

## Si tu es bloqué

Ne devine pas une décision de méthode (critères, seuils, règles d'exclusion, licence, nouvelle source) : écris l'hypothèse retenue dans la demande de fusion ou pose la question à Benoit.
