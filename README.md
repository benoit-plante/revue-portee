# revue-portee

Logiciel libre qui accompagne une équipe de recherche dans une revue de portée (*scoping review*) selon la méthode JBI et la norme PRISMA-ScR, avec l'IA comme second réviseur traçable. Licence : [AGPL-3.0-or-later](LICENSE).

## Démarrage

### Prérequis

- macOS, Linux ou Windows (natif ou WSL);
- Python 3.12 ou plus récent;
- [uv](https://docs.astral.sh/uv/) pour gérer l'environnement et les dépendances;
- Git; [GitHub CLI](https://cli.github.com/) (`gh`) pour ouvrir des demandes de fusion depuis le poste.

### Installation

```bash
uv sync
```

Cette commande crée l'environnement virtuel `.venv/` et installe les dépendances verrouillées dans `uv.lock`; relancez-la après chaque changement de `uv.lock`. Avec Claude Code, sur le poste comme dans une session infonuagique, le hook SessionStart de `.claude/settings.json` l'exécute automatiquement à l'ouverture d'une session (`uv sync --frozen`).

### Vérifier l'installation

```bash
uv run revue-portee --version
```

### Utiliser l'outil

```bash
uv run revue-portee nouveau ma-revue --titre "Titre de la revue" --reviseur "Prénom Nom"
uv run revue-portee serve ma-revue.revue            # interface web sur http://127.0.0.1:8000/
uv run revue-portee verifier-journal ma-revue.revue # vérifie la chaîne d'empreintes du journal
```

Un projet est un dossier `.revue` (fichier `projet.toml` et base `revue.sqlite`). L'interface web n'écoute que sur `127.0.0.1`. Elle offre les pages :

- « Cadrage » (question PCC) et « Critères » (brouillon, versions, différentiel, qualification des changements);
- « Recherche » (blocs de concepts, requêtes, test de sensibilité), « Collecte » (OpenAlex, PubMed, fichiers RIS, Crossref) et « Doublons »;
- « Pilote » (budget d'IA, échantillon trié à l'aveugle, table d'étalonnage, seuils) et « Tri » (tri au clavier, lots d'IA, réconciliation, analyse d'impact et réévaluation);
- « Protocole » (Markdown et DOCX, enregistrement OSF) et « Journal » (entrées, notes et vérification de la chaîne).

Gardez vos projets de revue hors du dossier du dépôt : le dépôt est public, et les dossiers `*.revue/` y sont ignorés par Git.

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
| `OPENALEX_API_KEY` | Clé d'API OpenAlex | Oui sur un poste (OpenAlex l'exige); non dans l'environnement infonuagique, où un mandataire réseau l'ajoute aux requêtes |

Définissez-les dans le profil de votre shell (par exemple `~/.zshrc` ou `~/.bashrc`), puis ouvrez un nouveau terminal :

```bash
export REVUE_PORTEE_ANTHROPIC_KEY="…"
export CONTACT_EMAIL="…"
export OPENALEX_API_KEY="…"
```

Pour vérifier qu'une variable existe sans l'afficher : `test -n "$OPENALEX_API_KEY" && echo "défini"`. Avec Claude Code, préférez `REVUE_PORTEE_ANTHROPIC_KEY` à `ANTHROPIC_API_KEY` : Claude Code pourrait se servir d'`ANTHROPIC_API_KEY` pour s'authentifier lui-même et facturer vos sessions sur la clé du projet. Ces valeurs ne doivent jamais être écrites dans un fichier du dépôt, affichées ni journalisées. Le module `src/revue_portee/config/secrets.py` est le seul à les lire.

### Documentation

Le cadrage du projet (vision, exigences, architecture, feuille de route, décisions) se trouve dans [`docs/`](docs/).
