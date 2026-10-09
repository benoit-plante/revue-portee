# Essai réel du gabarit `screen_fulltext` v1 — 2026-10-09

**Nature** : essai de **mise au point** (fonctionnement), pas une mesure de performance. Les 10 textes ci-dessous sont désormais des données de mise au point ([08-journal-des-gabarits.md](../08-journal-des-gabarits.md)) et ne peuvent plus servir à évaluer le tri au texte intégral.

## Configuration

- Textes : 10 tirés avec la graine 2026 parmi les 97 PDF en libre accès d'Oud_2018 (SYNERGY) obtenus à l'essai de la tranche 2.1; texte par page sans la bibliographie (PyMuPDF 1.28.2).
- Critères : `synergy/Oud_2018.yaml` (SYNERGY+), saisis dans un projet d'essai hors du dépôt. Codes attribués par l'outil : P1 (adultes avec TPL), C1 (psychothérapie spécialisée), C2 (exclusion : version incomplète du traitement), X1 (essai randomisé contrôlé, critère « autre » d'inclusion).
- Modèle : `claude-haiku-5-5` (version renvoyée : `claude-haiku-5-5`), `effort: low`, un appel par texte, seuils par défaut (exclure sous 0,10, inclure à partir de 0,60).
- Plafond : 1 $ US, avec l'accord de Benoit. Estimation affichée avant les appels : 0,026 $ US au plus.

## Résultats

| Mesure | Valeur |
|---|---|
| Textes triés | 10 sur 10, aucune réponse inutilisable, aucun échec |
| Coût | 0,0198 $ US (environ 0,2 cent par texte) |
| Jetons | 190 604 en entrée (dont 15 588 lus en cache), 4 201 en sortie; environ 19 000 par texte |
| Durée moyenne d'un appel | 2,9 s |
| Décisions de l'IA | 9 exclusions (probabilités de 0,01 à 0,05), 1 inclusion (0,90) |
| Motifs des exclusions (premier critère décisif) | P1 : 6; C1 : 2; X1 : 2 (dont l'inclusion, qui cite X1 en premier) |
| Citations vérifiées | 28 : **24 à la page indiquée**, 0 à une autre page, 4 introuvables; 12 évaluations sans citation (« indéterminable » surtout) |

Aucun des 97 textes libres n'est une étude incluse dans Oud_2018 selon les étiquettes SYNERGY : l'essai ne mesure pas la sensibilité.

## Constats

1. **L'inclusion à vérifier par une personne.** L'IA inclut un essai randomisé de thérapie comportementale dialectique (12 mois, programme complet) chez des femmes adultes avec un trouble de la personnalité limite, que les étiquettes SYNERGY marquent comme exclu. Ses quatre évaluations reposent sur des passages réels du texte. Soit le rapport a été exclu par la revue pour une raison absente des critères résumés (par exemple un autre rapport de la même étude retenu à sa place), soit l'étiquette est discutable. Ce désaccord est exactement ce que la personne doit trancher, avec le texte sous les yeux.
2. **Les 4 citations « introuvables » sont exactes.** Elles appartiennent toutes à ce même texte : chaque fragment de quatre mots se retrouve dans le texte, mais le PDF contient **chaque ligne en double** (couche de texte « ombrée »), ce qui coupe la citation complète. La vérification signale donc un faux problème. Correction proposée : fusionner les lignes identiques consécutives à la conversion (nouvelle version du convertisseur, avec un test), ce qui donnera aussi au modèle un texte deux fois plus court pour ces PDF.
3. **Les pages sont justes** : aucune citation trouvée ailleurs qu'à la page indiquée.
4. **Coût** : environ 0,2 cent par texte avec le modèle par défaut, bien sous l'estimation de la conception (1 à 2 cents par lots).
5. **Nommage des codes** : l'outil attribue le préfixe X aux critères « autres » d'inclusion; X1 désigne ici le devis (essai randomisé), ce qui peut se confondre avec une exclusion. À revoir dans l'interface des critères (proposition).

## Textes de mise au point (SHA-256)

- `097f8413e65ff3248fa1c8c5871432e1da6e73536794aa0e92b586dafc486ad5`
- `0e17de9cb4d7f58f59305d210438ba186aff5fb143bfc578ab88ce9733ad55a4`
- `290e4917dcd06a8673646990f00a3e59889ccc3f0b7352b871732ae158f7b674`
- `318a9691b3098350d5d4fa4d004c532da4ad04357e46462863ffc26d733b4f49`
- `71c5e1f63ed0c0547f741e5f2110420211014d925cd78f50a3aee4dae66759f0`
- `7353e7c260bf91613dcf78587cb7efd7a8f984ddd4a7daf7d7b6afb908948527`
- `b479a78f1b0d61f1b067495c254546f28761b42c2e3afdcfdf5d5318a142486b`
- `c978274bc1519624758b108cc2ee7e7146ec7e10e4bae9cdbe39b788bd7a33a0`
- `cac7dc7c31367991127ea481b46d9b2d1e209d7883e7d5fe2f57dfa95a3c3fda`
- `d10ed98cfd011db2f8548393a30eb0d850d80303345a2634ec07b22e7cb5757b`
