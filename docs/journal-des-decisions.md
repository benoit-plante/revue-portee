# Journal des décisions

> Registre des décisions de conception et d'organisation du projet **revue-portee**. À ne pas confondre avec le *journal du projet de revue* que l'outil tient pour chaque revue de portée (voir [03-architecture.md](03-architecture.md)).
>
> **Règles**
> - Une entrée par décision, numérotée `D-NNN`, jamais renumérotée ni effacée.
> - Une décision qui change est **remplacée** par une nouvelle entrée; l'ancienne passe au statut « remplacée par D-NNN ».
> - Statuts : **décidée** (Benoit a tranché) · **proposée** (en attente de Benoit) · **remplacée**.
> - Les sessions de développement peuvent **proposer** une entrée dans leur demande de fusion; seul Benoit la fait passer à « décidée ».

## Gabarit

```markdown
### D-NNN — Titre court

- **Date** : AAAA-MM-JJ
- **Statut** : décidée | proposée | remplacée par D-NNN
- **Décision** : ce qui est décidé, en une ou deux phrases.
- **Contexte** : pourquoi la question se pose.
- **Options envisagées** :
  1. Option A — avantages / inconvénients
  2. Option B — avantages / inconvénients
- **Justification** : pourquoi cette option.
- **Conséquences** : ce que ça implique (code, documentation, coûts, risques).
- **Renvois** : exigences, documents, demandes de fusion.
```

---

## Décisions prises

### D-001 — Langue du code et de la documentation

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : le code, les noms de variables, les commentaires et les messages de commit sont en **anglais**; la documentation (`docs/`, `CLAUDE.md`, `README.md`) et l'interface sont en **français**.
- **Contexte** : public principal francophone; écosystème logiciel et contributeurs potentiels anglophones.
- **Options envisagées** :
  1. Tout en français — cohérent pour le public, mais freine la contribution et la réutilisation du code.
  2. Tout en anglais — maximise la portée, mais trahit le public cible et l'identité du projet.
  3. **Code en anglais, documentation et interface en français** — compromis usuel.
- **Justification** : le code reste lisible et réutilisable par la communauté internationale; l'expérience des équipes francophones est en français.
- **Conséquences** : chaînes d'interface externalisées (ENF-LAN-03) pour permettre une interface anglaise plus tard; exports de publication en français et en anglais (ENF-LAN-04).
- **Renvois** : ENF-LAN-01 à 06; [CLAUDE.md](../CLAUDE.md).

### D-002 — Python, géré avec uv

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : le projet est écrit en **Python** et ses dépendances sont gérées avec **uv** (`pyproject.toml` + `uv.lock`).
- **Contexte** : écosystème scientifique (scikit-learn, statsmodels), SDK des fournisseurs d'IA, familiarité des équipes de recherche; environnement infonuagique où Python, uv, pytest et ruff sont préinstallés.
- **Options envisagées** :
  1. **Python + uv** — rapide, reproductible (fichier de verrouillage), préinstallé.
  2. Python + pip/venv ou Poetry — plus lent ou plus lourd.
  3. TypeScript — bon pour le web, plus faible pour l'analyse et l'apprentissage automatique.
