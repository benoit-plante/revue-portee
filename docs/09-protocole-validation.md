# 09 — Protocole de l'étude de validation

> **Statut** : ébauche du 9 octobre 2026, détaillée à partir de [05-plan-de-validation.md](05-plan-de-validation.md). **Pas de dépôt OSF** (choix de Benoit, D-100) : ce protocole est versionné dans le dépôt public, et l'historique Git en date chaque version. Il sera **gelé** par un commit daté avant le repérage et le tirage de l'ensemble de test; après le gel, tout changement est un **amendement** daté, ajouté à la fin du document.
> **Écarts au plan 05, choisis par Benoit le 2026-10-09** : **15 revues** au lieu de 24 à 30 (précision d'environ ± 0,025 sur la sensibilité au lieu de ± 0,02); critères transcrits **par des personnes seulement**, sans brouillon d'un modèle d'IA; **un seul codeur (Benoit)** au lieu de deux, avec une règle de transcription écrite d'avance, une seconde transcription indépendante sur 5 revues et la publication de chaque transcription (§2.2). En conséquence : au moins 5 revues francophones et 5 postérieures à la fin d'entraînement du modèle, comparaison des stratégies d'invite sur 6 revues, sous-groupes descriptifs.
> **Renvois** : [06-liste-raise2.md](06-liste-raise2.md) (RAISE 2, §2 et §4), [07-fiche-outil.md](07-fiche-outil.md), [08-journal-des-gabarits.md](08-journal-des-gabarits.md), [resultats/](resultats/README.md).

## À décider avant le gel

Chaque point est marqué **[À DÉCIDER]** dans le texte.

1. **Équipe.** Le codeur des critères est Benoit (§2.2). Il reste à nommer la **seconde personne** qui transcrit indépendamment les critères de 5 revues, et au moins une personne qui n'a pas participé au développement de l'outil pour l'**analyse des erreurs** (§5.6).
2. **Version gelée du gabarit.** Le test se fait sur `screen_reference` v1, la version mesurée au banc, ou sur une v2 qui corrigerait le problème connu (évaluer tous les critères). Une v2 devrait d'abord être mise au point sur des données distinctes, puis consignée au journal des gabarits (08).
3. **Ensemble de développement.** Le plan 05 prévoit 3 jeux SYNERGY **et** 4 à 5 revues de portée admissibles. Les revues de portée de développement n'existent pas encore. Faut-il les constituer avant le gel, ou déclarer que le développement s'est fait sur SYNERGY seulement ?
4. **Condition principale.** Le test de stabilité (D-099) montre que 9,6 % des notices changent d'issue d'une exécution à l'autre. Je propose de garder comme condition principale **une seule exécution**, comme dans l'usage réel de l'outil, et de mesurer la reproductibilité en analyse secondaire.
5. **Budget.** Estimation pour 15 revues, seconde transcription comprise : environ **30 $ US** (§3.6). Plafond proposé : **40 $ US**.
6. **Date de fin des données d'entraînement du modèle**, à relever dans la documentation du fournisseur (sous-groupe de contamination).
7. **Références** : STARD 2015 et Cohen et al. (2006) sont à revérifier, comme le note 05.
8. **Réponses inutilisables** (choix ajouté, absent de 05) : je propose de les compter comme **conservées** dans l'analyse principale, puisque la personne les trierait de toute façon, et comme manquées dans une analyse de sensibilité (§5.5).
9. **Seuil de signification** (choix ajouté, absent de 05) : je propose des comparaisons bilatérales à α = 0,05, sans correction pour le petit nombre de comparaisons préspécifiées (§5.3).

---

## 1. Présentation

### 1.1 Titre

*Un grand modèle de langage comme second réviseur au tri des titres et résumés dans les revues de portée en psychologie, sciences sociales et santé : étude rétrospective de précision sur des revues publiées.*

### 1.2 Équipe

Benoit Plante, développeur de l'outil et codeur des critères. **[À DÉCIDER : la seconde personne qui transcrit les critères de 5 revues; au moins une personne indépendante du développement pour l'analyse des erreurs.]**

### 1.3 Contexte

revue-portee est un logiciel libre (AGPL-3.0-or-later) qui accompagne les revues de portée selon la méthode JBI et PRISMA-ScR, avec un grand modèle de langage comme second réviseur traçable des titres et résumés.

