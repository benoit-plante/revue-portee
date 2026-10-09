# 04 — Feuille de route

> **Statut** : version de travail du 7 octobre 2026. Aucune date d'échéance : le projet est mené sur du temps personnel. L'ordre compte, pas le calendrier.
> **Renvois** : identifiants d'exigences → [02-exigences.md](02-exigences.md); structure du code → [03-architecture.md](03-architecture.md).

## 0. Principes de découpage

- **Tranches verticales** : chaque tranche livre une capacité utilisable de bout en bout (domaine → stockage → service → interface ou ligne de commande → tests), même petite. On évite les « couches » livrées séparément.
- **Une tranche = une ou plusieurs branches** `tranche/<version>.<numéro>-<nom-court>` (ex. `tranche/1.3-requetes`) et une ou plusieurs demandes de fusion, révisées par Benoit avant fusion.
- **Définition de « terminé »** commune à toutes les tranches :
  1. tous les critères d'acceptation de la tranche sont vérifiés et cochés dans la demande de fusion;
  2. `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` et `uv run pytest` passent, seuil de couverture de 90 % par paquet compris (D-022, D-023);
  3. aucun test ordinaire n'appelle le réseau; aucun secret dans le dépôt;
  4. les exigences couvertes sont citées par identifiant dans la demande de fusion;
  5. toute décision d'architecture nouvelle est proposée pour le [journal des décisions](journal-des-decisions.md);
  6. l'interface est en français, le code en anglais.
- **Jeu de démonstration** : un petit projet de revue fictif mais réaliste (thème suggéré : interventions de soutien à la parentalité et santé mentale des enfants), construit au fil des tranches dans `tests/fixtures/demo/`, sert aux tests de bout en bout.

---

## Jalon 0 — Fondations

**But** : un dépôt où une session infonuagique peut installer, tester et vérifier le style sans intervention.

