# Résultats de validation

Ce dossier reçoit les rapports produits par les outils de validation (`docs/05-plan-de-validation.md`). Chaque rapport ne contient que des nombres et la configuration utilisée : aucune notice, aucun résumé, aucune réponse brute du modèle.

## Banc SYNERGY (tranche 1.6) — exécuté le 2026-10-08

Configuration par défaut : `screen_reference` v1, Haiku 5.5 (`effort: low`), seuils 0,10 et 0,60, règle EF-SEL-07. Référence : inclusions au texte intégral de chaque revue. Données : notices de SYNERGY 1.0 (titres et résumés OpenAlex); critères reformulés à partir de ceux publiés avec SYNERGY+ 3.0 (`synergy/*.yaml`).

| Jeu | Références | Incluses | Sensibilité (IC 95 %) | Spécificité | Coût pour 1 000 | Rapport |
|---|---|---|---|---|---|---|
| Oud_2018 | 952 | 20 | 95,0 % (76,4 – 99,1) | 78,7 % | 0,36 $ | [rapport](banc-synergy-Oud_2018.md) |
| van_de_Schoot_2018 | 4 544 | 38 | 97,4 % (86,5 – 99,5) | 84,2 % | 0,34 $ | [rapport](banc-synergy-van_de_Schoot_2018.md) |
| van_Dis_2020 | 9 128 | 72 | 97,2 % (90,4 – 99,2) | 80,0 % | 0,46 $ | [rapport](banc-synergy-van_Dis_2020.md) |

**Critère d'acceptation atteint** : sensibilité d'au moins 0,95 sur 3 jeux en psychologie, coût bien sous 5 $ US pour 1 000 références. Coût total des trois exécutions : 6,11 $ US.

Inclusions manquées (4 sur 130) : un programme de 12 semaines alors que le critère en exige 16 (Oud_2018); un échantillon recruté en centres de traitement des brûlés, exclu par le critère « échantillons cliniques » déduit pour van_de_Schoot_2018; deux essais dont le résumé ne décrit qu'un bras non TCC (pharmacothérapie, psychothérapie centrée sur les émotions) pour van_Dis_2020. Dans les quatre cas, l'IA applique les critères écrits; les auteurs les ont appliqués plus largement au texte intégral. Deux réponses sur 14 624 sont restées inutilisables après une nouvelle tentative (aucune ne portait sur une référence incluse) : le modèle omettait parfois un critère d'exclusion quand un critère d'inclusion suffisait à exclure.

### Préparer un jeu

1. Exporter le jeu SYNERGY (licence CC0) en CSV avec au moins les colonnes `title`, `abstract` et `label_included` (1 = inclus au texte intégral, 0 = exclu). Le fichier reste **hors du dépôt**.
2. Écrire les critères du jeu dans un fichier YAML, à partir de la question et des critères publiés de la revue d'origine :

```yaml
review_question: "…"
language: en
criteria:
  - code: P1
    pcc_element: population   # population, concept, context ou other
    kind: inclusion           # inclusion ou exclusion
    text: "…"
    guidance: ""              # facultatif
```

### Lancer

```bash
uv run revue-portee banc-synergy jeu.csv --criteres jeu.yaml --plafond 5 --nom <jeu> --paralleles 8
```

- La commande affiche d'abord le nombre de références et le coût maximal estimé, puis demande confirmation (`--oui` pour s'en passer).
- `--echantillon N --graine S` trie toutes les inclusions et un tirage des exclusions, jusqu'à N références (la sensibilité porte toujours sur toutes les inclusions).
- L'exécution s'arrête avant un appel qui dépasserait `--plafond`, même avec plusieurs appels simultanés (`--paralleles`, de 1 à 16) : le coût estimé de chaque appel est réservé avant l'appel.
- Les réponses brutes vont dans `jeu.brut.jsonl` (ou `--brut`), à garder hors du dépôt. Le rapport `banc-synergy-<jeu>.md` est écrit dans ce dossier (`--sortie` pour en changer).
- `--repetitions N` (de 2 à 5) relance le même échantillon N fois, sous le même plafond pour toutes les exécutions, et écrit `banc-stabilite-<jeu>.md` au lieu du rapport habituel : notices qui gardent la même valeur et la même issue (conserver ou exclure) d'une exécution à l'autre, AC1 de Gwet entre les exécutions, sensibilité et spécificité de chacune (stabilité des réponses, RAISE 2). Réponses brutes : `jeu.brut.1.jsonl`, `jeu.brut.2.jsonl`, etc. Le coût affiché tient compte des N exécutions.