Pour chaque référence :
- le modèle évalue chaque critère (satisfait, non satisfait, impossible à déterminer) avec une citation du titre ou du résumé, et donne une probabilité d'inclusion;
- l'outil en déduit la décision de l'IA à l'aide de deux seuils : exclure sous 0,10, inclure à partir de 0,60, incertain entre les deux;
- l'outil n'exclut jamais une référence dont un critère d'inclusion est indéterminable et qu'aucun critère n'écarte (règle EF-SEL-07).

Presque toutes les évaluations du tri par grand modèle de langage portent sur des revues systématiques biomédicales. Les revues de portée ont des critères plus larges et plus conceptuels, et aucune donnée n'existe sur la littérature francophone.

À ce jour, l'outil n'a été testé que sur son **ensemble de développement** : trois revues systématiques SYNERGY en psychologie clinique. Résultats : sensibilité de 95,0 à 97,4 %; même issue pour 90,4 % des références sur trois exécutions. Au sens de RAISE 2, ce sont des résultats de développement, ni un test sur des données mises de côté ni une validation.

Cette étude mesure l'exactitude de l'outil sur des revues de portée publiées **mises de côté**. Le gabarit d'invite, les seuils, le modèle et le code sont gelés avant le tirage de l'ensemble de test.

### 1.4 Hypothèse principale

**H1.** Aux seuils par défaut, la sensibilité groupée du réviseur IA, par rapport aux études finalement incluses dans des revues de portée publiées, est d'au moins 0,95, et la borne inférieure de son intervalle de confiance à 95 % est d'au moins 0,90.

Repère : un réviseur humain unique manque environ 13 % des études pertinentes, soit une sensibilité d'environ 0,87 (Gartlehner et al., 2020).

Les objectifs secondaires (§4.3) sont estimés sans test d'hypothèse, sauf les comparaisons appariées du §5.3.

## 2. Devis

### 2.1 Type d'étude

Étude méthodologique sur des données existantes : étude rétrospective de précision diagnostique, par simulation. L'outil est appliqué aux références criblées (ou reconstituées) de revues de portée publiées, et ses décisions sont comparées à une norme de référence tirée de ces revues. Aucun participant humain; seulement de la littérature publiée et des données publiques.

### 2.2 Aveugle

**Transcription des critères par un seul codeur.** Benoit transcrit les critères de chaque revue dans le format de l'outil. Comme il est aussi le développeur de l'outil, et qu'il sait donc comment l'outil réagit aux critères, la transcription suit les garde-fous ci-dessous.

