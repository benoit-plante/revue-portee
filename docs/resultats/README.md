# Résultats de validation

Ce dossier reçoit les rapports produits par les outils de validation (`docs/05-plan-de-validation.md`). Chaque rapport ne contient que des nombres et la configuration utilisée : aucune notice, aucun résumé, aucune réponse brute du modèle.

## Banc SYNERGY (tranche 1.6) — **à exécuter**

Le banc est outillé, mais il n'a pas encore été lancé : il appelle le modèle configuré pour `screen_reference` (`api.anthropic.com`, absent de la liste réseau de l'environnement infonuagique), il coûte et il exige l'accord de Benoit. Critère d'acceptation : sensibilité d'au moins 0,95 sur au moins 3 jeux SYNERGY en psychologie, et coût d'au plus 5 USD pour 1 000 références.

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
uv run revue-portee banc-synergy jeu.csv --criteres jeu.yaml --plafond 5 --nom <jeu>
```

- La commande affiche d'abord le nombre de références et le coût maximal estimé, puis demande confirmation (`--oui` pour s'en passer).
- `--echantillon N --graine S` trie toutes les inclusions et un tirage des exclusions, jusqu'à N références (la sensibilité porte toujours sur toutes les inclusions).
- L'exécution s'arrête avant un appel qui dépasserait `--plafond`.
- Les réponses brutes vont dans `jeu.brut.jsonl` (ou `--brut`), à garder hors du dépôt. Le rapport `banc-synergy-<jeu>.md` est écrit dans ce dossier (`--sortie` pour en changer).

Les seuils appliqués sont ceux par défaut de `resources/ai_defaults.yaml` (`supervision`), avec la règle EF-SEL-07 : une référence dont un critère d'inclusion est indéterminable, et qu'aucun critère n'écarte, n'est jamais exclue.
