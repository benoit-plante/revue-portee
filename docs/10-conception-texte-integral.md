# 10 — Conception du tri au texte intégral (tranches 2.1 et 2.2)

> **Statut** : proposition du 9 octobre 2026, à trancher par Benoit avant le développement. Elle précède l'étude de validation, dont le protocole ([09](09-protocole-validation.md)) devra être ajusté en conséquence.
> **Exigences** : EF-COL-02 (Unpaywall), EF-SEL-14 (obtention), EF-SEL-15 (texte avec pages), EF-SEL-16 (tri, motifs d'exclusion), EF-DEC-01 (diagramme complet). Feuille de route : tranches 2.1 et 2.2 ([04](04-feuille-de-route.md)).
> **Normes** : RAISE 2 et RAISE 3 ([01](01-etat-de-l-art.md), §5.1; [06](06-liste-raise2.md)).

## 0. Décisions à trancher

| # | Question | Recommandation | Pourquoi |
|---|---|---|---|
| 1 | Mode de tri | **A. Double tri à l'aveugle** : la personne trie chaque texte sans voir l'IA, et la justification de l'IA n'apparaît qu'à la réconciliation | Cohérent avec la V1. La performance de l'IA reste mesurable. RAISE 2 craint qu'une IA vue d'avance rende le travail humain moins exact; RAISE 3 veut une IA qui appuie et double-vérifie, sans remplacer la personne |
| 2 | Motif d'exclusion | **Un motif principal**, le premier critère non satisfait dans l'ordre des critères; les autres critères non satisfaits restent consignés | PRISMA déclare un motif par rapport exclu; l'ordre des critères rend le choix reproductible |
| 3 | Validation dans chaque revue | **Essai pilote obligatoire au texte intégral** avant le premier lot d'IA : 20 textes tirés au hasard, ou tous s'il y en a moins de 40, triés à l'aveugle par la personne et par l'IA; résultats dans la section méthode | RAISE 3 classe le tri par un modèle de langage en « validation dans la revue requise » |
| 4 | Droits de transmission | **Déclaration de la personne** avant le premier envoi de textes au modèle, consignée au journal; seuls le corps du texte et ses annexes sont envoyés, sans la bibliographie | RAISE 3 : le droit de lire un article ne vaut pas droit de le faire traiter par une IA |
| 5 | Sources des textes | OpenAlex (versions en libre accès), puis Unpaywall, puis PubMed Central; **téléversement** des PDF obtenus par l'établissement, un à un ou en lot | RAISE 2 et 3 : ne pas dépendre du libre accès seul (biais FUTON) |
| 6 | Étude de validation | Texte intégral en **objectif secondaire**; protocole gelé après les tranches 2.1 et 2.2 | Le tri au texte intégral doit être évalué à part (RAISE 2) |

## 1. Principes

1. **La personne trie tous les textes.** En V2 comme en V1, l'IA n'exclut jamais seule au texte intégral : elle est second réviseur (principe 1).
2. **Validation dans chaque revue** : le tri des titres et résumés ne dit rien de celui du texte intégral. Chaque revue mesure l'IA sur son propre pilote (RAISE 3).
3. **Chaque affirmation de l'IA est vérifiable** : chaque critère s'appuie sur une citation et un numéro de page, que l'outil vérifie dans le texte (RAISE 2 : le contenu inventé guette même quand l'information est présente).
4. **Les textes protégés ne sortent jamais du projet** : PDF et texte extrait restent dans `textes/`, hors de toute archive (D-092). Leur envoi au modèle est déclaré et consigné.
5. **Ajout seulement** : un document obtenu, une décision ou un motif ne se modifient jamais; on ajoute (D-028).

## 2. Tranche 2.1 : obtenir et convertir les textes

### 2.1.1 Obtention

- **Population** : les références conservées au tri des titres et résumés (inclure ou incertain), c'est-à-dire la case « Rapports recherchés » du diagramme.
- **Sources automatiques, dans l'ordre** :
  1. la version en libre accès connue d'OpenAlex (déjà interrogé à la collecte);
  2. Unpaywall par DOI (exige `CONTACT_EMAIL`);
  3. PubMed Central, pour les articles qui y sont déposés.
  
  Chaque téléchargement consigne l'URL, la licence déclarée, la date et l'empreinte du fichier.
- **Nouvelles sources à signaler** (règle de CLAUDE.md) : Unpaywall (`api.unpaywall.org`, déjà dans la liste réseau) et le service de PubMed Central, dont le domaine reste à confirmer. Les éditeurs eux-mêmes ne sont jamais interrogés.
- **Téléversement** :
  - un PDF à la fois depuis la page d'une référence;
  - ou un **dossier** de PDF, apparié par DOI (lu dans le PDF ou dans le nom du fichier), puis par titre; les fichiers non appariés sont listés.
