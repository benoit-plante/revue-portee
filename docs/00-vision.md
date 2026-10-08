# 00 — Vision du projet

> **Statut** : version de travail du 7 octobre 2026. Document de cadrage rédigé avant toute ligne de code.
> **Lire ensuite** : [01-etat-de-l-art.md](01-etat-de-l-art.md) pour le contexte, [02-exigences.md](02-exigences.md) pour le détail de ce qui doit être construit.

## 1. En une phrase

**revue-portee** est un logiciel libre qui accompagne une équipe de recherche à travers toutes les étapes d'une revue de portée (*scoping review*) selon la méthode JBI et la norme de déclaration PRISMA-ScR, en utilisant l'IA comme assistant traçable — jamais comme décideur caché.

## 2. Le problème

### 2.1 La revue de portée est lourde et itérative

Une revue de portée en psychologie, en sciences sociales ou en santé mobilise typiquement une équipe pendant 6 à 18 mois. Les étapes les plus coûteuses sont :

- **la construction des stratégies de recherche** : traduire une question PCC (Population, Concept, Contexte) en requêtes pour plusieurs bases dont les syntaxes et les vocabulaires contrôlés diffèrent (MeSH pour PubMed, Thesaurus of Psychological Index Terms pour PsycINFO, aucun vocabulaire contrôlé pour OpenAlex);
- **la sélection** : des milliers de titres et résumés à trier, idéalement par deux réviseurs indépendants, puis des centaines de textes complets;
- **l'extraction (« charting »)** : remplir une grille pour chaque étude retenue, avec un retour constant au texte.

Contrairement à la revue systématique, la revue de portée est **itérative par conception** : le manuel JBI admet que les critères d'inclusion et la grille d'extraction soient précisés en cours de route, à condition que ces changements soient documentés et justifiés. Dans la pratique, ces ajustements se font dans des courriels, des tableurs et des versions de fichiers Word; la traçabilité se perd et la section méthode devient difficile à rédiger honnêtement.

### 2.2 Les outils actuels couvrent mal ce besoin

L'état de l'art ([01-etat-de-l-art.md](01-etat-de-l-art.md)) montre que :

- les outils libres (ASReview, Colandr) couvrent surtout le tri des titres et résumés;
- les plateformes commerciales complètes (Covidence, DistillerSR, EPPI-Reviewer, Nested Knowledge, Laser AI) sont payantes, fermées, et souvent conçues pour la revue systématique biomédicale;
- les outils « natifs IA » (Elicit, DistillerSR Smart Screening) introduisent des exclusions automatiques et **ne divulguent pas toujours le modèle ni sa version**, ce qui empêche de déclarer l'usage de l'IA comme l'exigent les recommandations RAISE et l'énoncé de position conjoint de Cochrane, Campbell, JBI et CEE (2025);
- **aucun outil repéré ne versionne les critères et la grille d'extraction en signalant les références touchées par un changement** — c'est pourtant le cœur méthodologique d'une revue de portée;
- la littérature francophone (Érudit, Cairn, dépôts de thèses québécois et français) est peu ou pas prise en charge.

### 2.3 La pression sur l'usage de l'IA monte

Depuis 2025, les grandes organisations de synthèse des connaissances demandent que tout usage de l'IA qui produit ou suggère un jugement soit déclaré de façon complète et transparente, sous supervision humaine, avec un outil dont la validité a été démontrée pour l'usage visé. Les équipes veulent gagner du temps, mais n'ont ni les moyens de valider les outils elles-mêmes ni de quoi rédiger cette déclaration.

## 3. Publics

| Public | Rôle dans une revue | Ce qu'il attend de l'outil |
|---|---|---|
| **Coordonnateur ou coordonnatrice scientifique** | Organise la revue, forme les assistants, rédige la méthode | Un fil conducteur qui suit JBI, un protocole prêt à déposer, une section méthode générée à partir de ce qui s'est réellement passé |
| **Chercheur ou chercheuse principale** | Définit la question, tranche les cas difficiles | Contrôle sur les critères, vue d'ensemble, confiance dans la rigueur |
| **Assistant ou assistante de recherche, étudiant·e aux cycles supérieurs** | Fait le tri et l'extraction | Une interface claire en français, des suggestions de l'IA qui citent le critère et la page |
| **Bibliothécaire documentaliste** | Construit et valide les stratégies de recherche | Des requêtes lisibles et modifiables, un test de sensibilité avec des articles clés, une déclaration conforme à PRISMA-S |
| **Parties prenantes (cliniciens, organismes, usagers)** | Consultées en fin de revue (étape facultative) | Des synthèses vulgarisées, un moyen simple de commenter |
| **Méthodologues et évaluateurs** | Lisent ou évaluent la revue publiée | Une trace complète et exportable des décisions humaines et de l'IA |