Les seuils appliqués sont ceux par défaut de `resources/ai_defaults.yaml` (`supervision`), avec la règle EF-SEL-07 : une référence dont un critère d'inclusion est indéterminable, et qu'aucun critère n'écarte, n'est jamais exclue.

## Stabilité des réponses de l'IA (Oud_2018) — exécuté le 2026-10-09

Même configuration que le banc (`screen_reference` v1, `claude-haiku-5-5`, effort `low`, seuils 0,10 et 0,60, règle EF-SEL-07). Échantillon de 500 notices d'Oud_2018 : les 20 inclusions et 480 exclusions tirées avec la graine 2026. Les 500 notices ont été triées **trois fois**, chaque fois par de nouveaux appels au modèle. Coût : 0,54 $ US, avec l'accord de Benoit (plafond de 1,20 $ US). Rapport : [banc-stabilite-Oud_2018.md](banc-stabilite-Oud_2018.md).

| Mesure | Résultat |
|---|---|
| Notices décidées aux trois exécutions | 498 sur 500 |
| Même valeur aux trois exécutions | 438 (88,0 %) |
| Même issue (conserver ou exclure) aux trois exécutions | 450 (90,4 %) |
| Notices conservées par certaines exécutions et exclues par d'autres | 48 (9,6 %) |
| AC1 de Gwet entre deux exécutions | 0,888 à 0,909 |
| Sensibilité des trois exécutions | 95,0 %, 100,0 %, 95,0 % |
| Spécificité des trois exécutions | 76,8 %, 76,2 %, 77,7 % |

**Analyse des 48 notices qui basculent**, faite à partir des réponses brutes :
- **Toutes basculent entre « exclure » et « incertain »**, jamais vers « inclure » : 24 sont exclues une fois sur trois, 24 deux fois sur trois.
- Elles se trouvent **près du seuil d'exclusion** (0,10). La probabilité d'inclusion la plus haute donnée par le modèle a une médiane de 0,12 (au plus 0,55), et la plus basse est d'au plus 0,08.
- **Une seule est une inclusion** (sur 20) : la notice manquée au banc, conservée par la 2ᵉ exécution seulement. D'où une sensibilité de 95 % ou de 100 % selon l'exécution.

**Conséquences** :
- En V1, la variabilité ne fait perdre aucune étude, puisque la personne trie toutes les références. Elle peut en revanche changer la file de réconciliation : une notice que la personne conserve forme un désaccord si l'IA l'exclut, pas si elle la juge incertaine.
- Une seule exécution peut varier de quelques points de sensibilité sur un petit jeu. Une **exclusion par l'IA seule** (V2, tranche 2.5) devrait en tenir compte, par exemple en rejouant les notices proches du seuil ou en exigeant plusieurs exécutions concordantes.
- Les résultats du banc SYNERGY (une exécution par jeu) portent cette incertitude de plus, en plus de celle de l'échantillonnage.

## Textes intégraux : obtention et extraction par page (tranche 2.1) — exécuté le 2026-10-09

**Obtention en libre accès** (`textes-libres`) sur un projet d'essai, hors du dépôt : les 912 références d'Oud_2018 (SYNERGY) qui ont un DOI, toutes retenues sans IA. Sans coût.

| Étape | Références |
|---|---|
| Connues d'OpenAlex | 912 |
| Version en libre accès selon OpenAlex | 261 (28,6 %) |
| dont avec un lien PDF (OpenAlex ou Unpaywall) | 166 |
| **PDF obtenus** | **97 (10,6 % des références recherchées)** |

Liens refusés : 56 fois une erreur 403 (surtout Wiley), 17 pages web au lieu d'un PDF, 6 autres erreurs. 96 versions en libre accès n'ont qu'une page web (souvent PubMed Central ou Europe PMC) : un accès à PubMed Central en récupérerait une partie. Le corpus (psychiatrie clinique, revues surtout payantes) explique le taux bas : le téléversement par l'équipe reste la voie principale.

**Extraction par page** (`banc-pages`) sur ces 97 PDF (1 821 pages) : passages de 8 mots tirés avec la graine 2026 dans le texte lu par les deux autres bibliothèques. [Rapport](extraction-pages.md).

| Bibliothèque | Passages | Bonne page | Autre page | Introuvables | Bonne page parmi les passages trouvés |
|---|---|---|---|---|---|
| **PyMuPDF** (par défaut) | 10 779 | 8 089 | 9 | 2 681 | **99,9 %** |
| pypdf | 10 776 | 8 112 | 0 | 2 664 | 100,0 % |
| pdfplumber | 10 779 | 6 064 | 73 | 4 642 | 98,8 % |

