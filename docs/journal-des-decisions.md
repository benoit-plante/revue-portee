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
- **Statut** : décidée; complétée par D-020 (nom de la variable de la clé Anthropic) et D-021 (clé OpenAlex facultative)
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
