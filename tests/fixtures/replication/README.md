# Revue fictive du banc de réplication

Jeu de test de la tranche 3.8 (`revue-portee banc-replication`, D-103, D-104). Tout y est **inventé** : aucune vraie revue n'entre dans le dépôt, qui est public, et les revues de réplication ne doivent jamais y apparaître (docs/11-plan-de-replication.md §5.4).

Ce fichier donne le décompte à la main de chaque nombre du rapport `replication-Fictive_2026_marche_anxiete.md`. Les tests (`tests/unit/replication/test_bench.py`) vérifient que l'outil retrouve exactement ces nombres, dans les deux modes.

## Contenu

```
revue/
├── fiche.yaml                       # id, date de la recherche d'origine (2025-03-01)
├── criteres.yaml                    # question, P1 et C1 (inclusion), O1 (exclusion)
├── grille.yaml                      # 3 champs catégoriels : D1 Devis, D2 Milieu, D3 Suivi (oui/non)
├── recherche/export-base-fictive.ris   # 29 notices inventées
├── GEL.sha256                       # empreintes de criteres.yaml, grille.yaml et du RIS
└── norme/
    ├── incluses.csv                 # 6 études incluses (S6 hors recherche)
    ├── extraction-publiee.csv       # D1, D2, D3 codés dans les catégories de la grille
    └── resultats-publies.yaml       # diagramme publié, répartitions de D1 et de D2 (« Milieu »)
```

Les PDF de `textes/` sont produits par les tests (`tests/replication_support.py`) : de petits textes inventés, sans valeur.

## Les notices (29)

| Clé | Titre (début) | DOI 10.5555/fict.… | Année | Rôle |
|---|---|---|---|---|
| S1 | Brisk walking groups… | 0001 | 2019 | incluse publiée (rapport principal) |
| S1b | Twelve-month follow-up… | 0002 | 2021 | 2ᵉ rapport de S1 (même NCT01234567), absent de `incluses.csv` |
| S2 | Nordic walking… (2 notices) | 0003 | 2020 | incluse publiée; **doublon** (même DOI) |
| S3 | A walking prescription… | 0004 | 2018 | incluse publiée |
| S4 | Neighbourhood strolls… | 0005 | 2017 | incluse publiée, **sans résumé**; sans DOI dans `incluses.csv` (appariée par le titre dans la citation) |
| R10 | Walking football… | 0010 | 2022 | non incluse par les auteurs |
| R11 | Treadmill walking… | 0011 | 2026 | non incluse, publiée après la recherche d'origine |
| R12 | Dog walking… | 0012 | 2019 | non incluse |
| R13 | Garden walking… | 0013 | 2020 | non incluse |
| — | 18 notices hors sujet (19 notices : la première en double, même DOI 0101) | 0101 à 0118 | | non incluses |

S5 (« Aquatic walking classes… », DOI 0006, dans une base interrogée) n'est **pas** dans l'export : perdue à la recherche. S6 (mémoire de maîtrise) est **hors recherche**.

29 notices, 2 doublons groupés automatiquement par le DOI (S2, première notice hors sujet) : **27 références après dédoublonnage**.

## L'IA simulée (FakeProvider, `tests/replication_support.py`)

Coût fictif de 0,01 $ par appel, 0,005 $ dans un lot (facteur 0,5). Seuils par défaut : exclure sous 0,10, inclure à partir de 0,60.

| Étape | Réponses |
|---|---|
| Titres et résumés | probabilité 0,9 : S1, S1b, S2, S3, R10, R11 (inclure); 0,4 : R12 (incertain); R13 : réponse inutilisable deux fois (critère Z9 inconnu); toutes les autres : 0,05 (exclure, P1 non satisfait; S4 : C1 non satisfait) |
| Libre accès | seul S2 est trouvé (OpenAlex) |
| Texte intégral | 0,9 : S1, S1b; 0,85 : R10; 0,8 : S4, S5; 0,4 : R11 (incertain); 0,3 : S6 (incertain); toutes les autres : 0,05 (exclure) |
| Rapports d'une même étude | S1 et S1b : même étude; toute autre paire : différente |
| Extraction (D1, D2, D3) | S1 : Essai randomisé, Communauté, oui · S2 : Quasi expérimental, Résidence, non · S4 : Qualitatif, Communauté, non rapporté · S5 : Essai randomisé, Hôpital, oui · S6 : Qualitatif, Communauté, non · R10 : Quasi expérimental, Résidence, non · R11 : Essai randomisé, Hôpital, non rapporté |
| Synthèse narrative | une phrase par champ |

## Norme de référence

| Étude | D1 | D2 | D3 |
|---|---|---|---|
| S1 | Essai randomisé | Communauté | oui |
| S2 | Quasi expérimental | Résidence | oui |
| S3 | Quasi expérimental | Hôpital | non |
| S4 | Qualitatif | Résidence | non rapporté |
| S5 | Quasi expérimental | Hôpital | oui |
| S6 | Qualitatif | Communauté | non |

