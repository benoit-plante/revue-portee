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
- **Statut** : remplacée par D-085 (développement local, l'environnement infonuagique restant possible); complétée par D-020 (nom de la variable de la clé Anthropic) et D-021 (clé OpenAlex facultative)
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
- **Statut** : décidée; complétée par D-085 (les sessions de Claude Code peuvent être locales)
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
- **Statut** : décidée et réalisée (2026-10-07) : la clé est créée et `OPENALEX_API_KEY` est définie dans les réglages de l'environnement infonuagique; complétée par D-021 (2026-10-07) : dans l'environnement infonuagique, la clé est ajoutée aux requêtes par le mandataire réseau et `OPENALEX_API_KEY` est facultative
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

## Décisions issues du jalon 0 (2026-10-07)

Ces décisions ont été proposées ou tranchées pendant le jalon 0 (demande de fusion benoit-plante/revue-portee#1), puis approuvées par Benoit le 7 octobre 2026.

### D-016 — Blocage du réseau dans les tests ordinaires

- **Date** : 2026-10-07
- **Statut** : décidée (proposée au jalon 0, approuvée par Benoit le 2026-10-07)
- **Décision** : en plus des cassettes en lecture seule (`--record-mode=none`), tout test non marqué `integration` s'exécute avec les connexions réseau bloquées (`block_network` de pytest-recording, appliqué automatiquement par `tests/conftest.py`).
- **Contexte** : les cassettes en lecture seule empêchent seulement les appels qui passent par VCR. Un appel direct par socket ou par une bibliothèque non interceptée pourrait atteindre le réseau sans qu'aucun test ne le signale (ENF-QUA-01).
- **Options envisagées** :
  1. **Cassettes en lecture seule + blocage du réseau** — toute tentative de connexion échoue immédiatement (« Network is disabled »).
  2. Cassettes en lecture seule seulement — conforme à [03-architecture.md §11](03-architecture.md#11-tests), mais sans garantie pour les appels hors VCR.
- **Justification** : la règle « aucun appel réseau dans les tests » devient vérifiée par le code, pas seulement par convention. Un test le confirme.
- **Conséquences** :
  - les tests d'intégration ne sont pas bloqués; pour enregistrer une cassette : `uv run pytest -m integration --record-mode=once`, puis nettoyage et vérification anti-secrets;
  - documentation mise à jour dans la même demande de fusion : [03-architecture.md §11](03-architecture.md#11-tests) et CLAUDE.md (« Tests »).
- **Renvois** : ENF-QUA-01, ENF-QUA-02; D-006; demande de fusion benoit-plante/revue-portee#1.

### D-017 — Valeurs fictives reconnues dans `tests/`

- **Date** : 2026-10-07
- **Statut** : décidée (proposée au jalon 0, approuvée par Benoit le 2026-10-07)
- **Décision** : le test anti-secrets considère une valeur comme **fictive** si elle contient un marqueur explicite (`DUMMY`, `FAKE`, `REDACTED`, `placeholder`, `fictif`, `fictive`, `example`, `xxxx`, `***`, ou un gabarit `{…}`, `$…`, `<…>`). Une adresse courriel est fictive si son domaine est réservé (RFC 2606 et 6761 : `example.org`, `example.com`, `example.net`, `.test`, `.invalid`, `.example`, `localhost`). Valeurs de remplacement des cassettes : `DUMMY` pour les clés et les en-têtes, `contact@example.org` pour les adresses.
- **Contexte** : ENF-SEC-04 demande un test qui détecte les secrets dans `tests/`. Sans règle explicite pour reconnaître une valeur fictive, ce test signalerait aussi les valeurs de remplacement des cassettes et les exemples des tests.
- **Options envisagées** :
  1. **Liste de marqueurs et domaines réservés** — prévisible et documentée; les vraies clés (aléatoires) ne contiennent pas ces marqueurs.
  2. Liste d'exceptions par fichier — plus fine, mais fragile et facile à étendre par erreur.
- **Justification** : une règle simple, que chaque contributeur peut appliquer sans consulter de liste.
- **Conséquences** :
  - dans les fichiers de test, les chaînes qui ressemblent à des secrets sont construites à l'exécution par concaténation **explicite** (`"api_" + "key"`). ruff fusionne les concaténations implicites (`"api_" "key"`), qui ne protègent donc pas;
  - le rapport du test donne le fichier, la ligne et le type de fuite, jamais la valeur;
  - documentation mise à jour dans la même demande de fusion : CLAUDE.md (« Cassettes de test », « Tests »).
- **Renvois** : ENF-SEC-02, ENF-SEC-04; D-006; demande de fusion benoit-plante/revue-portee#1.

### D-018 — Typographie française dans les chaînes du code

- **Date** : 2026-10-07
- **Statut** : décidée (proposée au jalon 0, approuvée par Benoit le 2026-10-07)
- **Décision** : les chaînes d'interface écrites dans le code utilisent de vraies espaces insécables (U+00A0) avant `:` `;` `?` `!` et à l'intérieur des guillemets « ». ruff les autorise (`allowed-confusables`).
- **Contexte** : CLAUDE.md exige ces espaces dans l'interface. ruff signalait les espaces insécables comme caractères ambigus (règle RUF001).
- **Options envisagées** :
  1. **Espaces insécables autorisées par ruff** — typographie correcte, sans désactiver la règle pour les autres caractères ambigus.
  2. Désactiver RUF001 — plus simple, mais perd la détection des caractères trompeurs.
  3. Espaces ordinaires — typographie incorrecte dans l'interface.
- **Justification** : respecte la convention d'interface sans affaiblir la vérification.
- **Conséquences** : temporaire en partie. Une fois les chaînes externalisées avec Babel (ENF-LAN-03, prévu à la tranche 1.1), la typographie vivra surtout dans les catalogues de traduction.
- **Renvois** : ENF-LAN-03; CLAUDE.md (« Conventions »); demande de fusion benoit-plante/revue-portee#1.

### D-019 — Exclusion de `docs/` et des fichiers Markdown du formatage par ruff

- **Date** : 2026-10-07
- **Statut** : décidée (proposée au jalon 0, approuvée par Benoit le 2026-10-07)
- **Décision** : ruff ignore `docs/` et les fichiers `*.md` (`extend-exclude` dans `pyproject.toml`).
- **Contexte** : ruff 0.16 reformate les blocs de code Python dans les fichiers Markdown. Pendant le jalon 0, `ruff format .` a modifié `docs/03-architecture.md`, que les sessions de développement ne doivent pas toucher (D-007). Le changement a été annulé avant le commit.
- **Options envisagées** :
  1. **Exclure `docs/` et `*.md`** — protège la documentation rédigée dans Cowork.
  2. Exclure `docs/` seulement — `README.md` et `CLAUDE.md` resteraient exposés au reformatage.
- **Justification** : la documentation est rédigée dans Cowork et ne doit changer que là.
- **Conséquences** : les extraits de code de la documentation ne sont pas vérifiés par ruff; ils le seront, au besoin, à la relecture dans Cowork.
- **Renvois** : D-007; demande de fusion benoit-plante/revue-portee#1.

### D-020 — Nom de la variable d'environnement de la clé Anthropic

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : la clé d'API Anthropic est lue dans `REVUE_PORTEE_ANTHROPIC_KEY`, puis, à défaut, dans `ANTHROPIC_API_KEY`. Si les deux variables sont définies, les deux valeurs sont masquées dans les journaux et recherchées par le test anti-secrets.
- **Contexte** : dans l'environnement infonuagique, la clé du projet est fournie sous le nom `REVUE_PORTEE_ANTHROPIC_KEY`, et `ANTHROPIC_API_KEY` est absente. Dans les sessions Claude Code, `ANTHROPIC_API_KEY` peut être réservée à l'authentification de la session elle-même. La lire pour l'outil risquerait de mélanger les deux usages, notamment pour la facturation.
- **Options envisagées** :
  1. **`REVUE_PORTEE_ANTHROPIC_KEY` en priorité, `ANTHROPIC_API_KEY` en repli** — aucun conflit avec la session; reste compatible avec un poste où seule la variable standard est définie.
  2. Renommer la variable de l'environnement en `ANTHROPIC_API_KEY` — conforme à CLAUDE.md, mais risque de conflit avec l'authentification de Claude Code.
  3. `REVUE_PORTEE_ANTHROPIC_KEY` seulement — explicite, mais oblige les utilisateurs du SDK à dupliquer leur variable habituelle.
- **Justification** : le nom propre au projet évite toute ambiguïté sur la clé utilisée et facturée, et le repli garde l'outil simple à configurer sur un poste.
- **Conséquences** :
  - `config/secrets.py` : `SecretName.ANTHROPIC_API_KEY.env_vars` vaut `("REVUE_PORTEE_ANTHROPIC_KEY", "ANTHROPIC_API_KEY")`; le message d'erreur nomme les deux variables;
  - documentation mise à jour dans la même demande de fusion : CLAUDE.md (« Variables disponibles », « Secrets — règles absolues », exemple `test -n`), statut de D-005, ENF-SEC-01 et [03-architecture.md §10](03-architecture.md#10-sécurité-et-secrets).
- **Renvois** : ENF-SEC-01; D-005; demande de fusion benoit-plante/revue-portee#1.

### D-021 — Clé d'API OpenAlex facultative

- **Date** : 2026-10-07
- **Statut** : décidée (complète D-013)
- **Décision** : `OPENALEX_API_KEY` est **facultative**. Quand elle est définie, elle est traitée comme les autres secrets (`SecretStr`, masquage, test anti-secrets). Quand elle est absente, aucune erreur n'est levée au démarrage, et le connecteur OpenAlex envoie ses requêtes sans clé.
- **Contexte** : dans l'environnement infonuagique, la clé n'est pas une variable d'environnement : le mandataire réseau l'ajoute lui-même aux requêtes vers `api.openalex.org` (règle « Autoriser + injecter OpenAlex »). Exiger la variable ferait échouer le code dans le seul environnement de développement, alors que les appels réussissent.
- **Options envisagées** :
  1. **Clé facultative** — fonctionne avec ou sans mandataire; le connecteur ne l'ajoute que si elle existe. *Inconvénient* : sur un poste sans mandataire et sans clé, l'erreur viendra d'OpenAlex (refus HTTP) plutôt que d'un message clair au démarrage.
  2. Clé obligatoire, à ajouter aussi comme variable dans l'environnement infonuagique — même traitement que les autres secrets, conforme à la lettre de D-013, mais la clé serait alors présente deux fois.
  3. Clé obligatoire hors environnement infonuagique seulement (détection par `CLAUDE_CODE_REMOTE`) — message clair partout, mais comportement différent selon l'environnement, donc plus difficile à tester.
- **Justification** : l'option 1 est la plus simple et ne duplique pas la clé. Son inconvénient est corrigé par le connecteur (voir les conséquences).
- **Conséquences** :
  - `config/secrets.py` : `SecretName.OPENALEX_API_KEY.required` vaut `False`; le test d'intégration la signale comme « ignorée » quand elle est absente;
  - **à faire à la tranche 1.4** : le connecteur OpenAlex traduit une réponse 401 ou 403 en un message français clair qui nomme `OPENALEX_API_KEY` et rappelle comment la définir;
  - documentation mise à jour dans la même demande de fusion : statut de D-013, CLAUDE.md (« Variables disponibles ») et critère OpenAlex de la tranche 1.4 dans [04-feuille-de-route.md](04-feuille-de-route.md#tranche-14--collecte-et-import).
- **Renvois** : D-013; ENF-SEC-01; ENF-COU-06; demande de fusion benoit-plante/revue-portee#1.

### D-022 — Vérification des types avec mypy en mode strict

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : le code (`src/` et `tests/`) est vérifié par **mypy en mode `strict`**, avec le greffon Pydantic. `uv run mypy` doit passer avant toute demande de fusion, comme `ruff` et `pytest`, et la CI l'exécute.
- **Contexte** : CLAUDE.md exige un « typage complet ». ruff (règles `ANN`) vérifie la présence des annotations, mais pas leur cohérence. La couche IA, générique (`TaskSpec[InputT, OutputT]`), et les futurs modèles du domaine profitent d'une vérification réelle.
- **Options envisagées** :
  1. **mypy, mode strict** — vérificateur de référence, greffon Pydantic officiel, licence MIT.
  2. pyright — rapide et précis, mais distribué par npm (une chaîne Node, que D-011 cherche à éviter) ou par un paquet Python qui télécharge Node.
  3. ruff seulement — aucune dépendance de plus, mais aucune vérification de cohérence des types.
- **Justification** : mypy s'installe avec uv, sans Node, et le greffon Pydantic comprend les modèles du projet.
- **Conséquences** :
  - dépendance de développement mypy (MIT; dépendances : mypy-extensions et librt, MIT, et pathspec, MPL-2.0, compatible AGPL);
  - configuration dans `pyproject.toml` (`[tool.mypy]`, `mypy_path`, `explicit_package_bases`);
  - documentation mise à jour dans la même demande de fusion : CLAUDE.md (« Commandes », « Avant de proposer une demande de fusion »), ENF-QUA-03, [03-architecture.md §2](03-architecture.md#2-pile-technique) (ligne « Qualité ») et la définition de « terminé » de [04-feuille-de-route.md §0](04-feuille-de-route.md#0-principes-de-découpage).
- **Renvois** : ENF-QUA-03; ENF-LIC-01; D-011; demande de fusion benoit-plante/revue-portee#1.

### D-023 — Couverture de tests : mesure systématique et seuil de 90 % par paquet

- **Date** : 2026-10-07
- **Statut** : décidée
- **Décision** : pytest-cov mesure la couverture de `revue_portee`, branches comprises, à chaque exécution de `pytest`. `uv run pytest` **échoue** si l'un des paquets `domain`, `dedup` ou `reporting` est couvert à moins de **90 %**, chacun séparément. Aucun seuil global n'est imposé. Le seuil n'est vérifié que sur la suite complète.
- **Contexte** : ENF-QUA-04 fixe un objectif de 90 % pour les modules de domaine, de dédoublonnage et de diagramme, qui portent les calculs déclarés. pytest-cov n'offre qu'un seuil global, qui ne distingue pas ces modules des connecteurs ou de l'interface web.
- **Options envisagées** :
  1. **Seuil par paquet, vérifié par `pytest` lui-même** (greffon local `tests/_plugins/coverage_gate.py`) — même règle en local et en CI, une seule source de configuration (`pyproject.toml`).
  2. Seuil par paquet dans la CI seulement (`coverage report --include=… --fail-under=90`) — simple, mais l'échec n'apparaît qu'après la poussée.
  3. Seuil global (`--cov-fail-under`) — natif, mais pénalise les connecteurs et l'interface, ou laisse un paquet sous-couvert compensé par les autres.
- **Justification** : l'option 1 attrape l'écart avant la poussée et vise exactement les modules dont les nombres sont publiés.
- **Conséquences** :
  - dépendance de développement pytest-cov (MIT; coverage, Apache-2.0);
  - réglages `coverage_gate_packages` et `coverage_gate_fail_under` dans `[tool.pytest.ini_options]`;
  - le seuil est ignoré, avec un avertissement, pour une exécution partielle (chemins explicites, `-k`, un autre `-m`, `--lf`, `--deselect`), avec `--collect-only`, avec `--no-cov` et quand des tests échouent déjà. Un paquet introuvable compte pour 0 %;
  - `reporting/` contiendra aussi le protocole, la section méthode et la liste PRISMA-ScR : le seuil s'y appliquera aussi;
  - documentation mise à jour dans la même demande de fusion : ENF-QUA-04 (« doivent », trois paquets nommés), CLAUDE.md (« Commandes », « Tests »), [03-architecture.md §2](03-architecture.md#2-pile-technique) (ligne « Tests ») et §11.
- **Renvois** : ENF-QUA-04; ENF-QUA-05; demande de fusion benoit-plante/revue-portee#1.

### D-024 — Masquage des secrets dès la création des entrées de journal

- **Date** : 2026-10-07
- **Statut** : décidée (option A de la revue de code du jalon 0)
- **Décision** : `install_secret_redaction()` installe une **fabrique d'entrées de journal** (`logging.setLogRecordFactory`) qui masque chaque entrée dès sa création. Le filtre attaché aux gestionnaires reste une seconde protection.
- **Contexte** : [03-architecture.md §10](03-architecture.md#10-sécurité-et-secrets) prévoit « un filtre `logging` ». Un filtre ne protège que les gestionnaires auxquels on l'attache. Ceux configurés plus tard, comme ceux d'uvicorn pour `revue-portee serve` ou un fichier de journal, recevraient les secrets en clair.
- **Options envisagées** :
  1. **Fabrique d'entrées de journal + filtre en seconde protection** — couvre tous les gestionnaires, présents et futurs.
  2. Filtre seulement, attaché aussi aux gestionnaires d'uvicorn à la tranche qui ajoute `serve` — moins de code maintenant, mais chaque nouveau gestionnaire doit penser au filtre.
- **Justification** : la confidentialité des clés (ENF-SEC-01 à 03) ne doit pas dépendre de la discipline de chaque tranche.
- **Conséquences** :
  - les entrées gardent leur forme (`msg` et `args` séparés) tant qu'aucun secret n'apparaît, parce que certains formateurs, comme celui des accès d'uvicorn, lisent `record.args`;
  - le gabarit du message n'est masqué que pour les valeurs chargées : les motifs (par exemple `api_key=`) s'appliquent aux arguments, puis au message complet, pour ne pas avaler un `%s`;
  - le masquage ne lève jamais d'exception : un appel de journalisation mal formé est signalé par `logging` au moment de l'écriture, comme sans masquage;
  - coûts assumés : chaque message est mis en forme une fois de plus à sa création, et les traces d'exception sont rendues en texte dès ce moment;
  - limite : un gestionnaire qui rend lui-même les exceptions à partir de `record.exc_info`, sans utiliser `exc_text` (par exemple `RichHandler`), contourne le masquage des traces. À éviter, ou à envelopper;
  - documentation mise à jour dans la même demande de fusion : [03-architecture.md §10](03-architecture.md#10-sécurité-et-secrets).
- **Renvois** : ENF-SEC-01 à 03; demande de fusion benoit-plante/revue-portee#1.

## Décisions issues de la tranche 1.1 (2026-10-07)

### D-026 — Codes de critères stables, jamais réutilisés

- **Date** : 2026-10-07
- **Statut** : décidée (option A choisie par Benoit le 2026-10-07, à la revue de code de la tranche 1.1)
- **Décision** : chaque critère reçoit un code formé d'un préfixe selon l'élément PCC (`P` population, `C` concept, `CTX` contexte, `X` dimension transversale : type de source, langue, période, devis) et du numéro suivant (`P1`, `C2`, `CTX1`, `X3`). Un code n'est **jamais** réutilisé dans le projet, même s'il n'a existé que dans un brouillon abandonné ou a été retiré d'un brouillon. Le code et l'élément PCC d'un critère ne changent jamais : changer d'élément revient à retirer le critère, puis à en ajouter un autre.
- **Contexte** : EF-CAD-03 exige des codes stables d'une version à l'autre. Le journal consigne aussi les modifications des brouillons; si un code libéré était réattribué, le journal contiendrait deux critères différents sous le même code.
- **Options envisagées** :
  1. **Option A — aucun code n'est jamais réutilisé** (registre des codes attribués) — un code désigne toujours le même critère, dans les versions comme dans le journal.
  2. Option B — libérer les codes des brouillons jamais activés — numérotation sans trous, mais deux sens possibles pour un code dans le journal.
- **Justification** : la traçabilité prime sur une numérotation continue.
- **Conséquences** :
  - table `criterion_code` (code, élément PCC, première version, date), en ajout seulement, protégée par des déclencheurs SQLite (D-028);
  - la numérotation peut avoir des trous (`P1`, `P2`, `P4`);
  - documentation : [03-architecture.md §5.2](03-architecture.md#52-critères-versionnés).
- **Renvois** : EF-CAD-03, EF-VER-01; ENF-TRA-02; demande de fusion benoit-plante/revue-portee#2.

## Décisions proposées, en attente de Benoit

*Les sessions de développement ajoutent leurs propositions dans la description de leurs demandes de fusion; Benoit les reporte ici, puis les fait passer à « décidée ».*

Propositions de la tranche 1.1 (2026-10-07), mises en œuvre dans la demande de fusion benoit-plante/revue-portee#2 :

### D-025 — Identifiants ULID sans dépendance externe

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : les ULID (§5) sont générés par `domain/ids.py` avec la seule bibliothèque standard (48 bits de millisecondes, 80 bits aléatoires, base 32 de Crockford).
- **Contexte** : le module `domain/` ne doit importer rien d'externe hors Pydantic (CLAUDE.md).
- **Options envisagées** :
  1. **Implémentation interne** — environ trente lignes, testées sur des valeurs calculées à la main.
  2. Bibliothèque `python-ulid` — maintenue, mais une dépendance de plus dans le domaine.
- **Justification** : le format est simple et stable; la règle du domaine sans dépendance est préservée.
- **Conséquences** : aucune dépendance; les identifiants se trient par date de création.
- **Renvois** : [03-architecture.md §5](03-architecture.md#5-modèle-de-données), §12; demande de fusion benoit-plante/revue-portee#2.

### D-027 — Flux brouillon → version des critères

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - toute modification des critères passe par un **brouillon**, créé automatiquement au premier vrai changement (une modification qui ne change rien n'en crée pas); un seul brouillon à la fois;
  - l'**activation** du brouillon crée la version en vigueur; elle exige au moins un critère et, à partir de la version 2, une justification (la version 1 peut s'en passer); la version précédente passe à « remplacée »;
  - un brouillon peut être **abandonné**; ses codes restent réservés (D-026);
  - chaque modification du brouillon est journalisée.
- **Contexte** : EF-VER-01 exige une nouvelle version immuable, avec justification, à chaque modification. Créer une version par modification élémentaire multiplierait les versions pour un seul changement réfléchi.
- **Options envisagées** :
  1. **Brouillon, puis activation** — l'équipe regroupe ses changements; le différentiel avec la version en vigueur s'affiche avant l'activation.
  2. Une version par modification élémentaire — plus simple, mais beaucoup de versions intermédiaires sans justification propre.
- **Justification** : une version correspond à une décision de l'équipe, justifiée une fois.
- **Conséquences** : statuts `draft`, `active` et `superseded` (§5.2); au plus un brouillon et une version en vigueur (index partiels uniques).
- **Renvois** : EF-CAD-05, EF-VER-01, EF-VER-02; demande de fusion benoit-plante/revue-portee#2.

### D-028 — Immuabilité garantie par la base de données

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : des déclencheurs SQLite refusent toute modification ou suppression du journal, des versions du cadrage, du registre des codes de critères, du projet, et des versions de critères sorties du brouillon (y compris leurs critères). Seul le passage « en vigueur → remplacée » est permis.
- **Contexte** : ENF-TRA-02 (rien n'est modifié ni supprimé). Une règle appliquée seulement par le code peut être contournée par un autre chemin d'écriture.
- **Options envisagées** :
  1. **Déclencheurs dans la migration** — la règle tient pour toute écriture, même une requête SQL directe.
  2. Vérifications dans les dépôts seulement — plus simple, mais contournable.
- **Justification** : défense en profondeur; les tests vérifient les deux niveaux.
- **Conséquences** : les dépôts traduisent le refus de la base en `ImmutableVersionError`. Une modification du fichier qui supprime d'abord les déclencheurs reste détectée par la chaîne d'empreintes (D-029).
- **Renvois** : ENF-TRA-02; demande de fusion benoit-plante/revue-portee#2.

### D-029 — Format de la chaîne d'empreintes du journal

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : l'empreinte d'une entrée est le SHA-256 de son JSON canonique (clés triées, sans espaces, UTF-8, dates UTC ISO 8601 avec microsecondes), qui inclut l'empreinte de l'entrée précédente. Valeur initiale : 64 zéros. L'ordre de la chaîne est la colonne `position` (0, 1, 2…).
- **Contexte** : §5.1 prévoit une chaîne vérifiable sans en fixer le format.
- **Options envisagées** :
  1. **SHA-256 sur JSON canonique** — reproductible avec n'importe quel langage, sans dépendance.
  2. Signature numérique — prouverait l'auteur, mais exige une gestion de clés hors de portée de la V1.
- **Justification** : détecte toute altération, suppression ou interversion; vérifiable par un tiers à partir de l'archive.
- **Conséquences** : `revue-portee verifier-journal` et la page « Journal » vérifient la chaîne; tout changement de format exigera une nouvelle décision.
- **Renvois** : EF-PRJ-02; ENF-TRA-02; ENF-REP-06; demande de fusion benoit-plante/revue-portee#2.

### D-030 — Cadrage PCC versionné

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : chaque modification du cadrage (question principale, population, concept, contexte, questions secondaires) crée une version immuable, dans la table `framing_version`. Un enregistrement identique au cadrage en vigueur n'en crée pas.
- **Contexte** : le §5 ne prévoyait pas de table pour le cadrage; or le cadrage oriente les critères, et ses changements font partie de l'histoire méthodologique.
- **Options envisagées** :
  1. **Versions immuables** — même principe que les critères, sans brouillon.
  2. Champs modifiables dans la table `project` — plus simple, mais l'historique ne serait que dans le journal.
- **Justification** : cohérence avec ENF-TRA-02.
- **Conséquences** : table `framing_version` (§5.2); entrée de journal `framing.updated`.
- **Renvois** : EF-CAD-01; ENF-TRA-02; demande de fusion benoit-plante/revue-portee#2.

### D-031 — Internationalisation avec Babel

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - les identifiants de message sont en anglais dans le code et les gabarits; le catalogue `src/revue_portee/i18n/locale/fr/LC_MESSAGES/messages.po` fournit le français, langue par défaut;
  - le catalogue est lu directement depuis le `.po` et compilé en mémoire : aucun `.mo` n'est versionné;
  - les résumés du journal (`summary_fr`) passent toujours par le catalogue français, quelle que soit la langue de l'interface;
  - un test exige que chaque message extrait soit traduit, sans entrée obsolète, avec une espace insécable devant `:` `;` `?` `!`.
- **Contexte** : ENF-LAN-03 (chaînes externalisées) et D-001 (code en anglais, interface en français).
- **Options envisagées** :
  1. **Identifiants anglais, catalogue français** — usage standard de gettext; une interface anglaise ne demandera qu'un catalogue.
  2. Identifiants français — plus lisibles pour l'équipe, mais contraires à D-001 dans le code.
- **Justification** : respecte D-001 et prépare l'anglais sans le livrer.
- **Conséquences** : le module `i18n/` sert aussi à la ligne de commande et aux messages d'erreur; `babel.cfg` décrit l'extraction (CLAUDE.md, « Conventions »).
- **Renvois** : ENF-LAN-01, ENF-LAN-03; D-001; demande de fusion benoit-plante/revue-portee#2.

### D-032 — Sécurité de l'interface web locale

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : chaque formulaire porte un jeton propre au processus du serveur; un en-tête `Host` autre que `127.0.0.1` ou `localhost` est refusé, ainsi qu'un en-tête `Origin` étranger sur toute écriture.
- **Contexte** : même sur `127.0.0.1` (ENF-SEC-06), n'importe quelle page web ouverte dans le navigateur peut envoyer des requêtes au serveur local (requêtes intersites) ou l'atteindre par un nom de domaine qui pointe vers 127.0.0.1 (DNS rebinding).
- **Options envisagées** :
  1. **Jeton par processus + contrôle de `Host` et `Origin`** — aucune session ni compte à gérer.
  2. Aucune protection, l'écoute locale étant jugée suffisante — exposé aux deux attaques.
- **Justification** : protection simple et suffisante pour une application locale à un seul utilisateur.
- **Conséquences** : après un redémarrage du serveur, un formulaire déjà ouvert est refusé (403) et doit être rechargé; la future version hébergée (§12) remplacera ce mécanisme par des sessions.
- **Renvois** : ENF-SEC-06; [03-architecture.md §9](03-architecture.md#9-interface-web); demande de fusion benoit-plante/revue-portee#2.

### D-033 — HTMX versionné dans le dépôt

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : HTMX 2.0.11 est copié dans `src/revue_portee/web/static/vendor/`, avec sa source (registre npm), sa licence (0BSD) et l'empreinte `sha512` de l'archive. La navigation utilise `hx-boost`, et les réponses 4xx et 5xx sont affichées (configuration `htmx-config` dans `base.html`).
- **Contexte** : D-011 retient HTMX sans chaîne de compilation JavaScript. Par défaut, HTMX 2 n'affiche pas les réponses 4xx, alors que l'application renvoie ses erreurs de formulaire comme des pages complètes.
- **Options envisagées** :
  1. **Fichier versionné** — fonctionne hors ligne, contenu vérifié.
  2. Chargement depuis un CDN — dépend du réseau et d'un tiers.
- **Justification** : application locale autosuffisante; empreinte vérifiable.
- **Conséquences** : toute mise à jour d'HTMX remplace le fichier et met à jour `vendor/README.md`.
- **Renvois** : D-011; ENF-LIC-01; [03-architecture.md §9](03-architecture.md#9-interface-web); demande de fusion benoit-plante/revue-portee#2.

### D-034 — Version de l'outil consignée

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : la version de l'outil s'écrit `"<version> (<commit court>)"`. Le commit n'est consigné que si le dépôt git qui contient le code est bien celui de revue-portee (sa racine contient `src/revue_portee`); sinon : `"<version> (commit inconnu)"`.
- **Contexte** : ENF-REP-05. Installé depuis un paquet dans le `.venv` d'un autre dépôt git, l'outil consignerait sinon le commit de ce dépôt-là.
- **Options envisagées** :
  1. **Commit seulement pour le dépôt de revue-portee** — jamais d'information fausse.
  2. Inscrire le commit dans le paquet à sa construction — exact pour les paquets publiés, mais exige une étape de construction propre au projet.
- **Justification** : une valeur absente vaut mieux qu'une valeur fausse dans un registre de traçabilité.
- **Conséquences** : à revoir à la première publication d'un paquet (option 2 alors préférable).
- **Renvois** : ENF-REP-05; demande de fusion benoit-plante/revue-portee#2.

### D-035 — Vérification du journal en lecture seule

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : `revue-portee verifier-journal` ouvre le projet sans consigner d'entrée `project.opened`.
- **Contexte** : ENF-REP-05 demande de consigner la version de l'outil à chaque ouverture du projet; une vérification ne doit pourtant jamais modifier ce qu'elle vérifie.
- **Options envisagées** :
  1. **Exception pour la vérification** — la vérification ne change rien.
  2. Consigner aussi cette ouverture — conforme à la lettre d'ENF-REP-05, mais la vérification modifierait le journal.
- **Justification** : une vérification doit pouvoir être répétée sans effet.
- **Conséquences** : ENF-REP-05 pourrait préciser « à chaque ouverture en écriture ».
- **Renvois** : ENF-REP-05; demande de fusion benoit-plante/revue-portee#2.

### D-036 — Transactions d'écriture SQLite

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : toute écriture passe par `ProjectFolder.write()`, qui ouvre la transaction avec `BEGIN IMMEDIATE` (verrou pris dès le début; attente du verrou jusqu'à 30 s). Les lectures restent en mode `DEFERRED`.
- **Contexte** : les requêtes web s'exécutent en parallèle. Un cas d'usage qui lit avant d'écrire (par exemple la dernière entrée du journal) pouvait entrer en collision avec un autre : 17 notes sur 60 échouaient dans une reproduction de la revue de code.
- **Options envisagées** :
  1. **`BEGIN IMMEDIATE` pour les écritures** — sérialise les écritures sans bloquer les lectures.
  2. Un verrou dans le processus web — ne protège pas la ligne de commande ni un second processus.
- **Justification** : le verrou de la base vaut pour tous les processus.
- **Conséquences** : règle de développement dans CLAUDE.md (« Conventions »); un test fait écrire six fils d'exécution en même temps.
- **Renvois** : EF-PRJ-02; ENF-TRA-02; [03-architecture.md §5](03-architecture.md#5-modèle-de-données); demande de fusion benoit-plante/revue-portee#2.

Propositions de la tranche 1.2 (2026-10-07), mises en œuvre dans la demande de fusion benoit-plante/revue-portee#4 :

### D-037 — Fournisseur Claude : sorties structurées et replis côté serveur

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - `AnthropicProvider` envoie le schéma JSON de la tâche en sortie structurée (`output_config.format`, type `json_schema`); les mots-clés que l'API refuse (`minLength`, `maximum`, `pattern`…) sont retirés du schéma envoyé, sans toucher aux noms de champs, et Pydantic revalide la sortie;
  - un appel par entrée; le bloc d'instructions est marqué pour la mise en cache des invites (`cache_control`);
  - une réponse refusée, tronquée ou non conforme au schéma est un **appel en échec**, consigné comme tel;
  - les **replis côté serveur** (`fallbacks: "default"`) sont activés par défaut : si le modèle refuse, l'API relance la même demande sur un autre modèle; le modèle qui a réellement répondu (`model_returned`) est consigné et facturé à son propre tarif. Quand l'API n'a renvoyé aucun modèle (erreur), `model_returned` reste vide.
- **Contexte** : ENF-TRA-01 exige la version exacte du modèle; les sorties libres seraient fragiles à interpréter.
- **Options envisagées** :
  1. **Sorties structurées + validation Pydantic, replis activés** — format garanti; moins d'échecs pour refus; le modèle réel reste traçable.
  2. Sans replis — un refus reste un refus; traçabilité plus simple (un seul modèle par configuration).
- **Justification** : un refus de sécurité sur une question de recherche ordinaire bloquerait l'équipe sans raison; le modèle effectivement servi est consigné à chaque appel.
- **Conséquences** : les replis se désactivent en retirant `fallbacks` de `[ia]` dans `projet.toml`; l'étude de validation (05) devra déclarer les modèles effectivement servis.
- **Renvois** : ENF-TRA-01, ENF-TRA-03; [03-architecture.md §6](03-architecture.md#6-couche-dabstraction-des-modèles); demande de fusion benoit-plante/revue-portee#4.

### D-038 — Modèle par défaut des tâches de cadrage

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : les tâches `suggest_pcc` et `qualify_criterion_change` utilisent par défaut `claude-opus-5-5`, effort `medium`, `max_tokens` 16 000 (`resources/ai_defaults.yaml`). Les tâches `suggest_terms` et `screen_reference` restent « prévues », sans modèle.
- **Contexte** : aucun nom de modèle dans le code (CLAUDE.md); il faut néanmoins une configuration de départ.
- **Options envisagées** :
  1. **Modèle le plus capable pour les tâches de cadrage** — peu d'appels par projet; coût négligeable (quelques cents).
  2. Modèle plus rapide et moins cher — économie sans intérêt à ce volume.
- **Justification** : le cadrage et la qualification des changements engagent la méthode; le volume est faible.
- **Conséquences** : le modèle du tri (tranche 1.6) sera choisi au banc d'essai, selon la cible de coût de D-015.
- **Renvois** : D-015; ENF-COU-07; demande de fusion benoit-plante/revue-portee#4.

### D-039 — Configuration de l'IA dans le projet

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : la configuration de l'IA (supervision, et pour chaque tâche : statut, fournisseur, modèle, paramètres, sortie attendue) est la section `[ia]` de `projet.toml`, copiée des valeurs par défaut à la création; un projet antérieur reçoit les valeurs par défaut. Chaque configuration effectivement utilisée est consignée en ajout seulement (`ai_config`, entrée `ai.config_recorded`).
- **Contexte** : §4 prévoyait les réviseurs IA dans `projet.toml`; §6.1 définit le réviseur IA comme un couple tâche + fournisseur + modèle + gabarit + paramètres.
- **Options envisagées** :
  1. **`projet.toml` + consignation à l'usage** — lisible et modifiable sans outil; la base garde la trace de ce qui a servi.
  2. Table de configuration modifiée par l'interface — plus de code, sans gain pour la V1.
- **Justification** : la configuration demandée reste dans le fichier du projet; la configuration réellement utilisée est dans la base et au journal.
- **Conséquences** : pas encore de page pour modifier `[ia]`; la section « Usage de l'intelligence artificielle » du protocole en est tirée.
- **Renvois** : EF-CAD-07; [03-architecture.md §4](03-architecture.md#4-format-du-dossier-de-projet), §6; demande de fusion benoit-plante/revue-portee#4.

### D-040 — Estimation du coût avant l'appel

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - jetons d'entrée estimés à environ 4 caractères par jeton, arrondis au supérieur (invite et schéma);
  - les instructions sont comptées au tarif d'écriture en cache, le reste au tarif d'entrée, sans remise de lecture du cache : c'est le cas le plus coûteux pour le modèle demandé;
  - jetons de sortie : valeur `expected_output_tokens` de la configuration;
  - tarifs datés dans `resources/model_prices.yaml` (2026-10-06); **un modèle sans tarif connu bloque l'appel**;
  - l'interface affiche le modèle, le nombre d'appels, les jetons, le montant et la date des tarifs, puis demande confirmation. Un repli vers un autre modèle est facturé à ses propres tarifs.
- **Contexte** : ENF-COU-01 exige une estimation et une confirmation avant tout lot d'appels; compter les jetons exactement demanderait un appel réseau.
- **Options envisagées** :
  1. **Estimation locale prudente** — aucun appel, aucune clé requise pour estimer.
  2. API de comptage des jetons — exacte, mais un appel réseau et une clé avant même de décider.
- **Justification** : l'estimation sert à décider; une surestimation est préférable.
- **Conséquences** : le coût réel de chaque appel est consigné (`ai_call.cost_estimate`) à partir des jetons renvoyés par l'API; un test vérifie les calculs sur des cas faits à la main.
- **Renvois** : ENF-COU-01, ENF-COU-03, ENF-COU-05; demande de fusion benoit-plante/revue-portee#4.

### D-041 — Consignation des appels aux modèles

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - l'appel au modèle se fait sans tenir le verrou d'écriture SQLite (il peut durer une minute);
  - l'appel est ensuite consigné dans **sa propre transaction** : configuration si nouvelle, appel, réponse brute compressée (`brut/ia/AAAA/MM/<id>.json.gz`), entrée `ai.call_failed` en cas d'échec;
  - ce que le cas d'usage tire de la réponse (suggestions, propositions) est enregistré dans une seconde transaction; si cette étape échoue, l'appel reste consigné et le journal reçoit une entrée `ai.result_unusable`;
  - une réponse brute écrite pour un appel qui n'a pas pu être consigné est supprimée.
- **Contexte** : un appel payé ne doit jamais disparaître de la traçabilité (ENF-TRA-01), et l'écriture concurrente doit rester possible (D-036).
- **Options envisagées** :
  1. **Deux transactions** — l'appel est toujours consigné; l'exploitation peut échouer séparément.
  2. Une seule transaction — plus simple, mais une erreur d'exploitation effaçait la trace d'un appel payé (constat de la revue de code).
- **Justification** : traçabilité des coûts et des appels avant tout.
- **Conséquences** : la table `ai_call` est en ajout seulement; un appel « réussi » dont la réponse n'a pas pu être exploitée se reconnaît à l'entrée `ai.result_unusable`.
- **Renvois** : ENF-TRA-01, ENF-TRA-03; D-036; demande de fusion benoit-plante/revue-portee#4.

### D-042 — Décision sur une suggestion de l'IA

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - une seule décision par suggestion (acceptée, modifiée ou refusée), imposée par la base;
  - la décision est appliquée immédiatement au cadrage : une reformulation remplace la question principale; une suggestion de population, de concept ou de contexte remplace l'élément; une question secondaire est ajoutée si elle n'y est pas déjà;
  - une suggestion « modifiée » dont le texte est inchangé est consignée comme « acceptée »; une décision qui ne change rien au cadrage n'est liée à aucune version.
- **Contexte** : EF-CAD-02 exige un choix explicite, consigné, pour chaque suggestion.
- **Options envisagées** :
  1. **Application immédiate** — chaque décision produit sa version du cadrage; la provenance est complète.
  2. Panier de suggestions appliqué en bloc — moins de versions, mais une décision moins lisible au journal.
- **Justification** : la trace « telle suggestion de tel appel a produit telle version » est directe.
- **Conséquences** : tables `ai_suggestion` et `suggestion_review` (en ajout seulement).
- **Renvois** : EF-CAD-01, EF-CAD-02; demande de fusion benoit-plante/revue-portee#4.

### D-043 — Qualification des changements à l'activation

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - à partir de la version 2, l'activation exige un type confirmé par l'humain pour **chaque critère modifié** : élargissement, restriction ou clarification; les ajouts et les retraits sont qualifiés automatiquement;
  - l'IA peut proposer un type (tâche `qualify_criterion_change`), avec sa confiance et sa justification; une proposition devient caduque si le critère est modifié de nouveau;
  - `proposed_by = ai` seulement si l'humain confirme le type proposé par l'IA; sinon `human`, avec un lien vers la proposition écartée.
- **Contexte** : EF-VER-03 (l'IA peut proposer, l'humain confirme); l'analyse d'impact (EF-VER-04) reposera sur ces types.
- **Options envisagées** :
  1. **Qualification obligatoire à l'activation** — aucune version sans qualification complète.
  2. Qualification facultative, ajoutable plus tard — risque de versions non qualifiées, inutilisables pour l'analyse d'impact.
- **Justification** : la qualification se fait au moment où l'équipe comprend le mieux son changement.
- **Conséquences** : tables `qualification_proposal` et `criterion_change`; entrées `criteria.change_proposed` et `criteria.change_qualified`.
- **Renvois** : EF-VER-03, EF-VER-04; demande de fusion benoit-plante/revue-portee#4.

### D-044 — Écart au protocole

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : l'enregistrement du protocole (DOI normalisé, date, version des critères en vigueur) est consigné en ajout seulement; le plus récent fait foi. Toute version des critères **activée** après un enregistrement est marquée `after_protocol_registration` (« écart au protocole ») et le journal le signale.
- **Contexte** : EF-CAD-08.
- **Options envisagées** :
  1. **Marquage à l'activation** — la règle est simple et vérifiable.
  2. Marquage à la création du brouillon — un brouillon commencé avant l'enregistrement échapperait au marquage.
- **Justification** : c'est l'entrée en vigueur qui modifie la méthode.
- **Conséquences** : la section « Écarts au protocole » du protocole liste ces versions et leurs changements qualifiés; EF-VER-07 (section méthode) s'appuiera sur ce marquage.
- **Renvois** : EF-CAD-08, EF-VER-07; demande de fusion benoit-plante/revue-portee#4.

### D-045 — Production du protocole

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - le protocole est construit une fois comme un document neutre (titres, paragraphes, listes, tableaux), puis rendu en Markdown et en DOCX (python-docx);
  - les sections suivent les éléments de Peters et al. (2022); celles que l'outil ne peut pas remplir (contexte, stratégie de recherche, extraction…) viennent d'un texte libre versionné (`protocol_text_version`) et affichent « À compléter » quand il manque;
  - français et anglais : le texte fixe passe par le catalogue de traduction, l'anglais étant la langue des identifiants de message (pas de catalogue anglais); le texte de l'équipe est reproduit tel quel;
  - annexes : critères complets, état des éléments de Peters et al., correspondance avec les 65 éléments du formulaire OSF *Generalized Systematic Review Registration*.
- **Contexte** : EF-CAD-06, EF-CAD-07, ENF-LAN-04.
- **Options envisagées** :
  1. **Document neutre + deux rendus** — un seul constructeur testé, deux formats identiques.
  2. Gabarits séparés par format — duplication du contenu.
- **Justification** : la couverture des éléments se vérifie une seule fois, par un test.
- **Conséquences** : les exports vont dans `exports/` (`protocole-fr.md`, `protocole-en.docx`…), régénérables; commande `revue-portee protocole`.
- **Renvois** : EF-CAD-06, EF-CAD-07; ENF-LAN-04; demande de fusion benoit-plante/revue-portee#4.

### D-046 — Liste des éléments de Peters et al. (2022) à vérifier

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : la liste de contrôle `resources/protocol/peters_2022.yaml` (23 éléments) est reconstituée à partir du gabarit de protocole JBI décrit par l'article; elle porte `verified: false`, ce que le protocole indique en annexe. Benoit la compare à la liste de contrôle de l'article, puis la passe à `verified: true` (ou la corrige).
- **Contexte** : l'article n'est pas en libre accès (absent de PubMed Central) et était inaccessible depuis l'environnement de développement. Le formulaire OSF, lui, a été lu à la source (PMC10514995) et porte `verified: true`.
- **Options envisagées** :
  1. **Liste reconstituée, signalée comme non vérifiée** — la tranche avance; la vérification reste visible.
  2. Attendre l'accès à l'article — bloque la tranche.
- **Justification** : la structure (une section par élément, test de couverture) ne dépend pas du libellé exact; corriger la liste est une modification de données.
- **Conséquences** : tant que la liste n'est pas vérifiée, le critère « 100 % des éléments de Peters et al. » est satisfait sous réserve.
- **Renvois** : EF-CAD-06; [01-etat-de-l-art.md §5](01-etat-de-l-art.md#5-normes-et-recommandations); demande de fusion benoit-plante/revue-portee#4.

Propositions de la tranche 1.3 (2026-10-07), mises en œuvre dans la demande de fusion benoit-plante/revue-portee#6 :

### D-047 — Réponses enregistrées propres au projet pour httpx2

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : les tests des connecteurs rejouent des réponses enregistrées par un mécanisme du projet (`tests/recording.py`). Chaque cassette est un fichier JSON de paires requête et réponse, dans `tests/cassettes/<module>/<test>.json`.
  - Correspondance : méthode et URL, avec les paramètres triés et filtrés.
  - Conservé de la réponse : statut, type de contenu et corps.
  - Marqueur `cassette`, fixture `http_cassette`.
  - Mode d'enregistrement : celui de l'option `--record-mode` de pytest-recording. `none` (valeur par défaut) rejoue ; `once` enregistre seulement les cassettes absentes.
- **Contexte** : les connecteurs utilisent `httpx2`, que vcrpy (et donc pytest-recording) n'intercepte pas.
- **Options envisagées** :
  1. **Transport httpx2 de rejeu, avec enregistrement par un vrai client** : environ cent lignes de code, sans dépendance.
  2. Passer les connecteurs à `httpx` pour garder vcrpy : deux clients HTTP dans le projet.
  3. Doublures écrites à la main : elles ne vérifient pas les vraies réponses des API.
- **Justification** : l'option 1 garde de vraies réponses, des cassettes lisibles et sans dépendance supplémentaire.
- **Conséquences** :
  - À l'enregistrement, le client respecte le mandataire et les certificats de l'environnement.
  - `api_key`, `email` et `mailto` sont remplacés par `DUMMY` et `contact@example.org`.
  - La cassette n'est pas écrite si la vraie adresse de contact y figure.
  - En mode d'enregistrement, le réseau n'est pas bloqué pour les tests marqués `cassette` ; il reste bloqué pour tous les autres (D-016).
  - Enregistrer reste un appel volontaire aux vrais services, sur autorisation de Benoit.
- **Renvois** : D-016, D-017 ; ENF-SEC-04 ; demande de fusion benoit-plante/revue-portee#6.

### D-048 — Stratégie de recherche stockée en un seul document JSON

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : chaque version de la stratégie (blocs, termes, limites) est stockée en JSON dans `search_strategy_version.strategy_json`. Il n'y a pas de table `concept_block`.
- **Contexte** : l'architecture prévoyait une table `concept_block` par version. Or la stratégie se versionne d'un bloc : une modification d'un terme crée une nouvelle version de l'ensemble.
- **Options envisagées** :
  1. **Document JSON validé par Pydantic** (`SearchStrategy`) : une ligne par version ; relecture identique à l'écriture.
  2. Table `concept_block` : des jointures sans requête SQL qui en ait besoin.
- **Justification** : aucun traitement n'interroge les blocs en SQL. Les codes de bloc (`B1`, `B2`…) restent stables d'une version à l'autre, et ne sont jamais réattribués : un nouveau bloc ne reprend pas le code d'un bloc retiré dans une version antérieure.
- **Conséquences** : **écart à [03-architecture.md §5.3](03-architecture.md#53-recherche-et-collecte)**, que la section met à jour. Les requêtes produites (`query`) restent dans une table, une par base et par version.
- **Renvois** : EF-REC-01, EF-REC-06 ; demande de fusion benoit-plante/revue-portee#6.

### D-049 — Syntaxe d'une ligne de terme

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : un bloc contient un terme par ligne.
  - Mots et expressions :
    - un mot : `parent` ; troncature : `parent*` ;
    - une expression exacte : `"parenting program"`. Une ligne de plusieurs mots est toujours cherchée comme une expression.
  - Préfixes de champ : `ti:`, `ab:`, `tw:`, `all:`, `pt:` (titre et résumé par défaut).
  - Descripteurs :
    - MeSH : `mesh:` (avec les descripteurs plus spécifiques) ou `mesh-noexp:` ;
    - thésaurus de l'APA : `apa:`, ou `apa+:` avec les descripteurs plus spécifiques.
  - Texte recopié tel quel dans la requête d'une seule base : `pubmed:`, `openalex:`, `psycinfo:`.
  - Interdits dans une ligne : AND, OR, NOT, parenthèses et crochets. Une ligne invalide est signalée avec son bloc et son texte.
- **Contexte** : EF-REC-01 demande des blocs éditables (termes français et anglais, troncature, expressions) qui se traduisent automatiquement vers plusieurs bases.
- **Options envisagées** :
  1. **Une ligne par terme, avec préfixes** : lisible, et facile à traduire vers chaque base.
  2. Saisie de la requête PubMed, ensuite traduite vers les autres bases : il faut analyser toute la syntaxe de PubMed, et le texte saisi est propre à une base.
- **Justification** : la ligne de terme est la plus petite unité que toutes les bases savent exprimer. Les préfixes de texte brut couvrent ce qui est propre à une base.
- **Conséquences** :
  - Les suggestions de l'IA (`suggest_terms`) utilisent la même syntaxe ; une proposition illisible, déjà présente ou pour un bloc inconnu est écartée, et leur nombre est consigné.
  - Le texte d'aide de la page « Recherche » décrit la syntaxe.
- **Renvois** : EF-REC-01, EF-REC-02 ; demande de fusion benoit-plante/revue-portee#6.

### D-050 — Traduction vers OpenAlex

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : la requête OpenAlex est la valeur du paramètre `filter` de l'API `works`. Elle se compose :
  - d'un filtre `title_and_abstract.search.exact` qui contient l'expression booléenne ;
  - des filtres `from_publication_date`, `to_publication_date` et `language` ;
  - des termes bruts `openalex:` des blocs d'inclusion, combinés par AND.

  Ce qu'OpenAlex ne sait pas exprimer est écarté avec un avertissement :
  - descripteurs (OpenAlex n'a pas de vocabulaire contrôlé) ;
  - types de publication ;
  - virgules (interdites dans un filtre) ;
  - champs autres que titre et résumé (la recherche est élargie au titre et au résumé) ;
  - termes bruts d'un bloc d'exclusion (un filtre ne peut pas être retiré par NOT).
- **Contexte** : le filtre `title_and_abstract.search` racinise les mots et refuse les jokers ; `title_and_abstract.search.exact` les accepte, ainsi que les opérateurs et les expressions entre guillemets (vérifié contre l'API en octobre 2026).
- **Options envisagées** :
  1. **`title_and_abstract.search.exact`** : la troncature et les expressions se comportent comme dans PubMed.
  2. `title_and_abstract.search` : la racinisation élargit la recherche sans contrôle, et `*` est refusé.
  3. Paramètre `search` : il cherche aussi dans le texte intégral, ce qui ne correspond pas aux champs des autres bases.
- **Justification** : l'option 1 est la plus proche, en sens, de la requête PubMed.
- **Conséquences** :
  - Les avertissements sont affichés avec la requête et conservés avec elle.
  - Un bloc qui n'a que des termes bruts OpenAlex a sa propre requête (ses filtres), pour le test de sensibilité.
  - Chaque comptage consomme une petite part de l'allocation quotidienne d'OpenAlex.
- **Renvois** : EF-REC-03, EF-REC-04 ; [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026) ; demande de fusion benoit-plante/revue-portee#6.

### D-051 — Test de sensibilité et bloc responsable

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** : chaque article clé (DOI, PMID ou titre) est d'abord résolu en identifiant de la base. Un article sans correspondance unique est déclaré non indexé et exclu du rappel. On teste ensuite quels articles la requête complète retrouve :
  - PubMed : `(<requête>) AND (<pmid>[uid] OR …)`, par lots de 200 ;
  - OpenAlex : filtre `openalex:W…|W…`, par lots de 100 (limite des filtres OR d'OpenAlex).

  Un article manqué est attribué :
  - à chaque bloc d'inclusion qui, seul, ne le retrouve pas ;
  - à chaque bloc d'exclusion qui, seul, le retrouve ;
  - aux limites (années, langues), si elles seules ne le retrouvent pas ;
  - si aucun de ces cas ne s'applique, à « la combinaison des blocs ».

  Rappel = articles retrouvés / articles indexés, arrondi à trois décimales.
- **Contexte** : EF-REC-05 demande de nommer les articles manqués et le bloc responsable.
- **Options envisagées** :
  1. **Tester chaque bloc seul, seulement contre les articles manqués** : peu de requêtes et une explication directe.
  2. Retirer les blocs un à un de la requête complète : plus de requêtes, et une explication moins lisible quand plusieurs blocs sont en cause.
- **Justification** : un article manqué par une conjonction de blocs l'est forcément par au moins un bloc seul ; l'option 1 le nomme.
- **Conséquences** :
  - Le calcul est une fonction pure (`domain/sensitivity.py`), testée sur un cas calculé à la main.
  - Les réponses brutes sont conservées dans `brut/sources/`.
  - PsycINFO n'a pas d'API publique : le test n'y est pas disponible.
- **Renvois** : EF-REC-05 ; [05-plan-de-validation.md](05-plan-de-validation.md) ; demande de fusion benoit-plante/revue-portee#6.

### D-052 — Années ouvertes et requêtes sans bloc d'inclusion

- **Date** : 2026-10-07
- **Statut** : proposée
- **Décision** :
  - Dans PubMed, une année de fin absente devient `"3000"[dp]` et une année de début absente `"1800"[dp]`.
  - Dans EBSCOhost, les années ne s'écrivent pas dans la requête : un avertissement demande de les fixer avec le limiteur de l'interface.
  - Une stratégie sans bloc d'inclusion ni limites ne produit pas de requête : les blocs d'exclusion n'ont alors rien à retirer, et un avertissement est affiché.
- **Contexte** : une limite d'années peut n'avoir qu'une borne, et un NOT isolé n'est pas une requête valide.
- **Options envisagées** :
  1. **Bornes conventionnelles** : `3000` est la convention de PubMed pour « jusqu'à aujourd'hui » ; le texte reste le même d'un jour à l'autre (ENF-REP-01).
  2. Année courante comme borne : le texte de la requête changerait selon la date de production.
- **Justification** : une requête produite doit être identique pour une même version de stratégie.
- **Conséquences** : le comptage et le test de sensibilité refusent une base sans requête, avec un message qui demande un bloc d'inclusion.
- **Renvois** : EF-REC-03, ENF-REP-01 ; demande de fusion benoit-plante/revue-portee#6.

Propositions de la tranche 1.4 (2026-10-08), mises en œuvre dans les demandes de fusion benoit-plante/revue-portee#8 et benoit-plante/revue-portee#9 :

### D-053 — Collecte reprenable page par page

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Une collecte (`collection_run`) récupère tous les enregistrements d'une requête, page par page. Chaque page est conservée brute dans `brut/sources/<run_id>/page-NNNN.json.gz`, puis enregistrée dans une seule transaction avec ses références, leurs provenances et son entrée de journal (`collection_page`). La page est l'**unité de reprise** : une collecte interrompue reprend après sa dernière page enregistrée, avec le curseur de cette page.
  - Un identifiant déjà donné dans la même collecte n'est jamais enregistré de nouveau (contrainte d'unicité sur la collecte et l'identifiant d'origine).
  - Une seule collecte ouverte à la fois par base : il faut terminer ou reprendre la précédente.
  - À la fin (`collection_end`), le nombre d'enregistrements distincts collectés est comparé au nombre annoncé par l'API; un écart est expliqué et consigné.
  - Les erreurs qu'une nouvelle tentative ne peut pas corriger terminent la collecte comme `failed` : clé OpenAlex refusée (401, 403), plus de 10 000 notices PubMed (D-054), requête refusée par l'API (erreur 4xx autre que 408 et 429). Les autres erreurs (réseau, 5xx après les nouvelles tentatives) laissent la collecte ouverte et reprenable.
- **Contexte** : EF-COL-01 et ENF-PER-04 exigent une reprise sans doublon ni perte; une collecte peut compter des milliers de notices et être interrompue (serveur arrêté, réseau coupé).
- **Options envisagées** :
  1. **Tables propres à la collecte** (`collection_run`, `collection_page`, `collection_end`), en ajout seulement : l'état d'une collecte se lit dans ses lignes.
  2. Réutiliser `search_run` (prévu pour les comptes et les tests de sensibilité) avec un type `collect` : une ligne unique ne peut pas décrire une progression sans être modifiée.
- **Justification** : avec l'option 1, rien n'est modifié; une page est enregistrée entièrement ou pas du tout, ce qui suffit à garantir la reprise.
- **Conséquences** :
  - **Écart à 03-architecture.md** : la provenance pointe vers `collection_run_id` (et `query_id`) au lieu de `search_run_id`; `search_run` reste réservé aux comptes et aux tests de sensibilité.
  - Une collecte terminée en échec ne se reprend pas : on en lance une nouvelle.
  - Collecte disponible pour OpenAlex et PubMed; les bases sans API passent par l'import RIS (D-056).
- **Renvois** : EF-COL-01, EF-COL-05, ENF-PER-04; demandes de fusion benoit-plante/revue-portee#8 et benoit-plante/revue-portee#9.

### D-054 — PubMed : serveur d'historique et limite de 10 000 notices

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - La collecte PubMed lance `esearch` avec `usehistory=y`, puis lit les notices par `efetch` (XML, pages de 200) à partir de la session du serveur d'historique (`WebEnv`, `query_key`). Le curseur conservé avec chaque page contient la session et la position suivante; si la session a expiré, la recherche est relancée et la collecte continue à la même position.
  - Au-delà de 10 000 notices annoncées, la collecte est refusée avec un message clair en français qui demande de découper la recherche (par exemple par années de publication). Le découpage n'est pas automatique.
  - Une réponse d'erreur d'`efetch`, ou une page vide avant la fin annoncée, est une erreur (`SourceInvalidAnswerError`) et non la fin de la collecte.
- **Contexte** : depuis 2022, les E-utilities ne donnent pas plus de 10 000 notices d'une même recherche, même avec le serveur d'historique.
- **Options envisagées** :
  1. **Refus avec message** : la personne choisit le découpage, qui devient visible dans les requêtes versionnées.
  2. Découpage automatique par années : la requête exécutée ne serait plus celle de la stratégie versionnée, et le découpage devrait lui-même être documenté.
- **Justification** : pour une revue de portée, la requête rapportée doit être exactement celle qui a été exécutée (PRISMA-S); un découpage est une décision de méthode.
- **Conséquences** : un découpage par années se fait par des limites dans la stratégie (une version par tranche d'années, ou une stratégie dédiée); à reprendre si cela devient fréquent.
- **Renvois** : EF-COL-01; [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026); demande de fusion benoit-plante/revue-portee#8.

### D-055 — Références immuables et enrichissement par Crossref

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Une référence est enregistrée une fois, telle que reçue, et n'est jamais modifiée (table en ajout seulement). Chaque fois qu'une source la donne, une provenance s'ajoute (EF-COL-05).
  - L'enrichissement par Crossref (EF-COL-02) s'enregistre dans une table distincte, `enrichment`, qui ne contient que les champs manquants de la référence (titre, résumé, auteurs, année, revue, volume, numéro, pages). La référence « fusionnée » est calculée (`merged`) : un champ présent dans la référence n'est jamais remplacé.
  - Les références sont traitées par lots de 100, au plus trois requêtes simultanées (pool « poli » de Crossref); chaque lot est une transaction, avec ses réponses brutes dans `brut/sources/`.
  - Un DOI inconnu de Crossref est enregistré aussi (enrichissement vide), pour ne pas le redemander. Une référence déjà vérifiée n'est plus candidate : l'enrichissement reprend là où il s'était arrêté.
  - Un champ invalide d'une notice collectée (par exemple une année hors de 1000–2100) est retiré seul, et la liste des champs retirés est consignée (`invalid_fields_left_out`) au lieu de rejeter la notice.
- **Contexte** : le principe d'ajout seulement (ENF-TRA-02) interdit de compléter une référence en place.
- **Options envisagées** :
  1. **Table d'enrichissement distincte** : l'origine de chaque champ reste connue (source ou Crossref).
  2. Nouvelle version de la référence : multiplie les lignes et complique le dédoublonnage.
- **Justification** : l'option 1 garde la notice reçue intacte et rend l'enrichissement réversible.
- **Conséquences** : le dédoublonnage (tranche 1.5) et le tri utiliseront la référence fusionnée.
- **Renvois** : EF-COL-02, EF-COL-05, ENF-TRA-02; demandes de fusion benoit-plante/revue-portee#8 et benoit-plante/revue-portee#9.

### D-056 — Lecteur RIS du projet et règles de tolérance

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Les fichiers RIS sont lus par un lecteur propre au projet (`sources/ris.py`, fonctions pures), et non par rispy.
  - Variantes tolérées : marque d'ordre des octets, fins de ligne Windows, une ou deux espaces avant le trait d'union, lignes vides dans un enregistrement, valeurs sur plusieurs lignes (rattachées à la valeur précédente), étiquettes répétées (deux résumés sont gardés), DOI donné comme adresse ou dans un autre champ.
  - Encodage : UTF-8, puis Latin-1 à défaut; un fichier qui contient des octets nuls est refusé.
  - Un enregistrement sans aucun champ utilisable n'est pas importé, mais listé avec l'import; un enregistrement que le fichier termine sans `ER` est importé et signalé; les lignes hors enregistrement sont signalées (`import_file.issues_json`).
  - La base déclarée par la personne l'emporte sur les étiquettes `DB` et `DP` du fichier; à défaut de déclaration, la base est déduite du fichier. Un export Ovid, qui n'a pas d'étiquette `DP`, est reconnu à ses liens vers `ovid.com`.
  - Un fichier n'est importé qu'une fois (empreinte SHA-256, vérifiée aussi dans la transaction d'écriture); sa copie exacte est conservée dans `imports/<sha256>.ris`.
- **Contexte** : les exports réels testés (PsycINFO EBSCOhost et Ovid, CINAHL, ERIC, SocINDEX, PubMed, Érudit) présentent ces variantes; le critère d'acceptation demande de lister, avec leur position, les enregistrements vides ou mal formés, ce qu'un analyseur générique ne rapporte pas.
- **Options envisagées** :
  1. **Lecteur propre** : chaque écart est signalé avec sa ligne, ce que demande le critère « enregistrements vides ou mal formés listés ».
  2. rispy enveloppé (prévu dans 03-architecture.md §2) : il faudrait reprendre le texte avant et après lui.
- **Justification** : environ 200 lignes de fonctions pures, testées sur de vrais exports, sans dépendance; les 4 209 notices des sept exports complets sont importées.
- **Conséquences** :
  - **Écart à 03-architecture.md §2** : rispy n'est pas une dépendance.
  - Les bases déclarables sont listées dans `collect/imports.py` (`DECLARED_DATABASES`); Scopus et Web of Science y figurent mais n'ont pas encore été testés sur un vrai export.
- **Renvois** : EF-COL-03; [01-etat-de-l-art.md §6](01-etat-de-l-art.md#6-sources-de-données-et-conditions-daccès-2026); demandes de fusion benoit-plante/revue-portee#8 et benoit-plante/revue-portee#9.

### D-057 — Exports réels versionnés comme extraits

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Les exports réels servant aux tests sont versionnés sous forme d'**extraits** (`tests/fixtures/ris/`) : quelques dizaines d'enregistrements, octets conservés (encodage, fins de ligne, marque d'ordre des octets), protégés de la normalisation par git (`.gitattributes` : `tests/fixtures/ris/*.ris -text`).
  - Dans ces extraits : résumés tronqués, adresses de courriel masquées, numéro de bibliothèque des liens Ovid remplacé par `0000`, champs répétés (`M1`, `A2`) limités à trois par enregistrement.
  - Les exports complets ne sont pas versionnés; les nombres obtenus sur eux sont rapportés dans la demande de fusion.
- **Contexte** : le dépôt est public (2026-10-07); un export contient des résumés sous droit d'auteur, des adresses d'auteurs et des identifiants d'abonnement.
- **Options envisagées** :
  1. **Extraits nettoyés** : les variantes de format sont testées sans publier ce qui n'est pas à nous.
  2. Exports complets : droits d'auteur et identifiants d'abonnement publiés.
  3. Fichiers synthétiques : ne prouvent pas la lecture des vrais exports.
- **Justification** : les tests portent sur la forme des fichiers, que les extraits conservent.
- **Conséquences** : un nouvel export réel s'ajoute de la même façon; le nettoyage est vérifié par le test anti-secrets.
- **Renvois** : EF-COL-03, ENF-SEC-04; demandes de fusion benoit-plante/revue-portee#8 et benoit-plante/revue-portee#9.

### D-058 — Nettoyage des réponses enregistrées

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : avant d'écrire une cassette `httpx2`, `tests/recording.py` (`trim_body`) réduit chaque réponse à ce dont les tests ont besoin, sans en changer la structure :
  - résumés tronqués à 200 caractères (OpenAlex : 30 premiers mots de l'index inversé);
  - adresses de courriel remplacées par `masked@example.org`;
  - listes de références citées des notices PubMed (`ReferenceList`) retirées.

  Le XML est traité par ElementTree, pas par des expressions régulières. Les paramètres `api_key`, `email` et `mailto` sont toujours remplacés par des valeurs fictives (D-047), et une cassette qui contient une valeur de secret n'est pas écrite.
- **Contexte** : les cassettes de collecte contiennent des centaines de notices complètes (résumés, adresses d'auteurs), dans un dépôt public.
- **Options envisagées** :
  1. **Nettoyage à l'enregistrement** : rien de superflu n'atteint le disque.
  2. Nettoyage manuel après coup : risque d'oubli.
- **Justification** : comme le filtrage des secrets, le nettoyage doit être automatique.
- **Conséquences** : les nombres (notices annoncées et collectées) restent exacts; les tests ne doivent pas dépendre du texte intégral d'un résumé.
- **Renvois** : D-017, D-047, ENF-SEC-04; demande de fusion benoit-plante/revue-portee#8.

### D-059 — Tâches de fond par fils, sans file persistée

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Les opérations longues lancées depuis l'interface (collecte, enrichissement) s'exécutent dans un fil du processus du serveur (`jobs/runner.py`, `BackgroundJobs`), au plus une par clé (par exemple une par base).
  - L'état d'une tâche est ce qu'elle a enregistré dans le projet : la page « Collecte » le relit toutes les 2 secondes (HTMX). Le message de la dernière erreur est gardé en mémoire et affiché.
  - Il n'y a pas de file persistée : une tâche arrêtée avec le serveur se reprend en la relançant, car les cas d'usage reprennent là où ils s'étaient arrêtés (D-053, D-055).
- **Contexte** : 03-architecture.md §9 prévoyait une file persistée dans SQLite, reprise au redémarrage.
- **Options envisagées** :
  1. **Fils sans file** : la reprise repose sur les données déjà enregistrées, sans seconde source de vérité.
  2. File persistée dans SQLite : il faudrait une table modifiable ou une suite d'événements, et une reprise automatique au démarrage qui pourrait relancer des appels payants sans que la personne le sache.
- **Justification** : en V1, un seul réviseur humain lance les tâches; une reprise explicite est plus prévisible.
- **Conséquences** :
  - **Écart à 03-architecture.md §9** : pas de reprise automatique au redémarrage; la page « Collecte » propose de reprendre chaque collecte ouverte.
  - À revoir pour les lots de tri par l'IA (tranche 1.6), si une reprise automatique devient nécessaire.
- **Renvois** : ENF-PER-04; demande de fusion benoit-plante/revue-portee#8.

Propositions de la tranche 1.5 (2026-10-08), mises en œuvre dans la demande de fusion benoit-plante/revue-portee#11 :

### D-060 — Jeu annoté du dédoublonnage

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Le jeu de test du critère « rappel ≥ 0,98 et précision ≥ 0,99 » (`tests/fixtures/dedup/`) réunit 4 486 notices :
    - les exports réels LUDIQ de Benoit (4 209 notices de PubMed, PsycInfo EBSCOhost et Ovid, CINAHL, SocINDEX, Érudit et ERIC);
    - des notices OpenAlex (CC0) : 23 vraies paires prépublication–article et des paires difficiles;
    - 103 variantes construites à partir de notices OpenAlex (accents, majuscules, sous-titre, ponctuation, DOI absent, initiales, année de mise en ligne, balises HTML, faute de frappe).
  - Les exports LUDIQ sont versionnés **sans résumés**, ni URL, ni numéros d'accès : seulement les métadonnées bibliographiques et le groupe annoté.
  - Annotation : paires candidates produites indépendamment de l'outil, doublons évidents par identifiant et titre, revue manuelle des 87 paires limites. La méthode est décrite dans `tests/fixtures/dedup/README.md`.
  - Règles d'annotation :
    - la même notice dans plusieurs bases est un doublon;
    - une thèse, une communication ou une prépublication et l'article, ou le même travail publié dans deux revues, sont des **versions**;
    - les correctifs, rétractations, réponses et commentaires sont des notices distinctes.
  - Un jeu de démonstration de 9 notices fictives (`demo-*.ris`) sert aux nombres calculés à la main.
- **Contexte** : le critère demande au moins 1 000 références annotées avec des doublons connus; le dépôt est public (2026-10-07).
- **Options envisagées** :
  1. **Exports LUDIQ et compléments OpenAlex** : des doublons réels entre bases, et des cas rares ajoutés de façon contrôlée.
  2. OpenAlex seulement : annotation certaine, mais doublons peu réalistes.
  3. Jeu public de référence (par exemple ASySD) : un domaine à ajouter à la liste réseau et une licence à vérifier.
- **Justification** : choix de Benoit (option 1, métadonnées sans résumés). La CI peut vérifier le critère à chaque demande de fusion.
- **Conséquences** :
  - **Écart à D-057**, qui ne versionne que des extraits d'exports : ici, les métadonnées des exports complets sont publiées, sans les résumés.
  - L'annotation des doublons évidents s'appuie sur les identifiants, comme la première étape de l'outil. Une mesure sans aucun identifiant vérifie l'appariement approximatif seul : rappel 0,998, précision 1,000.
  - Un échantillon des grappes et les paires revues à la main restent à vérifier par Benoit.
- **Renvois** : EF-COL-06, ENF-QUA-01, D-057; demande de fusion benoit-plante/revue-portee#11.

### D-061 — Exécutions, paires et décisions en ajout seulement

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Trois tables en ajout seulement :
    - `dedup_run` : une exécution, avec ses seuils et la version des règles;
    - `duplicate_pair` : les paires trouvées par une exécution, avec leur type, leur règle, leur score et leur proposition (regroupée ou à examiner);
    - `pair_decision` : les décisions d'une personne.
  - Un lien entre deux références est **en vigueur** si la dernière décision humaine sur la paire dit « doublons », ou, sans décision, si la dernière exécution l'a regroupée automatiquement. Les décisions sont ordonnées selon le journal, pas selon leur identifiant.
  - Les groupes sont les références reliées entre elles. La **référence principale est calculée** : la notice la plus complète (DOI, résumé, PMID, champs remplis), puis la plus ancienne.
  - Annuler un regroupement consigne la décision « pas des doublons »; regrouper de nouveau en consigne une autre. Une nouvelle exécution conserve les décisions prises.
  - Une paire dont les deux références sont déjà dans le même groupe, par d'autres liens, n'est plus à examiner.
  - Le dédoublonnage s'exécute en arrière-plan (`BackgroundJobs`, D-059), et chaque exécution est une seule transaction.
- **Contexte** : EF-COL-07 exige un regroupement réversible, sans suppression, qui consigne la règle appliquée.
- **Options envisagées** :
  1. **Paires et décisions, liens calculés** : rien n'est modifié; l'état se recalcule à partir des lignes.
  2. Table `duplicate_link` avec `primary_reference_id` et une colonne `active` (prévue dans 03-architecture.md §5.4) : une colonne `active` devrait être modifiée, et une référence principale stockée deviendrait fausse après une annulation.
- **Justification** : l'option 1 respecte l'ajout seulement (ENF-TRA-02) sans exception.
- **Conséquences** :
  - **Écart à 03-architecture.md §5.4** : `duplicate_link` est remplacée.
  - Le choix manuel de la référence principale n'est pas offert en V1.
- **Renvois** : EF-COL-07, ENF-TRA-01, ENF-TRA-02, D-028, D-059; demande de fusion benoit-plante/revue-portee#11.

### D-062 — Règles d'appariement

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** (version 1 des règles, consignée dans chaque exécution) :
  - **Étape 1, identifiants.** Un même DOI normalisé, PMID ou identifiant OpenAlex donne un doublon. Si les titres divergent, ou si un autre identifiant diffère, la paire va à une personne.
  - **Étape 2, appariement approximatif.**
    - Blocage par cinq clés : début du titre, trois mots les plus longs, fin du titre, auteur et année et première page, revue et volume et première page.
    - Score : moyenne pondérée des champs connus des deux notices : titre 0,55, premier auteur 0,15, année 0,10, revue 0,10, volume et première page 0,10.
    - Normalisation : balises, accents, casse et ponctuation retirés; titre tronqué ou sans sous-titre compté à 0,95; nom de famille du premier auteur lu dans tous les formats usuels.
  - **Jamais regroupées automatiquement** : DOI ou PMID différents, nombres différents dans les titres (« partie II » et « partie III »), années distantes de plus d'un an, premier auteur différent ou absent, premières pages différentes dans le même volume, titre traduit par PubMed (entre crochets).
  - **Jamais appariées** : deux notices dont les titres n'ont pas les mêmes mots de correctif, de rétractation, de réponse, de commentaire ou de matériel supplémentaire.
  - **Seuils réglables**, par défaut 0,75 (paire soumise à une personne) et 0,93 (paire regroupée automatiquement).
- **Contexte** : EF-COL-06 demande un appariement avec score et des paires incertaines soumises à un humain; le principe n° 1 du projet exclut toute exclusion automatique non vérifiable.
- **Options envisagées** :
  1. **Règles explicables et score pondéré** : chaque paire donne sa règle et les raisons d'un examen humain.
  2. Modèle appris (classificateur) : moins explicable, et il faudrait des données d'entraînement par revue.
- **Justification** : sur le jeu annoté, l'option 1 atteint un rappel et une précision de 1,000, avec 59 paires soumises; les résultats tiennent pour les seuils 0,60/0,85 et 0,80/0,97.
- **Conséquences** : toute modification des règles incrémente `ALGORITHM_VERSION` (`domain/dedup.py`), et le test sur le jeu annoté doit rester au-dessus des cibles.
- **Renvois** : EF-COL-06, ENF-REP-01; demande de fusion benoit-plante/revue-portee#11.

### D-063 — Versions d'un même travail

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : une prépublication et l'article, une thèse ou une communication et l'article, ou le même travail publié dans deux revues (DOI différents, revues différentes) forment une paire de type `version`. Elle est toujours soumise à une personne, qui choisit de les regrouper ou non; sans décision, elles restent distinctes. Pour le préfixe DOI 10.1101/, seules les formes de bioRxiv et medRxiv comptent comme prépublications (le préfixe sert aussi à des revues de Cold Spring Harbor Laboratory Press).
- **Contexte** : le critère d'acceptation demande que la paire prépublication–version publiée soit signalée.
- **Options envisagées** :
  1. **Lien distinct, décision humaine** : la personne décide selon le protocole de la revue.
  2. Doublons ordinaires, regroupés au-dessus du seuil : une décision de méthode serait prise par l'outil.
- **Justification** : choix de Benoit (option 1); inclure les deux versions ou une seule relève du protocole.
- **Conséquences** : le rapport de recherche devra pouvoir mentionner les versions regroupées (tranche de la section méthode).
- **Renvois** : EF-COL-06; demande de fusion benoit-plante/revue-portee#11.

### D-064 — Nombres du diagramme de flux

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Références repérées par source : les références de chaque base, nommée par la collecte (base de la requête) ou par la base déclarée pour un fichier RIS (la première provenance d'une référence en a plusieurs).
  - Doublons retirés : les références regroupées sous une référence principale.
  - Références après dédoublonnage : les repérées moins les doublons retirés.
  - Les paires encore à examiner comptent comme distinctes, et la page l'indique.
- **Contexte** : EF-COL-08 demande des nombres calculés à partir des données, jamais saisis à la main.
- **Options envisagées** :
  1. **Comptes calculés à chaque affichage** (`dedup/counts.py`, fonction pure) : toujours cohérents avec les liens en vigueur.
  2. Comptes enregistrés avec chaque exécution : faux dès la décision suivante.
- **Justification** : les décisions humaines changent les nombres; seul un calcul à la demande reste exact.
- **Conséquences** : le jeu de démonstration (9 notices fictives) vérifie les nombres calculés à la main : 9 repérées, 3 doublons retirés, 6 après dédoublonnage et 1 paire à examiner, puis 4 et 5 après la décision.
- **Renvois** : EF-COL-08; demande de fusion benoit-plante/revue-portee#11.

### D-065 — Probabilité d'inclusion et valeur de l'IA tirée des seuils

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - La « confiance » consignée pour une décision de l'IA (`confidence_raw`) est la **probabilité que la référence soit incluse**, donnée par le modèle entre 0 et 1.
  - La valeur retenue pour l'IA se **déduit des seuils** : sous `exclude_below`, exclure; à partir de `include_above`, inclure; entre les deux, incertain. La règle EF-SEL-07 s'applique ensuite (D-068).
  - La probabilité utilisée est la probabilité étalonnée quand un étalonnage est en vigueur (`confidence_calibrated`), sinon la probabilité brute.
  - La décision globale proposée par le modèle reste conservée (`model_decision`), sans déterminer la valeur.
- **Contexte** : EF-SEL-06 demande une confiance entre 0 et 1; EF-SEL-09 place des seuils sur cette confiance. Une confiance « dans la décision » n'a pas le même sens selon que la décision est d'inclure ou d'exclure, et ne s'étalonne pas sur une seule échelle.
- **Options envisagées** :
  1. **Probabilité d'inclusion, valeur tirée des seuils** : une seule échelle, étalonnable par régression isotonique, avec des seuils lisibles.
  2. Confiance dans la décision du modèle : deux échelles mêlées; les seuils d'EF-SEL-09 deviennent ambigus.
- **Justification** : la courbe seuil → sensibilité (EF-SEL-03) et l'étalonnage (EF-SEL-05) supposent une seule échelle ordonnée.
- **Conséquences** : une même réponse brute donne toujours la même décision, ce qui permet de reconstituer une décision sans rappeler le modèle (ENF-REP-02).
- **Renvois** : EF-SEL-05, EF-SEL-06, EF-SEL-09, ENF-REP-02; demande de fusion benoit-plante/revue-portee#13.

### D-066 — Seuils par défaut au tri des titres et résumés

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : avant tout pilote, l'IA exclut sous **0,10** et inclut à partir de **0,60** de probabilité d'inclusion (`supervision` dans `resources/ai_defaults.yaml` et `[ia]` de `projet.toml`). Après le pilote, une personne fixe les seuils avec leur justification (`threshold_setting`).
- **Contexte** : EF-SEL-09 demande des seuils par défaut qui favorisent la sensibilité, documentés et modifiables.
- **Options envisagées** :
  1. **0,10 et 0,60** : n'exclut que les références que le modèle juge très peu probables; une large zone d'incertitude.
  2. Seuil d'exclusion plus élevé (0,20 ou 0,30) : plus de références évitées, au risque de la sensibilité.
- **Justification** : au banc SYNERGY, ces seuils donnent une sensibilité de 95,0 à 97,4 % sur trois jeux en psychologie, avec une spécificité de 78,7 à 84,2 % (`docs/resultats/`).
- **Conséquences** : la feuille de route ne demande pas de revoir le seuil par défaut, puisque la cible de sensibilité est atteinte. En V1, l'IA n'exclut jamais seule (D-014) : ces seuils ne servent qu'à présenter les décisions de l'IA et à mesurer le pilote.
- **Renvois** : EF-SEL-09, D-014; demandes de fusion benoit-plante/revue-portee#13 et benoit-plante/revue-portee#14.

### D-067 — Modèle par défaut du tri des titres et résumés

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : la tâche `screen_reference` utilise par défaut `claude-haiku-5-5`, effort `low`, `max_tokens` 8 000, sortie attendue de 1 200 jetons pour l'estimation du coût (`resources/ai_defaults.yaml`). Ce modèle n'offre pas de repli côté serveur : le paramètre `fallbacks` de D-037 est absent pour cette tâche.
- **Contexte** : D-038 renvoyait le choix du modèle du tri au banc d'essai, sous la cible de coût de D-015.
- **Options envisagées** :
  1. **Haiku 5.5, effort `low`** : environ 0,35 à 0,45 $ US pour 1 000 références au banc.
  2. Sonnet 5.5 : plus capable, pour un coût plusieurs fois plus élevé.
- **Justification** : choix de Benoit au lancement de la tranche 1.6. Le banc SYNERGY le confirme : sensibilité d'au moins 95 % sur les trois jeux, pour 0,34 à 0,46 $ US pour 1 000 références, bien sous la cible de 5 $ US (D-015).
- **Conséquences** :
  - un projet créé avant la tranche 1.6 garde `screen_reference` au statut « prévue » dans `[ia]` : la page « Pilote » l'indique, et la section doit être mise à jour à la main;
  - un autre modèle reste possible par projet, en modifiant `[ia]`.
- **Renvois** : D-015, D-037, D-038, ENF-COU-07; demandes de fusion benoit-plante/revue-portee#13 et benoit-plante/revue-portee#14.

### D-068 — Règle EF-SEL-07 précisée

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Un critère **écarte** une référence quand c'est un critère d'inclusion « non satisfait » ou un critère d'exclusion « satisfait ».
  - Si un critère d'inclusion est « impossible à déterminer » et qu'aucun critère n'écarte la référence, l'IA ne l'exclut jamais : une valeur « exclure » tirée des seuils devient « incertain ».
  - Un critère d'exclusion « non satisfait » n'écarte rien; un critère d'exclusion « impossible à déterminer » ne protège pas la référence.
- **Contexte** : EF-SEL-07 parle d'un critère « impossible à déterminer », sans dire ce qui se passe quand un autre critère écarte clairement la référence.
- **Options envisagées** :
  1. **Protection seulement sans critère qui écarte** : un résumé vague sur la population ne sauve pas un article clairement hors sujet.
  2. Protection dès qu'un critère est indéterminable : presque toutes les références seraient « incertaines », puisque les résumés taisent souvent la durée, le plan ou l'âge.
- **Justification** : l'option 1 garde l'intention d'EF-SEL-07 (ne pas exclure faute d'information) sans vider le tri de son utilité.
- **Conséquences** : la règle est une fonction pure du domaine (`must_not_exclude`), vérifiée par des tests.
- **Renvois** : EF-SEL-07; demande de fusion benoit-plante/revue-portee#13.

### D-069 — Budget du projet et plafond de lot

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Aucun plafond par défaut : un budget de projet doit être **fixé avant le premier lot** de tri par l'IA. Le budget est en ajout seulement (`budget_setting`), et la dépense se calcule à partir des coûts consignés des appels (`ai_call.cost_estimate`).
  - Chaque lot a en plus son propre plafond, proposé à l'estimation majorée de 25 %, arrondie au cent supérieur.
  - Le plafond du projet et celui du lot sont vérifiés **avant chaque appel**, nouvelles tentatives comprises. Le lot s'arrête alors proprement, et ce qui est trié reste enregistré (`budget.reached`).
- **Contexte** : ENF-COU-02 demande un plafond global et par lot, avec un arrêt sans perte de travail. 03-architecture.md §5.6 prévoyait une table `budget` avec un montant dépensé modifiable.
- **Options envisagées** :
  1. **Budget en ajout seulement, dépense calculée** : aucune ligne modifiée; la dépense ne peut pas diverger des appels consignés.
  2. Table `budget` avec `spent_amount` mis à jour : contraire à l'ajout seulement (D-028).
- **Justification** : choix de Benoit (aucun plafond par défaut); l'option 1 respecte D-028.
- **Conséquences** : **écart à 03-architecture.md §5.6** (`budget` remplacée par `budget_setting`). La dépense du projet compte tous les appels, y compris ceux des tâches de cadrage.
- **Renvois** : ENF-COU-01, ENF-COU-02, ENF-COU-03, D-028; demande de fusion benoit-plante/revue-portee#13.

### D-070 — Une seule nouvelle tentative par référence

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : une réponse non conforme au schéma, ou qui n'évalue pas chaque critère exactement une fois, ou qui cite comme déterminant un critère inconnu, est consignée (`ai.result_unusable`) puis **redemandée une fois**. Après deux réponses inutilisables, l'échec est consigné (`screening.ai_failed`) et la référence reste à trier par l'humain.
- **Contexte** : le critère d'acceptation demande 100 % de sorties valides, sinon une nouvelle tentative, puis un statut « échec » consigné.
- **Options envisagées** :
  1. **Une nouvelle tentative** : coût borné à deux appels par référence.
  2. Plusieurs nouvelles tentatives : coût imprévisible, pour un gain faible.
- **Justification** : au banc SYNERGY, 2 références sur 14 624 sont restées inutilisables après la nouvelle tentative.
- **Conséquences** : la cause observée (le modèle omet un critère d'exclusion quand un critère d'inclusion suffit à exclure) appelle une version 2 du gabarit `screen_reference`.
- **Renvois** : EF-SEL-06, ENF-TRA-01; demandes de fusion benoit-plante/revue-portee#13 et benoit-plante/revue-portee#14.

### D-071 — Tri à l'aveugle garanti par l'interface

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : l'IA peut trier les références du pilote avant, pendant ou après le réviseur humain. L'interface ne montre la décision de l'IA sur une référence qu'**après** la décision humaine sur cette même référence (`PilotState.visible_ai`). Les décisions humaines du pilote sont marquées `blinded`; une nouvelle décision humaine sur la même référence remplace la précédente (`supersedes_decision_id`).
- **Contexte** : EF-SEL-02 exige que le réviseur humain décide à l'aveugle.
- **Options envisagées** :
  1. **Masquage à l'affichage** : l'IA travaille en arrière-plan sans attendre l'humain.
  2. Lancer l'IA seulement après le tri humain complet : plus lent, sans gain pour l'aveugle.
- **Justification** : l'aveugle porte sur ce que voit la personne, pas sur l'ordre des calculs.
- **Conséquences** : un test de l'interface vérifie que la justification de l'IA est absente avant la décision humaine, puis présente pour la seule référence décidée.
- **Renvois** : EF-SEL-02; demande de fusion benoit-plante/revue-portee#13.

### D-072 — Étalonnage et seuil d'exclusion suggéré

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - L'étalonnage s'ajuste sur les paires (humain, IA) d'un tour de pilote : une référence est positive quand l'humain l'inclut ou la juge incertaine.
  - Méthode `isotonic` par défaut (pool-adjacent-violators, interpolation linéaire); `platt` sur demande; `none` quand le pilote n'a qu'une seule catégorie. L'étalonnage est enregistré dans `etalonnage/<id>.json` et dans `calibration_model`.
  - Le **seuil d'exclusion suggéré** est le plus élevé qui garde la sensibilité du pilote au moins égale à la cible (0,95 par défaut). Si le pilote n'a aucun positif, la suggestion n'exclut rien.
  - Une personne fixe les seuils, avec une justification obligatoire, et choisit de les appliquer ou non aux probabilités étalonnées.
- **Contexte** : EF-SEL-05 demande des seuils fixés à partir des données observées, avec une préférence explicite pour la sensibilité.
- **Options envisagées** :
  1. **Suggestion, puis décision humaine justifiée** : l'outil calcule, la personne tranche.
  2. Seuil appliqué automatiquement : contraire au principe de vérification humaine.
- **Justification** : la suggestion rend le compromis visible; la décision reste humaine et consignée (`thresholds.set`).
- **Conséquences** : avec peu de positifs, la suggestion est fragile; la page affiche l'intervalle de Wilson de la sensibilité (03-architecture.md §6.5).
- **Renvois** : EF-SEL-03, EF-SEL-05, EF-SEL-09; demande de fusion benoit-plante/revue-portee#13.

### D-073 — Détection de la langue des références

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : la langue consignée avec chaque décision de l'IA est la langue déclarée par la notice (nom ou code ISO) quand elle existe; sinon, elle est déduite du titre et du résumé en comptant des mots outils français et anglais. Sans indice, elle reste vide.
- **Contexte** : ENF-LAN-05 demande que la langue de chaque référence soit détectée et consignée.
- **Options envisagées** :
  1. **Langue déclarée, puis mots outils** : sans dépendance, suffisant pour le français et l'anglais.
  2. Bibliothèque de détection de langue : une dépendance de plus, utile surtout pour d'autres langues.
- **Justification** : le corpus visé est surtout français et anglais; les autres langues sont traitées sans erreur, avec une langue vide au besoin.
- **Conséquences** : la justification de l'IA est rédigée dans la langue du projet, quelle que soit la langue de la référence.
- **Renvois** : ENF-LAN-05; demande de fusion benoit-plante/revue-portee#13.

### D-074 — Banc SYNERGY : réponses brutes hors du dépôt, échantillon et appels simultanés

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Le banc (`revue-portee banc-synergy`) lit un CSV local et un fichier YAML de critères, affiche le coût maximal estimé et demande confirmation. Il n'utilise aucun dossier de projet.
  - Les réponses brutes vont dans un fichier JSON Lines **hors du dépôt**; le rapport versionné dans `docs/resultats/` ne contient que des nombres.
  - L'option `--echantillon` garde toutes les inclusions et tire des exclusions avec une graine consignée.
  - L'option `--paralleles` fait jusqu'à 16 appels simultanés : le coût estimé de chaque appel est réservé avant l'appel, ce qui maintient le plafond.
- **Contexte** : le critère d'acceptation demande un banc lancé à la main, avec ses résultats dans `docs/resultats/`. Le dépôt est public, et un appel à la fois prenait environ 3,6 secondes (15 heures pour 14 624 références).
- **Options envisagées** :
  1. **Rapport chiffré versionné, réponses brutes locales** : rien de tiers n'est republié.
  2. Réponses brutes versionnées : elles reprennent des extraits de résumés.
- **Justification** : les rapports suffisent à vérifier les critères d'acceptation; les réponses brutes se régénèrent avec les mêmes données et critères.
- **Conséquences** : avec 8 appels simultanés, le banc complet a pris environ 2 heures.
- **Renvois** : ENF-COU-01, ENF-COU-02; [05-plan-de-validation.md](05-plan-de-validation.md); demandes de fusion benoit-plante/revue-portee#13 et benoit-plante/revue-portee#14.

### D-075 — Données et critères du banc SYNERGY

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Trois jeux en psychologie clinique : Oud_2018, van_de_Schoot_2018 et van_Dis_2020.
  - Notices de **SYNERGY 1.0** (titres et résumés d'OpenAlex); SYNERGY+ 3.0 n'a de résumé que pour 25 à 30 % des notices de ces jeux.
  - Critères **reformulés** à partir de ceux publiés avec SYNERGY+ 3.0 et versionnés dans `docs/resultats/synergy/`. Pour van_de_Schoot_2018, SYNERGY+ ne publie que les critères de la mise à jour de 2025 : les échantillons cliniques, nouveaux en 2025, sont exclus.
  - Référence de comparaison : les **inclusions au texte intégral** de chaque revue.
  - Justifications de l'IA rédigées en français, comme dans un projet réel.
- **Contexte** : la feuille de route demande une sensibilité d'au moins 0,95 sur au moins 3 jeux SYNERGY en psychologie, par rapport aux inclusions finales.
- **Options envisagées** :
  1. **Jeux de psychologie clinique chez l'humain** : proches des revues visées; coût total d'environ 6 $ US.
  2. Jeux classés en psychologie mais portant sur l'animal (Sep_2021, Leenaars_2019), ou très volumineux (Brouwer_2019, 46 376 notices).
- **Justification** : choix de Benoit (trois jeux recommandés; critères publiés par SYNERGY); lecture validée par Benoit pour van_de_Schoot_2018.
- **Conséquences** :
  - les inclusions au texte intégral sous-estiment la sensibilité au tri des titres et résumés : les 4 inclusions manquées sur 130 relèvent de critères appliqués plus largement au texte intégral qu'ils ne sont écrits;
  - le banc exige les domaines `api.anthropic.com`, `dataverse.nl` et `objectstore.surf.nl` dans l'environnement infonuagique.
- **Renvois** : [05-plan-de-validation.md](05-plan-de-validation.md); [docs/resultats/README.md](resultats/README.md); demande de fusion benoit-plante/revue-portee#14.

### D-076 — Résultat du banc SYNERGY

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : la configuration par défaut (D-066, D-067) est retenue. Au banc SYNERGY, la sensibilité est de **95,0 %** (Oud_2018, 19 sur 20), **97,4 %** (van_de_Schoot_2018, 37 sur 38) et **97,2 %** (van_Dis_2020, 70 sur 72), pour **0,34 à 0,46 $ US** pour 1 000 références.
- **Contexte** : la feuille de route prévoit de revoir le seuil par défaut si la cible n'est pas atteinte.
- **Options envisagées** :
  1. **Garder la configuration par défaut** : les deux cibles sont atteintes.
  2. Baisser le seuil d'exclusion : sans motif, puisque la cible est atteinte.
- **Justification** : critère d'acceptation atteint sur les trois jeux; coût environ dix fois sous la cible de D-015.
- **Conséquences** : la sensibilité d'Oud_2018 est tout juste à la cible et son intervalle est large (76,4 à 99,1 %), avec 20 inclusions; l'étude de validation (05) mesurera la sensibilité sur des revues de portée.
- **Renvois** : D-015, D-066, D-067; [docs/resultats/README.md](resultats/README.md); demande de fusion benoit-plante/revue-portee#14.

### D-077 — Réévaluation des clarifications sur un échantillon

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : les références touchées par une clarification seulement sont réévaluées sur un échantillon aléatoire de **20 %**, au moins **20** (toutes s'il y en a moins), tiré avec une graine consignée. La personne peut choisir de les réévaluer toutes au moment de l'analyse d'impact. Les références touchées par un autre type de changement sont toujours toutes réévaluées.
- **Contexte** : EF-VER-04 prévoit pour une clarification les références qui citent le critère, « à revoir par échantillon »; une clarification ne vise pas à changer la portée.
- **Options envisagées** :
  1. **Échantillon réglable** : coût borné; un changement de décision dans l'échantillon signale une clarification qui change en fait la portée.
  2. Toutes les références touchées : sans choix d'échantillon à justifier, mais plus coûteux.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : la graine et le choix (échantillon ou toutes) sont consignés avec l'analyse (`impact_assessment.seed`, `sampled`); l'échantillon ne peut pas être étendu après coup.
- **Renvois** : EF-VER-04, EF-VER-05; demande de fusion benoit-plante/revue-portee#16.

### D-078 — Décisions du pilote reprises au tri principal

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : les décisions humaines d'un tour pilote pris avec la même version des critères que le tri principal comptent pour le tri principal : ces références ne sont pas triées de nouveau par la personne. Elles sont **calculées**, pas recopiées. Les décisions de l'IA du tri principal sont refaites dans tous les cas, avec les seuils fixés après le pilote.
- **Contexte** : le pilote porte sur un échantillon des mêmes références, souvent une centaine.
- **Options envisagées** :
  1. **Reprises si mêmes critères** : pas de travail refait; un changement de critères impose un nouveau tri.
  2. Jamais reprises : plus simple à expliquer, mais une centaine de références à trier de nouveau.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : le journal du début du tri consigne les tours repris et le nombre de décisions reprises (`screening.started`).
- **Renvois** : EF-SEL-01, EF-SEL-08; demande de fusion benoit-plante/revue-portee#16.

### D-079 — Définition du désaccord au tri des titres et résumés

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : l'humain et l'IA sont en **désaccord** quand l'un conserve la référence (inclure ou incertain) et l'autre l'exclut. « Inclure » contre « incertain » n'est pas un désaccord : les deux passent au texte intégral.
- **Contexte** : EF-SEL-08 présente les désaccords pour réconciliation; le critère d'acceptation exige une file qui contient exactement les références où les deux décisions diffèrent.
- **Options envisagées** :
  1. **Conserver ou exclure** : même règle que la sensibilité du pilote; file limitée à ce qui change l'issue.
  2. Toute valeur différente : file plus longue, sans effet sur ce qui passe au texte intégral.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : la même règle sert à la réévaluation (D-082).
- **Renvois** : EF-SEL-08; demande de fusion benoit-plante/revue-portee#16.

### D-080 — Tri par l'IA au moyen de l'API Batches

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - Le tri principal et la réévaluation envoient les références à l'API de traitement par lots du fournisseur (`BatchProvider`), au tarif des lots (`batch_factor` dans `model_prices.yaml`, 0,5 pour Anthropic).
  - Au plus **5 000** requêtes par lot; chaque lot enregistre la version des critères donnée au modèle (`ai_batch`), et la décision de l'IA renvoie à cette version.
  - Avant chaque lot, son estimation est ajoutée à la dépense du projet et aux estimations des lots encore en cours : aucun lot n'est envoyé qui dépasserait le budget du projet ou le plafond de l'envoi.
  - La collecte enregistre chaque résultat dans sa propre transaction, avec sa réponse brute, puis la fin du lot (`ai_batch_end`); collecter de nouveau saute les appels déjà consignés.
  - Une référence est envoyée au plus **deux fois** en tout; après deux réponses inutilisables ou en erreur, l'échec est consigné.
- **Contexte** : ENF-COU-04 demande les mécanismes de réduction des coûts du fournisseur; un projet peut compter des dizaines de milliers de références.
- **Options envisagées** :
  1. **API Batches** : moitié prix; résultats en général en moins d'une heure, au plus en 24 heures; reprise après interruption.
  2. Appels simultanés (comme au banc SYNERGY) : plus simple, au plein tarif.
- **Justification** : choix de Benoit (option 1, prévu pour la tranche 1.7 au lancement de la tranche 1.6).
- **Conséquences** : le suivi des lots tourne en arrière-plan dans le serveur (`BackgroundJobs`, D-059) et se reprend depuis la page après un redémarrage. L'API Batches n'a pas encore été essayée avec le vrai modèle.
- **Renvois** : ENF-COU-01, ENF-COU-02, ENF-COU-04, ENF-PER-04, D-041, D-069; demande de fusion benoit-plante/revue-portee#16.

### D-081 — Règles de l'analyse d'impact

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** :
  - L'état courant d'une référence est sa dernière décision humaine (indépendante, de réconciliation ou de réévaluation), dans l'ordre du journal.
  - Les références pas encore triées ne sont pas touchées : elles seront triées avec la nouvelle version.
  - Élargissement : références exclues qui citent le critère. Restriction : références conservées. Clarification : références qui citent le critère. Critère ajouté : références conservées (« encore à l'étape »). Critère retiré : références exclues pour ce seul critère.
  - Les versions activées pendant le tri sont analysées une à une, dans l'ordre.
- **Contexte** : EF-VER-04 décrit les cinq règles; il fallait préciser l'état de référence et le sens de « encore à l'étape ».
- **Options envisagées** :
  1. **Règles appliquées à la dernière décision humaine** : l'IA seule ne détermine aucun état en V1 (D-014).
  2. Règles appliquées aussi aux décisions de l'IA : contraire à la décision finale humaine.
- **Justification** : cohérence avec EF-SEL-08 et D-014.
- **Conséquences** : un jeu construit à la main (12 références, 28 cas, au moins 5 par type) vérifie chaque règle.
- **Renvois** : EF-VER-04, D-014; [03-architecture.md §7](03-architecture.md#7-analyse-dimpact-fonctionnalité-distinctive); demande de fusion benoit-plante/revue-portee#16.

### D-082 — Réévaluation par l'IA, puis vérification humaine des changements

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : l'IA trie de nouveau, avec la nouvelle version des critères, les références à réévaluer. La personne ne vérifie que celles où l'IA ferait passer la référence de « conserver » à « exclure » ou l'inverse (D-079); sa décision remplace la précédente, qui demeure. Là où l'IA ne change pas l'issue, l'ancienne décision reste en vigueur. La fin de la réévaluation consigne, pour chaque changement et en tout, les références réévaluées, triées par l'IA, les changements proposés par l'IA, les décisions changées et les décisions confirmées.
- **Contexte** : EF-VER-05 prévoit en V1 la réévaluation par l'IA puis la vérification humaine des changements de décision.
- **Options envisagées** :
  1. **Vérifier les seuls changements** : effort humain limité à ce qui change l'issue.
  2. Vérifier toutes les références réévaluées : plus sûr, mais l'IA n'apporte alors presque rien.
- **Justification** : conforme à EF-VER-05 (V1).
- **Conséquences** : la réévaluation par la personne seule est reportée à la V2.
- **Renvois** : EF-VER-05, EF-VER-07; demande de fusion benoit-plante/revue-portee#16.

### D-083 — Ordre du tri principal

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : les références du tri principal sont présentées dans un ordre tiré au hasard avec une graine consignée. Les références ajoutées plus tard (collecte ou import après le début du tri) se placent à la suite, dans un ordre tiré avec la graine du tri plus le nombre de références déjà au tour. La priorité selon la probabilité d'inclusion de l'IA reste facultative (EF-SEL-10).
- **Contexte** : un ordre fixe (par source ou par identifiant) peut biaiser le tri, par exemple par fatigue en fin de liste.
- **Options envisagées** :
  1. **Ordre aléatoire avec graine** : reproductible et sans biais d'ordre.
  2. Ordre d'arrivée : simple, mais regroupe les références d'une même source.
- **Justification** : reproductibilité (ENF-REP-01) et absence de biais d'ordre.
- **Conséquences** : la graine figure au journal (`screening.started`, `screening.members_added`).
- **Renvois** : EF-SEL-10, ENF-REP-01; demande de fusion benoit-plante/revue-portee#16.

### D-084 — Touches du tri au clavier

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : `i` inclure, `d` incertain (« doute »), `e` exclure, `1` à `9` pour cocher ou décocher un critère, `p` pour passer la référence pour l'instant. Les touches sont sans effet pendant la saisie d'une note; les boutons portent `aria-keyshortcuts`.
- **Contexte** : ENF-PER-02 exige un tri entièrement au clavier.
- **Options envisagées** :
  1. **Lettres mnémoniques en français** : « inclure » et « incertain » commencent par la même lettre, d'où `d` pour le doute.
  2. Chiffres pour les décisions : en conflit avec les chiffres des critères.
- **Justification** : mémorisation facile; les chiffres restent aux critères.
- **Conséquences** : les mêmes touches servent à la réconciliation et à la réévaluation (sans `p`).
- **Renvois** : ENF-PER-02, ENF-PER-03; demande de fusion benoit-plante/revue-portee#16.

### D-085 — Développement local avec Claude Code

- **Date** : 2026-10-08
- **Statut** : décidée (Benoit passe à Claude Code sur son poste); remplace D-005
- **Décision** : le développement se fait désormais avec **Claude Code sur le poste de Benoit** (macOS ou Linux; sous Windows, dans WSL). L'environnement infonuagique reste possible et décrit dans `CLAUDE.md`. Sur le poste :
  - prérequis : Python 3.12 ou plus récent, uv, Git; facultativement `gh` pour les demandes de fusion;
  - le hook SessionStart de `.claude/settings.json` (`uv sync --frozen`) s'exécute aussi en local; il exige uv dans le `PATH`;
  - les variables `REVUE_PORTEE_ANTHROPIC_KEY`, `CONTACT_EMAIL` et `OPENALEX_API_KEY` sont définies par Benoit dans le profil de son shell (ou dans `env` de `.claude/settings.local.json`, non versionné), jamais dans un fichier du dépôt; `OPENALEX_API_KEY` y est **nécessaire**, aucun mandataire ne l'ajoutant;
  - `ANTHROPIC_API_KEY` n'est pas définie dans le shell : en local, Claude Code peut s'en servir pour s'authentifier (il le propose au démarrage), ce qui facturerait les sessions de développement sur la clé du projet (D-020);
  - le réseau n'est plus limité à une liste : les tests ordinaires restent coupés du réseau (D-016), et les appels réels (tests d'intégration, cassettes, banc SYNERGY) restent soumis à la demande explicite de Benoit;
  - les données hors dépôt (jeux SYNERGY, réponses brutes du banc, projets `.revue` de travail) vont dans un dossier hors du dépôt, par exemple `~/revue-portee-donnees/`.
- **Contexte** : Benoit souhaite travailler avec Claude Code hors de l'environnement infonuagique.
- **Options envisagées** :
  1. **Poste local, environnement infonuagique toujours possible** : fichiers persistants, réseau libre, outils de Benoit.
  2. Environnement infonuagique seulement (D-005).
- **Justification** : choix de Benoit. Le dépôt est déjà autonome (hook d'installation, tests sans réseau, secrets lus par `config/secrets.py`), ce qui rend le passage sans risque.
- **Conséquences** :
  - `CLAUDE.md` et le `README` décrivent les deux environnements, le poste local d'abord;
  - sur le poste, rien ne garantit plus qu'une nouvelle source soit bloquée : la règle de signaler toute nouvelle source à Benoit demeure, pour la méthode et les licences;
  - une session locale ne repart pas de zéro : `uv sync` reste la commande de référence après un changement de `uv.lock`.
- **Renvois** : D-005, D-007, D-013, D-016, D-020, D-021, D-086 (Windows natif); [CLAUDE.md](../CLAUDE.md); [README.md](../README.md).

### D-086 — Adresse de bouclage permise dans les tests ordinaires

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit); complète D-016 et D-085
- **Décision** : les tests ordinaires bloquent toute connexion, sauf vers `127.0.0.1`, et les variables de mandataire (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, en majuscules et en minuscules) leur sont retirées. Le développement est possible sous Windows natif, et toujours dans WSL.
- **Contexte** : sous Windows, la boucle asyncio ouvre une connexion TCP vers `127.0.0.1` pour son fonctionnement interne (`socket.socketpair()`). Le blocage du réseau la refusait, et les 53 tests de l'interface échouaient sur le poste de Benoit.
- **Options envisagées** :
  1. **Bouclage seulement, sans mandataire** : la suite passe sous Windows; aucune API réelle ne répond sur cette adresse.
  2. Exiger WSL (D-085) : aucun changement de code, mais un poste plus lourd à préparer.
- **Justification** : choix de Benoit (option 1). Sans le retrait des variables de mandataire, un mandataire local permettrait à une requête de sortir.
- **Conséquences** : `tests/conftest.py` applique `block_network(allowed_hosts=[r"127\.0\.0\.1$"])`; des tests vérifient que `127.0.0.2` et `::1` restent bloqués. Les réglages de mandataire du système Windows (registre) ne sont pas neutralisés : le risque est jugé faible. La CI ne compte pas de tâche Windows.
- **Renvois** : D-016, D-085; demande de fusion benoit-plante/revue-portee#18.

### D-087 — Formats du diagramme en V1

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : en V1, le diagramme de flux est produit en **SVG** seulement, en français et en anglais. Le PNG et le PDF demandés par EF-DEC-01 viendront en V2.
- **Contexte** : la feuille de route (tranche 1.8) ne demande que le SVG; l'architecture prévoit CairoSVG pour la conversion, en V2.
- **Options envisagées** :
  1. **SVG seulement** : aucune dépendance graphique; un SVG s'ouvre dans un navigateur et s'imprime en PDF.
  2. SVG, PNG et PDF : CairoSVG exige la bibliothèque Cairo, difficile à installer sous Windows.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : EF-DEC-01 reste partiellement couverte; la conversion est à prévoir avec la tranche 2.2.
- **Renvois** : EF-DEC-01; [03-architecture.md §2](03-architecture.md#2-pile-technique); demande de fusion benoit-plante/revue-portee#19.

### D-088 — Bas du diagramme en V1

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : le diagramme reprend le gabarit PRISMA 2020 complet. Les cases sont remplies jusqu'à « Rapports recherchés pour le texte intégral », qui compte les références conservées (inclure ou incertain). Les cases suivantes (rapports non obtenus, évalués, exclus avec motifs, sources incluses) sont en pointillés, avec la mention « étape à venir ».
- **Contexte** : en V1, le tri s'arrête aux titres et résumés.
- **Options envisagées** :
  1. **Gabarit complet, étapes à venir grisées** : forme conforme au gabarit; la V2 n'aura qu'à remplir les cases.
  2. Diagramme coupé après le tri des titres et résumés.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : le gabarit (`resources/reporting/prisma_2020_flow.yaml`) marque ces cases `stage: later`.
- **Renvois** : EF-DEC-01, ENF-NOR-03; demande de fusion benoit-plante/revue-portee#19.

### D-089 — Exclusions par des outils d'automatisation dans le diagramme

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : les cases « Références jugées inadmissibles par des outils d'automatisation » (avant la sélection) et « Références exclues… par des outils d'automatisation » sont affichées, avec leur nombre. Le second est calculé à partir des décisions en vigueur : il vaut 0 en V1 et montrerait toute exclusion par l'IA seule. Quand le diagramme est final, une note dit que l'IA a servi de second réviseur et qu'aucune exclusion n'a été décidée par elle seule.
- **Contexte** : PRISMA 2020 demande de déclarer les exclusions faites par des outils d'automatisation.
- **Options envisagées** :
  1. **Afficher n = 0** : transparent, conforme à RAISE et au principe 1 du projet.
  2. Omettre ces cases.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : les cases « Registres » et « Retirées pour d'autres raisons » sont aussi affichées; aucune de ces deux opérations n'existe dans l'outil en V1, d'où n = 0.
- **Renvois** : EF-DEC-01, D-014; demande de fusion benoit-plante/revue-portee#19.

### D-090 — Diagramme provisoire

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : un diagramme est toujours produit. Il porte le filigrane « PROVISOIRE » et une note qui liste ce qui reste à faire tant qu'il reste : le tri principal à commencer, des références non triées par la personne ou par l'IA, des désaccords à réconcilier, des paires de doublons à examiner, ou une réévaluation non terminée. La section méthode le signale de la même façon.
- **Contexte** : un diagramme est utile pendant le travail, mais ne doit pas être publié par mégarde avant la fin du tri.
- **Options envisagées** :
  1. **Produit, marqué provisoire** : utile en cours de route, sans risque de confusion.
  2. Refusé tant que le tri n'est pas fini.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : `reporting/flow.py` calcule ce qui reste (`Pending`); la page « Rapports » l'affiche aussi.
- **Renvois** : EF-DEC-01; demande de fusion benoit-plante/revue-portee#19.

### D-091 — Réévaluations dans le diagramme

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : les réévaluations dues aux changements de critères sont rendues visibles par une note marquée « † » sur la case « Références triées » : nombre de changements et versions, références réévaluées (par l'IA, puis par la personne pour les décisions que l'IA changerait), décisions passées de « conserver » à « exclure » et l'inverse. Les cases donnent l'état final. Le détail par version va dans la section méthode.
- **Contexte** : critère d'acceptation de la tranche 1.8 (« note ou case dédiée »).
- **Options envisagées** :
  1. **Note** : permise par le gabarit, qui reste intact.
  2. Case dédiée : s'écarte du gabarit PRISMA 2020.
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : une décision changée est une vérification humaine dont la valeur diffère, au sens « conserver » ou « exclure », de la décision qu'elle remplace (D-079, D-082).
- **Renvois** : EF-DEC-01, EF-VER-07, D-082; demande de fusion benoit-plante/revue-portee#19.

### D-092 — Archive publique ou complète

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** :
  - l'archive **publique** (par défaut) contient les données lisibles (CSV, JSON lines), le diagramme, la section méthode, les étalonnages et `projet.toml`, mais ni résumé, ni URL, ni réponse brute, ni base SQLite. Chaque nombre du diagramme s'y recalcule sans l'outil (`LISEZMOI.md`);
  - l'archive **complète** (`--complete`) y ajoute une copie du dossier sans `textes/`; elle se rouvre avec l'outil et n'est pas destinée à un dépôt public;
  - un secret trouvé dans les fichiers texte arrête l'export; chaque export est consigné au journal (`archive.exported`) avec l'empreinte SHA-256 du fichier.
- **Contexte** : les résumés appartiennent en général aux éditeurs, et un dépôt OSF est public; ENF-REP-06 demande que chaque nombre déclaré soit vérifiable sans clé d'API.
- **Options envisagées** :
  1. **Deux archives** : dépôt public sans texte protégé; copie complète pour l'équipe ou un réviseur.
  2. Le dossier sans `textes/` seulement (prévu par l'architecture) : il contient les résumés.
- **Justification** : choix de Benoit (option 1). À confirmer auprès d'une bibliothécaire pour les droits d'auteur.
- **Conséquences** :
  - un test relit l'archive publique avec la bibliothèque standard seulement et retrouve le décompte fait à la main, ainsi que la chaîne d'empreintes du journal;
  - le même projet donne la même archive (dates des entrées fixées, rendu DOCX reproductible);
  - les citations courtes de l'IA dans les justifications restent dans l'archive publique.
- **Renvois** : EF-PRJ-04, ENF-REP-06, ENF-SEC-01; [03-architecture.md §4](03-architecture.md#4-format-du-dossier-de-projet); demande de fusion benoit-plante/revue-portee#19.

### D-093 — Contenu de la section méthode sur l'IA au tri

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** :
  - la section suit les quatre volets du guide de la CEE (Macura et al., 2025) : description et justification, validation, limites et éthique, financement et conflits d'intérêts; les résultats du tri avec l'IA viennent après la validation;
  - des marqueurs « À compléter » remplacent tout texte rédigé d'avance sur la justification du recours à l'IA, les limites propres à la revue, le financement et les conflits d'intérêts;
  - les limites générées sont factuelles et citent la validation SYNERGY (D-076), avec l'intervalle du plus petit jeu;
  - le coût est ventilé par phase (pilote, tri principal, réévaluations, appels échoués non rattachés), d'après les tarifs datés;
  - toutes les versions exactes du modèle renvoyées par l'API sont listées, avec leur nombre d'appels et les dates du premier et du dernier;
  - l'essai pilote rapporté est celui d'après lequel les seuils ont été fixés (à défaut, le dernier); les autres tours sont seulement comptés.
- **Contexte** : EF-DEC-03 (tri) et l'exigence de RAISE de déclarer l'usage de l'IA de façon complète et transparente.
- **Options envisagées** :
  1. **Faits générés, jugements laissés à l'équipe** : rien n'est affirmé à la place des auteurs.
  2. Texte complet rédigé d'avance : plus rapide, mais attribue aux auteurs des jugements qu'ils n'ont pas portés.
- **Justification** : choix de Benoit (option 1). Selon RAISE, les auteurs restent responsables de ces jugements.
- **Conséquences** : la section dit si la configuration de la revue diffère de celle qui a été évaluée (modèle, version du gabarit d'invite).
- **Renvois** : EF-DEC-03, ENF-LAN-04, D-076; demande de fusion benoit-plante/revue-portee#19.

### D-094 — Terminologie des exports

- **Date** : 2026-10-08
- **Statut** : décidée (choix de Benoit)
- **Décision** : en français, « références » (*records*), « rapports » (*reports*) et « sources de données probantes » (*sources of evidence*, PRISMA-ScR) au lieu d'« études ». Les nombres s'écrivent « n = 1 234 » (espace insécable) en français et « n = 1,234 » en anglais.
- **Contexte** : ENF-LAN-01 demande le français standard du Québec; PRISMA-ScR parle de *sources of evidence*.
- **Options envisagées** :
  1. **« Données probantes »** : terme recommandé au Québec pour *evidence*.
  2. « Éléments probants ».
- **Justification** : choix de Benoit (option 1).
- **Conséquences** : la traduction française du gabarit est celle du projet; elle n'a pas été comparée à une traduction publiée (`verified: false`).
- **Renvois** : ENF-LAN-01, ENF-LAN-04; demande de fusion benoit-plante/revue-portee#19.

### D-095 — Validation de l'outil en fichier de données

- **Date** : 2026-10-08
- **Statut** : proposée
- **Décision** : les résultats publiés du banc SYNERGY (D-076) sont repris dans `resources/reporting/tool_validation.yaml` (date, source, configuration évaluée, résultats par jeu), que la section méthode cite. Le fichier est mis à jour à chaque nouveau banc publié dans `docs/resultats/`.
- **Contexte** : la section méthode doit citer la validation de l'outil, mais `docs/` ne fait pas partie du paquet installé.
- **Options envisagées** :
  1. **Fichier de données daté dans le paquet** : même principe que les autres normes (« les normes sont des données »).
  2. Lire `docs/resultats/` : absent d'une installation.
- **Justification** : principe 4 de l'architecture.
- **Conséquences** : le fichier nomme le modèle évalué comme donnée historique, pas comme réglage; la configuration en usage reste dans `ai_defaults.yaml` et `projet.toml`.
- **Renvois** : EF-DEC-03, ENF-NOR-02, D-076; demande de fusion benoit-plante/revue-portee#19.

### D-096 — Export des références retenues pour le texte intégral

- **Date** : 2026-10-08
- **Statut** : décidée (demandée et approuvée par Benoit)
- **Décision** : les références qui restent après dédoublonnage et dont la décision en vigueur est « inclure » ou « incertain » s'exportent en RIS et en CSV (`exports/references-retenues.ris` et `.csv`, commande `retenues`, page « Rapports »). Chaque notice RIS porte le mot-clé `revue-portee: include|uncertain` et une note avec l'identifiant dans le projet, la décision, la version des critères, le PMID et l'identifiant OpenAlex. Ces exports sont destinés à l'équipe et contiennent les résumés, contrairement à l'archive publique (D-092).
- **Contexte** : la V1 s'arrête au tri des titres et résumés; pour l'essai de bout en bout, l'équipe doit poursuivre le texte intégral dans un autre outil (Zotero, EndNote, Covidence, Rayyan) en attendant la V2.
- **Options envisagées** :
  1. **RIS et CSV** : RIS pour les logiciels de gestion bibliographique et les outils de tri; CSV pour un tableur.
  2. Retrouver les références dans l'archive : possible, mais peu pratique (deux fichiers à croiser).
- **Justification** : demande de Benoit.
- **Conséquences** : le RIS est relu par le lecteur RIS du projet dans les tests; l'import dans les outils tiers est à vérifier pendant l'essai de bout en bout.
- **Renvois** : D-079, D-088, D-092; demande de fusion benoit-plante/revue-portee#21.
