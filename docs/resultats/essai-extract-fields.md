# Essai réel du pré-remplissage de la grille par l'IA (extract_fields)

- Date : 2026-10-09; accord de Benoit, plafond de 5 $ US
- Revue de référence : Seunanden TC, Ngwenya N, Seeley J. *Experiences and perceptions on antiretroviral therapy adherence and non-adherence: a scoping review of young people living with HIV in sub-Saharan Africa.* BMC Public Health. 2025. doi:10.1186/s12889-025-22579-6 (PMC12004696, CC-BY)
- Modèle : `claude-haiku-5-5`, effort faible (configuration par défaut de `extract_fields`)
- Ce rapport ne contient que des nombres : aucune valeur ni citation des articles.

## Données

- **Études** : les 22 études incluses par la revue, importées avec leur PMID et leur DOI. Textes intégraux obtenus : **11** sur 22. L'outil en a trouvé 5 en libre accès (OpenAlex, Unpaywall); 6 ont été versés par l'équipe à partir de l'entrepôt public de PubMed Central (`pmc-oa-opendata`). Les 11 autres ne sont pas en libre accès.
- **Grille** : 7 champs repris des colonnes du tableau d'extraction des auteurs.

| Code | Champ | Type |
|---|---|---|
| D1 | Pays | texte |
| D2 | Participants et taille de l'échantillon | texte |
| D3 | Devis | choix unique (4 choix) |
| D4 | Mode d'acquisition du VIH | choix unique (4 choix) |
| D5 | Âge des participants | texte |
| D6 | Durée sous antirétroviraux | texte |
| D7 | Objet de l'étude | choix unique (3 choix) |

- **Référence** : le tableau des auteurs, transcrit selon des règles écrites (« NR » = non rapporté; catégorie d'âge entre parenthèses retirée; « Vertical and horizontal acquired » = « Vertical and horizontal »). Elle compte 154 valeurs, dont 17 non rapportées. Elle a été figée avant tout appel à l'IA (SHA-256 `0e3003fd902d97495bcbb88f912dbdca6193e11bd0e7aca3e2829466d1c71878`). Le fichier reste hors du dépôt.
- **Concordance automatique** (`banc-extraction`) : « non rapporté » ne concorde qu'avec « non rapporté »; les choix concordent s'ils sont égaux; les textes concordent si l'un contient l'autre ou s'ils partagent au moins la moitié de leurs mots.

## Version 1 (résultat de test)

- Appels : 16, nouvelles tentatives comprises, pour 0,030 $ US.
- Études pré-remplies : **7** sur 11. Les 4 autres ont été refusées après deux tentatives, toutes pour la même raison : un choix unique rangé parmi les choix multiples.
- Ces 7 études n'avaient servi ni à écrire ni à ajuster le gabarit.

| Champ | Valeurs comparées | Concordantes | Exactitude |
|---|---|---|---|
| D1 — Pays | 7 | 7 | 100,0 % |
| D2 — Participants et taille de l'échantillon | 7 | 7 | 100,0 % |
| D3 — Devis | 7 | 5 | 71,4 % |
| D4 — Mode d'acquisition du VIH | 7 | 4 | 57,1 % |
| D5 — Âge des participants | 7 | 6 | 85,7 % |
| D6 — Durée sous antirétroviraux | 7 | 6 | 85,7 % |
| D7 — Objet de l'étude | 7 | 2 | 28,6 % |
| **Total** | **49** | **37** | **75,5 %** |

**Citations** : 43 au total.
- 38 se trouvaient à la page indiquée par l'IA.
- 3 se trouvaient à une autre page ; l'outil les a placées à la bonne page.
- 2 étaient introuvables.
- Pages exactes : 88,4 %.

**Les 12 désaccords, lus un à un dans les textes**

| Nature | Nombre | Champs |
|---|---|---|
| Erreur de l'IA | 4 | D3 (1), D4 (1), D5 (1), D6 (1); 2 valeurs données dans le texte et déclarées « non rapportées » |
| Erreur de la référence (l'IA suit le texte) | 2 | D3 (1), D4 (1) |
| Écart de convention | 6 | D7 (5) : définition trop vague dans notre grille; D4 (1) : « Unknown/assumed » relève d'une inférence des auteurs |

Sans le champ D7, dont la définition est en cause, la concordance est de 35 sur 42 (83,3 %).

## Version 2 (résultat de développement)

Elle a été écrite à partir des réponses de la v1 sur ces 11 études, qui ne peuvent donc plus servir à la mesurer ([journal des gabarits](../08-journal-des-gabarits.md)). Elle n'a été essayée que sur les 4 études que la v1 avait refusées.

- Appels : 4, pour 0,008 $ US.
- Réponses utilisables : 4, toutes au premier essai, sans aucun choix unique mal rangé.
- Concordance : **23 sur 28 (82,1 %)**. Le champ D7 n'en compte que 1 sur 4 ; c'est le même problème de définition.
- Citations : 24 au total ; 18 à la page indiquée, 4 à une autre page, 2 introuvables.

## Limites et suites

- **Taille** : petit échantillon, 7 études pour la v1 et 4 pour la v2. Le critère de la tranche 3.2 (20 études) n'est pas atteint, faute de textes en libre accès.
- **Qualité de la référence** : elle vient d'autres réviseurs, avec leurs conventions, et contient au moins 2 erreurs. Un désaccord n'est donc pas toujours une erreur de l'IA ; d'où le classement des désaccords ci-dessus.
- **Champ D7** : sa définition dans notre grille (« adherence, non-adherence or both ») ne suffit pas à reproduire la convention des auteurs. Une grille réelle devrait la préciser, par exemple avec des exemples.
- **Mesure de la v2** : elle demande une autre revue, distincte de celle-ci.