Répartitions publiées : D1 sur 6 études (Essai randomisé 1, Quasi expérimental 3, Qualitatif 2); D2 (« Milieu ») : Communauté 2, Résidence 2, Hôpital 2. Diagramme publié : 30 identifiées, 27 après doublons, 27 triées, 8 textes évalués, 7 rapports inclus, 6 études incluses.

## Déroulement de l'essai à sec

1. Première exécution : elle s'arrête à l'étape 4, car le texte de **S3** manque (une seule référence à téléverser).
2. Deuxième exécution avec `--poursuivre` : S3 est déclarée non obtenue, et la suite se déroule sans rappeler l'IA pour le tri des titres et résumés (28 appels avant comme après).

## Décompte à la main — commun aux deux modes

- Références reconstituées : **29**; après dédoublonnage : **27**.
- Études de la norme appariées à une référence collectée : S1, S2 (2 notices, une seule après dédoublonnage), S3 (DOI), S4 (titre dans la citation) → **4**; sans référence appariée : S5, S6 → **2**.
- Retrouvabilité : **4/6** (66,7 %); parmi les 5 études d'une base interrogée : **4/5** (80,0 %).

## Mode en chaîne

- **Tri des titres et résumés** : 27 références; 26 décisions de l'IA + R13 conservée faute de réponse utilisable → **27** triées; exclues : 18 hors sujet + S4 = **19/27** (70,4 %); incertaine : **1** (R12). Rappel par rapport à la revue publiée : S1, S2, S3 conservées sur S1 à S4 collectées → **3/4** (75 %).
- **Obtention** : cherchées 8 (S1, S1b, S2, S3, R10, R11, R12, R13); libre accès **1** (S2); téléversées **6**; non obtenue **1** (S3).
- **Texte intégral** : **7** textes; conservés S1, S1b, R10, R11 → **4**, dont incertain **1** (R11). Rappel : études publiées dont le texte est obtenu S1, S2 → conservée S1 → **1/2**.
- **Rapports** : 4 rapports inclus; S1 + S1b = une étude → **3 études** (S1, R10, R11).
- **Extraction** : seule S1 correspond à une étude publiée → 1 comparaison par champ, accord **1/1**; kappa et AC1 indéfinis (une seule catégorie) → « — »; « non rapporté » 0 / 0.
- **Répartition D1** (outil sur 3 études : Essai randomisé 2 (S1, R11), Quasi expérimental 1 (R10), Qualitatif 0) :

  | Catégorie | Publiée | Outil | Écart |
  |---|---|---|---|
  | Essai randomisé | 1/6 = 16,7 % | 2/3 = 66,7 % | 50,0 |
  | Quasi expérimental | 3/6 = 50,0 % | 1/3 = 33,3 % | 16,7 |
  | Qualitatif | 2/6 = 33,3 % | 0 % | 33,3 |

  Moins de 5 points : **0/3**; mode publié {Quasi expérimental}, mode de l'outil {Essai randomisé} → **non**. Rangs (Spearman) : publiée (1, 3, 2), outil (3, 2, 1); covariance des écarts aux moyennes = −1, variances 2 et 2 → **−0,5**.
- **Répartition D2** (outil : Communauté 1, Résidence 1, Hôpital 1 sur 3) : 33,3 % partout de chaque côté → écarts 0 → **3/3** à moins de 5 points; modes identiques (les trois catégories) → **oui**; rangs tous égaux → corrélation **indéfinie** (« — »).
- **Diagramme** (outil / publié) : identifiées 29 / 30 (−1, −3,3 %); après doublons 27 / 27 (0); triées 27 / 27 (0); textes évalués 7 / 8 (−1, −12,5 %); rapports inclus 4 / 7 (−3, −42,9 %); études incluses 3 / 6 (−3, −50,0 %).
- **De bout en bout** : publiées 6, retrouvables 5 (S1 à S5), études de l'outil 3, dont 1 (S1) correspond à une étude publiée.
  - Rappel : **1/6** (16,7 %); sur les retrouvables : **1/5** (20,0 %).
  - Précision : **1/3** (33,3 %).
  - F1 = 2 × (1/3) × (1/6) / (1/3 + 1/6) = **2/9 = 0,222**; sur les retrouvables : 2 × (1/3) × (1/5) / (1/3 + 1/5) = **0,250**.
  - Jaccard = 1 / (6 + 3 − 1) = **0,125**; sur les retrouvables : 1 / (5 + 3 − 1) = **0,143**.
