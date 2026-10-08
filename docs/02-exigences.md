# 02 — Exigences

> **Statut** : version de travail du 7 octobre 2026.
> **Prérequis** : [00-vision.md](00-vision.md). **Suite** : [03-architecture.md](03-architecture.md) (comment), [04-feuille-de-route.md](04-feuille-de-route.md) (quand).

## 0. Conventions

- Chaque exigence a un **identifiant stable** (ex. `EF-SEL-04`). Les branches, demandes de fusion, tests et entrées du journal y renvoient. Ne jamais renuméroter : une exigence abandonnée est marquée **(retirée)**.
- **Préfixes** : `EF` = exigence fonctionnelle; `ENF` = exigence non fonctionnelle.
- **Version cible** : V1 à V4, selon la [feuille de route](04-feuille-de-route.md). « V1 (base) » signifie que la structure de données doit exister dès la V1 même si l'interface complète vient plus tard.
- **Doit** = obligatoire; **devrait** = fortement souhaité; **peut** = facultatif.
- **Vocabulaire** :
  - **Référence** : un enregistrement bibliographique (titre, résumé, auteurs, etc.) issu de la collecte.
  - **Étude** : une recherche incluse, qui peut correspondre à plusieurs références (rapports multiples).
  - **Décision** : un jugement d'inclusion ou d'exclusion porté sur une référence, à une étape, par un réviseur (humain ou IA).
  - **Réviseur IA** : une configuration précise (fournisseur, modèle, version, gabarit d'invite, paramètres) qui produit des décisions.
  - **Version des critères** / **version de la grille** : instantané immuable de l'ensemble des critères ou des champs d'extraction.

---

## 1. Exigences fonctionnelles par étape

### 1.1 Projet et journal (transversal)

| ID | Exigence | Version |
|---|---|---|
| EF-PRJ-01 | L'utilisateur doit pouvoir créer un projet de revue (titre, équipe, langue principale, description) qui correspond à un dossier sur son poste. | V1 |
| EF-PRJ-02 | Toute action qui modifie l'état méthodologique du projet (critères, requêtes, collecte, décisions, grille, extractions, paramètres de l'IA) doit être consignée automatiquement dans le **journal du projet**, en ajout seulement (jamais modifié ni effacé). | V1 |
| EF-PRJ-03 | L'utilisateur doit pouvoir ajouter une note libre au journal (ex. compte rendu de réunion d'équipe qui motive un changement). | V1 |
| EF-PRJ-04 | Le projet doit pouvoir être exporté en une **archive autonome** (données + journal + exports lisibles CSV, JSON, RIS, Markdown) déposable sur OSF. | V1 |
| EF-PRJ-05 | L'outil doit gérer plusieurs réviseurs humains identifiés (nom, initiales, rôle). En V1, un seul réviseur humain actif à la fois, mais le modèle de données prévoit plusieurs réviseurs. | V1 (base), V2 |

### 1.2 Étape 1 — Cadrage, critères et protocole

