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

- **Code, identifiants, commentaires, docstrings, messages de commit : anglais.** Documentation et interface : **français** (guillemets « », espace insécable avant `:` `;` `?` `!` dans l'interface). Chaînes d'interface externalisées (Babel).
- Disposition `src/revue_portee/`, tests dans `tests/`. Le module `domain/` n'importe rien d'externe hors Pydantic.
- Typage complet; Pydantic v2 pour les modèles; fonctions pures pour les calculs (métriques, impact, dédoublonnage, diagramme).
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
- Variables disponibles : `ANTHROPIC_API_KEY`, `CONTACT_EMAIL`, `OPENALEX_API_KEY` (OpenAlex exige une clé depuis février 2026, D-013). Si une variable manque, le code échoue proprement avec un message clair en français.
- Dépendances installées par un **hook SessionStart** dans `.claude/settings.json` (à créer au jalon 0). Forme attendue :

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

- **Ne jamais afficher, journaliser, imprimer, écrire dans un fichier ni committer** la valeur de `ANTHROPIC_API_KEY`, `OPENALEX_API_KEY`, `CONTACT_EMAIL` ou de toute autre clé. Pas de `echo $ANTHROPIC_API_KEY`, pas de `env`/`printenv` sans filtre, pas de valeur dans un message d'erreur, une exception, un `repr`, une cassette de test ou un dossier de projet.
- Pour vérifier qu'une variable existe : `test -n "$ANTHROPIC_API_KEY" && echo "défini"`.
- Seul `src/revue_portee/config/secrets.py` lit ces variables (`SecretStr`).
- Cassettes de test : filtrer `x-api-key`, `authorization`, `api_key`, `email`, `mailto` (remplacer par des valeurs fictives) **avant** de les committer.

## Tests

- Les tests ordinaires **n'appellent jamais les vraies API** : réponses enregistrées (pytest-recording, mode lecture seule) et `FakeProvider` pour l'IA.
- Les tests qui appellent de vrais services portent le marqueur `@pytest.mark.integration`, sont exclus par défaut et ne sont lancés **que sur demande explicite de Benoit** (ils coûtent et consomment des quotas).
- Enregistrer une nouvelle cassette = test d'intégration lancé volontairement, puis nettoyage et vérification anti-secrets.

## Commandes (valides à partir du jalon 0)

```bash
uv sync                              # installer / mettre à jour l'environnement
uv run pytest                        # tests (sans réseau, sans intégration)
uv run pytest -m integration         # tests d'intégration — seulement sur demande
uv run ruff check . && uv run ruff format --check .   # avant chaque commit
uv run ruff format .                 # formater
uv add <paquet> / uv add --dev <paquet>
uv run revue-portee --help           # ligne de commande (nom à confirmer au jalon 0)
uv run revue-portee serve            # interface web sur 127.0.0.1
```

Avant de proposer une demande de fusion : `ruff check`, `ruff format --check` et `pytest` doivent passer.

## Si tu es bloqué

Ne devine pas une décision de méthode (critères, seuils, règles d'exclusion, licence, nouvelle source) : écris l'hypothèse retenue dans la demande de fusion ou pose la question à Benoit.