- **Cascade** : S6 hors de toute base, S5 recherche, S4 tri des résumés, S3 obtention, S2 texte intégral → **1 à chaque étape**; S1 retrouvée.
- **Descripteurs** : étude perdue au tri des résumés sans résumé : **1** (S4); premier critère cité pour l'exclure : **C1 : 1**. Inclusions de l'outil absentes de la revue publiée : R10 (2022, dans la période de la recherche, qui finit en 2025) et R11 (2026, après) → **1** et **1**, année inconnue 0.
- **Appels** : titres et résumés 27 + 1 (R13 de nouveau) = **28** (2 réponses inutilisables); texte intégral **7**; paire de rapports **1**; extraction **3**; synthèse narrative **3** (D1, D2, D3) → **42** appels. Coût : 28 × 0,005 + 7 × 0,005 + 1 × 0,01 + 3 × 0,01 + 3 × 0,01 = **0,245 $**. Conservées faute de réponse utilisable : **1**.

## Mode par étape

Le tri des titres et résumés n'est pas rejoué : il est le même dans les deux modes (docs/11 §3) et payé une fois, en chaîne. Les 6 études publiées sont importées (provenance `reference_standard`), avec les champs de leur notice collectée (S1 à S4) ou de `incluses.csv` (S5, S6).

- **Obtention** : cherchées **6**; libre accès **1** (S2); téléversées **4** (S1, S4, S5 par le DOI du nom de fichier, S6 par sa citation dans le texte); non obtenue **1** (S3).
- **Texte intégral** : **5** textes; conservés S1, S4, S5, S6 → **4**, dont incertain **1** (S6). Rappel par rapport à la revue publiée : **4/5** (80 %).
- **Rapports** : chaque étape reçoit les études publiées; aucune paire proposée → **5** rapports, **5** études.
- **Extraction** (5 études comparées; S3 sans texte) :

  | Champ | Paires (publiée, outil) | Accord | Kappa | AC1 |
  |---|---|---|---|---|
  | D1 | S1 (ER, ER), S2 (QE, QE), S4 (Q, Q), S5 (QE, ER), S6 (Q, Q) | 4/5 | 0,706 | 0,701 |
  | D2 | S1 (C, C), S2 (R, R), S4 (R, C), S5 (H, H), S6 (C, C) | 4/5 | 0,688 | 0,710 |
  | D3 | S1 (oui, oui), S2 (oui, non), S4 (∅, ∅), S5 (oui, oui), S6 (non, non) | 4/5 | 0,688 | 0,710 |

  - D1 : parts publiées ER 1/5, QE 2/5, Q 2/5; outil ER 2/5, QE 1/5, Q 2/5. Kappa : accord attendu = 0,2 × 0,4 + 0,4 × 0,2 + 0,4 × 0,4 = 0,32; (0,8 − 0,32) / (1 − 0,32) = 0,48 / 0,68 = **0,70588**. AC1 : π = 0,3, 0,3, 0,4; Σ π(1 − π) = 0,66; ÷ (3 − 1) = 0,33; (0,8 − 0,33) / 0,67 = **0,70149**.
  - D2 : publiées C 2/5, R 2/5, H 1/5; outil C 3/5, R 1/5, H 1/5. Kappa : attendu 0,24 + 0,08 + 0,04 = 0,36; 0,44 / 0,64 = **0,6875**. AC1 : π = 0,5, 0,3, 0,2; Σ = 0,62; ÷ 2 = 0,31; 0,49 / 0,69 = **0,71014**.
  - D3 (« non rapporté », ∅, est une catégorie) : publiées oui 3/5, non 1/5, ∅ 1/5; outil oui 2/5, non 2/5, ∅ 1/5. Mêmes calculs que D2 → **0,6875** et **0,71014**; « non rapporté » **1 / 1**.
- **Répartition D1** (outil sur 5 études : Essai randomisé 2, Quasi expérimental 1, Qualitatif 2 → 40 %, 20 %, 40 %) : écarts 23,3, 30,0, 6,7 → **0/3** à moins de 5 points; modes {Quasi expérimental} et {Essai randomisé, Qualitatif} → **non**. Rangs : publiée (1, 3, 2), outil (2,5, 1, 2,5); covariance −1,5, variances 2 et 1,5 → −1,5 / √3 = **−0,866**.
- **Répartition D2** (outil : Communauté 3, Résidence 1, Hôpital 1 sur 5 → 60 %, 20 %, 20 %) : écarts 26,7, 13,3, 13,3 → **0/3**; modes {les trois} et {Communauté} → **non**; rangs publiés tous égaux → corrélation **indéfinie**.
- **Appels** : texte intégral **5**, extraction **5**, synthèse narrative **3** → **13** appels; coût 5 × 0,005 + 5 × 0,01 + 3 × 0,01 = **0,105 $**.

## Plafond

Avec un plafond de 0,10 $, le premier lot de tri ne peut pas tout envoyer : 0,10 / 0,005 = **20** références partent, puis le lot s'arrête avant l'appel suivant (« plafond atteint »), sans rien perdre : les 20 décisions sont enregistrées et la dépense est de **0,10 $**. Relancée avec un plafond plus élevé, la commande envoie les 7 autres références et la seconde tentative pour R13 : **28** appels de tri en tout, comme sans plafond.
