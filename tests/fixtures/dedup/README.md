# Jeu annoté de dédoublonnage (tranche 1.5)

Jeu de test du critère d'acceptation « rappel des doublons ≥ 0,98 et précision ≥ 0,99 » (`tests/unit/dedup/test_benchmark.py`). Décision proposée : D-060 (dans la demande de fusion de la tranche 1.5).

## Fichiers

- `references.jsonl` : une notice par ligne. Elle contient l'identifiant de la notice, la base, le titre, les auteurs, l'année, la revue ou le livre, le volume, le numéro, les pages, le DOI, le PMID, l'identifiant OpenAlex, la langue et le type. Le champ `cluster` donne le groupe annoté : deux notices du même groupe sont des doublons. Le champ `variant` donne le type d'une variante construite.
- `versions.json` : paires de groupes qui sont deux versions d'un même travail, avec leur nature : `preprint_article`, `thesis_article`, `conference_article` ou `co_publication`. Ces paires ne sont **pas** des doublons. L'outil doit les signaler et les laisser à une personne.
- `demo-*.ris` : le jeu de démonstration, soit 9 notices fictives dont les nombres ont été calculés à la main (`tests/unit/collect/test_deduplication.py`).

## Contenu

| Partie | Notices | Origine |
|---|---|---|
| Exports réels LUDIQ | 4 209 | Exports RIS complets de Benoit Plante : PubMed 1 617, APA PsycInfo (EBSCOhost) 1 039, CINAHL 850, SocINDEX 500, Érudit 129, ERIC 54, APA PsycInfo (Ovid) 20 |
| OpenAlex | 174 | 23 paires réelles prépublication–article (medRxiv, Research Square, SocArXiv), notices de base et paires difficiles (titres identiques ou presque, travaux distincts) |
| Variantes construites | 103 | Variantes d'une notice OpenAlex : accents retirés, majuscules, sous-titre retiré, ponctuation, DOI absent et revue en minuscules, initiales des auteurs, version en ligne avant le numéro (année − 1, sans volume ni pages), balises HTML, faute de frappe |

Au total, le jeu compte 4 486 notices et 2 642 travaux. Il contient 1 844 doublons (2 670 paires de doublons) et 30 paires de versions.

**Aucun résumé** n'est publié, ni aucune adresse, URL ou numéro d'accès d'abonnement. Les notices OpenAlex sont sous licence CC0.

## Annotation des exports LUDIQ

1. **Candidats.** Les paires candidates sont produites indépendamment de l'algorithme de l'outil : toutes les paires dont la similarité des titres (`token_set_ratio`) atteint 70, et toutes les paires qui partagent un DOI ou un PMID, soit 8 162 paires.
2. **Doublons évidents.** Une paire est un doublon évident si elle partage un DOI ou un PMID et que ses titres sont semblables à 90 % au moins (2 523 paires). C'est aussi le cas d'un titre identique à 95 % au moins, avec la même année, le même premier auteur, le même volume et la même première page (30 paires).
3. **Paires non doublons.** Les paires qui suivent ne sont pas des doublons :
   - DOI ou PMID différents, avec des titres semblables à moins de 85 %;
   - titres semblables à moins de 85 %, avec des premiers auteurs différents.
4. **Revue manuelle.** Les 87 autres paires ont été examinées une à une. S'y ajoutent les notices de même auteur, même année, même volume et même première page, pour repérer les titres traduits. Deux doublons à titre traduit par PubMed ont ainsi été trouvés.
5. **Règles retenues.** La même notice présente dans plusieurs bases est un **doublon**, y compris sous un titre tronqué, un titre traduit ou une même thèse listée deux fois. Les cas suivants sont des **versions** :
   - une thèse et l'article qui en est tiré;
   - une communication et l'article;
   - une prépublication et l'article;
   - le même travail publié dans deux revues.

   Les correctifs, les rétractations, les réponses et les commentaires sont des **notices distinctes**.

Les grappes sont la fermeture transitive des paires de doublons. Aucune grappe ne contient deux DOI différents.

**À vérifier** : un échantillon des grappes et toutes les paires revues à la main, par Benoit. L'annotation des doublons évidents s'appuie sur les identifiants, comme la première étape de l'outil. La mesure sans identifiants (`test_without_any_identifier_approximate_matching_still_finds_duplicates`) vérifie l'appariement approximatif seul.
