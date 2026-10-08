# 07 — Fiche de l'outil : le réviseur IA du tri des titres et résumés

> **Statut** : version du 8 octobre 2026, pour revue-portee **0.1.0.dev0** (V1). À mettre à jour à chaque nouvelle version du gabarit d'invite, du modèle par défaut ou des seuils, et à chaque nouveau résultat publié dans [resultats/](resultats/README.md).
> **Cadre** : éléments de déclaration de RAISE 2 v4, §4 (cadre adapté de Kolbinger et al.); voir [06-liste-raise2.md](06-liste-raise2.md), partie 5.
> **Vocabulaire** (RAISE 2) : *test* = mesure sur des données mises de côté; *évaluation* = aptitude à un usage précis; *validation* = toujours qualifiée. Les résultats ci-dessous sont des **résultats de développement** (D-097).

## Introduction

### Outils existants

Plusieurs plateformes commerciales proposent un tri assisté par l'IA, parfois avec exclusion automatique, mais divulguent rarement le modèle et sa version ([01-etat-de-l-art.md](01-etat-de-l-art.md)). revue-portee vise l'inverse : un outil libre, centré sur les revues de portée JBI, où chaque décision de l'IA est traçable et où l'IA ne remplace jamais la personne.

### L'outil

| Élément | Description |
|---|---|
| Nom et version | revue-portee 0.1.0.dev0; tâche `screen_reference`, gabarit d'invite version 1 |
| Développeur | Benoit Plante, Canada (Québec); projet personnel |
| Accès | Code public : [github.com/benoit-plante/revue-portee](https://github.com/benoit-plante/revue-portee), licence AGPL-3.0-or-later. Installation et commandes : [README](../README.md). Aucun guide d'utilisation détaillé ni soutien organisé à ce jour |
| Étape visée | Tri des titres et résumés d'une revue de portée (EF-SEL-01 à 12) |
| Remplace ou complète | **Complète** : l'IA tient le rôle du second réviseur indépendant, à côté d'une personne qui trie elle-même toutes les références |
| Fonctionnement | Un appel au modèle par référence, avec le titre, le résumé et les critères versionnés du projet. Pour chaque critère, le modèle rend une évaluation (satisfait, non satisfait, impossible à déterminer) et la citation exacte qui l'appuie, puis une décision, une probabilité d'inclusion et une justification qui nomme les critères décisifs. La sortie est validée par un schéma. La valeur retenue pour l'IA est **déduite** de la probabilité et des seuils, puis de la règle EF-SEL-07 (jamais d'exclusion si un critère d'inclusion est indéterminable et qu'aucun critère n'écarte la référence), et non reprise telle quelle du modèle (D-065, D-068) |
| Supervision humaine | La personne trie toutes les références **sans voir** la décision de l'IA (D-071). Quand l'une conserve une référence (inclure ou incertain) et l'autre l'exclut, la personne réconcilie en voyant la justification de l'IA (D-079). **L'IA n'exclut jamais une référence seule** en V1 (principe 1, D-014). Un essai pilote à l'aveugle précède le tri : accord, sensibilité, étalonnage et seuils fixés par la personne avec une justification (EF-SEL-01 à 05). L'interface signale que le réviseur IA est en cours d'évaluation (D-097) |

### Objectif des évaluations

Mesurer la **sensibilité** du réviseur IA (les références pertinentes sont-elles conservées?), au seuil par défaut, ainsi que sa spécificité et son coût.

## Méthode

| Élément | Description |
|---|---|
| Devis | Rétrospectif, de type précision diagnostique : l'outil trie des références déjà jugées, et ses décisions sont comparées aux jugements publiés. Exécuté le 2026-10-08 par le développeur (D-074 à D-076) |
| Contexte | Psychologie clinique chez l'humain, revues **systématiques**, notices en anglais. L'usage visé (revues de portée, littérature francophone) n'est pas encore couvert |
| Sources des données | SYNERGY 1.0 (licence CC0) : titres et résumés OpenAlex de trois revues, Oud_2018 (952 notices, 20 incluses), van_de_Schoot_2018 (4 544, 38) et van_Dis_2020 (9 128, 72), soit 14 624 notices et 130 inclusions |
| Rôle des données | **Ensemble de développement** ([05-plan-de-validation.md](05-plan-de-validation.md), §5.3), donc ni un test ni une validation. Un ensemble de test distinct, tiré au hasard parmi des revues de portée publiées, est prévu dans l'étude de validation |
| Sélection | Trois jeux de psychologie clinique chez l'humain, retenus par Benoit parmi les jeux SYNERGY en psychologie; écartés : les jeux sur l'animal et un jeu de 46 376 notices (D-075) |
| Prétraitement | Aucun : notices utilisées telles que fournies par SYNERGY 1.0. Les critères ont été **reformulés** à partir de ceux publiés avec SYNERGY+ 3.0 ([resultats/synergy/](resultats/synergy/)); pour van_de_Schoot_2018, seuls les critères de la mise à jour de 2025 étaient publiés |
| Norme de référence | Inclusions **au texte intégral** des revues d'origine, étiquetées par leurs auteurs. Leur qualité n'a pas été évaluée. Elles sous-estiment la sensibilité au tri des titres et résumés : une référence incluse au texte intégral peut être exclue à bon droit sur son seul résumé |
| Modèle | Anthropic `claude-haiku-5-5` (version renvoyée par l'API : `claude-haiku-5-5`), effort `low`, `max_tokens` 8 000, par l'API Messages, un appel à la fois au banc (D-067, D-074); seuils par défaut : exclusion sous 0,10, inclusion à partir de 0,60, sans étalonnage (D-066) |
| Développement de l'outil | Gabarit `screen_reference` v1 ([src/revue_portee/ai/prompts/screen_reference/](../src/revue_portee/ai/prompts/screen_reference/)), écrit à la tranche 1.6 et inchangé depuis le banc. **Les données et les essais qui ont servi à le mettre au point ne sont pas documentés** (liste RAISE 2, point 2.3) |
| Mesures | Sensibilité et spécificité avec intervalles de Wilson à 95 %, matrice de confusion, coût pour 1 000 références; une référence « incertain » compte comme conservée |
| Analyse des erreurs | Chaque inclusion manquée a été examinée par le développeur seul, sans évaluateur indépendant |

## Résultats

| Jeu | Sensibilité (IC à 95 %) | Spécificité (IC à 95 %) | Manquées | Réponses inutilisables | Coût pour 1 000 références |
|---|---|---|---|---|---|
| Oud_2018 | 95,0 % (76,4 – 99,1) | 78,7 % (76,0 – 81,2) | 1 sur 20 | 1 | 0,36 $ US |
| van_de_Schoot_2018 | 97,4 % (86,5 – 99,5) | 84,2 % (83,1 – 85,2) | 1 sur 38 | 0 | 0,34 $ US |
| van_Dis_2020 | 97,2 % (90,4 – 99,2) | 80,0 % (79,2 – 80,9) | 2 sur 72 | 1 | 0,46 $ US |

Détails : [resultats/README.md](resultats/README.md) et les rapports de chaque jeu.

**Erreurs.** Les 4 inclusions manquées tiennent à des critères appliqués plus largement au texte intégral qu'ils ne sont écrits :
- un programme de 12 semaines alors que le critère en exige 16;
- un échantillon recruté en centres de traitement des brûlés, exclu par le critère « échantillons cliniques »;
- deux essais dont le résumé ne décrit qu'un bras non TCC.

Deux réponses sur 14 624 sont restées inutilisables après une nouvelle tentative; aucune ne portait sur une référence incluse.

**Interprétation.** Sur l'ensemble de développement, la sensibilité atteint la cible de 0,95 sur les trois jeux, pour un coût environ dix fois sous la cible de 5 $ US pour 1 000 références (D-015). L'intervalle d'Oud_2018, avec 20 inclusions seulement, est large (76,4 à 99,1 %). Ces résultats justifient de passer à une évaluation sur des données mises de côté; ils ne suffisent pas à recommander un usage autre que celui de la V1, où la personne trie tout.

## Discussion

### Forces et limites

- **Forces** : traçabilité complète (modèle, version exacte, gabarit et version, paramètres, réponse brute, citation vérifiée dans le texte); supervision humaine complète; code, gabarits et critères publics; coût faible.
- **Limites** :
  - résultats de développement seulement, sur trois revues systématiques en psychologie clinique, en anglais;
  - aucune mesure sur des revues de portée, ni sur des références en français;
  - stabilité des réponses entre exécutions non mesurée;
  - contamination possible : ces revues publiées peuvent figurer dans les données d'entraînement du modèle;
  - norme de référence au texte intégral, qui ne correspond pas exactement au tri des titres et résumés;
  - le modèle est un service tiers dont le comportement peut changer d'une version à l'autre.

### Biais

- **Langue** : les grands modèles de langage sont surtout entraînés en anglais. La langue de chaque référence est détectée et consignée (D-073), mais la performance en français n'est pas mesurée.
- **Couverture des sources** : OpenAlex et PubMed couvrent mal la littérature grise et une partie de la littérature non anglophone. L'import RIS permet d'ajouter les bases sous abonnement (EF-COL-03); d'autres sources francophones sont prévues en V2 (tranche 2.7).
- **Biais de publication** : l'outil ne classe jamais les références par nombre de citations.
- **Atténuation** : la personne trie toutes les références, et un essai pilote sur les références du projet mesure la sensibilité dans son propre contexte avant le tri.

### Valeur pratique et coût

En V1, l'IA ne réduit pas le nombre de références que la personne trie : elle **remplace le second réviseur humain** d'un double tri. Coût mesuré au banc : 0,34 à 0,46 $ US pour 1 000 références, par appels individuels; le tri principal passe par l'API Batches, facturée à moitié prix (D-080). Coûts d'usage : une clé d'API Anthropic et un budget de projet, avec plafond par lot (D-069). La priorisation par probabilité d'inclusion est facultative et n'entraîne aucun arrêt anticipé.

### Conséquences pour l'usage

Le risque principal n'est pas l'exclusion d'une étude par l'IA, puisqu'elle n'exclut jamais seule. C'est l'influence de la justification de l'IA sur la personne au moment de réconcilier un désaccord (ancrage). La personne voit la justification seulement à ce moment, après avoir décidé à l'aveugle.

La section méthode générée par l'outil (D-093) rapporte, pour chaque revue :
- les versions exactes du modèle;
- les désaccords et leur résolution;
- les réévaluations;
- le coût;
- le caractère de développement des résultats ci-dessus.

## Autres informations

| Élément | Description |
|---|---|
| Éthique | Aucune donnée de participants : seulement de la littérature publiée (principe 5). Les titres et résumés sont transmis à l'API d'Anthropic; aucun secret ni donnée personnelle n'est écrit dans le dossier du projet (ENF-SEC-01). Position du développeur sur les grands modèles de langage : à rédiger par Benoit |
| Protocole | Le banc SYNERGY n'a pas fait l'objet d'un protocole public préalable. Le protocole de l'étude de validation est rédigé ([05-plan-de-validation.md](05-plan-de-validation.md)); son préenregistrement OSF est à faire avant le tirage de l'ensemble de test |
| Soutien | Projet personnel, sans financement déclaré à ce jour (à confirmer par Benoit); coût du banc : 6,11 $ US d'appels au modèle |
| Intérêts | Outil non commercial et libre, sans revenu tiré de son usage. Le développeur est aussi l'évaluateur des résultats ci-dessus : l'étude de validation prévoit un préenregistrement, le gel de l'outil avant le test et au moins un évaluateur indépendant pour l'analyse des erreurs (05, §10) |
| Disponibilité | Publics : code, gabarits d'invite, critères du banc, rapports chiffrés, jeux SYNERGY (CC0). Non publiés : les réponses brutes du modèle et les décisions par notice du banc, gardées hors du dépôt parce qu'elles citent des résumés (D-074); la publication des identifiants et des décisions, sans texte protégé, est prévue (05, §11) |
| Reproductibilité | `revue-portee banc-synergy` relance le banc avec les mêmes CSV et critères, sous un plafond de coût. Les décisions peuvent différer d'une exécution à l'autre, et un modèle retiré par le fournisseur ne pourra plus être appelé : les réponses brutes conservées permettent de reconstituer chaque décision sans rappeler le modèle (ENF-TRA-03) |
| Impact environnemental | Non mesuré. Le modèle par défaut est le plus petit de sa famille, avec un effort de raisonnement faible; la consommation de jetons par référence est consignée à chaque appel et pourrait servir d'indicateur indirect |