- **Justification** : cohérence avec l'environnement de développement et les besoins d'analyse.
- **Conséquences** : commandes `uv sync`, `uv run …`, `uv add …`; le hook SessionStart utilise uv (D-005).
- **Renvois** : [03-architecture.md §2](03-architecture.md#2-pile-technique).

### D-003 — Projet personnel, dépôt privé au départ

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : revue-portee est un **projet personnel de Benoit Plante**, réalisé **hors de son emploi, avec ses propres ressources** (matériel, comptes, abonnements, clés d'API). Le dépôt `benoit-plante/revue-portee` est **privé** au départ.
- **Contexte** : clarifier la propriété intellectuelle et éviter toute ambiguïté avec les employeurs et établissements de Benoit.
- **Options envisagées** :
  1. **Projet personnel, dépôt privé puis public** — contrôle de la propriété, ouverture au moment choisi.
  2. Projet institutionnel — accès à des ressources, mais propriété partagée et contraintes.
  3. Public dès le départ — transparence, mais exposition d'un travail non stabilisé.
- **Justification** : liberté de licence et de diffusion; ouverture quand la V1 sera utilisable.
- **Conséquences** : aucune ressource de l'employeur (comptes, clés, données, temps de travail) n'est utilisée; aucune donnée de recherche d'un projet institutionnel n'entre dans le dépôt. Le passage au public fera l'objet d'une nouvelle entrée.
- **Renvois** : D-004.

### D-004 — Licence : AGPL-3.0-or-later

- **Date** : 2026-10-07
- **Statut** : décidée (proposée et confirmée par Benoit le 2026-10-07)
- **Décision** : publier le code sous **GNU AGPL-3.0-or-later**.
- **Contexte** : une version hébergée (service web) est envisageable. Avec une licence permissive ou la GPL ordinaire, un tiers pourrait offrir l'outil en ligne, modifié, sans partager ses modifications.
- **Options envisagées** :
  1. **AGPL-3.0-or-later** — toute version modifiée offerte en réseau doit publier son code; protège le caractère libre de l'outil et de ses améliorations; même licence que prismAId. *Inconvénients* : certaines institutions et entreprises évitent l'AGPL; contributions et réutilisation commerciale freinées; impose une vigilance sur la compatibilité des dépendances.
  2. **MIT** — maximise l'adoption et la réutilisation, compatible avec tout; *inconvénients* : un service commercial fermé pourrait être bâti sur le code sans contrepartie; aucune garantie que les améliorations reviennent à la communauté.
  3. GPL-3.0 — protège la distribution du logiciel, mais **pas** l'usage en tant que service réseau.
  4. Apache-2.0 — comme MIT, avec une clause de brevets; mêmes inconvénients que MIT pour notre objectif.
- **Justification** : la revue de portée est une méthode d'intérêt public; la version hébergée possible est précisément le cas visé par l'AGPL; Benoit, seul titulaire des droits, conserve la possibilité d'offrir lui-même d'autres licences (double licence) s'il le souhaite.
- **Conséquences** :
  - fichier `LICENSE` (texte officiel AGPL-3.0, gabarit GitHub, ajouté le 2026-10-07) et mention SPDX `AGPL-3.0-or-later` dans `pyproject.toml`;
  - dépendances compatibles (MIT, BSD, Apache-2.0, LGPL, GPL-3, AGPL); **PyMuPDF (AGPL) devient utilisable** pour la conversion des PDF (V2);
  - si des contributions externes sont acceptées, prévoir un accord de contribution (CLA ou DCO) pour préserver la possibilité de double licence.
- **Renvois** : ENF-LIC-01, ENF-LIC-02; [03-architecture.md §2](03-architecture.md#2-pile-technique).

### D-005 — Environnement de développement infonuagique

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : le code est développé dans **Claude Code en mode infonuagique**, dans une machine virtuelle Ubuntu 24.04 neuve à chaque session (Python, uv, pytest, ruff préinstallés), avec un **accès réseau limité à une liste** (`api.openalex.org`, `eutils.ncbi.nlm.nih.gov`, `api.crossref.org`, `api.unpaywall.org` et les registres de paquets) et deux variables d'environnement : `ANTHROPIC_API_KEY` et `CONTACT_EMAIL`. Les dépendances sont installées par un **hook SessionStart** dans `.claude/settings.json`, créé au jalon 0.
- **Contexte** : chaque session repart de zéro et ne connaît le projet que par les fichiers du dépôt.
- **Options envisagées** :
  1. **Sessions infonuagiques éphémères** — reproductibles, isolées, aucune dépendance au poste de Benoit.
  2. Développement local — persistant, mais dépendant d'un poste et moins reproductible.
- **Justification** : l'environnement neuf à chaque session force une installation automatisée et une documentation autonome, ce qui sert aussi les futurs contributeurs.
- **Conséquences** :
  - `CLAUDE.md` décrit l'environnement et les règles; la documentation de `docs/` doit être complète et autonome;
  - toute **nouvelle source** (Érudit, theses.fr, HAL, dépôts OAI-PMH) exige d'**ajouter son domaine** dans les réglages de l'environnement avant de pouvoir être testée en intégration;
  - les secrets ne sont **jamais** affichés, journalisés ni écrits dans un fichier.
- **Renvois** : D-006, D-007; ENF-SEC-01 à 04; [CLAUDE.md](../CLAUDE.md).

### D-006 — Tests sans appel aux vraies API

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : les tests automatisés **n'appellent jamais** les vraies API; ils utilisent des **réponses enregistrées** (et un fournisseur d'IA factice). Seuls des **tests d'intégration marqués**, lancés volontairement, appellent les vrais services.
- **Contexte** : coûts des appels de modèles, limites de débit des sources, reproductibilité des tests, protection des secrets.
- **Options envisagées** :
  1. **Réponses enregistrées + tests d'intégration marqués** — tests rapides, gratuits, déterministes; vérification réelle à la demande.
  2. Appels réels dans tous les tests — coûteux, lents, non déterministes, risque de fuite de secrets.
  3. Simulations écrites à la main seulement — risque d'écart avec les vraies réponses.
- **Justification** : l'option 1 combine fidélité (réponses réelles enregistrées) et sécurité.
- **Conséquences** : `pytest` exclut le marqueur `integration` par défaut; les réponses enregistrées sont nettoyées de toute clé et de l'adresse de contact; un test vérifie l'absence de secrets dans `tests/`.
- **Renvois** : ENF-QUA-01, ENF-QUA-02, ENF-SEC-04; [03-architecture.md §11](03-architecture.md#11-tests).

### D-007 — Répartition du travail entre Cowork et les sessions de développement

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : `docs/` (et `CLAUDE.md`) sont rédigés dans **Cowork**; le code est écrit dans les **sessions infonuagiques de Claude Code**, sur des **branches**; Benoit **révise chaque demande de fusion** avant de fusionner.
- **Contexte** : séparer le cadrage (méthode, exigences, décisions) de la mise en œuvre, et garder Benoit maître des choix.
- **Options envisagées** :
  1. **Cadrage dans Cowork, code dans Claude Code, fusion après révision** — séparation claire des rôles.
  2. Tout dans Claude Code — plus fluide, mais la documentation risque de suivre le code au lieu de le guider.
- **Justification** : la documentation sert de contrat; la révision humaine de chaque fusion est cohérente avec le principe de supervision humaine que l'outil défend.
- **Conséquences** : les sessions de développement ne modifient pas `docs/` sauf demande explicite (elles peuvent proposer des changements dans la description de la demande de fusion, et créer `docs/resultats/` quand une tranche le prévoit); aucun commit direct sur `main`.
- **Renvois** : [04-feuille-de-route.md §0](04-feuille-de-route.md#0-principes-de-découpage); [CLAUDE.md](../CLAUDE.md).

### D-008 — Forme de la version 1 : application web locale

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : la V1 est une **application web locale** : un serveur Python lancé sur le poste, une interface en français dans le navigateur, et une ligne de commande pour les traitements en lot.
- **Options envisagées** :
  1. **Web locale** — accessible aux équipes, aucune infrastructure, ouvre la voie à une version hébergée.
  2. Ligne de commande d'abord — plus rapide à livrer, peu accessible aux assistants de recherche.
  3. Web hébergée dès la V1 — authentification, base serveur, sécurité : trop lourd au départ.
- **Justification** : meilleur équilibre entre accessibilité et simplicité.
- **Conséquences** : serveur sur `127.0.0.1`; projet = dossier sur le poste; architecture séparant domaine, stockage et web pour une version hébergée future.
- **Renvois** : [00-vision.md §6.2](00-vision.md#62-forme-du-logiciel); [03-architecture.md](03-architecture.md).

### D-009 — Un réviseur humain + l'IA en version 1

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : en V1, la sélection se fait avec **un réviseur humain et l'IA comme second réviseur**; la gestion de plusieurs réviseurs humains (accord interjuges, arbitrage) arrive en V2. Le modèle de données prévoit plusieurs réviseurs dès la V1.
- **Options envisagées** :
  1. **1 humain + IA en V1** — périmètre maîtrisé; correspond au cas d'usage principal (petites équipes).
  2. Plusieurs humains dès la V1 — plus complet, mais retarde la V1.
- **Justification** : livrer tôt la valeur distinctive (IA traçable, étalonnage, itération) sans la complexité de la coordination multi-réviseurs.
- **Conséquences** : EF-SEL-08 (double révision humain + IA) en V1; EF-SEL-13 en V2; tables `reviewer` et `decision` génériques dès la V1.
- **Renvois** : EF-PRJ-05, EF-SEL-08, EF-SEL-13.

### D-010 — Étude de validation visant une publication

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : l'étude de validation est conçue pour être **préenregistrée sur OSF** et **publiée** (article méthodologique), pas seulement comme banc d'essai interne.
- **Options envisagées** :
  1. **Publication** — crédibilité, conformité à l'énoncé de position conjoint (publication des données de validation par les développeurs), contribution scientifique.
  2. Banc d'essai interne — plus léger, mais insuffisant pour que les utilisateurs justifient l'usage de l'outil.
- **Justification** : un outil d'IA pour la synthèse des connaissances doit pouvoir être cité avec des données de validation publiques.
- **Conséquences** : séparation stricte développement / test, gel avant évaluation, évaluateurs indépendants pour l'analyse des erreurs, déclaration du conflit d'intérêts du développeur.
- **Renvois** : [05-plan-de-validation.md](05-plan-de-validation.md); ENF-NOR-02.

---

## Décisions issues du cadrage (confirmées le 2026-10-07)

Ces décisions ont été proposées dans les documents de cadrage, puis confirmées par Benoit le 7 octobre 2026.

### D-011 — Pile technique de la V1

- **Date** : 2026-10-07
- **Statut** : décidée (2026-10-07)
- **Décision** : FastAPI + gabarits Jinja2 + HTMX (sans chaîne de compilation JavaScript), Pydantic v2, SQLite via SQLAlchemy Core + Alembic, httpx, Typer, rispy, RapidFuzz, SDK `anthropic`, pytest + pytest-recording.
- **Options envisagées** :
  1. **Rendu serveur + HTMX** — une seule langue (Python), développement simple dans la VM.
  2. Interface React/Vue séparée — plus riche, mais chaîne Node à maintenir et double compétence.
  3. Streamlit ou NiceGUI — très rapide à prototyper, mais moins de contrôle sur le tri au clavier, l'accessibilité et une future version hébergée.
- **Justification** : simplicité, testabilité, aucune dépendance à npm.
- **Renvois** : [03-architecture.md §2](03-architecture.md#2-pile-technique).

### D-012 — Format du projet de revue : dossier avec SQLite

- **Date** : 2026-10-07
- **Statut** : décidée (2026-10-07)
- **Décision** : un projet = un dossier `.revue` contenant `projet.toml`, `revue.sqlite` (source de vérité), les réponses brutes compressées et les imports.
- **Options envisagées** :
  1. **Dossier + SQLite** — transactions, performance, un seul fichier de données; non lisible directement dans git.
  2. Fichiers texte (JSON Lines, YAML) versionnés dans git — lisibles et comparables, mais lents et fragiles au-delà de quelques milliers de références, sans transactions.
  3. Base serveur (PostgreSQL) — prématuré pour une application locale.
- **Justification** : robustesse et performance; la traçabilité est assurée par le journal interne à chaîne d'empreintes et par l'archive exportable en formats ouverts.
- **Renvois** : [03-architecture.md §4](03-architecture.md#4-format-du-dossier-de-projet).

### D-013 — Clé d'API OpenAlex

- **Date** : 2026-10-07
- **Statut** : décidée et réalisée (2026-10-07) : la clé est créée et `OPENALEX_API_KEY` est définie dans les réglages de l'environnement infonuagique
- **Contexte** : depuis le 24 février 2026, OpenAlex exige une clé d'API (gratuite, avec une allocation quotidienne gratuite puis facturation à l'usage); le paramètre `mailto` ne suffit plus. L'environnement infonuagique n'a que `ANTHROPIC_API_KEY` et `CONTACT_EMAIL`.
- **Décision** : utiliser une clé OpenAlex personnelle, ajoutée comme variable d'environnement `OPENALEX_API_KEY` dans les réglages de l'environnement; même traitement que les autres secrets. Facultatif : `NCBI_API_KEY` pour passer de 3 à 10 requêtes/s sur PubMed.
- **Renvois** : [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026); ENF-SEC-01; ENF-COU-06.

### D-014 — Garde-fous de l'exclusion assistée par l'IA

- **Date** : 2026-10-07
- **Statut** : décidée (2026-10-07)
- **Décision** : aucune exclusion par l'IA seule en V1. À partir de la V2, mode d'exclusion assistée seulement si : pilote terminé; sensibilité estimée au seuil ≥ 0,95 (cible réglable) avec borne inférieure d'intervalle consignée; vérification humaine d'un échantillon aléatoire des exclusions de l'IA (par défaut 10 %, minimum 50), avec suspension automatique au-delà d'une tolérance.
- **Justification** : principe non négociable « aucune exclusion entièrement automatique sans étalonnage préalable et vérification humaine d'un échantillon »; données montrant la variabilité de la sensibilité selon la rédaction des critères.
- **Renvois** : EF-SEL-11; [01-etat-de-l-art.md §4](01-etat-de-l-art.md#4-ce-que-disent-les-données-sur-les-grands-modèles-de-langage).

### D-015 — Cible de coût de l'IA au tri des titres et résumés

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : avec la configuration par défaut du réviseur IA, trier **5 000 titres et résumés** doit coûter **25 $ US ou moins** en frais de modèle (tarifs du fournisseur à la date de la mesure, traitement par lots et mise en cache des invites compris). Cette cible équivaut à **5 $ US par 1 000 références**.
- **Contexte** : ENF-COU-07 demandait un montant de référence pour guider le choix du modèle par défaut et des stratégies d'invite.
- **Options envisagées** :
  1. **25 $ US** — cible serrée; oriente vers un modèle rapide, le traitement par lots et la mise en cache.
  2. 50 $ US — marge pour un modèle plus capable ou des exécutions répétées.
  3. 100 $ US — permet l'auto-cohérence (plusieurs exécutions par référence).
- **Justification** : coût accessible pour une petite équipe universitaire qui paie avec ses propres fonds; la cible reste compatible avec un modèle performant grâce au traitement par lots et à la mise en cache du préfixe de l'invite (critères).
- **Conséquences** :
  - la cible est une **contrainte de conception de la configuration par défaut**, pas un plafond imposé à l'équipe : chaque projet garde son propre plafond budgétaire réglable (ENF-COU-02);
  - le banc d'essai de la tranche 1.6 mesure le coût par 1 000 références; si la cible n'est pas atteinte avec une sensibilité ≥ 0,95, le compromis est présenté à Benoit plutôt que tranché par la session de développement;
  - les options coûteuses (auto-cohérence, un appel par critère) restent offertes, avec leur coût estimé affiché.
- **Renvois** : ENF-COU-01 à 07; [04-feuille-de-route.md](04-feuille-de-route.md) (tranche 1.6).

## Décisions proposées, en attente de Benoit

*(Aucune pour l'instant. Les sessions de développement ajoutent leurs propositions dans la description de leurs demandes de fusion; Benoit les reporte ici.)*