**Contexte principal visé** : équipes universitaires francophones et bilingues (Québec, France, Belgique, Suisse) en psychologie, sciences sociales, sciences de l'éducation et santé. L'outil doit fonctionner aussi pour des revues entièrement anglophones.

## 4. Ce que l'outil fait

L'outil suit les huit étapes d'une revue de portée selon JBI et PRISMA-ScR :

1. **Cadrage** — question selon le cadre PCC, critères d'inclusion et d'exclusion explicites et numérotés, protocole prêt à déposer sur OSF (gabarit *Generalized Systematic Review Registration*).
2. **Stratégies de recherche** — concepts, synonymes, descripteurs, traduction de la requête pour chaque base, test de sensibilité avec des articles clés connus, plan de recherche de littérature grise.
3. **Collecte** — interrogation des sources ouvertes (OpenAlex, PubMed, Crossref, Unpaywall), import RIS des bases sous abonnement (PsycINFO, CINAHL, ERIC, etc.), sources francophones (Érudit, dépôts de thèses), dédoublonnage.
4. **Sélection** — en deux temps (titres et résumés, puis texte complet), précédée d'un **essai pilote** qui sert d'étalonnage; l'IA agit comme **second réviseur** : décision, niveau de confiance, justification qui cite le critère; seuils réglables qui favorisent la sensibilité.
5. **Extraction (« charting »)** — grille définie par l'équipe, pré-remplie par l'IA avec renvoi à la page, validée par un humain.
6. **Synthèse et cartographie** — tableaux de fréquences, cartes de données probantes (*evidence maps*), repérage des lacunes.
7. **Consultation des parties prenantes** (facultative) — synthèses vulgarisées, suivi des commentaires.
8. **Déclaration** — diagramme de flux, liste de contrôle PRISMA-ScR remplie, section méthode qui décrit précisément l'usage de l'IA.

### 4.1 Fonctionnalité distinctive : l'itération traçable

L'outil **versionne les critères d'inclusion et la grille d'extraction**. À chaque modification :

- il qualifie le changement (élargissement, restriction, clarification, ajout ou retrait de champ);
- il calcule **quelles références ou études sont touchées** (par exemple : un élargissement du critère de population touche les références exclues pour ce critère);
- il propose de les **réévaluer**, par un humain, par l'IA ou les deux;
- il **consigne** le changement, sa justification et ses effets dans le journal du projet, qui alimente la section méthode et la liste des écarts au protocole.

### 4.2 Principes non négociables

