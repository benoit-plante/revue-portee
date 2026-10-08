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