| ID | Exigence | Version |
|---|---|---|
| EF-CAD-01 | L'outil doit guider la formulation de la question selon le cadre **PCC** (Population, Concept, Contexte) et la ou les questions de recherche secondaires. | V1 |
| EF-CAD-02 | L'IA peut proposer des reformulations, des sous-questions et des éléments PCC; chaque proposition doit être acceptée, modifiée ou refusée explicitement par un humain, et ce choix est consigné. | V1 |
| EF-CAD-03 | Les critères d'inclusion et d'exclusion doivent être **explicites, numérotés et rattachés** à un élément PCC ou à une dimension transversale (type de source, langue, période, devis). Chaque critère a un identifiant stable (ex. `P1`, `C2`, `X1`) qui ne change pas d'une version à l'autre. | V1 |
| EF-CAD-04 | Chaque critère doit pouvoir être accompagné d'**exemples et de contre-exemples** (cas limites), qui servent aussi d'exemples dans les invites de l'IA. | V1 |
| EF-CAD-05 | L'ensemble des critères doit être **versionné** (voir 1.9). Toute décision de sélection référence la version en vigueur. | V1 |
| EF-CAD-06 | L'outil doit produire un **protocole** en Markdown et en DOCX, structuré selon les éléments de Peters et al. (2022) et prêt à être reporté dans le gabarit OSF *Generalized Systematic Review Registration*, avec une table de correspondance protocole ↔ éléments OSF. | V1 |
| EF-CAD-07 | Le protocole doit inclure une section sur l'usage prévu de l'IA (tâches, modèles, mode de supervision, plan d'étalonnage), conforme à RAISE. | V1 |
| EF-CAD-08 | L'outil doit enregistrer la date et l'identifiant (DOI OSF) du dépôt du protocole; toute modification ultérieure des critères est alors signalée comme **écart au protocole** à déclarer. | V1 |

### 1.3 Étape 2 — Stratégies de recherche

| ID | Exigence | Version |
|---|---|---|
| EF-REC-01 | L'utilisateur doit pouvoir structurer la stratégie en **blocs de concepts** (en général un par élément PCC), chacun contenant des termes libres, des synonymes, des variantes orthographiques et des troncatures, en anglais et en français. | V1 |
| EF-REC-02 | L'IA peut suggérer des synonymes et des descripteurs (MeSH, Thesaurus APA); chaque suggestion indique sa source et doit être validée par un humain. Les descripteurs suggérés doivent être **vérifiés** contre le vocabulaire officiel quand une API le permet (MeSH via E-utilities), sinon marqués « à vérifier ». | V1 (MeSH), V2 (autres) |
| EF-REC-03 | L'outil doit **traduire** la stratégie dans la syntaxe de chaque base visée : PubMed, OpenAlex (V1); PsycINFO via EBSCOhost et via Ovid, CINAHL, ERIC, Scopus, Web of Science (texte à copier, V1 pour PsycINFO EBSCOhost, V2 pour les autres). | V1, V2 |
| EF-REC-04 | Pour les bases interrogeables (PubMed, OpenAlex), l'outil doit afficher le **nombre de résultats** par bloc et pour la requête complète, avant la collecte. | V1 |
| EF-REC-05 | **Test de sensibilité** : l'équipe fournit une liste d'articles clés (DOI, PMID ou titre); l'outil vérifie lesquels sont retrouvés par chaque requête, indique ceux qui manquent et le bloc responsable, et consigne le taux de rappel. | V1 |
| EF-REC-06 | Chaque version de requête est conservée (texte exact, base, date d'exécution, nombre de résultats) pour la déclaration PRISMA-S. | V1 |
| EF-REC-07 | L'outil doit aider à établir un **plan de recherche de littérature grise** (sites d'organismes, dépôts de thèses, registres, recherche manuelle de références, consultation d'experts), avec suivi de l'exécution et du nombre de références trouvées par source. | V2 |

### 1.4 Étape 3 — Collecte et dédoublonnage

| ID | Exigence | Version |
|---|---|---|
| EF-COL-01 | L'outil doit collecter les références depuis **OpenAlex** et **PubMed** à partir des requêtes validées, avec pagination complète, reprise après interruption et respect des limites de débit. | V1 |
| EF-COL-02 | L'outil doit **enrichir** les références par DOI via **Crossref** (métadonnées manquantes) et **Unpaywall** (lien vers une version en libre accès). | V1 (Crossref), V2 (Unpaywall pour le texte complet) |
| EF-COL-03 | L'outil doit **importer des fichiers RIS** exportés des bases sous abonnement (PsycINFO via EBSCOhost et Ovid en priorité), en tolérant les variantes de fournisseurs et en signalant les enregistrements vides ou mal formés. | V1 |
| EF-COL-04 | L'outil devrait collecter depuis des **sources francophones** : Érudit (OAI-PMH), theses.fr, HAL, dépôts institutionnels québécois (OAI-PMH). Toute nouvelle source exige l'ajout de son domaine à la liste réseau de l'environnement. | V2 |
| EF-COL-05 | Chaque référence doit conserver sa **provenance** : source, requête (et sa version), date de collecte, identifiant d'origine, fichier d'import le cas échéant. Une référence trouvée par plusieurs sources garde toutes ses provenances. | V1 |
| EF-COL-06 | **Dédoublonnage** en deux temps : (1) automatique sur identifiants exacts (DOI normalisé, PMID, identifiant OpenAlex); (2) appariement approximatif (titre normalisé, année, premier auteur, revue, pages) avec score; les paires incertaines sont soumises à un humain. | V1 |
| EF-COL-07 | Le dédoublonnage ne doit **jamais supprimer** : il regroupe les doublons sous une référence principale, réversible, et consigne la règle appliquée. | V1 |
| EF-COL-08 | Les nombres nécessaires au diagramme de flux (références par source, doublons retirés) doivent être calculés automatiquement à partir des données, jamais saisis à la main. | V1 |

### 1.5 Étape 4 — Sélection

#### 1.5.1 Essai pilote (étalonnage)

| ID | Exigence | Version |
|---|---|---|
| EF-SEL-01 | Avant le tri, l'outil doit proposer un **essai pilote** sur un échantillon aléatoire de références (taille réglable; par défaut 100 au tri des titres et résumés), tiré avec une graine consignée. JBI recommande un pilote avec une cible d'accord d'environ 75 % avant de commencer *(à confirmer dans la version 2026 du chapitre 10)*. | V1 |
| EF-SEL-02 | Pendant le pilote, le réviseur humain décide **à l'aveugle** : les décisions de l'IA ne lui sont montrées qu'après sa propre décision. | V1 |
| EF-SEL-03 | À la fin d'un tour de pilote, l'outil doit afficher : accord humain-IA (pourcentage, kappa de Cohen, AC1 de Gwet), sensibilité et spécificité de l'IA par rapport à l'humain, matrice de confusion, désaccords classés par critère cité, et une **courbe seuil → sensibilité / références évitées**. | V1 |
| EF-SEL-04 | Les désaccords du pilote doivent pouvoir mener à une **clarification des critères** (nouvelle version, voir 1.9), puis à un nouveau tour de pilote sur un nouvel échantillon. Chaque tour est consigné. | V1 |
| EF-SEL-05 | Le pilote doit fixer les **seuils** de décision de l'IA (voir EF-SEL-09) sur la base des données observées, avec une préférence explicite pour la sensibilité; le seuil retenu et sa justification sont consignés. | V1 |

#### 1.5.2 Tri des titres et résumés

| ID | Exigence | Version |
|---|---|---|
| EF-SEL-06 | Le réviseur IA doit évaluer chaque référence **critère par critère** (satisfait / non satisfait / impossible à déterminer), en citant le passage du titre ou du résumé qui fonde son évaluation, puis produire une **décision globale** (inclure / exclure / incertain), une **confiance** entre 0 et 1 et une **justification** qui nomme le ou les critères déterminants. | V1 |
| EF-SEL-07 | Une référence pour laquelle un critère est « impossible à déterminer » (résumé absent ou vague) ne doit **pas** être classée « exclure » par l'IA; elle est « incertain » par défaut. | V1 |
| EF-SEL-08 | **Mode V1 — double révision humain + IA** : le réviseur humain trie toutes les références; l'IA trie toutes les références de façon indépendante; les désaccords sont présentés au réviseur humain pour **réconciliation**, avec la justification de l'IA. La décision finale est toujours humaine. | V1 |
| EF-SEL-09 | **Seuils réglables** : un seuil d'exclusion et un seuil d'inclusion sur la confiance; entre les deux, « incertain ». Par défaut, les seuils favorisent la sensibilité (une référence n'est classée « exclure » par l'IA que si la confiance d'exclusion est élevée). Les valeurs par défaut sont documentées et modifiables dans les paramètres du projet. | V1 |
| EF-SEL-10 | L'outil devrait permettre de **prioriser** l'ordre de présentation au réviseur humain selon la probabilité d'inclusion estimée par l'IA, pour repérer tôt les études pertinentes. | V1 |
| EF-SEL-11 | **Exclusion assistée encadrée** (mode « IA seule pour les exclusions à haute confiance ») : uniquement si (a) un pilote est terminé, (b) la sensibilité estimée au seuil choisi atteint la cible fixée par l'équipe (par défaut ≥ 0,95) avec une borne inférieure d'intervalle de confiance consignée, et (c) un **échantillon aléatoire** des exclusions de l'IA (par défaut 10 %, minimum 50) est vérifié par un humain. Si l'échantillon révèle une inclusion manquée au-delà d'une tolérance fixée, le mode est suspendu. L'outil refuse d'activer ce mode tant que ces conditions ne sont pas remplies. | V2 |
| EF-SEL-12 | Chaque décision d'exclusion humaine doit indiquer le ou les critères en cause (choix dans la liste des critères de la version en vigueur). | V1 |
| EF-SEL-13 | L'outil doit gérer plusieurs réviseurs humains (double tri humain, mesure de l'accord interjuges, arbitrage par un troisième réviseur), en plus ou à la place de l'IA. | V2 |

#### 1.5.3 Tri du texte complet

| ID | Exigence | Version |
|---|---|---|
| EF-SEL-14 | L'outil doit gérer l'obtention du texte complet : lien Unpaywall en libre accès, téléversement d'un PDF par l'équipe, statut « introuvable » (déclaré dans le diagramme). | V2 |
| EF-SEL-15 | Le texte complet doit être converti en texte **avec correspondance des pages**, pour permettre les renvois à la page. | V2 |
| EF-SEL-16 | Le tri du texte complet suit les mêmes règles que les titres et résumés (EF-SEL-06 à 13), avec des citations qui renvoient à la page; tout motif d'exclusion à cette étape est déclaré dans le diagramme. | V2 |
| EF-SEL-17 | L'outil doit regrouper les références qui rapportent la **même étude** (rapports multiples), sur proposition de l'IA validée par un humain. | V2 |

### 1.6 Étape 5 — Extraction (« charting »)

| ID | Exigence | Version |
|---|---|---|
| EF-EXT-01 | L'équipe doit pouvoir définir une **grille d'extraction** : champs typés (texte, nombre, choix unique, choix multiple, catégorie hiérarchique, booléen, date), avec définition, consignes et exemples; modèles de départ inspirés de Pollock et al. (2023). | V3 |
| EF-EXT-02 | La grille doit être **versionnée** (voir 1.9). | V3 |
| EF-EXT-03 | L'IA doit **pré-remplir** chaque champ avec la valeur proposée, la **citation exacte** et le **numéro de page**, ou indiquer « non rapporté ». | V3 |
| EF-EXT-04 | Chaque valeur pré-remplie doit être **validée, corrigée ou rejetée** par un humain; aucune valeur de l'IA n'entre dans la synthèse sans validation humaine. | V3 |
| EF-EXT-05 | L'outil doit permettre un **pilote d'extraction** (quelques études extraites par l'humain et l'IA) et en mesurer l'exactitude par champ. | V3 |

### 1.7 Étape 6 — Synthèse et cartographie

| ID | Exigence | Version |
|---|---|---|
| EF-SYN-01 | Tableaux de fréquences et tableaux croisés sur les champs de la grille, exportables (CSV, XLSX, Markdown). | V3 |
| EF-SYN-02 | **Cartes de données probantes** (matrice à deux dimensions avec taille ou couleur selon le nombre d'études), inspirées des cartes Campbell (White et al., 2020); export image et HTML. | V3 |
| EF-SYN-03 | **Repérage des lacunes** : cellules vides ou peu peuplées de la carte, signalées et commentables. | V3 |
| EF-SYN-04 | L'IA peut proposer une synthèse narrative par catégorie, **toujours** rattachée aux études qui la fondent (références cliquables) et révisée par un humain. | V3 |

### 1.8 Étape 7 — Consultation des parties prenantes (facultative)

| ID | Exigence | Version |
|---|---|---|
| EF-CON-01 | L'outil peut produire des **synthèses vulgarisées** des résultats (niveau de langue réglable), révisées par un humain. | V4 |
| EF-CON-02 | L'outil peut **suivre les commentaires** des parties prenantes (qui, quand, sur quoi, suite donnée), en conformité avec Pollock et al. (2022). | V4 |
| EF-CON-03 | Aucune donnée personnelle des parties prenantes au-delà du nom, du rôle et de l'organisation ne doit être conservée. | V4 |

### 1.9 Itération : versionnement et analyse d'impact (fonctionnalité distinctive)

| ID | Exigence | Version |
|---|---|---|
| EF-VER-01 | Toute modification des critères (ajout, retrait, reformulation, ajout d'exemple) crée une **nouvelle version** immuable, avec auteur, date, justification obligatoire et lien éventuel vers une note du journal. | V1 |
| EF-VER-02 | L'outil doit afficher un **différentiel lisible** entre deux versions (critère par critère). | V1 |
| EF-VER-03 | Chaque modification de critère doit être **qualifiée** : *élargissement* (plus inclusif), *restriction* (plus exclusif), *clarification* (sans changement de portée voulu), *ajout*, *retrait*. L'IA peut proposer la qualification; l'humain la confirme. | V1 |
| EF-VER-04 | **Analyse d'impact** : selon la qualification, l'outil calcule les références touchées : élargissement → références **exclues** pour ce critère; restriction → références **incluses** ou incertaines; clarification → références dont la décision cite ce critère (par défaut, à revoir par échantillon); ajout → toutes les références encore à l'étape concernée; retrait → références exclues **uniquement** pour ce critère. | V1 |
| EF-VER-05 | L'outil doit proposer la **réévaluation** des références touchées (par l'humain, par l'IA, ou par l'IA puis vérification humaine des changements de décision) et conserver les anciennes décisions (jamais écrasées). | V1 (IA + humain), V2 (flux complet) |
| EF-VER-06 | Les mêmes mécanismes s'appliquent à la **grille d'extraction** : ajout de champ → toutes les études incluses à compléter; modification de définition → valeurs existantes signalées à revoir; retrait → valeurs archivées. | V3 |
| EF-VER-07 | Chaque version, chaque analyse d'impact et chaque réévaluation alimentent automatiquement la section « écarts au protocole » et la section méthode. | V1 (consignation), V4 (texte généré) |

### 1.10 Étape 8 — Déclaration

| ID | Exigence | Version |
|---|---|---|
| EF-DEC-01 | **Diagramme de flux** conforme au gabarit PRISMA 2020 adapté aux revues de portée, généré à partir des données (jamais saisi à la main), exportable en SVG, PNG et PDF, en français et en anglais. Les éventuelles réévaluations dues aux changements de critères sont visibles dans les nombres. | V1 (bases et registres, SVG seulement, D-087), V2 (autres sources, texte complet, PNG et PDF) |
| EF-DEC-02 | **Liste de contrôle PRISMA-ScR** pré-remplie : pour chaque élément, l'outil propose le texte ou l'emplacement correspondant à partir des données du projet; l'équipe complète. La liste est un fichier de données versionné pour accueillir la mise à jour 2026 de PRISMA-ScR. | V4 |
| EF-DEC-03 | **Section méthode** générée à partir du journal, qui décrit précisément l'usage de l'IA selon RAISE et le gabarit de la CEE (Macura et al., 2025) : outil et version, modèles et versions exactes, tâches, mode de supervision, résultats de l'étalonnage, seuils, proportion des décisions où l'IA est intervenue, désaccords et leur résolution, limites, coûts, conflits d'intérêts. | V1 (tri), V4 (toutes étapes) |
| EF-DEC-04 | **Déclaration de la recherche** conforme à PRISMA-S (requêtes complètes, dates, bases, plateformes, limites appliquées). | V2 |
| EF-DEC-05 | Export du tableau des études incluses avec leurs caractéristiques, et de la liste des exclusions au texte complet avec motifs. | V2 |

---

## 2. Exigences non fonctionnelles

### 2.1 Traçabilité (ENF-TRA)

| ID | Exigence |
|---|---|
| ENF-TRA-01 | Chaque décision (sélection, extraction, dédoublonnage, qualification d'un changement) doit enregistrer : **type de réviseur** (humain ou IA); **identité** (personne, ou fournisseur + modèle + **version exacte renvoyée par l'API**); **confiance**; **justification**; **critères cités**; **date et heure** (UTC, ISO 8601); **version des critères ou de la grille** en vigueur; **étape**; pour l'IA : version du gabarit d'invite, empreinte (hachage) de l'invite rendue, paramètres (température, nombre maximal de jetons, etc.), jetons consommés, coût estimé, identifiant de la réponse brute. |
| ENF-TRA-02 | Les décisions ne sont **jamais modifiées ni supprimées** : une nouvelle décision remplace logiquement la précédente, qui reste consultable. |
| ENF-TRA-03 | La **réponse brute** de chaque appel de modèle doit être conservée dans le projet (compressée), pour vérification ultérieure. |
| ENF-TRA-04 | Pour toute référence, l'outil doit pouvoir afficher **l'historique complet** : provenances, doublons, décisions successives, versions de critères, réévaluations. |
| ENF-TRA-05 | Un test automatisé doit vérifier qu'aucune décision ne peut être enregistrée sans l'ensemble des champs de ENF-TRA-01. |

### 2.2 Reproductibilité (ENF-REP)

| ID | Exigence |
|---|---|
| ENF-REP-01 | Les traitements non IA (traduction des requêtes, dédoublonnage, calcul des nombres du diagramme, tirage des échantillons) doivent être **déterministes** : mêmes entrées et même graine → mêmes sorties. |
| ENF-REP-02 | Les traitements IA doivent être **rejouables** : à partir de la réponse brute conservée, on doit pouvoir reconstituer la décision sans rappeler le modèle. Un nouvel appel au même modèle est consigné comme une **nouvelle** décision. |
| ENF-REP-03 | L'outil doit pouvoir mesurer la **stabilité** d'un réviseur IA (répétition sur un échantillon, accord entre exécutions), et en rendre compte dans la section méthode. |
| ENF-REP-04 | Les gabarits d'invite sont des fichiers versionnés dans le dépôt; leur version figure dans chaque décision. |
| ENF-REP-05 | La version de revue-portee (numéro et empreinte du commit) est consignée dans le journal à chaque ouverture du projet et dans chaque décision. |
| ENF-REP-06 | L'archive du projet (EF-PRJ-04) doit permettre à un tiers de **vérifier** chaque nombre déclaré (diagramme, étalonnage) sans clé d'API. |

### 2.3 Coûts (ENF-COU)

| ID | Exigence |
|---|---|
| ENF-COU-01 | Avant tout lot d'appels à un modèle payant, l'outil doit afficher une **estimation du coût** (jetons × tarif) et demander confirmation. |
| ENF-COU-02 | Le projet doit avoir un **plafond budgétaire** (global et par lot); l'outil s'arrête proprement à l'atteinte du plafond, sans perte de travail. |
| ENF-COU-03 | Le coût réel (jetons, montant estimé) est consigné par décision et totalisé par étape, pour la section méthode. |
| ENF-COU-04 | L'outil devrait utiliser les mécanismes de réduction des coûts du fournisseur quand ils n'altèrent pas la traçabilité (mise en cache des invites, traitement par lots asynchrone). |
| ENF-COU-05 | Les tarifs des modèles sont dans un fichier de configuration daté, modifiable sans changer le code. |
| ENF-COU-06 | La consommation des API de données payantes au-delà d'un seuil gratuit (OpenAlex) doit être suivie et affichée. |
| ENF-COU-07 | **Cible de conception** (D-015) : avec la configuration par défaut, le coût de l'IA pour trier **5 000 titres et résumés** est **≤ 25 $ US** (≤ 5 $ US par 1 000 références), traitement par lots et mise en cache compris. Mesuré au banc d'essai de la tranche 1.6. |

### 2.4 Confidentialité des clés et des données (ENF-SEC)

| ID | Exigence |
|---|---|
| ENF-SEC-01 | Les clés d'API (`REVUE_PORTEE_ANTHROPIC_KEY`, à défaut `ANTHROPIC_API_KEY` (D-020); `OPENALEX_API_KEY`, facultative (D-021); et toute autre clé ajoutée) sont lues **uniquement** depuis les variables d'environnement (ou, sur le poste de l'utilisateur, depuis le trousseau du système en V2). Elles ne sont **jamais** affichées, journalisées, écrites dans un fichier du projet, dans une archive, dans un message d'erreur ou dans une réponse enregistrée pour les tests. |
| ENF-SEC-02 | Le même traitement s'applique à `CONTACT_EMAIL` : utilisé dans les en-têtes et paramètres requis par les API, jamais écrit dans les fichiers du projet ni dans les réponses enregistrées (remplacé par une valeur fictive). |
| ENF-SEC-03 | Un filtre de journalisation doit masquer toute chaîne ressemblant à une clé connue; un test automatisé le vérifie. |
| ENF-SEC-04 | Les réponses enregistrées pour les tests doivent être **nettoyées** (en-têtes d'authentification, paramètres `api_key`, `email`, `mailto`) avant d'être versionnées; un test vérifie qu'aucun fichier de `tests/` ne contient de secret. |
| ENF-SEC-05 | L'outil ne traite **aucune donnée de participants**. L'interface le rappelle à l'import de fichiers, et l'outil refuse les formats qui ne sont pas bibliographiques ou documentaires. |
| ENF-SEC-06 | En V1 (application locale), le serveur n'écoute que sur `127.0.0.1` par défaut. |
| ENF-SEC-07 | Le texte envoyé aux modèles se limite à la littérature publiée et aux critères de l'équipe. L'utilisateur est informé du fournisseur qui reçoit les données. |

### 2.5 Langue (ENF-LAN)

| ID | Exigence |
|---|---|
| ENF-LAN-01 | **Interface et documentation en français** (français standard du Québec, typographie française : espaces insécables avant `:` `;` `?` `!` dans l'interface, guillemets « »). |
| ENF-LAN-02 | **Code, noms de variables, commentaires, messages de commit en anglais.** |
| ENF-LAN-03 | Les chaînes de l'interface sont externalisées (catalogue de traduction) pour permettre une interface anglaise plus tard, sans la livrer en V1. |
| ENF-LAN-04 | Les exports destinés à la publication (diagramme, section méthode, liste PRISMA-ScR, protocole) sont disponibles **en français et en anglais**. |
| ENF-LAN-05 | Les références en français et en anglais (et, au minimum sans erreur, dans d'autres langues) doivent être traitées par le réviseur IA; la langue de chaque référence est détectée et consignée. La justification de l'IA est rédigée dans la langue du projet. |
| ENF-LAN-06 | La performance de l'IA sur les références en français doit être mesurée séparément dans l'étude de validation. |

### 2.6 Conformité aux normes (ENF-NOR)

| ID | Exigence |
|---|---|
| ENF-NOR-01 | **RAISE** : les recommandations de RAISE 2 (construction et évaluation des outils) doivent être transformées en une liste de vérification dans `docs/` et cochées à chaque version majeure. Liste : [06-liste-raise2.md](06-liste-raise2.md) (RAISE 2 v4, cochée pour la V1 le 2026-10-08). |
| ENF-NOR-02 | **Énoncé de position conjoint (2025)** : l'outil doit publier ses données de validation et ses limites connues (voir [05-plan-de-validation.md](05-plan-de-validation.md)). |
| ENF-NOR-03 | **PRISMA-ScR, PRISMA 2020 (diagramme), PRISMA-S** : les listes et gabarits sont des fichiers de données versionnés avec leur source et leur date. |
| ENF-NOR-04 | **JBI** : le vocabulaire et l'ordre des étapes suivent le chapitre 10 du manuel JBI (version 2026). |

### 2.7 Qualité logicielle et tests (ENF-QUA)

| ID | Exigence |
|---|---|
| ENF-QUA-01 | Les tests automatisés **n'appellent jamais les vraies API** : ils utilisent des réponses enregistrées et des modèles factices. |
| ENF-QUA-02 | Des **tests d'intégration**, marqués et exclus par défaut, appellent les vrais services; ils ne sont lancés que volontairement. |
| ENF-QUA-03 | `ruff check`, `ruff format --check`, `mypy` (mode strict, D-022) et `pytest` doivent passer avant toute demande de fusion. |
| ENF-QUA-04 | Couverture de tests : les paquets `domain` (critères, décisions, versionnement, impact), `dedup` (dédoublonnage) et `reporting` (diagramme, protocole, section méthode) doivent chacun atteindre au moins 90 %, branches comprises; `pytest` échoue sinon (D-023). |
| ENF-QUA-05 | Toute fonction qui produit un nombre déclaré (diagramme, accord, sensibilité) a un test sur un cas calculé à la main. |

### 2.8 Performance et utilisabilité (ENF-PER)

| ID | Exigence |
|---|---|
| ENF-PER-01 | Un projet de **50 000 références** doit rester utilisable sur un portable ordinaire (ouverture < 5 s, passage d'une référence à la suivante < 200 ms au tri). |
| ENF-PER-02 | Le tri humain doit pouvoir se faire **entièrement au clavier** (inclure, exclure, incertain, critère, suivant). |
| ENF-PER-03 | L'interface doit respecter les critères WCAG 2.1 niveau AA pour les contrastes et la navigation au clavier. |
| ENF-PER-04 | Les traitements longs (collecte, lots d'IA) s'exécutent en arrière-plan, affichent leur progression et reprennent après interruption. |

### 2.9 Licence et propriété (ENF-LIC)

| ID | Exigence |
|---|---|
| ENF-LIC-01 | Les dépendances doivent avoir une licence compatible avec la licence du projet, **AGPL-3.0-or-later** (D-004). Interdit : dépendances à licence non commerciale ou sans dérivé (ex. CC BY-NC-ND). |
| ENF-LIC-02 | Les gabarits et listes tirés de PRISMA (CC BY 4.0) et de JBI sont cités avec leur source et leur licence. |