1. **Aveugle** : le codeur ne consulte jamais la liste des études incluses. Il travaille seulement à partir de la section de l'article qui énonce la question et les critères d'admissibilité, sans les tableaux ni les résultats.
2. **Règle de transcription**, fixée avant le gel :
   - chaque critère reprend le texte de l'article presque mot pour mot;
   - un critère n'est découpé en plusieurs que si l'article énumère des conditions distinctes;
   - aucune consigne, aucun exemple ni contre-exemple n'est ajouté s'il ne figure pas dans l'article;
   - toute reformulation (traduction, précision d'un terme, regroupement) est notée dans un journal de transcription, avec sa justification;
   - les critères du cadre PCC sans critère explicite sont repris du texte de la question, sans les élargir ni les restreindre.
3. **Aucun modèle de langage ne rédige ni ne modifie les critères** : la transcription est entièrement humaine, pour qu'aucune connaissance des études incluses ne puisse s'y glisser.
4. **Gel des transcriptions** : toutes les transcriptions sont consignées par un commit daté **avant** le premier passage de l'IA sur l'ensemble de test. Aucune reformulation n'est permise ensuite.
5. **Seconde transcription sur 5 revues** : une seconde personne, aussi à l'aveugle des études incluses, transcrit indépendamment, selon la même règle, les critères de 5 des 15 revues, tirées au hasard avec une graine consignée. Elle ne voit pas les transcriptions de Benoit. On rapporte :
   - l'accord entre les deux transcriptions, critère par critère, sur l'étendue de chaque critère (même portée, plus large, plus étroite), jugé par les deux codeurs après coup;
   - la sensibilité et la spécificité de l'IA sur ces 5 revues avec chacune des deux versions des critères (§5.4).

   La version de Benoit reste celle de l'analyse principale.
6. **Transparence** : chaque transcription est publiée à côté du texte d'origine de l'article, avec le journal de transcription.

**Autres éléments d'aveugle.**

- L'outil ne voit jamais la norme de référence.
- Les études incluses manquées sont classées par deux évaluateurs, dont au moins un n'a pas participé au développement de l'outil.

### 2.3 Conditions

Les unités d'analyse sont les références, regroupées par revue.

1. **Par défaut** (condition principale) : une exécution de l'IA sur toutes les références, seuils par défaut, sans étalonnage.
2. **Pilote simulé** :
   - tirage aléatoire de 100 références avec une graine consignée;
   - leurs décisions de la norme de référence servent de « décisions humaines du pilote » pour ajuster l'étalonnage isotonique et choisir le seuil d'exclusion, selon la règle préétablie de l'outil (sensibilité visée de 0,95 sur le pilote);
   - l'évaluation porte sur les autres références;
   - cette condition réutilise les sorties de la condition 1, sans nouvel appel au modèle.
3. **Reproductibilité** : deux exécutions de plus sur 10 % des références de chaque revue, tirées au hasard (au moins 200).
4. **Stratégie d'invite** : sur 6 revues tirées au hasard, un appel par référence contre un appel par critère.
5. **Autres fournisseurs** (classificateur rapide, modèle local) : seulement s'ils existent dans la version gelée; sinon, condition non menée.

### 2.4 Tirages

- Les revues de test sont tirées au hasard, en strates par domaine (psychologie; sciences sociales et éducation; santé) et par langue, avec une graine consignée.
- Les échantillons des conditions 2 et 3 et les revues de la condition 4 sont aussi tirés avec des graines consignées.

## 3. Échantillonnage

### 3.1 Données existantes

Le protocole est gelé **avant** l'accès aux données de test : les revues admissibles n'ont pas encore été repérées, et aucune revue de test n'a été tirée ni passée dans l'outil.

Les données de développement (trois jeux SYNERGY : Oud_2018, van_de_Schoot_2018, van_Dis_2020) ont déjà servi et sont exclues de l'ensemble de test. Leurs résultats, publics dans `docs/resultats/`, ont orienté les seuils par défaut et le choix du modèle; ils ne font pas partie du test. **[À DÉCIDER : ajouter ou non 4 à 5 revues de portée à l'ensemble de développement avant le gel.]**

### 3.2 Admissibilité des revues

**Inclusion** :
- revue de portée publiée dans une revue révisée par les pairs entre 2019 et 2026;
- en psychologie, santé mentale, sciences sociales, éducation, travail social, santé publique ou soins (pas purement biomédicale ou clinique fondamentale);
- conforme à la méthode JBI ou à PRISMA-ScR, ou aux deux;
- critères d'admissibilité explicites, ou cadre PCC assez détaillé pour être transformé en critères;
- liste complète des études incluses, avec des références identifiables;
- au moins 10 études incluses;
- l'une des deux conditions suivantes :
  - **strate A** : décisions de tri des titres et résumés disponibles par référence (supplément, OSF, dépôt de données, ou transmises par les auteurs sur demande);
  - **strate B** : stratégie de recherche complète et reproductible (PRISMA-S), dans au moins une base que l'outil peut interroger (PubMed, OpenAlex) ou exporter en RIS (PsycINFO).

**Exclusion** :
- plus de 10 % des études incluses impossibles à apparier à une référence;
- revues portant uniquement sur des sources non textuelles ou non indexées;
- revues de l'ensemble de développement;
- revues dont un membre de l'équipe de validation est auteur. Une analyse de sensibilité pourra les inclure.

### 3.3 Repérage et reconstitution

**Repérage** :
1. Recherche de revues de portée dans OpenAlex, PubMed et PsycINFO; recherche sur OSF de projets de revues de portée qui partagent leurs données de tri; contact des auteurs pour obtenir leurs décisions de tri (strate A).
2. Tirage aléatoire parmi les revues admissibles, en strates comme au §2.4.
3. Sur-échantillonnage du français : au moins 5 revues dont au moins 20 % des références criblées sont en français.
4. Contamination : au moins 5 revues publiées après la fin des données d'entraînement du modèle. **[À DÉCIDER : consigner la date déclarée par le fournisseur.]**