| Livrable | Critères d'acceptation |
|---|---|
| `pyproject.toml`, `uv.lock`, structure `src/revue_portee/` et `tests/` | `uv sync` réussit dans une VM neuve; `uv run python -c "import revue_portee"` fonctionne |
| `.claude/settings.json` avec hook **SessionStart** | À l'ouverture d'une session infonuagique, les dépendances sont installées sans action manuelle; le hook est idempotent et termine en moins de 3 minutes |
| Configuration ruff et pytest | `ruff check` et `ruff format --check` passent; `pytest` exclut le marqueur `integration` par défaut; `pytest -m integration` est reconnu |
| `config/secrets.py` + filtre de journalisation | Test : une clé factice chargée n'apparaît dans aucune sortie de journal ni `repr` |
| Test anti-secrets sur `tests/` | Test qui échoue si un motif de clé (`sk-ant-`, en-tête d'authentification, paramètre `api_key=`) ou l'adresse réelle de `CONTACT_EMAIL` apparaît dans un fichier versionné de `tests/` |
| `FakeProvider` et interface `ModelProvider` | Un test exécute une tâche factice de bout en bout |
| Licence appliquée (D-004) | `LICENSE` (texte officiel AGPL-3.0) déjà présent depuis le 2026-10-07 : ne pas le modifier; `license = "AGPL-3.0-or-later"` dans `pyproject.toml` |
| CI GitHub Actions (facultatif) | Si ajoutée : ruff + pytest sur chaque demande de fusion, sans secret |

---

## Version 1 — Du cadrage au diagramme de flux du tri des titres et résumés

**Promesse de la V1** : une équipe (un réviseur humain + l'IA) peut cadrer sa revue, produire un protocole, construire et tester ses requêtes, collecter et dédoublonner, étalonner l'IA sur un pilote, trier tous les titres et résumés avec l'IA comme second réviseur, faire évoluer ses critères avec analyse d'impact, et produire le diagramme de flux de cette étape.

### Tranche 1.1 — Projet, journal et critères versionnés

**Exigences** : EF-PRJ-01 à 03, EF-PRJ-05 (base), EF-CAD-01, EF-CAD-03 à 05, EF-VER-01, EF-VER-02, ENF-TRA-02, ENF-REP-05.

| Critères d'acceptation |
|---|
| Créer un projet produit un dossier `.revue` conforme à [03-architecture.md §4](03-architecture.md#4-format-du-dossier-de-projet), qui se rouvre à l'identique |
| Saisir une question PCC et au moins 6 critères; chaque critère a un code stable |
| Modifier un critère crée la version 2; la version 1 reste consultable et immuable (test : toute tentative de modification d'une version active lève une erreur) |
| Le différentiel v1 → v2 affiche exactement les critères ajoutés, retirés et modifiés (test sur 5 cas calculés à la main) |
| Chaque action ci-dessus produit une entrée de journal; la chaîne d'empreintes du journal se vérifie (test : altérer une entrée fait échouer la vérification) |
| Interface : pages « Cadrage » et « Critères » en français, utilisables au clavier |

### Tranche 1.2 — Assistance IA au cadrage et protocole

**Exigences** : EF-CAD-02, EF-CAD-06 à 08, EF-VER-03, ENF-COU-01, ENF-TRA-01.

| Critères d'acceptation |
|---|
| La tâche `suggest_pcc` renvoie une sortie structurée valide; chaque suggestion est acceptée, modifiée ou refusée explicitement, et ce choix est consigné avec l'`ai_call` correspondant |
| La tâche `qualify_criterion_change` propose un type de changement; la confirmation humaine est obligatoire avant que la version devienne active |
| Le protocole est généré en Markdown et en DOCX; il contient 100 % des éléments de Peters et al. (2022) (vérifié par une liste de contrôle en données), et une table de correspondance vers le gabarit OSF *Generalized Systematic Review Registration* |
| La section « usage prévu de l'IA » du protocole est remplie à partir de la configuration du projet |
| Enregistrer le DOI OSF du protocole fait passer toute nouvelle version de critères au statut « écart au protocole » (test) |
| Un coût estimé est affiché avant tout appel; tests uniquement avec `FakeProvider` + un test d'intégration marqué avec Claude |

### Tranche 1.3 — Stratégies de recherche et test de sensibilité

**Exigences** : EF-REC-01 à 06 (V1), ENF-REP-01.

| Critères d'acceptation |
|---|
| Blocs de concepts éditables (termes FR et EN, troncature, expressions exactes) |
| Traduction automatique vers PubMed, OpenAlex et PsycINFO (EBSCOhost); **10 stratégies de référence** écrites à la main par un ou une bibliothécaire (ou tirées de revues publiées) sont reproduites à l'équivalence syntaxique près (tests de comparaison) |
| Suggestions IA de synonymes et de descripteurs; les descripteurs MeSH suggérés sont vérifiés via E-utilities (réponses enregistrées en test); tout descripteur inexistant est signalé |
| Nombre de résultats par bloc et total pour PubMed et OpenAlex (réponses enregistrées en test) |
| Test de sensibilité : avec une liste de 10 articles clés dont 2 volontairement hors requête, l'outil rapporte 8/10, nomme les 2 manquants et le bloc responsable |
| Chaque version de requête est conservée avec texte exact, base, date et nombre de résultats |

### Tranche 1.4 — Collecte et import

**Exigences** : EF-COL-01, EF-COL-02 (Crossref), EF-COL-03, EF-COL-05, ENF-PER-04.

| Critères d'acceptation |
|---|
| Collecte OpenAlex et PubMed paginée, avec limiteur de débit conforme aux conditions documentées; reprise après interruption simulée sans doublon ni perte (test) |
| Nombre de références collectées = nombre annoncé par l'API (à ± 0, ou écart expliqué et consigné) |
| Import RIS : **au moins 5 exports réels** (PsycINFO EBSCOhost, PsycINFO Ovid, CINAHL, ERIC, Scopus ou Web of Science), anonymisés au besoin, importés avec 100 % des enregistrements valides reconnus; les enregistrements vides ou mal formés sont listés |
| Enrichissement Crossref par DOI des champs manquants, concurrence ≤ 3 |
| Chaque référence porte sa ou ses provenances; les pages brutes sont conservées |
| Message clair en français si un domaine est bloqué par la liste réseau |
| La clé OpenAlex est lue depuis `OPENALEX_API_KEY` (D-013) par `config/secrets.py` et envoyée seulement si elle est définie : elle est facultative, car le mandataire réseau l'ajoute dans l'environnement infonuagique (D-021). Un refus 401 ou 403 d'OpenAlex produit un message clair en français qui nomme `OPENALEX_API_KEY`, et arrête proprement la collecte OpenAlex (test) |

### Tranche 1.5 — Dédoublonnage

**Exigences** : EF-COL-06 à 08.

| Critères d'acceptation |
|---|
| Jeu de test annoté d'au moins **1 000 références** comprenant des doublons connus (identifiants exacts, variantes de titre, accents, majuscules, sous-titres, prépublication + version publiée signalée) |
| **Rappel des doublons ≥ 0,98 et précision ≥ 0,99** sur ce jeu, pour la combinaison automatique + paires soumises à l'humain |
| Les paires incertaines (score entre deux seuils réglables) sont présentées côte à côte; la décision humaine est consignée |
| Aucun enregistrement n'est supprimé; tout regroupement est réversible (test) |
| Les nombres « références identifiées par source » et « doublons retirés » sont calculés et exacts sur le jeu de démonstration |

### Tranche 1.6 — Réviseur IA de tri et essai pilote

**Exigences** : EF-SEL-01 à 07, EF-SEL-09, ENF-TRA-01, ENF-TRA-03, ENF-TRA-05, ENF-REP-02 à 04, ENF-COU-01 à 05, ENF-LAN-05.

| Critères d'acceptation |
|---|
| La tâche `screen_reference` produit, pour chaque référence, une évaluation par critère avec citation, une décision, une confiance et une justification nommant au moins un critère; 100 % des sorties sont valides au schéma (sinon nouvelle tentative, puis statut « échec » consigné) |
| Règle EF-SEL-07 vérifiée par test : aucun « exclure » quand un critère d'inclusion est « impossible à déterminer » et aucun critère n'est « non satisfait » |
| Chaque décision IA contient tous les champs d'ENF-TRA-01 (test qui échoue si un champ manque); la réponse brute est conservée et une décision peut être reconstituée sans rappel du modèle |
| Pilote : échantillon tiré avec graine consignée; tri humain **à l'aveugle** (test : l'interface ne montre pas la décision de l'IA avant la décision humaine) |
| Tableau d'étalonnage : accord, kappa de Cohen, AC1 de Gwet, sensibilité, spécificité, matrice de confusion, courbe seuil → sensibilité / références évitées. **Chaque métrique est vérifiée sur un cas calculé à la main** |
| Étalonnage isotonique ajusté et sauvegardé; seuils fixés avec justification consignée |
| Coût estimé avant le lot, plafond respecté (test : le lot s'arrête au plafond sans perte), coût réel totalisé; au banc d'essai, coût mesuré par 1 000 références **≤ 5 $ US** avec la configuration par défaut (D-015, ENF-COU-07) |
| **Banc d'essai SYNERGY** (lancé manuellement, résultats consignés dans `docs/resultats/`) : sur au moins 3 jeux SYNERGY en psychologie, sensibilité de l'IA au seuil par défaut **≥ 0,95** par rapport aux inclusions finales, avec la spécificité correspondante rapportée. Si la cible n'est pas atteinte, la tranche n'est pas bloquée mais le seuil par défaut est revu et le résultat consigné |

### Tranche 1.7 — Tri des titres et résumés, réconciliation, analyse d'impact

**Exigences** : EF-SEL-08, EF-SEL-10, EF-SEL-12, EF-VER-03 à 05 (V1), EF-VER-07 (consignation), ENF-PER-01 à 03.

| Critères d'acceptation |
|---|
| Double révision humain + IA sur toutes les références; la file des désaccords contient exactement les références où les deux décisions diffèrent (test) |
| Réconciliation : la décision finale est humaine, la justification de l'IA est visible à ce moment seulement |
| Tri entièrement au clavier; passage à la référence suivante < 200 ms sur un projet de 50 000 références (mesure automatisée) |
| Priorisation optionnelle par probabilité d'inclusion |
| Analyse d'impact : pour chacun des 5 types de changement, l'ensemble des références touchées correspond exactement à l'ensemble attendu sur un jeu construit à la main (au moins 5 cas par type) |
| Réévaluation des références touchées par l'IA, puis vérification humaine des décisions qui changent; anciennes décisions conservées |
| Le journal contient, pour chaque changement : versions, type, justification, nombre de références touchées, résultat de la réévaluation |

### Tranche 1.8 — Diagramme de flux et section méthode (tri)

**Exigences** : EF-DEC-01 (V1), EF-DEC-03 (tri), EF-PRJ-04, ENF-REP-06, ENF-LAN-04.

| Critères d'acceptation |
|---|
| Diagramme conforme au gabarit PRISMA 2020 « bases de données et registres », adapté aux revues de portée, en SVG, en français et en anglais |
| **Tous les nombres sont calculés à partir des données**; sur le jeu de démonstration, ils correspondent à un décompte fait à la main |
| Les réévaluations dues aux changements de critères sont rendues visibles (note ou case dédiée) |
| Ébauche de section méthode (FR et EN) couvrant l'usage de l'IA au tri selon RAISE et le gabarit de la CEE : outil et version, modèle et version exacte, rôle (second réviseur), résultats de l'étalonnage, seuils, nombre de désaccords et leur résolution, coût, limites |
| Archive du projet exportée; un test vérifie que chaque nombre du diagramme peut être recalculé à partir de l'archive seule, sans clé d'API |

### Critère de sortie de la V1

- Les 8 tranches sont fusionnées.
- **Essai de bout en bout** : Benoit (ou une équipe volontaire) mène un projet réel ou une reproduction d'une revue publiée jusqu'au diagramme de flux du tri des titres et résumés, et consigne les irritants.
- Les résultats du banc d'essai SYNERGY sont publiés dans `docs/resultats/`.
- La liste de vérification RAISE 2 (ENF-NOR-01) est rédigée et cochée pour ce qui concerne la V1.

---

## Version 2 — Texte complet, plusieurs réviseurs, sources élargies

| Tranche | Contenu | Exigences | Critères d'acceptation principaux |
|---|---|---|---|
| 2.1 Texte complet | Obtention (Unpaywall, téléversement), conversion avec pages, statut « introuvable » | EF-COL-02, EF-SEL-14, EF-SEL-15 | Taux de PDF en libre accès trouvés rapporté; sur 30 PDF de test, numéro de page correct pour ≥ 98 % des citations vérifiées |
| 2.2 Tri du texte complet | Même logique que le tri des résumés, citations avec page, motifs d'exclusion | EF-SEL-16 | Motifs d'exclusion obligatoires; diagramme complété jusqu'aux études incluses |
| 2.3 Rapports multiples | Regroupement des références d'une même étude | EF-SEL-17 | Sur un jeu annoté, ≥ 0,95 de rappel des regroupements proposés; validation humaine obligatoire |
| 2.4 Plusieurs réviseurs humains | Double tri humain, accord interjuges, arbitrage | EF-PRJ-05, EF-SEL-13 | Accord interjuges calculé et vérifié à la main; arbitrage par un troisième réviseur consigné |
| 2.5 Exclusion assistée encadrée | Mode IA seule pour les exclusions à haute confiance, avec garde-fous | EF-SEL-11 | L'outil **refuse** d'activer le mode si une condition manque (tests pour chaque condition); échantillon de vérification tiré et suivi; suspension automatique si la tolérance est dépassée |
| 2.6 Classificateur rapide | `ClassifierProvider` (scikit-learn) entraîné sur les décisions humaines | — | Mêmes métriques que Claude sur le banc SYNERGY; absence de justification signalée dans la section méthode |
| 2.7 Sources francophones et littérature grise | Érudit, theses.fr, HAL, dépôts québécois (OAI-PMH); plan de littérature grise | EF-COL-04, EF-REC-07 | Chaque source testée par réponses enregistrées; domaines ajoutés à la liste réseau et documentés dans `CLAUDE.md`; nombre de références par source dans le diagramme (« autres sources ») |
| 2.8 Traductions vers d'autres bases et PRISMA-S | CINAHL, ERIC, Scopus, Web of Science, PsycINFO Ovid; déclaration PRISMA-S | EF-REC-03, EF-DEC-04, EF-DEC-05 | Stratégies de référence reproduites; les 16 éléments PRISMA-S couverts |
| 2.9 Réévaluation complète | Flux complet de réévaluation (humain seul, IA seule avec vérification, mixte) | EF-VER-05 | Tous les modes testés; effets visibles dans le diagramme |

**Sortie de la V2** : une revue de portée peut être menée jusqu'à la liste finale des études incluses, avec deux réviseurs humains ou un humain et l'IA. Lancement de l'**étude de validation** (protocole gelé dans le dépôt, voir [05-plan-de-validation.md](05-plan-de-validation.md) et [09-protocole-validation.md](09-protocole-validation.md)).

---

## Version 3 — Extraction, synthèse et cartographie

| Tranche | Contenu | Exigences | Critères d'acceptation principaux |
|---|---|---|---|
| 3.1 Grille d'extraction versionnée | Champs typés, consignes, exemples; modèles de départ (Pollock et al., 2023) | EF-EXT-01, EF-EXT-02 | Création, modification, différentiel et historique comme pour les critères |
| 3.2 Pré-remplissage IA avec renvoi à la page | Valeur, citation exacte, page; « non rapporté » | EF-EXT-03 | Sur 20 études de test extraites à la main : exactitude par champ rapportée; **100 % des citations retrouvées textuellement à la page indiquée** (vérification automatique) |
| 3.3 Validation humaine et pilote d'extraction | Validation, correction, rejet; exactitude par champ | EF-EXT-04, EF-EXT-05 | Aucune valeur non validée n'apparaît dans la synthèse (test) |
| 3.4 Impact des changements de grille | Ajout, modification, retrait de champ | EF-VER-06 | Ensembles d'études touchées exacts sur des cas construits à la main |
| 3.5 Tableaux et cartes | Fréquences, tableaux croisés, cartes de données probantes, lacunes | EF-SYN-01 à 03 | Nombres vérifiés à la main sur le jeu de démonstration; export CSV, XLSX, SVG, HTML |
| 3.6 Synthèse narrative assistée | Ébauche par catégorie, rattachée aux études | EF-SYN-04 | Chaque phrase rattachée à au moins une étude incluse; révision humaine obligatoire |
| 3.7 Modèle local | `LocalLLMProvider` (API compatible Ollama/OpenAI) | — | Mêmes tâches et mêmes tests que Claude avec `FakeProvider`; banc SYNERGY exécuté avec au moins un modèle local |

---

## Version 4 — Consultation, déclaration complète, ouverture

| Tranche | Contenu | Exigences | Critères d'acceptation principaux |
|---|---|---|---|
| 4.1 Synthèses vulgarisées | Niveau de langue réglable, révision humaine | EF-CON-01 | Indice de lisibilité rapporté (ex. Kandel-Moles pour le français) |
| 4.2 Suivi des commentaires | Parties prenantes, commentaires, suites données | EF-CON-02, EF-CON-03 | Aucune donnée personnelle au-delà de nom, rôle, organisation (test de schéma) |
| 4.3 Liste PRISMA-ScR remplie | Proposition de texte ou d'emplacement pour chaque élément | EF-DEC-02, ENF-NOR-03 | 22 éléments de PRISMA-ScR 2018 couverts; **version 2026 ajoutée dès sa parution** sans changement de code |
| 4.4 Section méthode complète | Toutes les étapes, écarts au protocole, usage de l'IA | EF-DEC-03, EF-VER-07 | Révisée par un méthodologue externe et jugée conforme à RAISE et à PRISMA-ScR |
| 4.5 Interface anglaise | Catalogue de traduction anglais | ENF-LAN-03 | 100 % des chaînes traduites |
| 4.6 Ouverture et version hébergée (à décider) | Dépôt public, documentation d'installation, éventuelle version multi-utilisateurs | ENF-LIC-01 | Décision consignée au journal avant tout travail |

---

## Suivi

| Élément | Où |
|---|---|
| État des tranches | Demandes de fusion GitHub (étiquettes `V1`, `tranche-1.x`) |
| Décisions | [journal-des-decisions.md](journal-des-decisions.md) |
| Résultats des bancs d'essai | `docs/resultats/` (à créer à la tranche 1.6) |