**Critère d'acceptation atteint** si l'on compte les citations retrouvées (au moins 30 PDF, bon numéro de page pour au moins 98 % des citations vérifiées) : 99,9 % avec PyMuPDF, choix confirmé. Le quart des passages introuvables ne sont pas des erreurs de page : ils chevauchent deux blocs (colonnes, encadrés, notes) que les bibliothèques lisent dans un ordre différent. Les citations du modèle étant tirées du texte de PyMuPDF lui-même, ce risque devra être mesuré avec elles au tri du texte intégral (tranche 2.2), avec les cas « trouvée ailleurs » et « introuvable » de la vérification des citations.

**Avec la conversion 2** (2026-10-09, texte ombré gardé une fois, texte indéchiffrable signalé) : PyMuPDF trouve la bonne page pour **99,9 %** des passages retrouvés (8 071 sur 8 080; 2 699 introuvables), comme avec la conversion 1. La légère baisse des passages retrouvés (8 089 avant) vient des passages tirés du texte d'autres bibliothèques qui contient encore le texte ombré en double.

### Relancer

```bash
uv run python -I ~/revue-portee-donnees/essai-textes/creer_projet_complet.py   # projet d'essai (hors du dépôt)
uv run revue-portee textes-libres ~/revue-portee-donnees/essai-textes/essai-complet.revue   # réseau : OpenAlex, Unpaywall
uv run revue-portee banc-pages ~/revue-portee-donnees/essai-textes/essai-complet.revue/textes   # local
```

## Essai réel du tri au texte intégral (`screen_fulltext` v1) — exécuté le 2026-10-09

Essai de mise au point sur 10 textes d'Oud_2018 (pas une mesure de performance) : 10 réponses utilisables sur 10, 0,0198 $ US, 24 citations sur 28 trouvées à la page indiquée et aucune à une autre page. Les 4 citations introuvables étaient exactes mais coupées par un PDF qui dessine son texte deux fois; après la conversion 2, 27 sur 28 sont trouvées à la page indiquée, 1 à une autre page (vraie erreur du modèle), aucune introuvable, et un texte indéchiffrable est signalé. Une inclusion de l'IA, étiquetée exclue par SYNERGY, est à vérifier par une personne. [Rapport](essai-screen-fulltext-v1.md).

## Essai réel du pré-remplissage de la grille (`extract_fields` v1 et v2) — exécuté le 2026-10-09

L'essai porte sur les 11 études en libre accès des 22 incluses par Seunanden et al. 2025 (BMC Public Health), comparées au tableau d'extraction des auteurs, figé avant les appels.

- **v1 (résultat de test)** : 7 études pré-remplies sur 11. Concordance : 37 valeurs sur 49 (75,5 %), ou 35 sur 42 (83,3 %) sans le champ dont la définition est trop vague. 41 citations retrouvées sur 43. Coût : 0,030 $ US.
- **Refus de la v1** : 4 études, parce qu'un choix unique était rangé parmi les choix multiples.
- **v2, qui corrige ce défaut (résultat de développement)** : 4 études sur 4, concordance de 23 valeurs sur 28. Coût : 0,008 $ US.
- **Les 12 désaccords de la v1** : 4 erreurs de l'IA, 2 erreurs de la référence, 6 écarts de convention.

[Rapport](essai-extract-fields.md).

## Rapports d'une même étude (tranche 2.3) — exécuté le 2026-10-09

Règles qui proposent les paires de rapports d'une même étude (`dedup/reports.py`), mesurées sur des notices PubMed étiquetées par leur numéro ClinicalTrials.gov (champ `DataBankList`, jamais montré aux règles). Métadonnées et résumés seulement, sans texte intégral : dans une revue, les numéros d'essai trouvés dans le texte intégral s'ajoutent.

| Jeu | Rôle | Notices | Études à plusieurs rapports | Paires vraies | Rappel | Précision | Rapport |
|---|---|---|---|---|---|---|---|
| Psychothérapie, 2015-2019 | développement (réglages choisis ici) | 1 798 | 211 | 388 | 96,9 % | 29,5 % | [rapport](etudes-dev-psychotherapie.md) |
| Exercice thérapeutique, 2015-2019 | **test**, mesuré une seule fois | 1 221 | 135 | 304 | **97,7 %** | 37,7 % | [rapport](etudes-test-exercice.md) |

