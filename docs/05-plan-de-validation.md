# 05 — Plan de validation

> **Statut** : ébauche de protocole du 7 octobre 2026, détaillée dans le **protocole versionné [09-protocole-validation.md](09-protocole-validation.md)**, gelé par un commit daté avant toute évaluation sur l'ensemble de test (pas de dépôt OSF, D-100), et à mener à une publication méthodologique.
> **Pourquoi** : l'énoncé de position conjoint Cochrane, Campbell, JBI et CEE (2025) demande aux développeurs d'outils de publier leurs données de validation et leurs limites; RAISE demande aux utilisateurs de justifier que l'outil convient à leur usage. Sans cette étude, l'outil ne peut pas être cité honnêtement dans une section méthode. Voir [01-etat-de-l-art.md §5](01-etat-de-l-art.md#5-normes-et-recommandations).

## 1. Titre provisoire

*Un grand modèle de langage comme second réviseur au tri des titres et résumés dans les revues de portée en psychologie, sciences sociales et santé : étude rétrospective de précision sur des revues publiées.*

## 2. Justification

- Presque toutes les évaluations du tri par grand modèle de langage portent sur des revues systématiques biomédicales (voir [01-etat-de-l-art.md §4](01-etat-de-l-art.md#4-ce-que-disent-les-données-sur-les-grands-modèles-de-langage)).
- Les revues de portée ont des critères plus larges, plus conceptuels et plus évolutifs; les rares données disponibles suggèrent des comportements différents (trop restrictifs ou trop inclusifs selon le modèle).
- **Aucune donnée** n'existe sur la littérature en français.
- La sensibilité d'un grand modèle de langage dépend fortement de la rédaction des critères (Covidence : 66 à 98 %), d'où l'intérêt de mesurer l'effet d'un **essai pilote d'étalonnage** — élément central de revue-portee.

## 3. Objectifs

### 3.1 Objectif principal
Estimer la **sensibilité** (rappel) du réviseur IA de revue-portee au tri des titres et résumés, au seuil par défaut favorisant la sensibilité, par rapport aux études finalement incluses dans des revues de portée publiées.

**Hypothèse principale (fixée au protocole)** : sensibilité groupée ≥ 0,95, avec une borne inférieure de l'intervalle de confiance à 95 % ≥ 0,90. Comme repère, un réviseur humain unique manque environ 13 % des études pertinentes (Gartlehner et al., 2020), soit une sensibilité d'environ 0,87.

### 3.2 Objectifs secondaires
1. **Charge de travail** : proportion de références qu'un humain n'aurait pas eu à examiner en mode d'exclusion assistée; WSS@95; proportion triée avant d'atteindre 95 % de rappel en mode priorisé.
2. **Spécificité et accord** avec les décisions humaines au tri des titres et résumés, quand celles-ci sont disponibles.
3. **Calibration** de la confiance, avant et après étalonnage sur un pilote simulé.
4. **Effet de l'étalonnage** : seuils par défaut contre seuils fixés sur un pilote de 100 références.
5. **Reproductibilité** : accord entre exécutions répétées.
6. **Langue** : performance sur les références en français contre en anglais.
7. **Stratégie d'invite** : un appel par référence contre un appel par critère.
8. **Fournisseurs** : Claude contre classificateur rapide (V2) et modèle local (V3), si disponibles au moment de l'étude.
9. **Qualité des justifications** : exactitude du critère cité et du passage cité.
10. **Coût** par 1 000 références.

### 3.3 Objectif exploratoire (après la V2)
Sensibilité et spécificité au tri du **texte complet**, pour les revues où les PDF sont accessibles en libre accès.

## 4. Devis

Étude rétrospective de **précision diagnostique** par simulation : l'outil est appliqué à l'ensemble des références criblées (ou reconstituées) de revues de portée déjà publiées, et ses décisions sont comparées à une **norme de référence** tirée de ces revues. Aucun participant humain; seulement de la littérature publiée et des données publiques.

**Lignes directrices de déclaration** : STARD 2015 (adaptée au contexte), recommandations d'évaluation de RAISE 2, et la future mise à jour PRISMA sur l'IA si elle paraît avant la soumission.

## 5. Sélection des revues

### 5.1 Critères d'admissibilité

**Inclusion**
1. Revue de portée (ou « scoping review ») publiée dans une revue révisée par les pairs entre **2019 et 2026**.
2. Domaine : psychologie, santé mentale, sciences sociales, sciences de l'éducation, travail social, santé publique ou soins (à l'exclusion des revues purement biomédicales ou cliniques fondamentales).
3. Se déclare conforme à la méthode JBI et/ou à PRISMA-ScR.
4. Critères d'admissibilité explicites, ou cadre PCC suffisamment détaillé pour être transformé en critères.
5. **Liste complète des études incluses** avec références identifiables (DOI, PMID ou référence complète).
6. Au moins **10 études incluses** au tri final.
7. Au moins une des conditions suivantes :
   - **Strate A** — décisions de tri des titres et résumés disponibles au niveau de la référence (supplément, OSF, dépôt de données, ou transmises par les auteurs sur demande);
   - **Strate B** — stratégie de recherche complète et reproductible (PRISMA-S) dans au moins une base interrogeable par l'outil (PubMed, OpenAlex) ou disponible en RIS (PsycINFO), permettant de reconstituer l'ensemble criblé.

**Exclusion**
1. Revues dont plus de 10 % des études incluses ne peuvent être appariées à une référence bibliographique.
2. Revues portant uniquement sur des sources non textuelles ou non indexées (ex. sites web, documents de politique non indexés).
3. Revues utilisées pour développer les invites ou fixer les seuils par défaut (**ensemble de développement**, section 5.3).
4. Revues dont un membre de l'équipe de validation est auteur (pour éviter le biais de connaissance préalable); une analyse de sensibilité pourra les inclure.

### 5.2 Repérage et échantillonnage

1. Recherche dans OpenAlex, PubMed et PsycINFO de revues de portée correspondant aux critères; recherche sur OSF de projets de revues de portée qui partagent leurs données de tri; contact des auteurs pour obtenir les décisions de tri (strate A).
2. Constitution d'une base de revues admissibles, puis **tirage aléatoire stratifié** par domaine (psychologie, sciences sociales et éducation, santé) et par langue, avec une graine consignée.
3. **Sur-échantillonnage du français** : au moins **6 revues** dont au moins 20 % des références criblées sont en français (revues québécoises, françaises, belges ou suisses, ou revues indexées dans Érudit ou Cairn).
4. **Contamination** : au moins un tiers des revues de l'ensemble de test doivent avoir été publiées **après la date de fin des données d'entraînement** du modèle évalué (le modèle n'a pas pu les « voir »). La date de fin d'entraînement déclarée par le fournisseur est consignée.

### 5.3 Ensembles de développement et de test

| Ensemble | Contenu | Usage |
|---|---|---|
| **Développement** | 3 jeux SYNERGY en psychologie (CC0) + 4 à 5 revues de portée admissibles | Mise au point des invites, choix des seuils par défaut, tests de la V1 |
| **Test** | Revues tirées selon 5.2 (taille en section 8) | Évaluation **une seule fois**, après gel des invites, des seuils par défaut et de la version du code |

**Gel** : avant l'évaluation de l'ensemble de test, on consigne dans le protocole (09), par un commit daté : empreinte du commit, versions des gabarits d'invite, modèle(s) et version(s) exactes, seuils par défaut, paramètres. Aucune modification n'est permise après; toute exécution supplémentaire est déclarée comme exploratoire.

## 6. Procédure

### 6.1 Reconstitution de l'ensemble criblé
- **Strate A** : utilisation directe des références criblées.
- **Strate B** : réexécution de la stratégie publiée avec une **limite de date égale à la date de recherche d'origine**; import RIS si la base est sous abonnement; dédoublonnage par l'outil. L'écart entre le nombre de références reconstituées et le nombre déclaré dans le diagramme d'origine est rapporté; une revue dont l'écart dépasse 20 % est exclue de l'analyse principale (analyse de sensibilité).

### 6.2 Opérationnalisation des critères
Deux membres de l'équipe, **à l'aveugle de la liste des études incluses**, transcrivent indépendamment les critères publiés dans le format de l'outil (codes, textes, exemples tirés uniquement de l'article), puis s'entendent. Aucune reformulation n'est permise après avoir vu les résultats. Le texte final des critères est publié avec les données.

### 6.3 Exécution
Pour chaque revue de l'ensemble de test :
1. **Condition « par défaut »** : tri de toutes les références par le réviseur IA, seuils par défaut, sans étalonnage.
2. **Condition « pilote simulé »** : tirage aléatoire de 100 références; les décisions de la norme de référence servent de « décisions humaines du pilote » pour l'étalonnage isotonique et le choix du seuil selon la règle fixée au protocole (sensibilité cible 0,95 sur le pilote); évaluation sur les références restantes.
3. **Reproductibilité** : nouvelle exécution sur un échantillon aléatoire de 10 % (au moins 200 références) à deux reprises.
4. **Stratégie d'invite** : sur un sous-ensemble de revues tiré au hasard (au moins 8), comparaison un appel par référence contre un appel par critère.
5. **Fournisseurs secondaires** (si disponibles) : mêmes références, mêmes critères.

### 6.4 Norme de référence
- **Positifs** : toutes les références correspondant aux études finalement incluses (y compris les rapports multiples).
- **Négatifs** : strate A — références exclues au tri des titres et résumés par les auteurs; strate B — toutes les autres références reconstituées (approximation : certaines ont été exclues au texte complet, ce qui **sous-estime la spécificité**).
- **Justification** : en revue de portée, l'erreur grave est de manquer une étude qui aurait été incluse; la sensibilité par rapport aux inclusions finales est donc la mesure principale.

### 6.5 Analyse des erreurs
Chaque étude incluse manquée par l'IA est examinée indépendamment par deux évaluateurs, dont au moins un **qui n'a pas participé au développement de l'outil**, et classée : (a) résumé absent ou non informatif; (b) critère ambigu dans l'article d'origine; (c) inclusion discutable dans la revue d'origine (erreur probable de la norme de référence); (d) erreur de l'IA (critère mal appliqué, hallucination, mauvaise lecture); (e) autre. Accord interévaluateurs rapporté; désaccords résolus par discussion.

### 6.6 Qualité des justifications
Sur un échantillon aléatoire de 300 décisions (stratifié : inclusions, exclusions, incertains), deux évaluateurs jugent : le critère cité est-il le bon? le passage cité existe-t-il textuellement et appuie-t-il la décision? Proportions et accord rapportés.

## 7. Mesures

| Mesure | Définition | Niveau |
|---|---|---|
| **Sensibilité** (principale) | VP / (VP + FN), positifs = références des études incluses; une référence « incertain » compte comme non exclue | Par revue; groupée |
| Sensibilité par étude | Une étude est retrouvée si au moins une de ses références est non exclue | Par revue; groupée |
| Spécificité | VN / (VN + FP) (strate A surtout) | Par revue; groupée |
| Proportion « incertain » | Part des références classées incertaines | Par revue |
| **Charge de travail évitée** | Proportion de références exclues par l'IA au seuil (en mode d'exclusion assistée) | Par revue |
| WSS@95 | Travail économisé par rapport au tri aléatoire à 95 % de rappel (Cohen et al., 2006) | Par revue |
| Rappel selon la proportion triée | Courbe de rappel en mode priorisé | Par revue |
| **Accord** | Pourcentage, kappa de Cohen, AC1 de Gwet, PABAK, IA contre humains (strate A) | Par revue; groupé |
| **Calibration** | Score de Brier, erreur d'étalonnage attendue (ECE, 10 classes), pente et ordonnée d'étalonnage, diagramme de fiabilité; avant et après étalonnage | Groupée |
| **Reproductibilité** | Proportion de décisions identiques entre exécutions; AC1 de Gwet entre exécutions | Groupée |
| Coût | Jetons et montant par 1 000 références; durée | Par revue |
| Qualité des justifications | Section 6.6 | Groupée |

## 8. Taille d'échantillon

- Pour estimer une sensibilité de 0,95 avec une demi-largeur d'intervalle de 0,02 : n = 1,96² × 0,95 × 0,05 / 0,02² ≈ **456 références positives** sans effet de grappe.
- Les références sont regroupées par revue. Avec environ 40 études incluses par revue et un coefficient de corrélation intraclasse supposé de 0,025, l'effet de plan est d'environ 2, soit environ **900 références positives**.
- D'où une cible de **24 à 30 revues** dans l'ensemble de test (dont au moins 6 avec une part importante de littérature francophone), plus 4 à 5 revues de développement.
- Hypothèses (nombre médian d'inclusions, corrélation intraclasse) à revoir après le repérage (5.2); la taille finale est fixée au protocole avant le tirage. Le protocole (09) retient 15 revues (choix de Benoit, 2026-10-09).

## 9. Analyse statistique

- **Par revue** : sensibilité et spécificité avec intervalles de Wilson.
- **Groupée** : modèle linéaire généralisé à effets mixtes (logit, effet aléatoire de revue); pour la strate A, modèle bivarié sensibilité-spécificité. Intervalles par bootstrap en grappes (revues) comme analyse de confirmation.
- **Comparaisons** (par défaut contre pilote simulé; stratégies d'invite; fournisseurs) : modèles mixtes appariés sur les références; test de McNemar par revue en complément.
- **Sous-groupes fixés au protocole** : domaine; langue de la référence (FR / EN); publication avant ou après la date de fin d'entraînement du modèle; présence d'un résumé; strate A / B.
- **Analyses de sensibilité** : exclusion des études manquées classées (c) en 6.5; inclusion des revues exclues pour écart de reconstitution; inclusion des revues à auteurs de l'équipe.
- **Données manquantes** : références sans titre ni résumé conservées (traitées comme « incertain » par la règle EF-SEL-07) et rapportées.
- Logiciel : Python (statsmodels) ou R (lme4), code publié.

## 10. Considérations éthiques et juridiques

- Aucune donnée de participants; aucune approbation éthique requise (à confirmer auprès d'un comité si une revue le demande).
- Les décisions de tri obtenues des auteurs sont utilisées avec leur accord et citées.
- **Droits d'auteur des résumés** : les données publiées contiendront les **identifiants** (DOI, PMID, identifiant OpenAlex) et les décisions, **pas** les titres et résumés, sauf pour les sources sous licence ouverte (ex. OpenAlex CC0 pour les métadonnées).
- **Conflit d'intérêts** : le développeur de l'outil (Benoit Plante) fait partie de l'équipe; atténuation : protocole public daté, gel avant le test, évaluateurs indépendants pour l'analyse des erreurs, publication quels que soient les résultats.

## 11. Science ouverte

- Protocole détaillé ([09-protocole-validation.md](09-protocole-validation.md)) versionné dans le dépôt public et gelé par un commit daté **avant** le tirage de l'ensemble de test. Pas de dépôt OSF (choix de Benoit, D-100).
- Publication dans un dépôt de données public : critères transcrits, gabarits d'invite, versions exactes, décisions de l'IA avec confiance et justification, réponses brutes (sans texte protégé), code d'analyse.
- Prépublication puis soumission à une revue méthodologique (ex. *Research Synthesis Methods*, *JBI Evidence Synthesis*, *Systematic Reviews*).
- Résultats repris dans `docs/resultats/` et cités dans la section méthode générée par l'outil.

## 12. Calendrier indicatif (par jalons, pas par dates)

| Jalon | Activité |
|---|---|
| Pendant la V1 | Ensemble de développement : banc SYNERGY (tranche 1.6), réglage des invites et des seuils par défaut |
| Fin de la V1 | Repérage des revues admissibles; contact des auteurs (strate A); gel du protocole (09) |
| Début de la V2 | Gel; tirage et évaluation de l'ensemble de test au tri des titres et résumés |
| V2 | Analyses, rédaction; exploration texte complet |
| V3 | Mise à jour avec modèle local et classificateur (étude complémentaire) |

## 13. Risques et atténuation

| Risque | Atténuation |
|---|---|
| Peu de revues de portée partagent leurs décisions de tri (strate A rare) | Strate B par reconstitution; contact systématique des auteurs; jeux SYNERGY en développement |
| Reconstitution imparfaite des recherches | Seuil d'écart de 20 %, analyse de sensibilité |
| Contamination (le modèle connaît la revue) | Sous-groupe postérieur à la date de fin d'entraînement |
| Retrait ou changement du modèle pendant l'étude | Version exacte consignée; exécution complète dans une fenêtre courte; réponses brutes conservées |
| Norme de référence imparfaite | Analyse des erreurs (catégorie c) et analyse de sensibilité |
| Coût | Estimation préalable avec l'outil; traitement par lots; budget fixé au protocole |
| Biais du développeur | Section 10 |

## 14. Références principales

- Bossuyt PM et al. STARD 2015. *BMJ* 2015;351:h5527.
- Cohen AM et al. Reducing workload in systematic review preparation using automated citation classification. *JAMIA* 2006;13(2):206–219.
- De Bruin J et al. SYNERGY — Open machine learning dataset on study selection in systematic reviews. 2023. [DOI 10.34894/HE6NAQ](https://doi.org/10.34894/HE6NAQ)
- Flemyng E et al. Position statement on AI use in evidence synthesis (Cochrane, Campbell, JBI, CEE). *JBI Evid Synth* 2025;23(11):2162–2166. [DOI 10.11124/JBIES-25-00480](https://doi.org/10.11124/JBIES-25-00480)
- Gartlehner G et al. Single-reviewer abstract screening missed 13 percent of relevant studies: a crowd-based, randomized controlled trial. *J Clin Epidemiol* 2020. ([notice](https://cris.maastrichtuniversity.nl/en/publications/single-reviewer-abstract-screening-missed-13-percent-of-relevant-/))
- Thomas J et al. RAISE: Guidance and Recommendations. OSF, 2025 (v4, 2026). [DOI 10.17605/OSF.IO/FWAUD](https://doi.org/10.17605/OSF.IO/FWAUD)
- Tran VT et al. Sensitivity and specificity of using GPT-3.5 Turbo models for title and abstract screening. *Ann Intern Med* 2024. [DOI 10.7326/M23-3389](https://doi.org/10.7326/M23-3389)
- Vembye MH et al. GPT models can function as highly reliable second screeners of titles and abstracts. *Psychological Methods* 2025. [DOI 10.1037/met0000769](https://doi.org/10.1037/met0000769)

*Les références de STARD 2015 et de Cohen et al. (2006) sont citées de mémoire documentaire et doivent être revérifiées avant le gel du protocole.*
