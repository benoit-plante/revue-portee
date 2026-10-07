# 01 — État de l'art

> **Statut** : recherche documentaire réalisée le 7 octobre 2026 à partir des sites officiels, journaux des modifications, dépôts de paquets (PyPI, CRAN) et articles révisés par les pairs.
> **Convention** : chaque affirmation est suivie de sa source. La mention **[non vérifié]** signale ce qui n'a pas pu être confirmé à une source primaire. Les prix sont en dollars américains sauf indication contraire et changent souvent : les revérifier avant de les citer.
> **Limites de la recherche** : l'API GitHub et certaines pages (PubMed/PMC, OSF, Abstrackr) étaient inaccessibles depuis l'environnement de recherche; les dates de version proviennent alors de PyPI, CRAN, Zenodo ou des sites des éditeurs.

## 1. Synthèse

- **Aucun outil repéré ne versionne les critères d'inclusion et la grille d'extraction en signalant les références touchées par un changement.** Elicit et Nested Knowledge permettent de modifier les critères et de refaire le tri, mais sans historique de versions documenté **[non vérifié en profondeur]**. C'est le créneau principal de revue-portee.
- **Les seuls outils libres actifs** pour le tri sont ASReview (Apache-2.0, apprentissage actif, sans grand modèle de langage) et Colandr (dorsal sous licence MIT). Parmi les projets libres à base de grands modèles de langage, prismAId (AGPL-3.0), AIscreenR (GPL-3) et LatteReview (CC BY-NC-ND, donc non libre au sens OSI) sont les plus actifs.
- **Les plateformes commerciales** ajoutent rapidement des fonctions d'IA générative, y compris l'exclusion automatique (DistillerSR, Elicit en mode « strict », Covidence pour les ECR), mais **divulguent rarement le modèle et sa version**, ce qui complique la déclaration exigée par RAISE.
- **Presque toute la validation porte sur des revues biomédicales.** Pour la psychologie et les sciences sociales, les données se limitent à quelques études (Vembye et al., 2025; Hilkenmeier et al., 2025). Pour le français, aucune donnée spécifique n'a été trouvée.
- **Normes** : RAISE en est à sa version 4 (mars 2026) et est endossée par Cochrane, Campbell, JBI et CEE (énoncé de position conjoint, novembre 2025). **PRISMA-ScR est en cours de mise à jour**, avec une nouvelle version annoncée pour 2026 mais non publiée au 7 octobre 2026. Le chapitre 10 du manuel JBI (revues de portée) a été remplacé par une version 2026.
- **API des sources** : OpenAlex exige désormais une clé d'API et facture au-delà d'une allocation quotidienne gratuite (depuis le 24 février 2026); Crossref a réduit ses limites de débit le 1er décembre 2025. Les deux changements touchent directement l'architecture et l'environnement de développement.

## 2. Outils de tri et de gestion de revues

### 2.1 Tableau comparatif

