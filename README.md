# revue-portee

Logiciel libre qui accompagne une équipe de recherche dans une revue de portée (*scoping review*) selon la méthode JBI et la norme PRISMA-ScR, avec l'IA comme second réviseur traçable. Licence : [AGPL-3.0-or-later](LICENSE).

## Démarrage

### Prérequis

- Python 3.12 ou plus récent;
- [uv](https://docs.astral.sh/uv/) pour gérer l'environnement et les dépendances.

### Installation

```bash
uv sync
```

Cette commande crée l'environnement virtuel `.venv/` et installe les dépendances verrouillées dans `uv.lock`. Dans les sessions infonuagiques de Claude Code, le hook SessionStart de `.claude/settings.json` l'exécute automatiquement (`uv sync --frozen`).

### Vérifier l'installation

```bash
uv run revue-portee --version
```

### Tests et style

```bash
uv run pytest                                         # tests ordinaires, sans réseau, avec couverture
uv run ruff check . && uv run ruff format --check .   # vérification du style
uv run ruff format .                                  # formatage
uv run mypy                                           # vérification des types (mode strict)
```

Le rapport de couverture (pytest-cov, branches comprises) s'affiche à la fin de `pytest`; il ne liste que les fichiers incomplètement couverts. Les paquets `domain`, `dedup` et `reporting` doivent chacun être couverts à au moins 90 % (ENF-QUA-04) : `uv run pytest` le vérifie automatiquement et échoue sinon. Le seuil n'est vérifié que sur la suite complète ; il est ignoré, avec un avertissement, quand on lance seulement une partie des tests (chemin explicite, `-k`, `-m`, `--lf`) ou avec `--no-cov`. Les paquets et le seuil se règlent dans `pyproject.toml` (`coverage_gate_packages`, `coverage_gate_fail_under`).

Les tests ordinaires n'appellent jamais les vraies API : ils utilisent des réponses enregistrées et un fournisseur d'IA factice, et l'accès au réseau y est bloqué. Les tests d'intégration, qui appellent de vrais services, sont exclus par défaut et se lancent seulement volontairement :

```bash
uv run pytest -m integration
```

### Variables d'environnement

| Variable | Rôle | Obligatoire |
|---|---|---|
| `REVUE_PORTEE_ANTHROPIC_KEY` (ou, à défaut, `ANTHROPIC_API_KEY`) | Clé d'API Anthropic du réviseur IA | Oui |
| `CONTACT_EMAIL` | Adresse de contact transmise aux API bibliographiques | Oui |
| `OPENALEX_API_KEY` | Clé d'API OpenAlex | Non (facultative si un mandataire réseau l'ajoute aux requêtes) |

Ces valeurs ne doivent jamais être écrites dans un fichier du dépôt, affichées ni journalisées. Le module `src/revue_portee/config/secrets.py` est le seul à les lire.

### Documentation

Le cadrage du projet (vision, exigences, architecture, feuille de route, décisions) se trouve dans [`docs/`](docs/).