**Reconstitution (strate B)** :
- la stratégie publiée est relancée avec une limite de date égale à la date de recherche d'origine;
- les bases sous abonnement sont importées en RIS, et l'outil dédoublonne (règles version 1, testées sur des données mises de côté d'ASySD : rappel de 0,998 à 1,000, précision de 0,994 à 0,998);
- l'écart entre le nombre reconstitué et le nombre déclaré est rapporté;
- une revue dont l'écart dépasse 20 % est retirée de l'analyse principale et gardée pour une analyse de sensibilité.

### 3.4 Gel de la configuration

Avant le tirage de l'ensemble de test, un commit daté ajoute à ce protocole :
- l'empreinte du commit de l'outil;
- le gabarit `screen_reference` et sa version **[À DÉCIDER : v1, ou une v2 mise au point sur des données distinctes]**;
- le modèle demandé (`claude-haiku-5-5`, effort `low`); la version exacte renvoyée par l'API est consignée à chaque appel;
- les seuils (0,10 et 0,60) et tous les paramètres.

Rien ne change ensuite; toute exécution supplémentaire est déclarée exploratoire.

**Exécution** : toutes les exécutions de test se font dans une courte période, par l'API de traitement par lots du fournisseur. Les réponses brutes sont conservées, pour pouvoir reconstituer chaque décision sans rappeler le modèle.

### 3.5 Taille de l'échantillon

**15 revues de test** : au moins 5 avec une part importante de littérature francophone et au moins 5 publiées après la fin d'entraînement du modèle (une revue peut compter pour les deux), plus l'ensemble de développement.

