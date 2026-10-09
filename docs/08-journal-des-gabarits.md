# 08 — Journal de mise au point des gabarits d'invite

> **Statut** : ouvert le 8 octobre 2026; les entrées des versions 1 ont été **reconstituées** à partir de l'historique Git, des demandes de fusion et du journal des décisions.
> **Pourquoi** : selon RAISE 2 (§1, encadré 1), concevoir un gabarit d'invite pour une tâche, c'est construire un outil. Sa mise au point doit être décrite en détail, et les données qui servent à la mettre au point ne doivent jamais servir à en mesurer la performance ([06-liste-raise2.md](06-liste-raise2.md), points 2.2, 2.3 et 5.5).
> **Renvois** : gabarits dans `src/revue_portee/ai/prompts/<id>/` ([03-architecture.md](03-architecture.md), §6.4); configuration dans `resources/ai_defaults.yaml`; [07-fiche-outil.md](07-fiche-outil.md).

## Règle pour chaque nouvelle version

Toute modification d'un gabarit incrémente sa version (`meta.yaml`). Elle ajoute aussi ici, **avant la fusion**, une entrée « `<id>` v`<N>` » qui donne :

1. **Motif** : ce qui ne va pas dans la version précédente, avec la preuve (erreurs observées, cas précis).
2. **Données de mise au point** : les notices ou les cas utilisés pour écrire et ajuster le gabarit, désignés précisément (jeu, échantillon, graine). Ces données ne peuvent plus servir à mesurer la performance de cette version.
3. **Versions essayées** : chaque variante essayée, avec le résultat obtenu sur les données de mise au point, y compris les variantes abandonnées.
4. **Données de test** : le jeu mis de côté sur lequel la version retenue est mesurée une seule fois, après le gel du gabarit. S'il n'y en a pas, l'écrire.
5. **Résultats** : renvoi aux rapports de `docs/resultats/`, en disant s'il s'agit de résultats de développement ou de test.
6. **Appels réels** : date, nombre d'appels, coût, et l'accord de Benoit (appels payants).

Un test (`tests/unit/test_prompt_journal.py`) échoue si une version de gabarit n'a pas d'entrée ici.

## Entrées

### screen_reference v1

