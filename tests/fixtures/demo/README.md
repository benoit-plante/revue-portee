# Jeu de démonstration

Petit projet de revue fictif, construit par `tests/demo.py` et réutilisé par les tests de bout en bout. Il part des 9 notices fictives du dédoublonnage (`tests/fixtures/dedup/demo-*.ris`) et va jusqu'au tri des textes intégraux, avec une réconciliation et un changement de critère réévalué.

## Critères

| Code | Version 1 | Version 2 |
|---|---|---|
| P1 (inclusion, population) | Personnes aînées (65 ans et plus) | Adultes (18 ans et plus), élargissement |
| C1 (inclusion, concept) | Logement, conditions de vie ou soins | inchangé |
| X1 (exclusion) | Errata et corrections | inchangé |

## Décompte fait à la main

**Repérage** : 9 notices (APA PsycInfo 4, CINAHL 3, PubMed 2), registres 0.

**Dédoublonnage** : l'article sur l'instabilité résidentielle est dans les trois bases (2 doublons), l'étude sur les proches aidants dans deux (1 doublon), et la paire « Loneliness » (premiers auteurs différents) est jugée doublon par la personne (1 doublon). Doublons retirés : **4**; références après dédoublonnage : **5**.

**Tri avec la version 1**

| Référence | Personne | IA | Désaccord | Décision en vigueur |
|---|---|---|---|---|
| Correction (erratum) | exclure (X1) | exclure | non | exclure |
| Instabilité résidentielle, jeunes adultes | exclure (P1) | exclure | non | exclure, puis inclure après réévaluation |
| Proches aidants de personnes aînées | incertain | inclure | non (deux fois « conserver ») | incertain |
| Jardins communautaires, logement social | incertain | exclure | **oui** | exclure (réconciliation, P1) |
| Solitude des aînés après un déménagement | inclure | inclure | non | inclure |

**Citations de l'IA** (version 1, critère P1) : « older adults » pour les proches aidants et pour la solitude des aînés, présent dans leur titre; « older residents » pour les jardins communautaires, absent du titre et du résumé (citation inventée). Citations vérifiées : **3**, retrouvées : **2**.

**Changement de critère** (version 1 → 2, élargissement de P1) : références exclues qui citent P1 = instabilité résidentielle et jardins communautaires, soit **2 réévaluées**. L'IA garderait désormais l'instabilité résidentielle (la personne confirme : inclure) et exclut toujours les jardins (pas de vérification). Décisions changées : **0** de « conserver » à « exclure », **1** d'« exclure » à « conserver ».

**Textes intégraux** (tranche 2.1) : les 3 références retenues sont cherchées en libre accès, dans l'ordre des titres.

| Référence | OpenAlex | Unpaywall (par DOI) | Résultat |
|---|---|---|---|
| Proches aidants | rien | pas de DOI, non interrogé | non trouvé, puis **déclaré introuvable** par la personne (« Revue non accessible par la bibliothèque; auteurs sans réponse. ») |
| Instabilité résidentielle | rien | 2 liens : l'éditeur refuse le premier (erreur 403), le dépôt donne le second | **obtenu** (Unpaywall, cc-by, version acceptée, 2 pages) |
| Solitude des aînés | 1 lien (dépôt) | non interrogé | **obtenu** (OpenAlex, cc-by, 3 pages, bibliographie à la page 3) |

Textes obtenus : **2**, tous deux en libre accès (2 sur 3 recherchés, soit 66,7 %); téléversés : 0; rapports non obtenus : **1**.

**Tri des textes intégraux** (tranche 2.2, critères version 2) : l'essai pilote contient les deux textes obtenus (moins de 40 textes : tous), triés à l'aveugle par la personne et par l'IA, puis le tour principal est en **double tri à l'aveugle** ; les décisions du pilote y comptent (même version des critères).

| Texte | Personne | IA | Citations de l'IA (page donnée → vérification) | Décision en vigueur |
|---|---|---|---|---|
| Instabilité résidentielle | exclure (P1 : le texte révèle des adolescents de 14 à 17 ans) | exclure | P1 « A cohort of 1,200 adolescents aged 14 to 17 » (p. 2 → trouvée à la page) ; C1 « Housing instability and the mental health » (p. 1 → trouvée à la page) | exclure, motif principal P1 |
| Solitude des aînés | inclure | inclure | P1 « We interviewed 24 older adults » (p. 2 → trouvée à la page) ; C1 « living in three residences » (p. 1 → trouvée, mais à la page 2) ; X1 « This is an original research article » (p. 1 → introuvable) | inclure |

Pilote : 2 textes, accord 100 %. Citations du tour principal : **5** vérifiées, **3** à la bonne page, **1** à une autre page, **1** introuvable. Désaccords : 0. Appels à l'IA au texte intégral : 2 au pilote et 2 au tour principal (un appel par texte, 0,002 $ chacun avec le fournisseur factice).

**Résultat**

| Case du diagramme | Nombre |
|---|---|
| Références repérées (bases de données) | 9 (4, 3, 2) |
| Registres | 0 |
| Doublons retirés | 4 |
| Jugées inadmissibles par des outils d'automatisation | 0 |
| Retirées pour d'autres raisons | 0 |
| Références triées | 5 |
| Références exclues | 2 (par une personne 2, par l'IA seule 0) |
| Rapports recherchés pour le texte intégral | 3 |
| Rapports non obtenus | 1 |
| Rapports évalués pour l'admissibilité | 2 |
| Rapports exclus (avec motifs) | 1 (P1 : 1) |
| Sources de données probantes incluses | 1 |
| Désaccords | 1, réconcilié |