Justification :
- avec environ 40 études incluses par revue, 15 revues donnent environ 600 références positives;
- avec une corrélation intraclasse supposée de 0,025, l'effet de plan est d'environ 2 (1 + 39 × 0,025 = 1,975), soit environ 304 positifs effectifs;
- pour une sensibilité de 0,95, la demi-largeur de l'intervalle à 95 % est alors d'environ 0,025 (1,96 × √(0,95 × 0,05 / 304)), ce qui suffit pour tester H1, dont le critère est une borne inférieure d'au moins 0,90;
- 15 revues gardent aussi assez de grappes pour estimer la variance entre revues du modèle mixte, qui deviendrait instable sous 10 à 12 revues;
- le nombre final est revu une fois les revues admissibles repérées (nombre médian d'inclusions), avant le tirage, par un amendement daté.

### 3.6 Règle d'arrêt et budget

La collecte s'arrête quand le nombre prévu de revues a été tiré et traité, ou quand le plafond de coût est atteint. **[À DÉCIDER : plafond, proposé à 40 $ US.]**

Estimation, au prix des lots mesuré à environ 0,18 $ US pour 1 000 références (la moitié des 0,36 $ US mesurés en appels individuels) :

| Condition | Hypothèse | Estimation |
|---|---|---|
| 1, par défaut | 15 revues × environ 4 000 références | environ 11 $ US |
| 2, pilote simulé | réutilise les sorties de la condition 1 | 0 $ US |
| 3, reproductibilité | 2 exécutions de plus sur 10 % | environ 2 $ US |
| 4, stratégie d'invite | 6 revues, un appel par critère | environ 11 à 15 $ US |
| Seconde transcription | 5 revues triées de nouveau avec les critères de la seconde personne | environ 4 $ US |
| **Total** | | **environ 30 $ US** |

Si le plafond est atteint, les revues déjà traitées sont analysées, et ce qui manque est rapporté.

## 4. Variables

### 4.1 Variables contrôlées

- Seuils : par défaut, ou fixés sur un pilote simulé.
- Stratégie d'invite : un appel par référence, ou un appel par critère.
- Fournisseur : s'il en existe d'autres.

### 4.2 Variables mesurées

- **Norme de référence** :
  - positifs : toutes les références des études finalement incluses, rapports multiples compris;
  - négatifs : en strate A, les références exclues par les auteurs au tri des titres et résumés; en strate B, toutes les autres références reconstituées. Certaines ont été exclues au texte intégral, ce qui sous-estime la spécificité.
- **Décision de l'IA** : inclure, incertain ou exclure, déduite par l'outil. Une référence est **conservée** quand l'IA l'inclut ou la juge incertaine.
- **Covariables** :
  - domaine;
  - langue de la référence, détectée et consignée par l'outil;
  - publication avant ou après la fin d'entraînement du modèle;
  - présence d'un résumé;
  - strate.

### 4.3 Mesures

**Principale** : sensibilité, soit les positifs conservés sur l'ensemble des positifs, par revue et groupée.

**Secondaires** :
- sensibilité par étude (une étude est retrouvée si au moins une de ses références est conservée);
- spécificité (surtout en strate A);
- proportion de références « incertain »;
- références que l'IA exclurait (charge de travail en mode d'exclusion assistée);
- WSS@95;
- rappel selon la proportion triée, en mode priorisé;
- accord avec les décisions humaines au tri des titres et résumés (pourcentage, kappa de Cohen, AC1 de Gwet, PABAK; strate A);
- calibration (score de Brier, ECE sur 10 classes, pente et ordonnée d'étalonnage, diagramme de fiabilité), avant et après étalonnage;
- reproductibilité : décisions identiques d'une exécution à l'autre, AC1 de Gwet entre exécutions;
- qualité des justifications, sur un échantillon aléatoire stratifié de 300 décisions : bon critère cité; passage cité présent mot pour mot et à l'appui de la décision. L'outil rapporte aussi automatiquement la proportion de citations retrouvées;
- effet du codeur, sur les 5 revues transcrites deux fois : accord entre les transcriptions, et écart de sensibilité et de spécificité entre les deux versions des critères;
- coût et jetons pour 1 000 références, et durée.

## 5. Plan d'analyse

### 5.1 Modèles statistiques

- **Par revue** : sensibilité et spécificité, avec intervalles de Wilson.
- **Groupée** : modèle linéaire généralisé à effets mixtes (lien logit, ordonnée aléatoire par revue). Pour la strate A, modèle bivarié sensibilité-spécificité. Bootstrap en grappes (revues) comme intervalle de confirmation.
- **Comparaisons** (par défaut contre pilote simulé; stratégies d'invite; fournisseurs) : modèles mixtes appariés sur les références, avec un test de McNemar par revue en complément.

### 5.2 Transformations

Aucune hormis le lien logit. Les décisions sont rendues binaires : conservée contre exclue.

### 5.3 Critères d'inférence

- **H1** est appuyée si la sensibilité groupée est d'au moins 0,95 **et** si la borne inférieure de son intervalle de confiance à 95 % (modèle mixte) est d'au moins 0,90.
- **[À DÉCIDER]** Les comparaisons appariées sont bilatérales, à α = 0,05, sans correction pour le petit nombre de comparaisons préspécifiées. Elles sont rapportées avec leur taille d'effet et leur intervalle.

### 5.4 Exclusion de données

- Les revues dont l'écart de reconstitution dépasse 20 % sont retirées de l'analyse principale (analyse de sensibilité).
- Les études manquées classées comme erreurs probables de la norme de référence (catégorie c, §5.6) restent dans l'analyse principale, et sont retirées dans une analyse de sensibilité.
- **Effet du codeur** : sur les 5 revues transcrites deux fois, la sensibilité est aussi calculée avec les critères de la seconde personne. Un écart important serait rapporté comme une limite majeure de l'analyse principale.

### 5.5 Données manquantes

- Les références sans titre ni résumé sont gardées : l'outil les traite comme « incertain » par la règle EF-SEL-07. Leur nombre est rapporté.
- Les réponses de l'IA encore inutilisables après une nouvelle tentative sont comptées comme échecs et rapportées. **[À DÉCIDER]** Dans l'analyse principale, elles comptent comme **conservées**, puisque la personne les trierait de toute façon. Une analyse de sensibilité les compte comme manquées.

### 5.6 Analyse des erreurs

Chaque étude incluse manquée est classée par deux évaluateurs, dont au moins un indépendant du développement de l'outil :

- (a) résumé absent ou peu informatif;
- (b) critère ambigu dans l'article d'origine;
- (c) inclusion discutable dans la revue d'origine (erreur probable de la norme de référence);
- (d) erreur de l'IA (critère mal appliqué, contenu inventé, mauvaise lecture);
- (e) autre.

L'accord entre évaluateurs est rapporté, et les désaccords se règlent par discussion.

### 5.7 Sous-groupes

Avec 15 revues, les sous-groupes sont **descriptifs** : estimations avec intervalles, sans test d'hypothèse.

- domaine;
- langue de la référence (français contre anglais);
- publication avant ou après la fin d'entraînement du modèle;
- présence d'un résumé;
- strate A contre B.

### 5.8 Analyses exploratoires

- Tri du texte intégral, après la V2, pour les revues dont les PDF sont en libre accès.
- Toute analyse absente de ce protocole est rapportée comme exploratoire.

## 6. Autres éléments

- **Logiciel** : revue-portee au commit gelé; analyse en Python (statsmodels) ou en R (lme4). Le code d'analyse est publié.
- **Science ouverte**. Sont publiés, dans un dépôt de données public :
  - les critères transcrits;
  - les gabarits d'invite et les versions exactes du modèle;
  - les décisions de l'IA, avec leur confiance et leur justification;
  - les réponses brutes, sans texte protégé;
  - le code d'analyse.

  Pour les références, seulement des identifiants (DOI, PMID, identifiant OpenAlex), sans titres ni résumés, sauf sous licence ouverte. Prépublication, puis soumission à une revue méthodologique (*Research Synthesis Methods*, *JBI Evidence Synthesis*, *Systematic Reviews*).
- **Déclaration** : STARD 2015 adaptée au contexte, les éléments de déclaration de RAISE 2 (§4), et l'extension de PRISMA sur l'IA si elle paraît avant la soumission.
- **Limites déclarées** : un seul codeur des critères, qui est aussi le développeur de l'outil; l'effet du codeur n'est mesuré que sur 5 revues.
- **Antériorité du protocole** : ce document, gelé par un commit daté dans le dépôt public avant la collecte, tient lieu de protocole préalable. L'article le citera, avec l'empreinte du commit de gel. Il n'y a pas de dépôt OSF (D-100).
- **Éthique** : aucune donnée de participants. Les décisions de tri obtenues des auteurs sont utilisées avec leur accord et citées.
- **Conflit d'intérêts** : le développeur de l'outil fait partie de l'équipe, et il est le seul codeur des critères. Atténuations :
  - ce protocole public, gelé avant la collecte;
  - la règle de transcription, le journal de transcription et le gel des transcriptions avant le passage de l'IA;
  - la seconde transcription indépendante sur 5 revues, et la publication de chaque transcription à côté du texte de l'article;
  - le gel de l'outil avant le test;
  - des évaluateurs indépendants pour l'analyse des erreurs;
  - la publication des résultats, quels qu'ils soient.
- **Historique du développement** : la liste RAISE 2, la fiche de l'outil et le journal de mise au point des gabarits, dans le dépôt. Le gabarit v1 n'a été mis au point sur aucune donnée avant le test.

## Références

- Bossuyt PM, et al. STARD 2015. *BMJ* 2015;351:h5527. **[À VÉRIFIER]**
- Cohen AM, et al. Reducing workload in systematic review preparation using automated citation classification. *JAMIA* 2006;13(2):206–219. **[À VÉRIFIER]**
- De Bruin J, et al. SYNERGY — Open machine learning dataset on study selection in systematic reviews. 2023. doi:10.34894/HE6NAQ
- Flemyng E, et al. Position statement on AI use in evidence synthesis across Cochrane, the Campbell Collaboration, JBI and the Collaboration for Environmental Evidence 2025. *JBI Evid Synth* 2025;23(11):2162–2166. doi:10.11124/JBIES-25-00480
- Gartlehner G, et al. Single-reviewer abstract screening missed 13 percent of relevant studies: a crowd-based, randomized controlled trial. *J Clin Epidemiol* 2020.
- Hair K, et al. The Automated Systematic Search Deduplicator (ASySD). *BMC Biology* 2023;21:189. doi:10.1186/s12915-023-01686-z
- Thomas J, et al. Responsible use of AI in Evidence Synthesis (RAISE 2026) 2: building and evaluating AI evidence synthesis tools. Version 4, 2026. OSF, doi:10.17605/OSF.IO/FWAUD
- Tran VT, et al. Sensitivity and specificity of using GPT-3.5 Turbo models for title and abstract screening. *Ann Intern Med* 2024. doi:10.7326/M23-3389
- Vembye MH, et al. GPT models can function as highly reliable second screeners of titles and abstracts. *Psychological Methods* 2025. doi:10.1037/met0000769

## Amendements

Aucun : le protocole n'est pas encore gelé.