| Outil | Étapes couvertes | IA | Exclusion automatique | Licence / prix | Activité récente |
|---|---|---|---|---|---|
| **ASReview LAB** | Tri titres et résumés; détection des doublons (v3) | Apprentissage actif; modèle multilingue; pas de grand modèle de langage génératif | Non (décision humaine; suggestions d'arrêt) | Apache-2.0, gratuit | v3.0.8, 18 juin 2026 |
| **Rayyan** | Doublons, titres et résumés, texte complet, extraction, diagramme PRISMA | Prédictions de pertinence; ResearchPilot (réviseur IA, extraction) | Non (l'IA « ne remplace jamais » la décision) | Propriétaire; gratuit (3 revues) à 41,67 $/licence/mois; IA avancée sur forfaits institutionnels | Aide mise à jour 27 mai 2026 |
| **Covidence** | Import, titres et résumés, texte complet, extraction | Tri par pertinence; classificateur d'ECR; suggestions d'extraction par grand modèle | Oui, pour les non-ECR (revues médicales) | Propriétaire; 339 $/an pour une revue | Page IA mise à jour 11 févr. 2026 |
| **DistillerSR** | Recherche (service), tri, extraction | IA générative (Smart Screening, Smart Evidence Extraction) | Oui (mode entièrement automatisé possible) | Propriétaire; 19,95 $ à 194 $/mois, institutionnel sur devis | Nouvelles du 22 sept. 2026 |
| **EPPI-Reviewer** | Tri, codage, extraction, cartographie | « Robots » à grand modèle de langage; apprentissage automatique classique | Non documenté pour l'usage réel (« évaluation seulement ») | Propriétaire; 10 £/utilisateur/mois + 35 £/revue partagée/mois; crédits de modèle en sus | v6.18.1.0, 27 juill. 2026 |
| **CADIMA** | Protocole à déclaration | Aucune | Non | Gratuit; licence du code non trouvée | v2.2.4.2, avril 2023 (inactif) |
| **Colandr** | Protocole, tri, texte complet, extraction, visualisation (v2) | Apprentissage actif | Non documenté | MIT (dorsal), gratuit | Présentation « Colandr 2.0 » à FOSDEM 2026 |
| **SysRev** | Tri, extraction | Étiquetage automatique par grand modèle de langage | **[non vérifié]** | Forfaits premium; prix et licence **[non vérifiés]** | Guide CMU mis à jour 27 mai 2026 |
| **Abstrackr** | Tri titres et résumés | SVM, apprentissage actif | Non | Code sur GitHub; licence **[non vérifiée]** | Site inaccessible; **à considérer comme abandonné [non vérifié]** |
| **SWIFT-ActiveScreener** | Tri, conflits, extraction, rapports PRISMA | Apprentissage actif + estimation du rappel pour l'arrêt | Non documenté | Propriétaire, prix non publics | Mises à jour listées en mars 2026 |
| **Research Screener** | Titres et résumés | Classement par apprentissage automatique | Non documenté | 250 $ AU/projet | Date de version non trouvée |

### 2.2 Fiches détaillées

#### ASReview LAB (Université d'Utrecht)
- **Couverture** : tri des titres et résumés; la version 3.0 ajoute la détection automatique des doublons et des étiquettes modifiables ([PyPI](https://pypi.org/project/asreview/); [annonce UU](https://www.uu.nl/en/news/asreview-30-now-available)). Ni protocole, ni texte complet, ni extraction.
- **IA** : apprentissage actif (modèles « ELAS » : Ultra par défaut, Multilingual, Heavy); pas de grand modèle de langage génératif dans la documentation ([documentation des modèles](https://asreview.readthedocs.io/en/latest/lab/models.html)). La version 2 (15 mai 2025) a ajouté le tri par foule, les agents multiples et des outils d'explicabilité ([annonce UU](https://www.uu.nl/en/news/launch-asreviewlab-v2); [article](https://pmc.ncbi.nlm.nih.gov/articles/PMC12416088)). L'extension Dory ajoute des modèles de traitement du langage récents ([UU](https://www.uu.nl/en/news/timo-van-der-kuils-first-paper-asreview-dory-bringing-new-and-exciting-models-to-asreview-lab-is)).
- **Limites pour nous** : le modèle multilingue couvre « plus de 100 langues » sans que le français soit évalué spécifiquement; le gain de travail est plus faible pour les revues larges qui ne portent pas sur des interventions ([Spiero et al., 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12657655)) — ce qui est justement le cas des revues de portée.
- **Licence et activité** : Apache-2.0; v3.0 annoncée le 15 avril 2026, v3.0.8 publiée le 18 juin 2026 ([PyPI](https://pypi.org/project/asreview/)).
- **Intérêt pour revue-portee** : référence méthodologique pour l'apprentissage actif et les critères d'arrêt; ses **jeux de données SYNERGY** (26 revues, 169 288 références étiquetées, dont 7 en psychologie, licence CC0; [dépôt](https://github.com/asreview/synergy-dataset); [DOI 10.34894/HE6NAQ](https://doi.org/10.34894/HE6NAQ)) serviront aux tests de performance (voir [05-plan-de-validation.md](05-plan-de-validation.md)).

#### Rayyan
- **Couverture** : doublons, titres et résumés, texte complet (forfait Advanced), extraction, diagrammes PRISMA (forfait Essential et plus) ([tarifs](https://www.rayyan.ai/pricing)).
- **IA** : prédictions de pertinence (gratuit); ResearchPilot (réviseur IA, analyse, extraction automatique depuis les PDF), qui « suggère, explique et met en évidence, mais ne remplace jamais vos décisions » ([aide, 27 mai 2026](https://help.rayyan.ai/hc/en-us/articles/28790380408337)); l'agent IA peut agir comme réviseur indépendant à l'aveugle ([billet, 27 juin 2025](https://www.rayyan.ai/post/how-to-screen-articles-using-ai-agents-in-rayyan)).
- **Limites** : code fermé; ResearchPilot réservé aux forfaits institutionnels; modèle utilisé et prise en charge du français non documentés **[non vérifié]**.
- **Prix** : gratuit (3 revues); Essential 4,99 $/siège/mois; Advanced 8,33 $/siège/mois (annuel); Business 41,67 $/licence/mois, minimum 2 500 $/an ([tarifs](https://www.rayyan.ai/pricing)).

#### Covidence
- **Couverture** : import, tri en deux temps, extraction ([aperçu des fonctions d'IA](https://support.covidence.org/help/overview-of-all-automation-ai-features-available-in-covidence)). Dédoublonnage, évaluation de qualité et export PRISMA non confirmés sur une page officielle **[non vérifié]**.
- **IA** : tri par pertinence (apprentissage actif); classificateur d'ECR qui peut déplacer automatiquement les non-ECR vers « non pertinent »; suggestions d'extraction par grand modèle de langage. **Point notable** : Covidence a testé le tri par grand modèle de langage selon les critères d'admissibilité et **a choisi de ne pas le publier**, le rappel variant de 66 % à 98 % selon les revues et dépendant « fortement de la façon dont les critères étaient rédigés » ([Covidence AI](https://www.covidence.org/ai/)). Ce constat appuie notre choix d'un essai pilote d'étalonnage obligatoire.
- **Prix** : 339 $/an pour une revue, 907 $/an pour trois ([tarifs](https://www.covidence.org/pricing/)).

#### DistillerSR
- **IA** : Smart Screening (10 septembre 2026), automatisable entièrement (lots jusqu'à 100 000 résumés) ou avec humain dans la boucle, avec « une justification entièrement traçable pour chaque décision »; exactitude de 90,1 % annoncée lors du pilote ([communiqué](https://www.newswire.com/news/distillersr-launches-regulatory-grade-smart-screening-for-titles-and-abstracts)). Smart Evidence Extraction depuis le 8 avril 2026 ([nouvelles](https://www.distillersr.com/about/news/newsreleases)).
- **Limites** : orienté industrie et réglementaire; code fermé; IA réservée aux forfaits supérieurs.
- **Prix** : étudiant 19,95 $/mois; professeur 94 $/mois; projet de recherche 194 $/mois ([tarifs](https://www.distillersr.com/pricing/student-pricing)).

#### EPPI-Reviewer (EPPI Centre, UCL)
- **IA** : « robots » à grand modèle de langage qui appliquent des codes aux titres, résumés ou PDF. Le codage du robot est enregistré **au nom du robot**, distinct du codage humain; le raisonnement du modèle n'est pas conservé, seule la valeur finale l'est. La documentation précise : à utiliser « pour évaluation seulement » et non dans de vraies revues sans en avoir testé l'exactitude; changer de modèle peut nuire à la reproductibilité ([aide sur les grands modèles](https://eppi.ioe.ac.uk/cms/Default.aspx?tabid=3921)).
- **Activité** : v6.18.1.0 du 27 juillet 2026, qui ajoute de nouveaux modèles et en retire d'autres ([journal des modifications](https://eppi.ioe.ac.uk/cms/er/Help/Version-History-Announcements/Latest-Changes-27-07-2026-V61810)). Cette rotation fréquente des modèles illustre le **risque de reproductibilité** que revue-portee doit gérer (consigner la version exacte du modèle, conserver les réponses brutes).
- **Prix** : 10 £/utilisateur/mois + 35 £/mois par revue partagée; gratuit pour les auteurs Cochrane et Campbell ([tarifs](https://eppi.ioe.ac.uk/cms/er4/About/Fees)); crédits de modèle achetés séparément depuis février 2025 ([aide](https://eppi.ioe.ac.uk/cms/Default.aspx?tabid=2935)).

#### CADIMA
- Conçu pour couvrir tout le processus, du protocole à la déclaration ([Kohl et al., 2018](https://environmentalevidencejournal.biomedcentral.com/track/pdf/10.1186/s13750-018-0115-5)); aucune IA; interface anglaise; dernière version 2.2.4.2 en avril 2023, donc **vraisemblablement plus développé** ([site](https://www.cadima.info/)).

#### Colandr
- Planification, tri avec dédoublonnage, texte complet, extraction ([JMLA, 2021](https://jmla.pitt.edu/ojs/jmla/article/download/1263/1363?inline=1)); Colandr 2.0 ajoute visualisation et flux de travail vérifiables ([FOSDEM 2026](https://fosdem.org/2026/schedule/event/colandr-sifting-through-the-evidence)). Dorsal sous licence MIT ([GitHub](https://github.com/datakind/permanent-colandr-back)). Date du dernier commit **[non vérifiée]**. Limites rapportées en 2021 : doublons exacts seulement, téléversement des PDF un à un.

#### SysRev, Abstrackr, SWIFT, Research Screener
- **SysRev** : étiquetage automatique par grand modèle de langage, facturé à la référence (environ 0,01 $ à 0,04 $ par citation selon le modèle) ([FAQ CMU](https://guides.library.cmu.edu/sysrev/faq)); licence et grille tarifaire **[non vérifiées]**.
- **Abstrackr** : SVM avec apprentissage actif ([Gates et al., 2018](https://link.springer.com/article/10.1186/s13643-018-0707-8)); site inaccessible, statut **[non vérifié]**; à traiter comme un outil historique.
- **SWIFT-Review** (gratuit, dernière version documentée 1.43 en 2019) et **SWIFT-ActiveScreener** (apprentissage actif + estimation du rappel pour décider quand arrêter; prix non publics) ([Sciome](https://www.sciome.com/swift-activescreener/)). Intérêt : l'**estimation statistique du rappel** comme règle d'arrêt.
- **Research Screener** : classement par apprentissage automatique, 250 $ AU par projet ([site](https://www.researchscreener.com/); validation : [Chai et al., 2021](https://link.springer.com/article/10.1186/s13643-021-01635-3)).

## 3. Outils « natifs IA » et projets libres à base de grands modèles de langage

### 3.1 Outils commerciaux

#### Elicit
- **Couverture** : recherche sémantique (plafonnée à 500 articles; Elicit reconnaît qu'une revue de niveau réglementaire exige encore des recherches par mots-clés), tri selon des critères générés par l'IA, tri du texte complet avec citation du passage, extraction avec citations ([blogue](https://elicit.com/blog/systematic-review); [aide](https://support.elicit.com/en/articles/14759157-full-text-screening-in-elicit-systematic-reviews)). Critères « stricts » qui excluent automatiquement, avec possibilité de renverser la décision (19 décembre 2025) ([billet](https://elicit.com/blog/introducing-strict-screening-and-80-paper-reports)). Diagrammes PRISMA 2020, double révision et suivi des motifs d'exclusion depuis le 26 août 2026, seulement sur les forfaits Enterprise et Scale ([aide](https://support.elicit.com/en/articles/15018527-elicit-systematic-review-now-supports-prisma-2020-guidelines)).
- **Traçabilité** : citations et explications affichées, mais **modèle et version non divulgués**.
- **Performance** : chiffres de l'éditeur : rappel de 93,6 % au tri sur 58 revues ([évaluation](https://elicit.com/blog/how-we-evaluated-elicit-systematic-review)). Étude indépendante en psychologie : exactitude d'extraction de 81,4 % pour Elicit contre 86,7 % pour les humains, différence non significative; quand Elicit et l'humain s'accordaient, ils avaient raison dans 100 % des cas (Hilkenmeier et al., *Social Science Computer Review*, 2025, [DOI 10.1177/08944393251404052](https://doi.org/10.1177/08944393251404052)).
- **Prix** : gratuit; Pro 49 $/mois; Scale 169 $/mois; Enterprise sur devis ([tarifs](https://elicit.com/pricing)).

#### Laser AI (Evidence Prime)
- Dédoublonnage, tri priorisé par l'IA, suggestions d'extraction avec mise en évidence de la source; « n'entraîne jamais ses modèles sur les données des clients » ([site](https://www.laser.ai/)). Modèle utilisé et affichage de la confiance **[non vérifiés]**. 3 000 $ par projet ou par utilisateur par an ([tarifs](https://www.laser.ai/pricing)).
- **Retenu par Cochrane** (avec Nested Knowledge) parmi 48 candidatures pour son étude de plateforme d'IA (17 mars 2026); résultats attendus fin 2026 ([Cochrane](https://www.cochrane.org/about-us/news/cochrane-announces-selected-ai-tools-innovative-platform-study)). **À surveiller** : ces résultats seront une référence de comparaison.

#### Nested Knowledge
- Import, tri, étiquetage, extraction, synthèse (y compris méta-analyse en réseau), éditeur de manuscrit ([site](https://about.nested-knowledge.com/)).
- **Smart Screener** : réponse oui/non pour chaque critère, sans entraînement, avec annotations; limites de 5 000 résumés et 1 000 textes complets ([documentation, 3 août 2026](https://about.nested-knowledge.com/docs/smart-screener/)). **Robot Screener** : modèle entraîné sur les décisions de l'équipe. Validation de l'éditeur : Smart Screener sensibilité 0,99, **spécificité 0,21**; extraction 72,9 % ([études de validation](https://about.nested-knowledge.com/docs/validation-studies-of-ai-tools-in-nested-knowledge/)). Le couple sensibilité très élevée / spécificité faible illustre le compromis que nos seuils devront rendre explicite.
- **Prix** : 295 $ à 695 $/utilisateur/mois; tarifs universitaires et première revue gratuite ([tarifs](https://about.nested-knowledge.com/pricing/)).

#### otto-SR (Cao, Bobrovitz et al.)
- Système de bout en bout (tri des résumés et du texte complet, extraction, risque de biais) combinant plusieurs modèles. Résultats rapportés : sensibilité au tri des résumés de 96,6 % contre 87,3 % pour les humains; spécificité de 93,9 % contre 95,7 %; extraction exacte à 93,1 % contre 79,7 % ([prépublication medRxiv, v4 du 4 mai 2026](https://www.medrxiv.org/content/10.1101/2025.06.13.25329541v4)).
- **Statut** : prépublication non encore publiée en revue; outil non diffusé (aperçu sur inscription); code « disponible à la publication ». Portée biomédicale; les auteurs appellent eux-mêmes à une validation sur d'autres types de revues.

#### SciSpace, Consensus, Undermind
- Moteurs de recherche et de synthèse plutôt qu'outils de revue. Aucune fonction de tri ou d'extraction documentée officiellement pour Consensus et Undermind ([Undermind](https://www.undermind.ai/pricing)); agents SciSpace trouvés seulement sur un sous-domaine de préproduction **[non vérifié]**. Utilité pour nous : **compléments de recherche** (repérage d'articles clés pour le test de sensibilité), pas plus.

### 3.2 Projets libres

| Projet | Fonction | Licence | Dernière version vérifiée | Intérêt pour revue-portee |
|---|---|---|---|---|
| **prismAId** (Go + Python, R, Julia) | Tri et extraction par grand modèle de langage; invite structurée en 6 parties; citations du manuscrit; exécutions multiples pour estimer l'incertitude; plusieurs fournisseurs dont Anthropic | AGPL-3.0 | PyPI 0.17.1 (20 août 2026); R 0.17.1 (9 sept. 2026) | Même licence que celle recommandée; idée des ensembles pour estimer l'incertitude ([JOSS](https://www.theoj.org/joss-papers/joss.07616/10.21105.joss.07616.pdf)) |
| **AIscreenR** (R) | Tri des titres et résumés par GPT + outils d'évaluation de la qualité du tri | GPL (≥ 3) | 0.4.0 (2 juill. 2026) | Issu de Vembye et al. (*Psychological Methods*) : rare validation en sciences sociales ([CRAN](https://cran.r-universe.dev/AIscreenR/DESCRIPTION)) |
| **LatteReview** (Python) | Tri multi-agents, score de pertinence, extraction; **raisonnement + score de certitude** pour chaque décision | CC BY-NC-ND 4.0 (**non libre** au sens OSI; incompatible avec une réutilisation du code) | 1.3.0 (27 sept. 2026) | Inspiration pour le format de décision seulement ([arXiv](https://arxiv.org/pdf/2501.05468v2)) |
| **screenllm** (R) | Ensemble de modèles locaux via Ollama, règle d'arrêt SAFE, aucun coût d'API | MIT | 0.1.0 (date **[non vérifiée]**) | Preuve de faisabilité du tri par modèle local ([README](https://rdrr.io/cran/screenllm/f/README.md)) |
| **MetaScreener** | Vote multi-modèles, confiance étalonnée, renvoi des cas incertains à l'humain, piste de vérification | Apache-2.0 | Date **[non vérifiée]** | Architecture proche de la nôtre; à examiner ([aperçu](https://gittrend.io/repo/ChaokunHong/MetaScreener)) |
| **metagear**, **revtools**, **litsearchr** (R) | Tri manuel assisté; dédoublonnage et modèles thématiques; construction de termes de recherche par réseaux de cooccurrence | GPL (≥ 2); **[non vérifiée]**; **[non vérifiée]** | 2021; 2019; 2020 | Inactifs; litsearchr reste une bonne idée pour l'étape 2 (suggestion de termes) |

## 4. Ce que disent les données sur les grands modèles de langage

### 4.1 Tri des titres et résumés
- **Tran et al., 2024** (*Annals of Internal Medicine*, GPT-3.5, [DOI 10.7326/M23-3389](https://doi.org/10.7326/M23-3389)) : règle équilibrée, sensibilité 81,1 à 96,5 %, spécificité 25,8 à 80,4 %; règle sensible, sensibilité 94,6 à 99,8 %, spécificité 2,2 à 46,6 %. **Le choix du seuil déplace tout le compromis.**
- **Kim et al., 2025** (méta-analyse, *J Med Artif Intell*, [DOI 10.21037/jmai-24-408](https://doi.org/10.21037/jmai-24-408)) : sensibilité groupée 0,812 (IC 95 % 0,617–0,920); les modèles proches de 100 % de rappel le paient en spécificité.
- **Xie et al., 2026** (prépublication, 18 études, [DOI 10.64898/2026.03.17.26348656](https://www.medrxiv.org/content/10.64898/2026.03.17.26348656v1.full)) : sensibilité groupée 0,92, spécificité 0,94; les invites avec exemples ou raisonnement par étapes donnent une sensibilité de 0,95 contre 0,86.
- **Vembye et al., 2025** (*Psychological Methods*, [DOI 10.1037/met0000769](https://doi.org/10.1037/met0000769)) : GPT comme second réviseur, performance « comparable » aux humains en utilisant **une invite par critère**. Chiffres exacts **[non vérifiés]** (résumé seulement).
- **Revues de portée** (prépublication, [DOI 10.1101/2024.10.01.24314702](https://www.medrxiv.org/content/10.1101/2024.10.01.24314702.full.pdf)) : les grands modèles récents étaient trop restrictifs (faible sensibilité) et les petits trop inclusifs; deux modèles + arbitrage humain des désaccords = 91 % d'automatisation avec 8 % d'erreur.
- **Référence humaine** : le tri par un seul réviseur humain manque environ 13 % des études pertinentes (Gartlehner et al., 2020, *J Clin Epidemiol*, « Single-reviewer abstract screening missed 13 percent of relevant studies: a crowd-based, randomized controlled trial », [notice](https://cris.maastrichtuniversity.nl/en/publications/single-reviewer-abstract-screening-missed-13-percent-of-relevant-/)). C'est l'étalon de comparaison naturel pour un « second réviseur ».

### 4.2 Extraction
- **Konet et al., 2024** (*Research Synthesis Methods*, [DOI 10.1002/jrsm.1732](https://doi.org/10.1002/jrsm.1732)) : extraction depuis des PDF complets, Claude 2 exact à 96,3 %, GPT-4 avec module d'extension à 68,8 %; **la plupart des erreurs venaient de la conversion des PDF**.
- **Hilkenmeier et al., 2025** : voir Elicit ci-dessus (psychologie).

### 4.3 Littérature non anglophone
- **Khraisha et al., 2024** (*Research Synthesis Methods*, GPT-4, plusieurs langues, littérature grise, [DOI 10.1002/jrsm.1715](https://doi.org/10.1002/jrsm.1715)) : accord « nul à modéré » selon les étapes et les langues, sauf au tri du texte complet avec des invites très fiables. **Aucune évaluation spécifique au français n'a été trouvée** : c'est une lacune que notre étude de validation peut combler.

### 4.4 Modes de défaillance connus
- **Non-déterminisme** même à température 0 : accord entre 5 exécutions de 0,55 à 1,0 (AC2 de Gwet) (Hida et al., 2026, [arXiv](https://arxiv.org/pdf/2604.27006)).
- **Sensibilité à l'invite et à la rédaction des critères**, hallucinations, contamination par les données d'entraînement (le modèle a pu « voir » la revue publiée), date de coupure des connaissances (Lieberum et al., revue de portée, [DOI 10.1101/2024.12.19.24319326](https://www.medrxiv.org/content/10.1101/2024.12.19.24319326.full.pdf)).
- **Étalonnage** : seuls MetaScreener, LatteReview et prismAId produisent une confiance ou une incertitude explicite; aucun outil commercial examiné ne documente une confiance étalonnée.

### 4.5 Évaluations comparatives d'outils (2022–2026)
1. Khalil, Ameen et Zarnegar (2022). Tools to support the automation of systematic reviews: a scoping review. *J Clin Epidemiol*, 144. [DOI 10.1016/j.jclinepi.2021.12.005](https://doi.org/10.1016/j.jclinepi.2021.12.005)
2. Burgard et Bittermann (2023; en ligne en 2022). Reducing literature screening workload with machine learning: a systematic review of tools and their performance. *Zeitschrift für Psychologie*, 231(1) — 15 outils, WSS moyen 0,55. [DOI 10.1027/2151-2604/a000509](https://doi.org/10.1027/2151-2604/a000509)
3. Campos et al. (2024). Screening smarter, not harder. *Educational Psychology Review*, 36. [DOI 10.1007/s10648-024-09862-5](https://doi.org/10.1007/s10648-024-09862-5)
4. Spiero et al. (2025). Évaluation d'ASReview pour des revues de pronostic et d'intervention. *Research Synthesis Methods*. [DOI 10.1017/rsm.2025.10025](https://doi.org/10.1017/rsm.2025.10025)
5. Trad et al. (2025). Rayyan contre une chaîne GPT-4 avec génération augmentée par récupération. *BMC Med Res Methodol*. [DOI 10.1186/s12874-025-02583-5](https://doi.org/10.1186/s12874-025-02583-5)

## 5. Normes et recommandations

### 5.1 RAISE — *Responsible AI in Evidence SynthEsis*
- **Référence** : Thomas J, Flemyng E, Noel-Storr A, et al. *Responsible AI in Evidence Synthesis (RAISE): Guidance and Recommendations*. OSF, 2025. [DOI 10.17605/OSF.IO/FWAUD](https://doi.org/10.17605/OSF.IO/FWAUD)
- **Structure** : trois documents ([Cochrane](https://www.cochrane.org/events/recommendations-and-guidance-responsible-ai-evidence-synthesis)) :
  - **RAISE 1** — recommandations pour la pratique ([osf.io/cqa82](https://osf.io/cqa82));
  - **RAISE 2** — construction et évaluation des outils de synthèse (**celui qui s'applique le plus directement à revue-portee**);
  - **RAISE 3** — choix et utilisation des outils ([osf.io/5xjpk](https://osf.io/5xjpk)).
- **Versions** : v1 en septembre 2024 (un document); version en trois documents à l'été 2025; **v4 au début de mars 2026**, qui ajoute des tableaux sur l'état actuel de l'IA, une taxonomie des usages et des précisions pour juger si un outil convient à une tâche ([rapport Cochrane Methods 2026](https://www.cochrane.org/nl/about-us/news/cochrane-methods-report-2026)). Soumis à *Research Synthesis Methods*; publication en revue **[non vérifiée]**. Dates exactes des fichiers sur OSF **[non vérifiées]** (OSF inaccessible).
- **Recommandations principales pour les auteurs** : les auteurs demeurent responsables de la synthèse; vérifier que l'outil fonctionne comme annoncé et justifier qu'il convient à l'usage; déclarer l'usage de l'IA « de façon transparente et détaillée » (nom et version de l'outil, dates, but, justification, intérêts financiers); respecter les normes éthiques et légales; contribuer à l'écosystème; l'IA est « un compagnon, pas un remplaçant » ([guide NEU](https://subjectguides.lib.neu.edu/systematicreview/automation); [diapositives Cochrane](https://training.cochrane.org/sites/training.cochrane.org/files/public/uploads/A%20global%20challenge%20and%20introducing%20RAISE_0.pdf)).
- **À faire** : lire RAISE 2 et 3 (v4) intégralement sur OSF et transformer leurs recommandations en exigences vérifiables (voir [02-exigences.md](02-exigences.md), exigence ENF-NOR-01).

### 5.2 Énoncé de position conjoint Cochrane, Campbell, JBI et CEE (2025)
- Flemyng E, Noel-Storr A, Macura B, et al. *Position statement on artificial intelligence (AI) use in evidence synthesis across Cochrane, the Campbell Collaboration, JBI and the Collaboration for Environmental Evidence 2025*. Publié simultanément dans quatre revues; version JBI : *JBI Evid Synth* 2025;23(11):2162–2166, [DOI 10.11124/JBIES-25-00480](https://doi.org/10.11124/JBIES-25-00480) ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12594113)).
- **Points clés** : endosse RAISE; usage de l'IA sous supervision humaine; tout usage de l'IA qui produit ou suggère un jugement doit être « déclaré de façon complète et transparente »; les auteurs restent responsables, y compris de la décision d'utiliser l'IA; **les développeurs d'outils doivent publier leurs données de validation et leurs limites**.
- **Guide connexe** : la CEE a publié un guide de déclaration (Macura et al., 2025) en quatre volets — description et justification, validation, limites et éthique, financement et conflits — avec un gabarit de section méthode ([CEE](https://environmentalevidence.org/artificial-intelligence-reporting-guidance/)). **C'est le modèle le plus concret pour notre générateur de section méthode.**

### 5.3 PRISMA-ScR et extensions
- **PRISMA-ScR** : Tricco AC, Lillie E, Zarin W, et al. *Ann Intern Med* 2018;169(7):467–473. DOI 10.7326/M18-0850 (DOI **[non revérifié]** à cause d'une limite de débit de Crossref). **20 éléments essentiels + 2 facultatifs** ([prisma-statement.org/scoping](https://www.prisma-statement.org/scoping)).
- **Mise à jour en cours** : listée comme « Update of PRISMA for scoping reviews » ([extensions PRISMA](https://www.prisma-statement.org/extensions)); le manuel JBI indique qu'une nouvelle version « doit paraître en 2026 » ([JBI 10.3](https://jbi-global.atlassian.net/wiki/spaces/MANUAL/pages/355862853)). **Non publiée au 7 octobre 2026.** Protocole de fond : Veroniki et al., *JBI Evid Synth* 2025;23(3), [DOI 10.11124/JBIES-24-00308](https://doi.org/10.11124/JBIES-24-00308).
  - **Conséquence pour l'architecture** : la liste de contrôle doit être un **fichier de données versionné**, pas du code, pour pouvoir ajouter la nouvelle version sans réécriture.
- **PRISMA et IA** : une « mise à jour partielle de PRISMA 2020 intégrant des recommandations sur l'usage des outils d'IA » est officiellement en développement ([extensions PRISMA](https://www.prisma-statement.org/extensions)). **PRISMA-trAIce** (Holst et al., *JMIR AI* 2025, [DOI 10.2196/80247](https://doi.org/10.2196/80247)) n'est **pas** une norme PRISMA : le comité exécutif PRISMA s'en est publiquement dissocié (Moher et al., *JMIR AI* 2026, [DOI 10.2196/104210](https://doi.org/10.2196/104210)). Ne pas la citer comme norme.
- **Diagramme de flux PRISMA 2020** : quatre gabarits (nouvelle revue ou mise à jour; bases et registres seulement ou avec d'autres sources), CC BY 4.0 ([page officielle](https://www.prisma-statement.org/prisma-2020-flow-diagram)). Référence : Page MJ et al. *BMJ* 2021;372:n71.
- **PRISMA-S** (déclaration des recherches) : Rethlefsen ML et al. *Syst Rev* 2021;10:39, [DOI 10.1186/s13643-020-01542-z](https://doi.org/10.1186/s13643-020-01542-z), 16 éléments. À couvrir à l'étape 2.

### 5.4 Méthode JBI pour les revues de portée
- **Chapitre 10 du manuel JBI, version 2026** : Pollock D, Peters MDJ, Tricco AC, Munn Z, et al. *Scoping reviews (2026)*. In : Aromataris E et al., dir. *JBI Manual for Evidence Synthesis*. JBI; 2024. [DOI 10.46658/JBIMES-24-09](https://doi.org/10.46658/JBIMES-24-09). Dernière mise à jour de la page : 28 septembre 2026 ([chapitre 10](https://jbi-global.atlassian.net/wiki/spaces/MANUAL/pages/355862497/10.+Scoping+reviews)). Remplace la version 2020. Nouveautés : abandon de l'expression « systematic scoping review », bonnes pratiques de protocole, engagement des utilisateurs de connaissances, équité-diversité-inclusion, extraction et présentation des données, **automatisation et approches rapides** (traitées brièvement, en citant Alexander et al., 2024, *J Clin Epidemiol* 170:111343).
- **Cadre PCC** ([10.2.4](https://jbi-global.atlassian.net/wiki/rest/api/content/355862707?expand=body.view,version)) : Population (caractéristiques clés, âge, autres critères), Concept (« clairement articulé pour guider la portée »), Contexte (selon les objectifs). Chaque élément se traduit en critères d'inclusion et d'exclusion.
- **Articles de référence** :
  - Peters MDJ et al. *Updated methodological guidance for the conduct of scoping reviews*. *JBI Evid Synth* 2020;18(10):2119–2126. [DOI 10.11124/JBIES-20-00167](https://doi.org/10.11124/JBIES-20-00167)
  - Peters MDJ et al. *Best practice guidance and reporting items for the development of scoping review protocols*. *JBI Evid Synth* 2022;20(4):953–968. [DOI 10.11124/JBIES-21-00242](https://doi.org/10.11124/JBIES-21-00242) — **base du gabarit de protocole**.
  - Pollock D et al. *Recommendations for the extraction, analysis, and presentation of results in scoping reviews*. *JBI Evid Synth* 2023;21(3):520–532. [DOI 10.11124/JBIES-22-00123](https://doi.org/10.11124/JBIES-22-00123) — **base des étapes 5 et 6**.
- **Enregistrement** : PROSPERO n'accepte pas les revues de portée; JBI renvoie à OSF ou FigShare ([10.2.2](https://jbi-global.atlassian.net/wiki/rest/api/content/355862667?expand=body.view,version)). Le gabarit OSF **Generalized Systematic Review Registration** couvre les revues de portée ([aide OSF](https://help.osf.io/hc/en-us/articles/360019738794-Select-a-Registration-Template)); 65 éléments (van den Akker OR et al., *Syst Rev* 2023;12, [DOI 10.1186/s13643-023-02281-7](https://doi.org/10.1186/s13643-023-02281-7)).

### 5.5 Parties prenantes et cartes de données probantes
- Pollock D et al. *Moving from consultation to co-creation with knowledge users in scoping reviews*. *JBI Evid Synth* 2022;20(4):969–979. [DOI 10.11124/JBIES-21-00416](https://doi.org/10.11124/JBIES-21-00416). JBI note que PRISMA-ScR « ne traite pas actuellement » de la déclaration de l'engagement des utilisateurs de connaissances.
- White H et al. *Guidance for producing a Campbell evidence and gap map*. *Campbell Syst Rev* 2020;16(4):e1125. [DOI 10.1002/cl2.1125](https://doi.org/10.1002/cl2.1125).

## 6. Sources de données et conditions d'accès (2026)

| Source | Accès | Conditions actuelles | Conséquence pour revue-portee |
|---|---|---|---|
| **OpenAlex** | `https://api.openalex.org` | **Clé d'API requise** depuis le 24 févr. 2026 (gratuite); allocation gratuite d'environ 1 $/jour (recherches, listes, téléchargements), puis facturation à l'usage; le paramètre `mailto` ne donne plus d'avantage; 100 requêtes/s max; données CC0 ([authentification](https://developers.openalex.org/api-reference/authentication.md); [dépréciations](https://developers.openalex.org/guides/deprecations.md); [blogue](https://blog.openalex.org/category/feature)) | Secret `OPENALEX_API_KEY` (ajouté à l'environnement le 7 oct. 2026, D-013); suivre la consommation; les « Concepts » sont remplacés par les « Topics » |
| **PubMed (E-utilities)** | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | 3 requêtes/s sans clé, 10 avec clé; paramètres `tool` et `email` à enregistrer auprès du NCBI; gros traitements la fin de semaine ou de 21 h à 5 h (heure de l'Est) ([NBK25497](https://www.ncbi.nlm.nih.gov/books/NBK25497/)) | Limiteur de débit; `email` = `CONTACT_EMAIL`; clé NCBI facultative |
| **Crossref** | `https://api.crossref.org` | Depuis le 1er déc. 2025 : public 5 req/s (enregistrement unique) et 1 req/s (listes), une à la fois; « poli » (avec `mailto`) 10 et 3 req/s, trois à la fois; erreur 429 au-delà ([annonce](https://crossref.org/blog/announcing-changes-to-rest-api-rate-limits/)) | Enrichissement par DOI seulement, avec `mailto=CONTACT_EMAIL`, concurrence ≤ 3 |
| **Unpaywall** | `https://api.unpaywall.org/v2/{doi}?email=` | Courriel réel obligatoire (une adresse fictive est refusée); environ 100 000 appels/jour (source secondaire); reconstruit en mai 2025, désormais « une tranche d'OpenAlex » ([blogue](https://blog.openalex.org/major-update-to-unpaywall-database)) | Repérage des versions en libre accès pour le texte complet |
| **Érudit** | OAI-PMH : `http://oai.erudit.org/oai/` | Pas d'API REST publique trouvée; OAI-PMH actif; jeux de données du corpus sous droit d'auteur ([Érudit](https://datasets.docs.erudit.org/i18n/en/datasets/erudit_revues_savantes_culturelles.html)) | **Domaine à ajouter à la liste réseau**; moissonnage par OAI-PMH puis filtrage local, ou import manuel |
| **theses.fr** | API ouverte, sans clé, Licence Ouverte 2.0 ([data.gouv.fr](https://www.data.gouv.fr/dataservices/api-export-des-donnees-de-theses-fr/)) | Limites de débit non documentées | Domaine à ajouter |
| **HAL** | `https://api.archives-ouvertes.fr` (recherche et OAI-PMH) | Sans inscription; « pas d'usage commercial des données extraites » ([HAL](https://api.archives-ouvertes.fr/docs/oai)) | Compatible avec un outil libre non commercial; **à vérifier si une version hébergée payante est envisagée** |
| **Dépôts québécois** | OAI-PMH : Papyrus (UdeM), Corpus UL (Laval), Archipel (UQAM); Cognitio (UQTR) probable | Adresses issues d'une source secondaire (Piedboeuf et al., [arXiv:2311.11140](https://arxiv.org/pdf/2311.11140)); **non testées** | À tester avant de s'y fier |
| **Cairn.info, Persée** | OAI-PMH (`oai.cairn.info`, `oai.persee.fr`) | Pas d'API publique documentée pour Cairn ([spécifications](https://apropos.cairn.info/en/institutions/technical-specifications)) | Version 2 ou plus tard |
| **Bases sous abonnement** (PsycINFO via EBSCOhost ou Ovid, CINAHL, ERIC, Scopus, Web of Science) | Pas d'API ouverte | Export RIS possible depuis EBSCOhost et Ovid ([guide McGill](https://libraryguides.mcgill.ca/epib629/exporting)); problèmes connus d'enregistrements vides dans certains exports Ovid PsycINFO ([forum Zotero](https://forums.zotero.org/discussion/comment/365197)) | Analyseur RIS robuste, testé sur de **vrais exports** |
| **Format RIS** | Spécification de Research Information Systems (2001, 2011), aujourd'hui propriété de Clarivate; spécification communautaire documentée ([gris](https://gris.readthedocs.io/en/latest/specification.html)) | Étiquette de deux lettres, deux espaces, trait d'union; `TY` en premier, `ER` en dernier | Tolérer les variantes des fournisseurs |

## 7. Leçons pour la conception

1. **Le créneau existe** : versionnement des critères et de la grille, analyse d'impact, section méthode générée à partir du journal, interface et sources francophones, logiciel libre.
2. **L'étalonnage n'est pas un luxe** : la sensibilité d'un grand modèle de langage varie énormément selon la rédaction des critères (Covidence : 66 à 98 %). L'essai pilote doit mesurer la performance de l'IA **sur la revue en cours** avant de lui faire confiance.
3. **Une invite par critère** (Vembye et al.) et des réponses structurées par critère facilitent la justification « qui cite le critère » et l'analyse d'impact quand un critère change.
4. **Conserver la réponse brute, le modèle exact, l'invite et ses paramètres** : les modèles sont retirés rapidement (EPPI-Reviewer), et le non-déterminisme est réel même à température 0.
5. **Rendre le compromis sensibilité-spécificité explicite** : afficher, après le pilote, ce qu'un seuil donné aurait coûté (études manquées) et rapporté (références évitées).
6. **Les PDF sont la principale source d'erreur d'extraction** : soigner la conversion, conserver la correspondance texte-page.
7. **Les conditions d'accès aux API changent** (OpenAlex, Crossref) : isoler chaque source derrière un connecteur, avec limiteur de débit et suivi de consommation.
8. **Les normes évoluent en 2026** (PRISMA-ScR, PRISMA-IA, RAISE v4) : listes de contrôle et gabarits en fichiers de données versionnés.
9. **Publier nos propres données de validation** : c'est une obligation pour les développeurs selon l'énoncé de position conjoint, et un argument de crédibilité.

## 8. Points non vérifiés à reprendre

- RAISE : dates exactes des fichiers v4 et DOI propres à chaque document sur OSF; publication dans *Research Synthesis Methods*.
- PRISMA-ScR : DOI 10.7326/M18-0850 à revérifier; surveiller la parution de la mise à jour 2026 et de la mise à jour PRISMA sur l'IA.
- Rayyan, Laser AI, Elicit, Nested Knowledge : identité et version des modèles utilisés.
- SysRev : licence, grille tarifaire, conservation des justifications.
- Abstrackr : site encore en ligne ou non. Colandr : date du dernier commit.
- Vembye et al. (2025) : chiffres exacts de sensibilité et de spécificité (lire l'article complet).
- Dépôts OAI-PMH québécois et Cognitio (UQTR) : tester les points d'accès.
- Unpaywall : limite quotidienne à confirmer dans la documentation officielle.
- Résultats de l'étude de plateforme d'IA de Cochrane (attendus fin 2026).