| Élément | Description |
|---|---|
| Tâche | Tri des titres et résumés par le réviseur IA, une référence par appel (EF-SEL-06, ENF-TRA-01) |
| Date | 2026-10-08, tranche 1.6 (commit 3d4a771, demande de fusion benoit-plante/revue-portee#13) |
| Rédaction | Écrit d'un seul jet à partir des exigences : une évaluation par critère avec la citation exacte qui l'appuie (EF-SEL-06); la règle de ne pas exclure quand un critère d'inclusion est indéterminable et qu'aucun critère n'écarte la référence (EF-SEL-07, D-068); la probabilité d'inclusion (D-065); la justification dans la langue du projet (ENF-LAN-05). Les critères vont dans l'invite système, mise en cache (ENF-COU-04) |
| Données de mise au point | **Aucune.** Le gabarit n'a été ni écrit ni ajusté sur des notices réelles. À sa fusion, il n'avait été exécuté qu'avec le fournisseur factice des tests |
| Versions essayées | Aucune autre |
| Premiers appels réels | 2026-10-08, avec l'accord de Benoit : un essai de 100 références (0,04 $ US; le jeu de l'essai n'est pas consigné), une exécution interrompue (environ 0,002 $ US), puis le banc SYNERGY sur trois jeux complets (14 624 références, 6,11 $ US). **Le gabarit n'a pas été modifié après ces appels** |
| Données de test | Aucune à ce jour. Les jeux SYNERGY forment l'ensemble de développement ([05-plan-de-validation.md](05-plan-de-validation.md), §5.3) : comme le gabarit n'a pas été ajusté sur eux, leurs résultats sont proches d'un test, mais ils servent à choisir les seuils et le modèle par défaut (D-066, D-067, D-076) et restent donc des résultats de développement (D-097) |
| Résultats | [resultats/README.md](resultats/README.md) : sensibilité de 95,0 à 97,4 %, 2 réponses inutilisables sur 14 624 |
| Problème connu | Le modèle omet parfois un critère d'exclusion quand un critère d'inclusion suffit déjà à exclure, d'où les nouvelles tentatives et les 2 échecs. Correction envisagée pour la v2 : exiger l'évaluation de **tous** les critères, y compris d'exclusion, même quand l'exclusion est acquise. Non faite pendant le banc, pour que les trois mesures restent comparables (#14) |

### suggest_pcc v1

| Élément | Description |
|---|---|
| Tâche | Suggestions de reformulation de la question, de questions secondaires et de libellés PCC au cadrage (EF-CAD-02) |
| Date | 2026-10-07, tranche 1.2 (commit d458f29, #4) |
| Rédaction | Écrit d'un seul jet à partir des exigences : rôle consultatif, chaque suggestion acceptée, modifiée ou refusée par une personne (EF-CAD-02, D-042); au plus 3 reformulations, 3 questions secondaires et 2 libellés par élément PCC; justification courte dans la langue du projet |
| Données de mise au point | Aucune |
| Versions essayées | Aucune autre |
| Appels réels | Le test d'intégration `tests/integration/test_claude.py` n'avait pas été lancé à la fusion (#4), et aucun lancement n'est consigné depuis |
| Données de test | Sans objet en V1 : chaque suggestion est jugée par une personne, et aucune performance n'est déclarée |
| Résultats | Aucun |

### qualify_criterion_change v1

| Élément | Description |
|---|---|
| Tâche | Proposition du type d'un changement de critère (élargissement, restriction, clarification), confirmé par une personne avant l'activation de la version (EF-VER-03) |
| Date | 2026-10-07, tranche 1.2 (commit d458f29, #4) |
| Rédaction | Écrit d'un seul jet à partir de la définition des types (EF-VER-03, D-043) : juger l'effet sur l'admissibilité et non la longueur du texte, tenir compte du type du critère (élargir un critère d'exclusion restreint la revue), donner une confiance et une justification courte |
| Données de mise au point | Aucune |
| Versions essayées | Aucune autre |
| Appels réels | Comme pour `suggest_pcc` : test d'intégration non lancé |
| Données de test | Sans objet en V1 : la confirmation humaine est obligatoire, et aucune performance n'est déclarée. Une erreur de type changerait pourtant l'ensemble des références réévaluées (D-081) : une évaluation sur des changements qualifiés à la main serait utile avant de déclarer une performance |
| Résultats | Aucun |

### suggest_terms v1

| Élément | Description |
|---|---|
| Tâche | Suggestions de termes libres et de descripteurs par bloc de concepts (EF-REC-02) |
| Date | 2026-10-07, tranche 1.3 (commit a1a57d7, #6) |
| Rédaction | Écrit d'un seul jet à partir des exigences : rôle consultatif (EF-REC-02), termes dans la syntaxe des blocs du projet (D-049), termes en anglais et dans la langue de la revue, consigne de ne jamais inventer un descripteur MeSH. Chaque descripteur proposé est ensuite vérifié dans MeSH par E-utilities, et un descripteur inexistant est signalé (critère de la tranche 1.3) |
| Données de mise au point | Aucune |
| Versions essayées | Aucune autre |
| Appels réels | Aucun consigné |
| Données de test | Sans objet en V1 : chaque terme est jugé par une personne. La proportion de descripteurs inexistants serait une mesure directe d'hallucination, à rapporter si une performance est un jour déclarée |
| Résultats | Aucun |

### screen_fulltext v1

| Élément | Description |
|---|---|
| Tâche | Tri des textes intégraux par le réviseur IA, un rapport par appel (EF-SEL-16, D-102) |
| Date | 2026-10-09, tranche 2.2 |
| Rédaction | Écrit d'un seul jet à partir de `screen_reference` v1 et de la conception du tri au texte intégral ([10](10-conception-texte-integral.md), §3.2) : même évaluation par critère et même règle EF-SEL-07, mais sur le texte page par page (« [p. N] »), sans la bibliographie; chaque citation donne sa page, que l'outil vérifie (trouvée à la page, ailleurs, introuvable); citation d'au plus 40 mots environ, recopiée telle quelle. Les critères vont dans l'invite système, mise en cache (ENF-COU-04) |
| Données de mise au point | **Désignées le 2026-10-09, avant tout appel réel** : 10 textes tirés avec la graine 2026 parmi les 97 PDF en libre accès d'Oud_2018 (SYNERGY), obtenus à l'essai de la tranche 2.1 ([resultats/README.md](resultats/README.md)); empreintes SHA-256 dans [resultats/essai-screen-fulltext-v1.md](resultats/essai-screen-fulltext-v1.md). Critères : `resultats/synergy/Oud_2018.yaml`. Ces 10 textes ne pourront plus servir à mesurer le tri du texte intégral. Aucun des 97 n'est une étude incluse dans Oud_2018 : l'essai vérifie le fonctionnement (réponses utilisables, citations et pages, coût), pas la sensibilité |
| Versions essayées | Aucune autre |
| Appels réels | 2026-10-09, avec l'accord de Benoit, plafond 1 $ US : voir [resultats/essai-screen-fulltext-v1.md](resultats/essai-screen-fulltext-v1.md) |
| Données de test | Aucune à ce jour. L'objectif secondaire de l'étude de validation (protocole en préparation) le mesurera sur des revues mises de côté; toute mise au point devra se faire sur d'autres textes, désignés ici avant |
| Résultats | Aucun |

### group_reports v1

| Élément | Description |
|---|---|
| Tâche | Deux rapports inclus sont-ils des rapports d'une même étude? Un appel par paire proposée par les règles (EF-SEL-17, tranche 2.3) |
| Date | 2026-10-09, tranche 2.3 |
| Rédaction | Écrit d'un seul jet : verdict (même étude, études différentes, incertain), éléments comparés avec une citation et sa page dans chaque rapport, que l'outil vérifie; mise en garde contre les équipes qui publient plusieurs études. Le modèle reçoit les métadonnées, les numéros d'enregistrement trouvés par l'outil et les premières pages de chaque texte |
| Données de mise au point | **Aucune.** Exécuté seulement avec le fournisseur factice des tests |
| Versions essayées | Aucune autre |
| Appels réels | Aucun |
| Données de test | Aucune à ce jour. Le rappel des regroupements se mesure sur les règles (jeu PubMed par numéro ClinicalTrials.gov); le gabarit ne fait qu'éclairer la décision de la personne |
| Résultats | Aucun |

## Bilan

Aucun des six gabarits n'a fait l'objet d'une mise au point sur des données. C'est une faiblesse au regard de RAISE 2, qui s'attend à une mise au point documentée. C'est aussi une protection : il n'y a pas de fuite entre des données de mise au point et des données de mesure.

Seul `screen_reference` sert à une performance déclarée. Sa v2 devra suivre la règle ci-dessus, avec un jeu de mise au point distinct des jeux SYNERGY et de l'ensemble de test de l'étude de validation (05). Faute de quoi, les résultats SYNERGY ne pourront plus servir de point de comparaison.