**Critère d'acceptation atteint** : rappel d'au moins 0,95 des regroupements proposés sur un jeu annoté mis de côté. Réglages retenus sur le jeu de développement : au moins 2 auteurs en commun et 3 % de mots en commun, ou 1 auteur et 12 % de mots; titres proches à 0,85; même numéro d'enregistrement toujours proposé, numéros différents jamais. Premiers réglages (2 auteurs et 15 % de mots, titres à 0,60) : rappel 68,0 % sur le développement, d'où leur révision. La précision mesure la charge de travail : chaque paire proposée est examinée par l'IA, puis décidée par une personne.

### Relancer

```bash
uv run revue-portee jeu-etudes "psychotherapy[mh] AND clinicaltrials.gov[si] AND 2015:2019[dp]" --sortie ~/revue-portee-donnees/etudes/dev-psychotherapie.csv   # réseau : PubMed
uv run revue-portee banc-etudes ~/revue-portee-donnees/etudes/dev-psychotherapie.csv --role développement   # local
```

## Test du dédoublonnage sur des données mises de côté (ASySD) — exécuté le 2026-10-08

Règles de dédoublonnage version 1 (D-062), seuils par défaut : examen à partir de 0,75, regroupement automatique à partir de 0,93. Les règles ont été mises au point sur le jeu annoté de la tranche 1.5 (D-060). Les jeux ci-dessous **n'ont jamais servi** à les construire ni à les ajuster, et les règles n'ont pas été modifiées après cette exécution : ce sont des **résultats de test** au sens de RAISE 2 (liste RAISE 2, point 2.10).

Données : les cinq jeux d'évaluation d'ASySD (Hair et al., *BMC Biology* 2023, doi:10.1186/s12915-023-01686-z), recherches biomédicales dédoublonnées par des personnes; [OSF 2b8uq](https://osf.io/2b8uq/), licence CC BY 4.0. Les fichiers restent **hors du dépôt** (ils contiennent des résumés). Les décisions de la personne sur les paires qui lui sont laissées sont simulées par l'annotation, comme pour le jeu de la tranche 1.5. Aucun appel à un modèle : les règles sont écrites à la main.

| Jeu | Notices | Paires annotées | Rappel | Précision | Regroupées automatiquement (dont erronées) | Laissées à une personne | Rapport |
|---|---|---|---|---|---|---|---|
| Diabetes | 1 845 | 2 555 | 0,998 | 0,994 | 2 410 (4) | 628 | [rapport](dedoublonnage-asysd-Diabetes.md) |
| NeuroImaging | 3 438 | 1 812 | 0,999 | 0,997 | 1 770 (3) | 90 | [rapport](dedoublonnage-asysd-NeuroImaging.md) |
| Cardiac | 8 948 | 3 822 | 0,999 | 0,998 | 3 408 (6) | 1 086 | [rapport](dedoublonnage-asysd-Cardiac.md) |
| SRSR | 53 001 | 22 700 | 1,000 | 0,997 | 21 640 (40) | 2 592 | [rapport](dedoublonnage-asysd-SRSR.md) |
| Depression | 79 880 | 15 202 | 1,000 | 0,998 | 12 322 (33) | 3 595 | [rapport](dedoublonnage-asysd-Depression.md) |
| **Total** | **147 112** | **46 091** | **0,999** | **0,997** | **41 550 (86)** | **7 991** | |

Totaux calculés à la main à partir des rapports : 46 067 paires justes sur 46 091 annotées (rappel), et sur 46 207 regroupées (précision).

**Cibles atteintes** sur les cinq jeux : rappel d'au moins 0,98 et précision d'au moins 0,99.

**À examiner** :
- **86 paires regroupées automatiquement** (0,21 %) sont des notices distinctes selon l'annotation d'ASySD. Elles n'ont pas été examinées une à une. Certaines peuvent venir d'une définition du doublon différente de la nôtre (D-060 : versions d'un même travail, correctifs); d'autres sont de vraies erreurs.
- La **charge humaine** varie beaucoup : de 90 paires à examiner pour 3 438 notices (NeuroImaging) à 1 086 pour 8 948 (Cardiac).

Ces jeux viennent de la recherche biomédicale, surtout préclinique, et sont en anglais : ils ne disent rien des notices francophones ni de la littérature grise.

### Relancer

```bash
uv run revue-portee banc-doublons ~/revue-portee-donnees/asysd/*_duplicates_labelled.csv --sortie docs/resultats
```

Toute modification des règles incrémente `ALGORITHM_VERSION` (D-062). Comme ces jeux ont été consultés pour la version 1, un nouveau test d'une version future demandera d'autres données mises de côté, si les erreurs de ces jeux servent à la mettre au point.