1. **Aucune exclusion entièrement automatique** sans étalonnage préalable sur un essai pilote et vérification humaine d'un échantillon.
2. **Traçabilité complète** : chaque décision indique qui l'a prise (humain ou IA), le modèle et sa version, la confiance, la justification, la date et la version des critères en vigueur.
3. **Alignement** sur les recommandations RAISE (usage responsable de l'IA en synthèse des connaissances) et sur PRISMA-ScR.
4. **Couche d'abstraction des modèles** : la même tâche peut être confiée à Claude, à un modèle de classification rapide ou à un modèle local.
5. **Aucune donnée de participants** : l'outil ne traite que de la littérature publiée.

## 5. Ce que l'outil ne fait pas

| Hors périmètre | Pourquoi |
|---|---|
| Remplacer les réviseurs humains | Contraire aux principes RAISE et à l'énoncé de position conjoint; l'IA est un second réviseur, pas un juge final |
| Méta-analyse, évaluation du risque de biais, GRADE | Hors de la méthode de la revue de portée (JBI ne recommande pas l'évaluation critique systématique en revue de portée); d'autres outils le font bien |
| Héberger ou traiter des données de participants | Principe non négociable; aucune donnée personnelle de recherche n'entre dans l'outil |
| Contourner les accès payants (récupérer des PDF sans droit) | L'outil n'utilise que des versions en libre accès (Unpaywall) ou des fichiers fournis par l'équipe |
| Interroger directement les bases sous abonnement (PsycINFO, Web of Science, Scopus) | Pas d'API ouverte; l'outil produit la requête traduite et importe le fichier RIS exporté par l'équipe |
| Rédiger l'article à la place des auteurs | L'outil produit des éléments déclaratifs (diagramme, liste PRISMA-ScR, ébauche de section méthode) que l'équipe révise |
| Revue systématique avec méta-analyse « clé en main » | La structure de données le permettrait plus tard, mais ce n'est pas l'objectif |
| Gestionnaire bibliographique général | Zotero et les autres le font; l'outil importe et exporte en RIS |

## 6. Positionnement

### 6.1 Ce qui distingue revue-portee

| Dimension | revue-portee | Situation la plus courante ailleurs |
|---|---|---|
| Méthode | Construit autour de JBI et PRISMA-ScR (revue de portée) | Construit pour la revue systématique d'interventions |
| Itération | Critères et grille versionnés, analyse d'impact, réévaluation | Critères modifiables sans historique exploitable |
| IA | Second réviseur, modèle et version consignés, confiance étalonnée sur un pilote | Modèle souvent non divulgué; exclusions automatiques possibles |
| Déclaration de l'IA | Section méthode générée depuis le journal, alignée sur RAISE | À rédiger à la main |
| Langue | Interface et documentation en français; sources francophones | Interfaces anglophones; sources francophones absentes |
| Licence | Libre (AGPL-3.0-or-later, D-004) | Propriétaire, abonnement par réviseur ou par projet |
| Coûts de l'IA | Estimés avant chaque lot, plafonnés, payés directement au fournisseur avec la clé de l'équipe | Inclus dans des forfaits ou facturés en crédits opaques |

### 6.2 Forme du logiciel

- **Version 1 : application web locale.** Un serveur Python s'exécute sur le poste de l'utilisateur; l'interface, en français, s'ouvre dans le navigateur. Une interface en ligne de commande sert aux traitements en lot et aux tests.
- **Projet de revue = dossier** sur le poste, facile à sauvegarder, à archiver et à déposer sur OSF à la fin.
- **Un réviseur humain + l'IA** en version 1; plusieurs réviseurs humains (accord interjuges, résolution des désaccords) à partir de la version 2. Le modèle de données les prévoit dès le départ.
- **Version hébergée possible plus tard** (multi-utilisateurs), ce qui motive la recommandation de licence AGPL.

### 6.3 Crédibilité scientifique

L'outil ne vaut que s'il est validé. Le [plan de validation](05-plan-de-validation.md) prévoit une étude préenregistrée sur OSF, menée sur des revues de portée publiées dont la liste d'études incluses est connue, et visant une publication méthodologique. Les résultats de cette étude doivent pouvoir être cités dans la section méthode des revues qui utilisent l'outil (exigence RAISE : justifier que l'outil convient à l'usage).

## 7. Indicateurs de réussite à long terme

- Sensibilité du tri assisté par l'IA, mesurée dans l'étude de validation, au moins équivalente à celle d'un second réviseur humain (cible détaillée dans [05-plan-de-validation.md](05-plan-de-validation.md)).
- Réduction mesurable de la charge de travail humaine au tri des titres et résumés, sans perte de sensibilité.
- Au moins une revue de portée réelle menée de bout en bout avec l'outil et publiée, dont la section méthode est issue de l'outil.
- Section méthode générée jugée conforme à RAISE et à PRISMA-ScR par un méthodologue externe.

## 8. Contexte du projet

- Projet personnel de Benoit Plante, réalisé hors de son emploi, avec ses propres ressources.
- Dépôt privé au départ (`benoit-plante/revue-portee` sur GitHub), destiné à devenir public sous licence libre.
- Documentation et interface en français; code, noms de variables et commentaires en anglais.
- Développement dans Claude Code à partir du dépôt, sur le poste de Benoit depuis octobre 2026 (sessions infonuagiques auparavant, toujours possibles); cadrage et documentation dans Cowork. Voir [journal-des-decisions.md](journal-des-decisions.md).
