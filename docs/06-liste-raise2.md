# 06 — Liste de vérification RAISE 2

> **Statut** : version de travail du 8 octobre 2026, cochée pour la **V1** (ENF-NOR-01). À recocher à chaque version majeure.
> **Source** : Thomas J, Flemyng E, Noel-Storr A, et al. *Responsible use of AI in Evidence Synthesis (RAISE 2026) 2: Living guidance for building and evaluating AI evidence synthesis tools*. Version 4, 25 août 2026, « draft for consultation and revision ». OSF, [osf.io/fwaud](https://osf.io/fwaud/) (fichier « RAISE 2 - building and evaluating v.4.pdf »). Lu en entier le 2026-10-08 : sections 1 à 4 et annexe 1.
> **Renvois** : [02-exigences.md](02-exigences.md) (ENF-NOR-01, ENF-NOR-02), [05-plan-de-validation.md](05-plan-de-validation.md), [journal-des-decisions.md](journal-des-decisions.md), [resultats/](resultats/README.md).

## Comment lire cette liste

RAISE 2 s'adresse aux équipes qui construisent des outils d'IA, aux méthodologistes et aux formateurs. Pour revue-portee, Benoit tient le rôle d'**équipe de développement** et, pour l'étude de validation prévue (05), celui de **méthodologiste**.

Au sens de RAISE 2, revue-portee contient trois **outils** :

| Outil | Classe de technologie (RAISE 2, §1) | Tâche |
|---|---|---|
| Gabarit d'invite `screen_reference` + seuils + règle EF-SEL-07 | Grand modèle de langage génératif (Claude), utilisé par un flux d'invite propre à la tâche (encadré 1 : concevoir un flux d'invite, c'est construire un outil) | Tri des titres et résumés, comme second réviseur |
| Règles de dédoublonnage (`dedup/`, D-062) | Algorithme à base de règles (IA symbolique) | Repérage des doublons |
| Traduction des requêtes (`search/translate.py`) | Algorithme à base de règles | Traduction d'une stratégie vers PubMed, OpenAlex et PsycINFO |

Les suggestions de l'IA au cadrage, aux critères et aux termes de recherche sont toujours acceptées, modifiées ou refusées par une personne. Elles sont couvertes par les mêmes principes de traçabilité, mais ne font pas l'objet d'une évaluation de performance en V1.

**Terminologie de RAISE 2** (§1, « Phases of building an AI tool »), reprise ici :
- **test** : mesure sur des notices mises de côté, jamais utilisées pour construire ou ajuster l'outil;
- **évaluation** : vérifier que l'outil convient à un usage précis, y compris dans des contextes indépendants;
- **validation** : toujours qualifiée (interne, externe ou propre au contexte).

**Légende** : ✅ couvert · ◐ partiel · ❌ à faire · — sans objet en V1.

## 1. Principes de conception (RAISE 2, §1)

| # | Recommandation | V1 | Preuve, ou ce qui manque |
|---|---|---|---|
| 1.1 | Viser l'exhaustivité : une source de recherche doit couvrir toute la littérature pertinente; signaler les limites de couverture (biais FUTON, libre accès) | ◐ | Recherche booléenne complète dans les bases (PubMed, OpenAlex), import RIS pour les bases sous abonnement (EF-COL-03); test de sensibilité sur des articles clés (D-051). Manque : un avertissement à l'utilisateur sur les limites de couverture d'OpenAlex (littérature grise, langues) |
| 1.2 | Privilégier le rappel à la précision; pas de recherche « top n » | ✅ | Collecte paginée complète, nombre annoncé comparé au nombre collecté (EF-COL-01, D-053) |
| 1.3 | Ne pas amplifier les biais de publication : pas de classement par nombre de citations | ✅ | Aucun classement par citations; la priorité facultative du tri repose sur la probabilité d'inclusion selon les critères (EF-SEL-10, D-083) |
| 1.4 | Responsabilité : chaque décision est auditable | ✅ | Journal à chaîne d'empreintes (D-029); chaque décision de l'IA consigne le modèle, la version exacte renvoyée, le gabarit et sa version, la confiance, les seuils, la justification, les critères cités et la réponse brute (ENF-TRA-01, ENF-TRA-03) |
| 1.5 | Cadrage : consulter des parties prenantes diverses, cadre d'innovation responsable, comité d'éthique consultatif | ❌ | Projet personnel, sans consultation formelle ni comité. À prévoir avant l'étude de validation (consultation de bibliothécaires et de méthodologistes JBI) |
| 1.6 | Données : collecte éthique, légale, transparente, avec sécurité | ✅ | Seulement de la littérature publiée, aucune donnée de participants (principe 5); secrets jamais écrits (ENF-SEC-01); archive publique sans texte protégé (D-092) |
| 1.7 | Tests et déploiement : évaluer sur des jeux indépendants et publier honnêtement | ◐ | Banc SYNERGY publié dans `docs/resultats/`. Ces jeux sont l'**ensemble de développement** (05, §5.3) : l'évaluation sur un ensemble de test indépendant reste à faire (voir 2.4 et 3.1) |
| 1.8 | Après le lancement : audit continu, évaluation indépendante facilitée, résultats publiés | ◐ | Code, gabarits d'invite et critères du banc sont publics (AGPL), et l'archive de chaque projet est vérifiable sans l'outil (ENF-REP-06). Manque : un suivi des changements de version du modèle d'un projet à l'autre, et un dispositif de retour des utilisateurs |

## 2. Construction et test (RAISE 2, §1)

| # | Recommandation | V1 | Preuve, ou ce qui manque |
|---|---|---|---|
| 2.1 | Données de qualité, en quantité suffisante, équilibrées et diverses | ◐ | Banc : 3 jeux de 952 à 9 128 notices, avec 20 à 72 inclusions; fort déséquilibre, d'où la sensibilité comme mesure principale. Diversité limitée : psychologie clinique, en anglais |
| 2.2 | Séparer les données de développement et de test, sans fuite entre les deux | ❌ | Le développement du gabarit `screen_reference` v1 n'est pas documenté (quelles notices ont servi à le mettre au point). Les jeux SYNERGY sont déclarés comme ensemble de développement (05, §5.3) : aucun résultat sur des notices mises de côté n'existe encore |
| 2.3 | Gabarits d'invite : la mise au point est un entraînement; ne jamais rapporter la performance sur les notices qui ont servi à la mise au point | ◐ | Les gabarits sont versionnés, et toute modification incrémente la version (CLAUDE.md, `ai/prompts/*/meta.yaml`). Le gabarit est resté en v1 après le banc. Manque : le journal de mise au point du gabarit (données utilisées, versions essayées) |
| 2.4 | Ensemble de test final mis de côté quand les choix sont ajustés à répétition | ❌ | Prévu : gel des invites, des seuils et du code avant l'ensemble de test, consigné sur OSF (05, §5.3) |
| 2.5 | Réduire la variabilité des modèles génératifs (paramètres, invites) et tester sur plusieurs exécutions | ◐ | Sortie structurée validée par schéma, une nouvelle tentative au plus (D-070), paramètres consignés à chaque appel. **Stabilité des réponses non mesurée** : prévue dans l'étude (05, §6.3, point 3) |
| 2.6 | Hallucinations : vérifier que les résultats sont exacts **et** fondés sur les données fournies | ✅ | Chaque critère évalué porte une citation, et l'outil vérifie qu'elle figure mot pour mot dans le titre ou le résumé (`quote_found`). La proportion de citations retrouvées est rapportée au banc et dans la section méthode |
| 2.7 | Tester les biais, dont le biais linguistique (modèles entraînés surtout en anglais) | ◐ | Langue de chaque référence détectée et consignée (ENF-LAN-05, D-073); justifications rédigées en français. Manque : la performance sur les références en français n'est pas mesurée (05, objectif 6) |
| 2.8 | Sans preuve d'évaluation suffisante, n'utiliser l'outil que dans un processus d'évaluation ou de pilote **clairement signalé**, avec supervision humaine, et le dire dans l'interface et la documentation | ✅ | Supervision complète en V1 : la personne trie toutes les références à l'aveugle, l'IA n'exclut jamais seule, et les désaccords sont réconciliés par la personne (principe 1, D-014, EF-SEL-08). Essai pilote et étalonnage avant le tri (EF-SEL-01). Les pages « Pilote » et « Tri » et la section méthode signalent que le réviseur IA est **en cours d'évaluation** tant qu'aucun résultat sur des données mises de côté n'est publié (D-097) |
| 2.9 | Documenter les contextes où l'outil peut convenir, avant une évaluation plus large | ✅ | La section méthode signale quand la configuration d'une revue diffère de celle qui a été évaluée (D-093); la [fiche de l'outil](07-fiche-outil.md) décrit le contexte testé et ses limites |
| 2.10 | Dédoublonnage : ne pas évaluer sur les données qui ont servi à mettre au point les règles; jeu de référence en **groupes** de doublons; définir ce qu'est un doublon | ◐ | Jeu annoté en groupes, avec une définition écrite du doublon, de la version et des notices distinctes (D-060). Mais les règles ont été mises au point sur ce même jeu (D-062) : le rappel et la précision de 1,000 sont **probablement surestimés**. Manque : un jeu de test indépendant (par exemple un jeu public de référence) |

## 3. Évaluations (RAISE 2, §2)

| # | Recommandation | V1 | Preuve, ou ce qui manque |
|---|---|---|---|
| 3.1 | Évaluation par l'équipe de développement avant le lancement, puis évaluations indépendantes | ◐ | Banc SYNERGY (développement). L'étude de validation est conçue (05) : préenregistrement OSF, ensemble de test tiré au hasard, analyse des erreurs par au moins un évaluateur indépendant du développement. Pas encore réalisée |
| 3.2 | Protocole enregistré; gabarits standards (études au sein d'une revue, SWAR) pour cumuler les résultats | ◐ | Protocole rédigé (05), préenregistrement prévu. L'essai de bout en bout de la V1 pourrait être conçu comme une SWAR |
| 3.3 | Mesurer le gain réel d'efficacité (temps consacré à la tâche) | ❌ | Chaque décision est horodatée, mais le temps de travail n'est ni mesuré ni rapporté. RAISE 2 rappelle qu'un horodatage ne dit pas si la personne travaillait vraiment |
| 3.4 | Tri : partir d'un jeu de référence couvrant tout le cas d'usage; viser une sensibilité très élevée | ◐ | Sensibilité de 95,0 à 97,4 % au banc, avec intervalles de Wilson. Le cas d'usage visé (revues de portée, littérature francophone) n'est pas encore couvert (05) |
| 3.5 | Tri priorisé : le critère d'arrêt n'est pas établi | ✅ | Aucun arrêt anticipé : la priorité ne change que l'ordre, et toutes les références sont triées par la personne (D-083) |
| 3.6 | Contamination : une revue présente dans les données d'entraînement du modèle surestime la performance | ❌ | Non évaluée : les revues SYNERGY sont publiées et pourraient figurer dans les données d'entraînement du modèle. À discuter dans les limites, et à considérer dans le choix de l'ensemble de test (05) |
| 3.7 | Les tâches de recherche et de traduction de requêtes s'évaluent avec un jeu de référence | ◐ | 10 stratégies de référence reproduites à l'équivalence syntaxique près (tranche 1.3); test de sensibilité sur des articles clés. Pas d'évaluation de la couverture des descripteurs |

## 4. Mesures de performance (RAISE 2, §3 et annexe 1)

| # | Recommandation | V1 | Preuve, ou ce qui manque |
|---|---|---|---|
| 4.1 | Plusieurs mesures complémentaires (exactitude, fiabilité, efficacité, utilisabilité, risques), choisies en tenant compte du déséquilibre des classes | ◐ | Pilote : matrice de confusion, accord, kappa de Cohen, AC1 de Gwet, sensibilité et spécificité avec intervalles, courbe seuil-sensibilité et références évitées. Chaque mesure est vérifiée sur un cas calculé à la main. Manque : précision (VPP), WSS@95 et calibration (Brier, ECE), prévus dans l'étude (05, §7) |
| 4.2 | Stabilité des réponses (même entrée, plusieurs exécutions), sans se laisser tromper par la mise en cache du fournisseur | ❌ | Non mesurée (voir 2.5) |
| 4.3 | Robustesse aux variantes de formulation de l'invite | ❌ | Non mesurée; une comparaison d'invites est prévue (05, objectif 7) |
| 4.4 | Hallucinations : poser des questions dont la réponse n'est pas dans les données; vérifier les citations | ◐ | Vérification des citations (voir 2.6); EF-SEL-07 interdit d'exclure quand un critère d'inclusion ne peut pas être évalué |
| 4.5 | Coût, charge de travail, effort de vérification humaine | ◐ | Coût réel par appel et par phase, coût pour 1 000 références au banc. Manque : le temps de vérification humaine (voir 3.3) |
| 4.6 | Interopérabilité (RIS, CSV) | ✅ | Import RIS de 5 plateformes et plus (D-056); export RIS et CSV des références retenues (D-096); archive CSV et JSON (D-092) |
| 4.7 | Transparence technique (version du modèle, paramètres) et explicabilité | ✅ | Version exacte renvoyée par l'API, paramètres, empreinte de l'invite, justification et passage cité pour chaque critère |
| 4.8 | Impact environnemental | ❌ | Rien n'est rapporté. On pourrait au moins déclarer le nombre de jetons pour 1 000 références, qui sert d'indicateur indirect |
| 4.9 | Publier les mesures **et les jeux de données** d'évaluation | ◐ | Rapports chiffrés et critères du banc publiés; jeux SYNERGY publics (CC0). Les décisions de l'IA au banc ne sont pas publiées (réponses brutes hors dépôt, D-074) : on pourrait publier les identifiants et les décisions, sans texte protégé, comme le prévoit 05 (§11) |

## 5. Déclaration (RAISE 2, §4, cadre adapté de Kolbinger et al.)

| # | Élément à déclarer | V1 | Où, ou ce qui manque |
|---|---|---|---|
| 5.1 | Outil : nom et version, développeur et pays, accès, guide d'utilisation, fonctionnement, étape visée, remplacement ou complément d'une tâche, mise en œuvre de la supervision humaine | ✅ | [Fiche de l'outil](07-fiche-outil.md), qui reprend tous les éléments du §4 de RAISE 2. Pas de guide d'utilisation détaillé à ce jour |
| 5.2 | Devis de l'évaluation, contexte (domaine, étape), sources des données | ✅ | [Fiche de l'outil](07-fiche-outil.md), « Méthode » |
| 5.3 | Données : sélection, prétraitement, données manquantes, création et qualité de la norme de référence | ◐ | D-075 (inclusions au texte intégral, résumés absents d'OpenAlex). Qualité de la norme de référence non évaluée (05, §6.5, catégorie c) |
| 5.4 | Type de modèle et version précise du modèle de fondation | ✅ | Modèle demandé et versions exactes renvoyées, avec leur nombre d'appels et leurs dates (section méthode, archive) |
| 5.5 | Développement de l'outil : invites décrites en détail, absence de contamination entre les données | ◐ | Gabarits versionnés et publics. Manque : le journal de mise au point (voir 2.3) |
| 5.6 | Résultats : mesures, comparateurs, variabilité, intervalles de confiance | ◐ | Intervalles de Wilson. Variabilité entre exécutions non mesurée |
| 5.7 | Analyse des erreurs | ◐ | Les 4 inclusions manquées au banc sont décrites (`docs/resultats/README.md`). Analyse systématique prévue (05, §6.5) |
| 5.8 | Forces, limites et généralisabilité (domaines, sources, langues, types de publication) | ◐ | Limites générées dans la section méthode (D-093); 05, §13 |
| 5.9 | Biais et enjeux d'équité, avec stratégies d'atténuation | ◐ | Biais linguistique reconnu, langue consignée; pas de mesure (voir 2.7) |
| 5.10 | Valeur pratique et coût | ✅ | Coût par phase dans la section méthode; coût pour 1 000 références au banc |
| 5.11 | Conséquences pour l'usage : risque que l'IA rende les conclusions non fiables, et dans quelles circonstances | ✅ | [Fiche de l'outil](07-fiche-outil.md), « Conséquences pour l'usage » (risque d'ancrage à la réconciliation) |
| 5.12 | Éthique, protocole public, sources de soutien, déclarations d'intérêts (outil commercial ou non) | ◐ | Outil libre et non commercial (AGPL-3.0); conflit d'intérêts du développeur et atténuations dans 05 (§10). La section méthode laisse ces éléments à compléter par l'équipe (D-093) |
| 5.13 | Disponibilité des données, du code, des invites et des analyses; reproductibilité par des tiers | ✅ | Code et gabarits publics; archive vérifiable sans clé d'API (ENF-REP-06, D-092); la reproduction exacte des décisions de l'IA reste impossible si le modèle change, d'où la conservation des réponses brutes (ENF-TRA-03) |
| 5.14 | Impact environnemental | ❌ | Voir 4.8 |

## 6. Bilan pour la V1

**Bien couvert** : traçabilité et auditabilité (1.4, 4.7, 5.4), supervision humaine complète (2.8, 3.5), interopérabilité (4.6), reproductibilité des nombres déclarés (5.13). C'est le cœur de la conception de revue-portee.

**Vocabulaire, corrigé le 2026-10-08 (D-097)** : les résultats SYNERGY portent sur l'**ensemble de développement** (05, §5.3). Au sens de RAISE 2, ce ne sont ni des résultats de test ni une validation. La section méthode générée (D-093) écrit que l'outil « a été validé ». Elle devrait plutôt parler d'une évaluation sur l'ensemble de développement, en annonçant l'étude de validation.

**Actions proposées, par ordre de priorité** :

1. ~~**Vocabulaire et mention « en cours d'évaluation »** (2.8, 2.9)~~, fait (#23, D-097) : corriger la section méthode et `tool_validation.yaml`, et signaler dans l'interface (pages « Pilote » et « Tri ») que le réviseur IA est en cours d'évaluation. Petit changement de code.
2. ~~**Fiche de l'outil** (5.1 à 5.14)~~, fait ([07-fiche-outil.md](07-fiche-outil.md)) : un document public qui suit le cadre de déclaration de RAISE 2 (§4) et renvoie aux preuves ci-dessus. Documentation seulement.
3. ~~**Rapporter les citations retrouvées** (2.6, 4.4)~~, fait : au banc et dans la section méthode.
4. **Journal de mise au point des gabarits d'invite** (2.2, 2.3, 5.5) : consigner, pour chaque version, les données utilisées et les essais faits; reconstituer ce qui est connu pour la v1.
5. **Jeu de test indépendant pour le dédoublonnage** (2.10).
6. **Stabilité des réponses** (2.5, 4.2) : petite expérience de réexécution. Elle appelle le vrai modèle, donc **seulement avec l'accord de Benoit** et sous un plafond.
7. **Étude de validation** (2.4, 3.1, 3.4, 3.6, 4.1, 4.3) : préenregistrement OSF puis exécution (05). C'est elle qui fournira les preuves d'évaluation au sens de RAISE 2.
8. **Impact environnemental** (4.8, 5.14) : déclarer au moins les jetons consommés pour 1 000 références.
9. **Consultation des parties prenantes** (1.5) : bibliothécaires et méthodologistes, avant l'étude de validation.

Le temps de travail (3.3) et l'utilisabilité seront mieux mesurés pendant l'essai de bout en bout, à concevoir si possible comme une étude au sein d'une revue (SWAR).
