# Jeu de démonstration

Petit projet de revue fictif, construit par `tests/demo.py` et réutilisé par les tests de bout en bout. Il part des 9 notices fictives du dédoublonnage (`tests/fixtures/dedup/demo-*.ris`) et va jusqu'à la fin du tri des titres et résumés, avec une réconciliation et un changement de critère réévalué.

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

**Changement de critère** (version 1 → 2, élargissement de P1) : références exclues qui citent P1 = instabilité résidentielle et jardins communautaires, soit **2 réévaluées**. L'IA garderait désormais l'instabilité résidentielle (la personne confirme : inclure) et exclut toujours les jardins (pas de vérification). Décisions changées : **0** de « conserver » à « exclure », **1** d'« exclure » à « conserver ».

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
| Désaccords | 1, réconcilié |