- **Liste des manquants** : export CSV (référence, DOI, titre, revue) pour récupérer les textes par l'accès de l'établissement.
- **Statuts** :
  - `obtained`;
  - `not_found` (cherché, introuvable pour l'instant);
  - `not_retrievable` (déclaré introuvable par la personne, avec une raison).
  
  Seul `not_retrievable` alimente la case « Rapports non obtenus » du diagramme.
- **Proportion trouvée en libre accès** : calculée et rapportée (critère de la tranche 2.1), et signalée dans la section méthode si les textes viennent surtout du libre accès.

### 2.1.2 Conversion avec les pages

- **PyMuPDF** par défaut (licence AGPL, compatible, D-004), confirmé par un essai comparatif avec pypdf et pdfplumber sur 30 PDF de test, comme le prévoit l'architecture.
- **Correspondance des pages** : le texte est découpé par page, avec son numéro dans le PDF. Le numéro imprimé, s'il diffère, est consigné quand il est détectable.
- **PDF sans texte** (numérisé) : signalé (« reconnaissance de caractères requise ») et laissé à la personne. Pas de reconnaissance de caractères en 2.1.
- **Bibliographie repérée** : la section des références est marquée, pour ne pas l'envoyer au modèle (décision 4).
- **Critère d'acceptation de la feuille de route** : sur 30 PDF de test, le bon numéro de page pour au moins 98 % des citations vérifiées.

### 2.1.3 Données

- La table `fulltext_document` de l'architecture (§5.7), avec en plus la source, l'URL, la licence déclarée et la date d'obtention.
- Un nouveau document pour la même référence (meilleure version, autre source) **s'ajoute** et devient le document en vigueur; l'ancien demeure.
- Journal : `fulltext.obtained`, `fulltext.uploaded`, `fulltext.not_retrievable`, `fulltext.converted`.

## 3. Tranche 2.2 : trier les textes

### 3.1 Déroulement

1. **Tour de tri au texte intégral** (`screening_round`, étape `full_text`) : les références conservées aux titres et résumés dont le texte est obtenu, dans un ordre tiré avec une graine (comme D-083).
2. **Déclaration de transmission** (décision 4), une fois par projet, avant le premier envoi au modèle.
3. **Essai pilote** (décision 3) : tirage avec graine; la personne trie à l'aveugle, l'IA trie; accord, sensibilité et spécificité avec intervalles. Pas d'étalonnage des probabilités, faute de nombre : les seuils par défaut s'appliquent et sont déclarés.
4. **Tri principal** :
   - la personne trie chaque texte à l'aveugle (décision 1), au clavier comme aux titres et résumés;
   - l'IA trie tous les textes par lots (API Batches, D-080), après estimation du coût et sous le plafond du projet.
5. **Réconciliation** des désaccords (conserver contre exclure, D-079), avec la justification de l'IA et ses citations paginées.
6. **Motifs** : toute exclusion humaine porte un motif principal (décision 2) et, au besoin, d'autres critères non satisfaits.

### 3.2 Tâche d'IA `screen_fulltext`

- **Nouveau gabarit d'invite**, version 1, avec son entrée au journal de mise au point (08). Il est mis au point sur des textes qui ne serviront pas à l'évaluer.
- **Entrée** : les critères de la version en vigueur, et le texte découpé par page (« [p. 4] … »), sans la bibliographie.
- **Sortie**, validée par un schéma :
  - pour chaque critère : satisfait, non satisfait ou impossible à déterminer, avec une citation exacte et sa page;
  - une décision, une probabilité d'inclusion, une justification qui nomme les critères décisifs.
- **Valeur de l'IA** : déduite des seuils et de la règle EF-SEL-07, comme aux titres et résumés (D-065, D-068); jamais prise telle quelle du modèle.
- **Vérification des citations** : chaque citation est recherchée mot pour mot **à la page indiquée**, puis ailleurs dans le texte. On consigne trois cas : trouvée à la bonne page, trouvée à une autre page, introuvable. La proportion de chacun est rapportée dans la section méthode, comme aux titres et résumés.
- **Coût** : environ 10 000 à 20 000 jetons par article, soit 1 à 2 cents par article avec le modèle par défaut par lots. Le coût est affiché avant chaque lot.
- **Modèle** : configurable (`resources/ai_defaults.yaml`, `[ia]`); jamais écrit dans le code. Un modèle local (tranche 3.7) évitera tout envoi à l'extérieur.

### 3.3 Diagramme, section méthode, archive

- **Diagramme** :
  - « Rapports évalués pour l'admissibilité » = textes triés;
  - « Rapports exclus (avec motifs) » = nombre par motif principal, avec le libellé du critère;
  - « Sources de données probantes incluses » = rapports inclus, en attendant le regroupement des rapports d'une même étude (tranche 2.3).
  
  Les cases ne sont plus en pointillés.
- **Section méthode** : une partie « texte intégral » :
  - sources des textes et proportion en libre accès;
  - déclaration de transmission;
  - résultats du pilote;
  - désaccords et leur résolution;
  - citations vérifiées;
  - coût.
- **Archive publique** : décisions, motifs et statuts d'obtention, mais jamais les PDF ni le texte extrait.
- **Changements de critères** : l'analyse d'impact et la réévaluation s'étendent au texte intégral avec les mêmes règles (D-081, D-082).

## 4. Conséquences pour l'étude de validation

- **Objectif secondaire** : sensibilité et spécificité de l'IA au texte intégral.
- **Norme de référence** : les études incluses (positifs) et les études exclues au texte intégral (négatifs), quand la revue publie leur liste, ce que font souvent les revues de portée JBI en annexe.
- **Données** : seulement les revues de test dont les textes sont accessibles, en libre accès ou par l'établissement. La transmission au modèle suit la décision 4.
- **Ordre** : tranches 2.1 et 2.2, puis gel du protocole (09), qui recevra une section sur le texte intégral.

## 5. Hors de portée de ces tranches

- Le mode de tri assisté (option B) : à envisager seulement après une évaluation de non-infériorité (RAISE 2), comme mode distinct et encadré.
- La reconnaissance de caractères des PDF numérisés.
- Le regroupement des rapports d'une même étude (tranche 2.3).
- L'extraction des données (V3), qui réutilisera la conversion paginée et la vérification des citations.
