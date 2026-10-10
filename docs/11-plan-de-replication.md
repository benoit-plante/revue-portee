# 11 — Plan des tests de réplication

> **Statut** : ébauche du 9 octobre 2026; **décisions du §13 tranchées par Benoit le 2026-10-09**, puis révisées le même jour : **aucun arbitrage ni jugement humain des écarts**, et les conclusions narratives retirées de l'étude. Rien n'est lancé.
> **Objet** : rejouer des revues de portée publiées en psychologie avec revue-portee **sans révision humaine**, de la recherche à la synthèse, et mesurer à quel point l'outil, laissé seul, **se rapproche des résultats obtenus par des humains**.
> **Renvois** : [05-plan-de-validation.md](05-plan-de-validation.md) et 09 (protocole de l'étude de validation, branche `tranche/1.8-preenregistrement`) pour le tri des titres et résumés; [10-conception-texte-integral.md](10-conception-texte-integral.md) pour le texte intégral; [resultats/](resultats/README.md).
> **Bassin de revues candidates** : classeur `candidates-replication.xlsx`, à garder **hors du dépôt**, par exemple dans `~/revue-portee-donnees/replication/` (§5.4).

## 0. En bref

| Élément | Proposition |
|---|---|
| Question | Laissé seul, à partir du protocole publié d'une revue de portée, à quel point l'outil **concorde-t-il** avec l'équipe humaine : mêmes études, mêmes données, mêmes répartitions chiffrées ? |
| Nature | Étude de **concordance**, pas d'exactitude : la revue publiée est la référence par définition, qu'elle ait tort ou raison. Aucun écart n'est arbitré |
| Devis | Étude **descriptive** de réplication. Chaque revue est rejouée selon deux modes : **par étape** (chaque étape reçoit les intrants de la revue publiée) et **en chaîne** (chaque étape reçoit les sorties de l'IA à l'étape précédente) |
| Ce qui reste humain | La transcription du protocole publié (question, critères, grille), à l'aveugle des études incluses; le codage du tableau d'extraction publié dans les catégories de la grille (préparation de la référence); le téléversement des textes payants (accès UQTR). **Aucune décision de tri ni valeur extraite n'est revue par une personne, et aucun écart n'est jugé** |
| Mesure principale | **Rappel de bout en bout** : part des études incluses dans la revue publiée qui sont aussi incluses par l'outil en mode en chaîne, avec la **précision** correspondante. Toutes les mesures sont calculées automatiquement |
| Revues | 3 revues de développement, puis **5 revues** tirées au hasard dans un bassin de revues admissibles (29 candidates repérées le 2026-10-09), dont 1 à 2 francophones si le repérage manuel en trouve |
| Coût | Environ 3 à 5 $ US par revue, soit environ 30 $ US en tout; **plafond de 40 $ US** (§11) |
| Prérequis côté outil | Un **mode « réplication »** réservé aux bancs d'essai, qui laisse l'IA décider seule (§2), et une commande `banc-replication` (§12) |

## 1. Pourquoi une étude distincte du protocole 09

Le protocole 09 mesure **une étape** (tri des titres et résumés), dans **l'usage prévu** de l'outil (l'IA comme second réviseur), avec une hypothèse confirmatoire. La réplication répond à une autre question : que produirait l'outil **sans personne dans la boucle**, du début à la fin ? Elle est donc :

- **descriptive** : pas d'hypothèse confirmatoire, des estimations avec intervalles;
- **de bout en bout** : elle seule mesure comment les erreurs **se propagent** d'une étape à l'autre (une étude manquée au tri des résumés ne sera jamais extraite);
- **une étude de concordance** : le but n'est pas de recommander qu'une équipe se fie à l'IA seule (l'outil l'interdit, principe 1), mais de voir **à quelle distance des humains** l'outil se trouve sans aucune validation. La revue publiée sert de référence par définition, et aucun écart n'est arbitré;
- **une borne prudente** : un écart peut venir d'une erreur des auteurs autant que de l'IA (une étude admissible manquée par l'équipe, par exemple). Sans arbitrage, ces cas comptent contre l'outil : la concordance mesurée **sous-estime** sa justesse, ce qui se défend bien dans un article (« au pire, voici l'écart »).

Les deux études ont des revues **distinctes** (§5.3, décision 3).

## 2. Mode « réplication » : une exception encadrée au principe 1

Le principe 1 interdit toute exclusion par l'IA seule. Pour la réplication, l'IA doit pourtant décider seule. **Accepté par Benoit le 2026-10-09** (décision 1), à consigner au journal des décisions :

> **D-1xx (décidée, numéro à attribuer) — Mode « réplication », réservé aux bancs d'essai.** Une commande de banc (`banc-replication`) crée un projet `.revue` marqué `replication` dans `projet.toml`. Dans ce projet seulement, les décisions de l'IA sont finales (nouveau contexte de décision `replication_ai`) et passent d'une étape à l'autre sans personne. Le mode **ne peut pas** être activé dans un projet ordinaire, ni un projet de réplication converti en projet ordinaire (test). Le diagramme, la section méthode et l'archive portent la mention « Simulation de réplication — ne constitue pas une revue ». Toute la traçabilité reste la même (ENF-TRA-01, ajout seulement, réponses brutes).

Règle de décision en mode réplication : une référence « incertaine » est **conservée** (elle passe à l'étape suivante), comme une personne la trierait. La règle EF-SEL-07 s'applique. Une réponse inutilisable après une nouvelle tentative est conservée, et comptée.

## 3. Devis : deux modes d'exécution, un troisième en option

| Étape | Mode **par étape** : intrant | Mode **en chaîne** : intrant |
|---|---|---|
| 1. Recherche | Stratégie publiée, reconstituée | Stratégie publiée, reconstituée |
| 2. Dédoublonnage | Références reconstituées | Références reconstituées |
| 3. Tri des titres et résumés | Toutes les références dédoublonnées | Idem |
| 4. Obtention des textes | **Toutes les études incluses dans la revue publiée** + un échantillon d'exclues au texte intégral si la liste existe | Références conservées par l'IA à l'étape 3 |
| 5. Tri du texte intégral | Idem 4 | Textes obtenus à l'étape 4 |
| 6. Rapports d'une même étude | Études incluses publiées | Inclusions de l'IA à l'étape 5 |
| 7. Extraction | **Études incluses publiées**, grille transcrite | Inclusions de l'IA, grille transcrite |
| 8. Synthèse (tableaux, cartes, synthèse narrative) | Valeurs extraites par l'IA sur les études publiées | Valeurs extraites en chaîne |
| 9. Diagramme de flux | — | Nombres de la chaîne |

- **Par étape** : mesure l'exactitude propre de chaque étape, sans erreur héritée. C'est ce qui oriente le développement.
- **En chaîne** : mesure ce que l'outil livrerait vraiment. L'écart entre les deux modes mesure la **propagation des erreurs**.
- **Mode « question seule »** (exploratoire, facultatif) : l'IA construit aussi la recherche à partir de la seule question PCC (suggestion de blocs de concepts, EF-REC), sans la stratégie publiée. Mesure : rappel des études incluses dans l'ensemble ainsi collecté. À réserver aux revues où le mode en chaîne a bien fonctionné.

## 4. Ce qui reste humain, et dans quel ordre

L'ordre est le garde-fou principal : **tout ce qui sert d'intrant à l'IA est figé avant que la norme de référence soit constituée**.

1. **Transcription du protocole** (Benoit), selon la règle de transcription du protocole 09 (§2.2), à partir des seules sections Introduction et Méthodes de l'article, sans les tableaux de résultats :
   - question et critères → `criteres.yaml` (format déjà utilisé par `banc-synergy`);
   - **grille d'extraction** → `grille.yaml` : les variables que la revue dit avoir extraites, avec leurs catégories quand l'article les donne (pas celles du tableau de résultats);
   - stratégie de recherche → blocs de concepts de l'outil, en reprenant la chaîne publiée;
   - journal de transcription (reformulations et leurs raisons).
2. **Gel** : commit daté (ou empreinte SHA-256 des fichiers) **avant** l'étape 3.
3. **Constitution de la norme de référence**, après le gel :
   - `incluses.csv` : chaque étude incluse avec DOI, PMID ou référence complète, et son appariement à une référence reconstituée;
   - `resultats-publies.yaml` : nombres du diagramme et distributions publiées (ex. pays, devis, population);
   - `extraction-publiee.csv` : le tableau d'extraction par étude de l'article, transcrit tel quel, puis **codé dans les catégories de la grille** pour les champs catégoriels (règle de codage écrite d'avance, consignée avec chaque correspondance). Ce codage prépare la référence; ce n'est pas un jugement des sorties de l'IA, qu'il précède.
4. **Obtention des textes payants** : téléversement des PDF obtenus par l'accès de l'UQTR (D-102 : la section méthode déclare l'envoi au fournisseur; la bibliographie n'est jamais envoyée).
Les exports RIS des bases sous abonnement (PsycINFO, CINAHL, Embase…) sont faits par Benoit avec la limite de date d'origine.

## 5. Sélection des revues

### 5.1 Admissibilité

Les critères du protocole 09 (§3.2), plus quatre exigences propres à la réplication :

1. **tableau d'extraction par étude** publié (dans l'article ou en supplément), sans quoi l'étape 7 ne peut pas être comparée;
2. **résultats chiffrés** dans la synthèse (au moins une distribution ou un tableau croisé);
3. **taille praticable** : de 10 à 80 études incluses, et de préférence au plus 5 000 références triées;
4. **textes des études incluses obtenables** (libre accès ou accès UQTR) pour au moins 90 % d'entre elles.

Exclusion supplémentaire : revues dont un auteur est lié aux équipes de Benoit (UQTR, GRIN, CEIDEF, projet ECOANXIETE). Une candidate du bassin est signalée à ce titre (Léger-Goodes et al., 2022). Une revue francophone peut être admise avec une stratégie annoncée mais non publiée en entier, si les auteurs la transmettent sur demande.

### 5.2 Bassin actuel (repérage du 2026-10-09)

- **29 candidates** vérifiées sur leur texte, en 4 groupes : clinique adulte (8), enfance et famille (7), psychologie sociale, éducation et santé (7), francophones ou à décisions de tri partagées (7). 18 revues examinées ont été écartées de justesse (onglet « Écartées »).
- **Médiane de 30 études incluses** par revue (1 208 au total); 48 006 références triées connues.
- **Strate A** (décisions de tri publiques) : 3 candidates (OSF ou annexe d'un article de méthode).
- **Littérature francophone** : faible partout. Aucune revue en psychologie publiée en français n'a pu être vérifiée avec une stratégie complète. Les revues francophones (Santé mentale au Québec, Revue québécoise de psychologie, Psychologie canadienne) sont surtout derrière Érudit ou l'APA, que la recherche automatique n'a pas pu lire. **Décision 8 : repérage manuel par Benoit, avec l'accès UQTR, avant le tirage** (§5.5).
- **Ce qui n'a pas été vérifié** : le contenu des suppléments (fichiers de stratégie, annexes OSF) et les nombres qui ne figurent que dans l'image du diagramme. Une vérification à la main par revue (environ 15 minutes) précède l'admission.
- **Pas recopié, volontairement** : les listes d'études incluses (emplacement et nombre seulement) et le texte des critères (emplacement et résumé PCC seulement), pour préserver l'aveugle de la transcription.

### 5.3 Rôles et tirage

| Rôle | Revues | Usage |
|---|---|---|
| **Développement** | 3, choisies (pas tirées) : petites, stratégie complète dans le texte, tableau d'extraction | Mise au point du **processus** (scripts, formats, comparateurs, règle de codage du tableau publié). **Pas** des gabarits d'invite : un changement de gabarit suit le journal des gabarits (08) avec ses propres données |
| **Strate A** | 2 à 3 | Comparer le tri de l'IA aux décisions humaines référence par référence (spécificité réelle, et non approchée) |
| **Réplication** | **5**, **tirées au hasard** parmi les admissibles, avec une graine consignée : 1 à 2 dans la strate francophone (si elle compte au moins 2 admissibles), le reste dans les autres groupes | Mesures déclarées |
| Réserve | le reste | Remplacement si une revue tirée se révèle inadmissible à la vérification |

**Relation avec le protocole 09** (décision 3 : **exclusion mutuelle**) : toutes les revues du bassin de réplication (les 29 candidates, les 18 écartées de justesse et celles du repérage francophone) sont **exclues** du futur tirage de l'ensemble de test du 09, qui fera son propre repérage après son gel. Une phrase est à ajouter aux critères d'exclusion du 09 (§3.2) : « revues examinées pour l'étude de réplication (liste dans `~/revue-portee-donnees/replication/`) ».

### 5.4 Où ranger les données

Le dépôt est public, et les sessions de développement des gabarits ne doivent jamais voir les revues de réplication. Donc, **hors du dépôt** :

```
~/revue-portee-donnees/replication/
├── candidates-replication.xlsx      # bassin, rôles, statuts
├── tirage.md                        # graine, liste tirée, date
└── <id-revue>/
    ├── fiche.yaml                   # métadonnées, intrants publiés, emplacements
    ├── criteres.yaml                # transcription gelée (intrant)
    ├── grille.yaml                  # grille d'extraction transcrite (intrant)
    ├── recherche/                   # blocs de concepts, exports RIS d'origine
    ├── journal-transcription.md
    ├── GEL.sha256                   # empreintes des intrants, avant l'étape 3
    ├── norme/                       # constituée APRÈS le gel
    │   ├── incluses.csv
    │   ├── extraction-publiee.csv
    │   └── resultats-publies.yaml
    ├── textes/                      # PDF, jamais publiés
    └── replication.revue/           # projet en mode réplication
```

Seuls les rapports chiffrés vont dans `docs/resultats/replication-<id>.md` (même règle que D-074 et D-092 : aucun résumé, aucun texte, aucune réponse brute).

Exemple de `fiche.yaml` :

```yaml
id: Gilbert_2025_alcoolprenatal_attachement
doi: 10.3390/children12091133
role: developpement            # developpement, strate_a, replication, reserve
strate: B
recherche:
  date_origine: [2021-05-20, 2021-06-17]
  mise_a_jour: 2023-09-01
  bases: [MEDLINE, CINAHL, APA PsycINFO, PubMed, ERIC, Web of Science, Child Development and Adolescent Studies, Google Scholar]
  interrogeables_par_outil: [PubMed]
  export_ris_requis: [APA PsycINFO, CINAHL, ERIC, Web of Science]
  litterature_grise: oui            # Google Scholar et listes de références; 3 thèses incluses
flux_publie: {identifies: 4199, apres_doublons: 3207, tries: 3207, textes_evalues: 29, inclus_etudes: 11}
emplacements:
  criteres: "Méthodes, sous-sections 2.x"
  strategie: "Méthodes, 2.3, dans le texte"
  incluses: "Tableau 1"
  extraction: "Tableau 1"
```

### 5.5 Repérage francophone (décision 8)

À faire par Benoit avec l'accès UQTR, avant le tirage :

- **Où chercher** : Érudit (Santé mentale au Québec, Revue québécoise de psychologie, Revue de psychoéducation, Service social, Nouvelles pratiques sociales); APA PsycNet (Psychologie canadienne, Revue canadienne des sciences du comportement); Cairn (Pratiques psychologiques, Psychologie française); Revue canadienne de santé mentale communautaire.
- **Termes** : « examen de la portée », « revue de la portée », « étude de la portée », « scoping review », « synthèse des connaissances » (à vérifier : certaines se réclament de la méthode JBI sans le mot).
- **Pour chaque revue trouvée** : remplir une ligne du classeur (mêmes colonnes) et noter l'accès (libre, UQTR).
- **Cible** : au moins 2 admissibles pour pouvoir en tirer 1 à 2. À défaut, la réplication se fait en anglais seulement et la limite est déclarée.
- Les plus prometteuses déjà repérées mais non lues : de Pierrepont et al. (2026) et Ouellet et al. (2023) dans *Psychologie canadienne*.

## 6. Préparation d'une revue (liste de contrôle)

1. Ouvrir les suppléments; confirmer la stratégie complète, la date de recherche et les nombres du diagramme (corriger le classeur).
2. Vérifier l'absence de conflit d'intérêts.
3. Transcrire question, critères, grille et blocs de concepts (§4.1). Consigner le temps passé.
4. Exporter les RIS des bases sous abonnement avec la limite de date d'origine.
5. Geler les intrants (`GEL.sha256`).
6. Constituer la norme de référence (§4.3) et apparier chaque étude incluse à une référence. Une étude incluse **absente de toute base interrogeable** (littérature grise, recherche manuelle, chaînage des références) est marquée `hors_recherche` : elle reste au dénominateur du rappel de bout en bout, mais elle est rapportée à part, car aucun outil de tri ne peut la retrouver.

## 7. Déroulement et mesures par étape

| Étape | Mesures | Commentaire |
|---|---|---|
| 1. Recherche | Écart entre références reconstituées et identifiées publiées (%); **retrouvabilité** : part des études incluses présentes dans l'ensemble reconstitué | La retrouvabilité sépare les pertes de la recherche de celles du tri. Écart > 20 % : revue gardée, mais signalée (pas d'analyse principale séparée, l'étude étant descriptive) |
| 2. Dédoublonnage | Écart au nombre publié après doublons | Règles version 1 (D-062) |
| 3. Tri des titres et résumés | Sensibilité, spécificité (approchée en strate B), proportion d'« incertain », charge évitée, coût | Mêmes définitions que le 09 |
| 4. Obtention | Part des textes obtenus en libre accès; part obtenue par téléversement; non obtenus | Un texte non obtenu en mode en chaîne = étude perdue (rapportée) |
| 5. Tri du texte intégral | Sensibilité et spécificité par rapport à l'inclusion finale; concordance des **motifs** d'exclusion quand la revue les donne par étude, sinon comparaison des répartitions de motifs | Mode aveugle de D-102 sans objet ici : aucune personne ne trie |
| 6. Rapports multiples | Nombre d'études contre nombre de rapports publiés | |
| 7. Extraction | **Champs catégoriels** communs à la grille et au tableau publié codé : pourcentage d'accord par champ, kappa de Cohen et AC1 de Gwet; part des valeurs « non rapporté » de chaque côté; citations de l'IA retrouvées à la page indiquée (vérification automatique de l'outil) | Comparaison entièrement automatique. Les champs en texte libre sont extraits mais **hors de la mesure** (pas de comparaison sans jugement) |
| 8. Synthèse | **Tableaux seulement** : pour chaque distribution publiée, écart absolu par catégorie (points de pourcentage), part des catégories à moins de 5 points, même catégorie modale ou non; corrélation de rang entre les répartitions | La synthèse narrative est produite (pour mesurer le coût et la faisabilité) mais **n'est pas comparée** (décision 9) |
| 9. Diagramme | Écart case par case | |
| Toutes | Coût, jetons, durée, réponses inutilisables | |

### Mesures de bout en bout (mode en chaîne)

- **Rappel de bout en bout** (principale) : études incluses publiées retrouvées parmi les inclusions de l'IA, divisées par toutes les études incluses publiées.
- **Précision de bout en bout** : inclusions de l'IA qui sont aussi des inclusions publiées, divisées par toutes les inclusions de l'IA. Une partie des « faux positifs » peut être de vraies études admissibles manquées par les auteurs : sans arbitrage, ils comptent contre l'outil (§9).
- **F1** et **indice de Jaccard** entre les deux ensembles d'études.
- **Décomposition des pertes** : pour chaque étude incluse publiée et non retrouvée, l'étape où elle a été perdue (hors recherche, recherche, tri des résumés, obtention, texte intégral). Présentée en cascade par revue et groupée.

## 8. Analyse

- **Par revue** : proportions avec intervalles de Wilson; cascade des pertes.
- **Groupée** : avec 5 revues de réplication, pas de modèle à effets aléatoires (variance entre revues inestimable). On rapporte la **médiane et l'étendue** des proportions par revue, et la proportion globale (somme des études) avec un intervalle par bootstrap en grappes, présenté comme indicatif.
- **Sous-groupes descriptifs** : publication avant ou après la fin d'entraînement du modèle (à consigner); stratégie complète dans le texte ou en supplément; groupe de domaine; strate A ou B.
- **Précision attendue** : avec 5 revues et une médiane de 30 études incluses, environ 150 études; pour un rappel de 0,90, demi-largeur d'environ ± 0,05 sans effet de grappe (1,96 × √(0,90 × 0,10 / 150)), nettement plus large avec. L'étude est donc **une étude pilote** : elle décrit des ordres de grandeur et des mécanismes de perte, pas une performance généralisable.

## 9. Norme de référence, sans arbitrage

**La revue publiée est la référence par définition** (décision 5, révisée le 2026-10-09). Aucun écart n'est examiné pour savoir qui a raison : l'étude mesure la proximité de l'outil avec l'équipe humaine, pas sa justesse.

Conséquences :
- toutes les mesures sont des **concordances** avec la revue publiée, et sont nommées ainsi dans le rapport (« rappel par rapport à la revue publiée », et non « sensibilité » au sens d'une vérité);
- la concordance est une **borne prudente** de la justesse de l'outil : les erreurs des auteurs comptent contre lui;
- pour aider la lecture sans juger, le rapport donne des **descripteurs automatiques** des écarts, calculés par l'outil :
  - étape où chaque étude incluse publiée a été perdue (cascade);
  - pour les études perdues au tri : résumé absent ou non, critère cité par l'IA pour exclure;
  - pour les inclusions de l'IA absentes de la revue : année de publication (hors de la période de recherche d'origine ou non), étape où les auteurs l'ont écartée quand leur liste d'exclusions au texte intégral est publiée;
- ces descripteurs décrivent, ils ne tranchent pas.

## 10. Déroulement par jalons

| Jalon | Activité |
|---|---|
| 0 (fait le 2026-10-09) | Bassin de 29 candidates; rôles proposés |
| 1 | Décisions du §13; mode réplication et `banc-replication` (Claude Code, une tranche) |
| 2 | Vérification à la main des suppléments; repérage francophone manuel; admission |
| 3 | **Développement**, une revue à la fois (§10.1) : essai à sec, puis 3 revues de bout en bout; journal des enjeux |
| 4 | Repérage francophone (§5.5); gel du présent plan (commit daté) et de la version de l'outil; tirage des 5 revues de réplication |
| 5 | Transcriptions et gel des intrants; normes de référence |
| 6 | Exécutions (API de lots, fenêtre courte), **sans aucune correction entre deux revues** (§10.2) |
| 7 | Calcul automatique des concordances, rapport dans `docs/resultats/` |

### 10.1 Développement : une revue à la fois (décidé le 2026-10-09)

Chaque revue de développement passe de bout en bout, dans les deux modes. Ensuite, ses enjeux sont consignés et corrigés **avant** de passer à la suivante. L'ordre suit une difficulté croissante, pour que chaque revue révèle des enjeux différents.

| Ordre | Revue | Taille | Ce qu'elle doit éprouver |
|---|---|---|---|
| 0 | **Essai à sec** sur la revue 1, avec `FakeProvider` | — | La plomberie, sans frais : création du projet de réplication, vérification du gel, collecte, dédoublonnage, import et appariement de la norme de référence, passage d'une étape à l'autre, arrêt et reprise après l'étape 4, comparateurs, rapport |
| 1 | Breth-Petersen et al. (2023), solastalgie | 145 références, 18 études; décisions de tri sur OSF (strate A) | Premier passage réel à faible coût; comparaison du tri avec les décisions humaines, référence par référence; format des fichiers de la norme |
| 2 | Reategui-Rivera et al. (2024), réalité virtuelle et dépression | 575 références, 15 études; chaîne PubMed dans le texte | Reconstitution de la recherche (écart au nombre publié, retrouvabilité); texte intégral et téléversement; extraction et codage du tableau publié |
| 3 | Gilbert et al. (2025), alcool prénatal et attachement | 3 207 références, 11 études, 8 bases, 3 thèses incluses | Cas difficiles : plusieurs exports RIS, études hors recherche (littérature grise), coût réel à l'échelle, durée |

**Règle de passage** : on passe à la revue suivante quand tous les enjeux de la revue en cours sont soit corrigés, soit consignés comme limites acceptées.

**Coût mesuré** : après la revue 3, le §11 est mis à jour avec les coûts réels (extraction et synthèse surtout). Le plafond de 40 $ US est revu si l'estimation pour les 5 revues de réplication le dépasse.

**Journal des enjeux** : un fichier `~/revue-portee-donnees/replication/journal-des-enjeux.md`, hors du dépôt, puisqu'il nomme les revues. Une entrée par enjeu :

```markdown
### E-001 — <titre court>

- Revue et étape : Breth-Petersen 2023, étape 1 (recherche)
- Nature : outil | processus | données de la revue | invite
- Constat : ce qui s'est passé, avec les nombres
- Correction : ce qui a été changé (commit, demande de fusion) ou « limite acceptée », avec la raison
- Vérifié sur : revue où la correction a été confirmée
```

Le journal devient une section du rapport final (« enjeux rencontrés pendant le développement »). Les nombres seuls vont dans `docs/resultats/`.

**Limite des corrections** :
- **Outil, processus, données** : corrigés librement pendant le développement, par des demandes de fusion ordinaires.
- **Invite** (l'IA applique mal un type de critère, rate un champ d'extraction…) : l'enjeu est consigné, mais la correction **ne se fait pas** sur les revues de réplication. Elle suit le journal des gabarits (08), avec ses propres données de mise au point. Les revues de développement peuvent y servir, à condition d'être déclarées comme telles. Sinon, l'outil serait ajusté aux revues mêmes qui servent à le mesurer.

### 10.2 Réplication : rien ne change entre deux revues

Après le gel (jalon 4), les 5 revues de réplication peuvent passer une à la fois, par commodité (téléversement des textes, par exemple), mais **aucune correction** n'est permise entre elles : toutes mesurent la même version gelée de l'outil.

Un enjeu découvert à ce stade est consigné dans le journal des enjeux avec la mention « découvert en réplication ». Il est corrigé **après** l'étude et déclaré comme limite. Si un enjeu empêche d'aller au bout d'une revue (plantage, données inutilisables), la revue est arrêtée, rapportée comme telle, puis remplacée par une revue de réserve tirée avec la même graine. Le remplacement est déclaré.

## 11. Coût estimé

À partir des mesures déjà faites (`docs/resultats/`) :

| Poste | Base | Par revue (environ 3 000 références, 100 textes, 30 études) |
|---|---|---|
| Tri des titres et résumés | 0,18 $ US pour 1 000 en lots (0,36 $ US en appels individuels) | 0,55 à 1,10 $ US |
| Tri du texte intégral | environ 0,002 $ US par texte (essai `screen_fulltext` v1) | 0,20 $ US, ×2 pour les deux modes |
| Extraction | **non mesuré** : hypothèse de 0,01 à 0,03 $ US par étude | 0,30 à 0,90 $ US, ×2 |
| Synthèse | **non mesuré** | moins de 1 $ US |
| **Total** | | **environ 3 à 5 $ US** |

Les textes payants des **références conservées à chaque étape** sont téléversés par Benoit avec l'accès UQTR (décision 6) : environ 30 à 100 PDF par revue, soit 5 à 10 heures pour les 8 revues. En mode en chaîne, le téléversement suit l'étape 3 de l'IA : il faut donc une pause dans la chaîne (`banc-replication` doit pouvoir s'arrêter après l'étape 4 et reprendre).

Pour 3 revues de développement et 5 de réplication : **environ 30 $ US**; **plafond : 40 $ US** (décision 7), vérifié avant chaque appel comme au banc SYNERGY (D-069). Les revues de développement serviront à remplacer les hypothèses par des mesures. Tout appel réel reste lancé avec l'accord de Benoit (CLAUDE.md).

## 12. Ce qu'il faut ajouter à l'outil

À proposer à Claude Code comme une tranche (par exemple `tranche/3.8-banc-replication`) :

1. **Mode réplication** (§2) : marqueur de projet, contexte de décision `replication_ai`, refus dans un projet ordinaire, mentions sur les exports. Tests.
2. **`banc-replication <dossier-revue>`** : crée le projet, vérifie `GEL.sha256`, enchaîne les étapes dans un mode donné (`--mode par-etape|en-chaine`), affiche le coût estimé et demande confirmation, respecte un `--plafond`, reprend après interruption sans repayer (D-059, D-080).
3. **Import de la norme de référence** (`incluses.csv`) et appariement aux références par DOI, PMID, puis titre (règles du dédoublonnage), avec liste des non appariées.
4. **Comparateurs**, fonctions pures avec tests calculés à la main : retrouvabilité, cascade des pertes, rappel, précision, F1, Jaccard de bout en bout; concordance des champs catégoriels de l'extraction (accord, kappa, AC1); écarts de distributions; descripteurs automatiques des écarts (§9).
5. **Rapport** `replication-<id>.md` : chiffres seulement.

## 13. Décisions (tranchées par Benoit le 2026-10-09)

| # | Question | Décision |
|---|---|---|
| 1 | Mode réplication | **Accepté**, limité aux bancs d'essai (§2); à consigner au journal (D-1xx) |
| 2 | Nombre de revues | **3 de développement + 5 de réplication** : étude pilote descriptive (§8) |
| 3 | Relation avec le protocole 09 | **Exclusion mutuelle** : le 09 fera son propre repérage après son gel (§5.3) |
| 4 | Études hors recherche | **Deux rappels** : au dénominateur du rappel de bout en bout, plus un rappel « sur les études retrouvables » rapporté à côté |
| 5 | Arbitrage | **Aucun** (révisé le 2026-10-09) : étude de concordance avec la revue publiée, référence par définition (§9) |
| 6 | Textes payants | **Téléversement par l'accès UQTR** pour tous les textes nécessaires (§11) |
| 7 | Plafond | **40 $ US** pour toute l'étude |
| 8 | Revues francophones | **Repérage manuel maintenant**, viser 1 à 2 revues parmi les 5 (§5.5) |
| 9 | Conclusions narratives | **Retirées de l'étude** : la synthèse n'est comparée que par ses tableaux chiffrés; tout reste automatique (§7) |

**Conséquences à reporter ailleurs** :
- protocole 09, §3.2 : ajouter l'exclusion des revues examinées pour la réplication;
- journal des décisions : D-1xx (mode réplication) et une entrée pour le présent plan;
- feuille de route : une tranche `banc-replication` (§12), avec arrêt et reprise après l'étape 4.

## 14. Limites prévisibles

- **Stratégies incomplètes ou en supplément illisible** : beaucoup de revues ne publient la chaîne complète que pour une base; la reconstitution des autres bases sera approximative.
- **Bases sous abonnement** : la reconstitution dépend des exports faits par Benoit, sur des plateformes dont le contenu change avec le temps, même avec une limite de date.
- **Contamination** : le modèle peut connaître les revues publiées avant la fin de ses données d'entraînement, et parfois leurs études incluses. Le sous-groupe des revues de 2026 permet d'en estimer l'effet.
- **Concordance, pas justesse** : les erreurs et les choix implicites des auteurs comptent contre l'outil; les résultats sous-estiment sa justesse (§9).
- **Grille d'extraction** : les catégories publiées sont souvent construites après coup (codage inductif); l'IA, qui part de la grille du protocole, peut produire des catégories différentes mais défendables, qui compteront comme des désaccords. Le codage du tableau publié dans les catégories de la grille réduit ce problème sans l'éliminer.
- **Champs en texte libre et conclusions narratives non mesurés** : l'étude ne dit rien de la qualité de la synthèse rédigée par l'IA.
- **Peu de littérature francophone** dans le bassin actuel.
- **Un seul codeur**, qui est aussi le développeur de l'outil, pour la transcription du protocole et le codage du tableau publié (garde-fous du 09 : règle écrite d'avance, aveugle, gel avant l'exécution).
- **Cinq revues seulement** : résultats d'étude pilote, à ne pas présenter comme une performance générale de l'outil.
