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

Les seuils appliqués sont ceux par défaut de `resources/ai_defaults.yaml` (`supervision`), avec la règle EF-SEL-07 : une référence dont un critère d'inclusion est indéterminable, et qu'aucun critère n'écarte, n'est jamais exclue.
