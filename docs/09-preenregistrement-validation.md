# 09 — Préenregistrement de l'étude de validation (ébauche)

> **Statut** : ébauche du 9 octobre 2026, tirée de [05-plan-de-validation.md](05-plan-de-validation.md), à déposer sur OSF **avant** le repérage et le tirage de l'ensemble de test. Rédigée en anglais, langue d'OSF et des revues visées, selon le gabarit « OSF Preregistration ». Une fois déposée, elle ne se modifie plus : tout changement devient un amendement daté.
> **Renvois** : [06-liste-raise2.md](06-liste-raise2.md) (RAISE 2, §2 et §4), [07-fiche-outil.md](07-fiche-outil.md), [08-journal-des-gabarits.md](08-journal-des-gabarits.md), [resultats/](resultats/README.md).

## À décider par Benoit avant le dépôt

Chaque point est marqué **[TO DECIDE]** dans le texte anglais.

1. **Équipe et auteurs.** Le plan exige deux personnes qui transcrivent les critères sans connaître les études incluses (§6.2 de 05), et au moins un évaluateur qui n'a pas participé au développement de l'outil pour l'analyse des erreurs (§6.5). Il faut nommer ces personnes.
2. **Version gelée du gabarit.** Le test se fait sur `screen_reference` v1, la version mesurée au banc, ou sur une v2 qui corrigerait le problème connu (évaluer tous les critères). Une v2 devrait d'abord être mise au point sur des données distinctes, puis consignée au journal des gabarits (08).
3. **Ensemble de développement.** Le plan prévoit 3 jeux SYNERGY **et** 4 à 5 revues de portée admissibles (§5.3). Les revues de portée de développement n'existent pas encore. Faut-il les constituer avant le gel, ou déclarer que le développement s'est fait sur SYNERGY seulement ?
4. **Condition principale et stabilité.** Le test de stabilité (D-099) montre que 9,6 % des notices changent d'issue d'une exécution à l'autre. Je propose de garder comme condition principale **une seule exécution**, comme dans l'usage réel de l'outil, et de mesurer la reproductibilité en analyse secondaire, comme le plan le prévoit.
5. **Budget.** Le plan demande de fixer un budget au préenregistrement. Estimation ci-dessous : environ **45 $ US**; je propose un plafond de **75 $ US**.
6. **Date de fin des données d'entraînement du modèle**, à relever dans la documentation du fournisseur et à consigner (sous-groupe de contamination).
7. **Références** : STARD 2015 et Cohen et al. (2006) sont à revérifier, comme le note 05.
8. **Réponses inutilisables** (choix ajouté, absent de 05) : je propose de les compter comme **conservées** dans l'analyse principale, puisque la personne les trierait de toute façon, et comme manquées dans une analyse de sensibilité (§5.5 du texte).
9. **Seuil de signification** (choix ajouté, absent de 05) : je propose des comparaisons bilatérales à α = 0,05, sans correction pour le petit nombre de comparaisons préspécifiées (§5.3 du texte).

---

# Preregistration

## 1. Study information

### 1.1 Title

A large language model as second reviewer for title and abstract screening in scoping reviews in psychology, the social sciences and health: a retrospective diagnostic accuracy study on published reviews.

### 1.2 Authors

Benoit Plante (developer of the tool). **[TO DECIDE: co-authors: two criteria transcribers blind to the included studies; at least one error-analysis assessor independent of the tool's development.]**

### 1.3 Description

revue-portee is free software (AGPL-3.0-or-later) that supports scoping reviews following the JBI method and PRISMA-ScR, with a large language model as a traceable second reviewer of titles and abstracts. For each reference, the model assesses every eligibility criterion (met, not met, cannot tell) with a quotation from the title or abstract, and gives a probability of inclusion. The tool derives the AI's decision from that probability and two thresholds (exclude below 0.10, include from 0.60, uncertain in between), and never excludes a reference when an inclusion criterion cannot be assessed and no criterion is failed (rule EF-SEL-07).

Almost all evaluations of LLM screening concern biomedical systematic reviews. Scoping reviews have broader, more conceptual criteria, and no data exist on French-language literature. So far, the tool has only been tested on its **development set**: three SYNERGY systematic reviews in clinical psychology (sensitivity 95.0–97.4%; response stability: same outcome for 90.4% of references over three runs). In RAISE 2 terms, these are development results, neither a held-out test nor a validation.

This study estimates the tool's accuracy on **held-out** published scoping reviews, with the prompt template, thresholds, model and code frozen before the test set is drawn.

### 1.4 Hypotheses

**H1 (primary).** At the default thresholds, the pooled sensitivity of the AI reviewer, against the studies finally included in published scoping reviews, is at least 0.95, and the lower bound of its 95% confidence interval is at least 0.90.

Benchmark: a single human reviewer misses about 13% of relevant studies (sensitivity about 0.87; Gartlehner et al., 2020).

The secondary objectives (section 4.2) are estimated without hypothesis tests, except for the paired comparisons named in section 5.3.

## 2. Design plan

### 2.1 Study type

Methodological study using existing data: retrospective diagnostic accuracy study by simulation. The tool is applied to the screened (or reconstructed) references of published scoping reviews, and its decisions are compared with a reference standard taken from those reviews. No human participants; published literature and public data only.

### 2.2 Blinding

- The criteria of each review are transcribed into the tool's format by two team members **blind to the list of included studies**, independently, then reconciled. They use only the eligibility criteria and examples given in the article. No rewording is allowed after the results are seen.
- The tool never sees the reference standard.
- Missed included studies are classified by two assessors, at least one of whom did not take part in the tool's development.

### 2.3 Study design

The units of analysis are references (records) within reviews (clusters).

**Conditions applied to every test review:**

1. **Default (primary)**: one AI run on every reference, default thresholds, no calibration.
2. **Simulated pilot**: 100 references drawn at random with a recorded seed. Their reference-standard decisions serve as pilot human decisions to fit the isotonic calibration and choose the exclusion threshold with the tool's pre-specified rule (target sensitivity 0.95 on the pilot). The evaluation is on the remaining references. This condition reuses the AI outputs of condition 1: no new model calls.
3. **Reproducibility**: two further runs on a random 10% of the references of each review (at least 200).
4. **Prompt strategy**: on at least 8 test reviews drawn at random, one call per reference against one call per criterion.
5. **Other providers** (fast classifier, local model): only if available in the frozen version; otherwise not run.

### 2.4 Randomization

- The test reviews are drawn at random, stratified by domain (psychology; social sciences and education; health) and by language, with a recorded seed.
- The pilot samples (condition 2), the reproducibility samples (condition 3) and the reviews of condition 4 are drawn with recorded seeds.

## 3. Sampling plan

### 3.1 Existing data

**Registration prior to accessing the test data.** The eligible reviews have not yet been searched, and no test review has been drawn or run through the tool. The development data (three SYNERGY datasets: Oud_2018, van_de_Schoot_2018, van_Dis_2020) have been used, and are excluded from the test set. **[TO DECIDE: whether 4–5 scoping reviews are added to the development set before the freeze.]**

### 3.2 Explanation of existing data

The development results are public in the repository (`docs/resultats/`). They informed the default thresholds and the choice of model; they are not part of the test.

### 3.3 Data collection procedures

**Eligibility of reviews.**

Inclusion:
- a scoping review published in a peer-reviewed journal between 2019 and 2026;
- in psychology, mental health, the social sciences, education, social work, public health or nursing (not purely biomedical or basic clinical);
- following the JBI method and/or PRISMA-ScR;
- with explicit eligibility criteria, or a PCC framework detailed enough to be turned into criteria;
- with a complete list of included studies, with identifiable references;
- with at least 10 included studies;
- with either:
  - **stratum A**: title and abstract screening decisions available per reference (supplement, OSF, data repository, or from the authors on request), or
  - **stratum B**: a complete, reproducible search strategy (PRISMA-S) in at least one database the tool can query (PubMed, OpenAlex) or export in RIS (PsycINFO).

Exclusion:
- more than 10% of included studies that cannot be matched to a reference;
- reviews of non-textual or non-indexed sources only;
- reviews of the development set;
- reviews authored by a member of the validation team. A sensitivity analysis may include them.

**Identification.**
1. Search OpenAlex, PubMed and PsycINFO for scoping reviews; search OSF for scoping review projects that share their screening data; contact authors for screening decisions (stratum A).
2. Draw at random from the eligible reviews, stratified as in 2.4.
3. Over-sample French: at least 6 reviews in which at least 20% of screened references are in French.
4. Contamination: at least one third of the test reviews published after the model's training data cut-off. **[TO DECIDE: record the cut-off date declared by the provider.]**

**Reconstruction (stratum B).** The published strategy is rerun with a date limit equal to the original search date. Subscription databases are imported in RIS, and the tool deduplicates (rules version 1, tested on held-out ASySD data: recall 0.998–1.000, precision 0.994–0.998). The gap between the reconstructed and reported numbers is reported. A review with a gap above 20% is left out of the primary analysis and kept for a sensitivity analysis.

**Frozen configuration, recorded on OSF (amendment) before the test set is drawn:**
- commit hash of the tool;
- prompt template `screen_reference` and its version **[TO DECIDE: v1 or a v2 developed on separate data]**;
- model requested (`claude-haiku-5-5`, effort `low`), with the exact version returned by the API recorded on every call;
- thresholds (0.10 and 0.60) and all parameters.

Nothing may change afterwards; any further run is declared exploratory.

**Execution.** All test runs are made in a short time window, through the provider's batch API. Raw responses are kept, so that every decision can be rebuilt without calling the model again.

### 3.4 Sample size

24 to 30 test reviews, at least 6 with a large share of French literature, plus the development set.

### 3.5 Sample size rationale

- Estimating a sensitivity of 0.95 with a half-width of 0.02 needs about 456 positive references without clustering (n = 1.96² × 0.95 × 0.05 / 0.02²).
- With about 40 included studies per review and an assumed intraclass correlation of 0.025, the design effect is about 2, hence about 900 positive references, or 24 to 30 reviews.
- The final number is fixed once the eligible reviews have been identified (median number of inclusions), before the draw, and recorded as an amendment.

### 3.6 Stopping rule

Data collection stops when the planned number of reviews has been drawn and run, or when the budget ceiling is reached. **[TO DECIDE: ceiling, proposed at 75 USD.]**

Budget estimate, at the batch price measured at about 0.18 USD per 1,000 references (half the 0.36 USD measured with individual calls):

| Condition | Assumption | Estimate |
|---|---|---|
| 1, default | 30 reviews × about 4,000 references | about 22 USD |
| 2, simulated pilot | reuses the outputs of condition 1 | 0 USD |
| 3, reproducibility | 2 more runs on 10% | about 4 USD |
| 4, prompt strategy | 8 reviews, one call per criterion | about 15 to 20 USD |
| **Total** | | **about 45 USD** |

If the ceiling is reached, the reviews already run are analysed, and the shortfall is reported.

## 4. Variables

### 4.1 Manipulated variables

- Thresholds: default, or set on a simulated pilot.
- Prompt strategy: one call per reference, or one call per criterion.
- Provider: if available.

### 4.2 Measured variables

- **Reference standard.**
  - Positives: all references of the studies finally included, multiple reports included.
  - Negatives: in stratum A, references the authors excluded at title and abstract; in stratum B, all other reconstructed references. Some of these were excluded at full text, which underestimates specificity.
- **AI decision**: include, uncertain or exclude, derived by the tool. A reference is **kept** when the AI includes it or is uncertain.
- **Covariates**:
  - domain;
  - language of the reference, detected and recorded by the tool;
  - publication before or after the training cut-off;
  - presence of an abstract;
  - stratum.

### 4.3 Indices

**Primary.** Sensitivity: kept positives / all positives, per review and pooled.

**Secondary:**
- sensitivity per study (a study is found if at least one of its references is kept);
- specificity (mainly stratum A);
- proportion of « uncertain »;
- references the AI would exclude (assisted exclusion workload);
- WSS@95;
- recall as a function of the screened proportion in prioritised mode;
- agreement with the human title and abstract decisions (percentage, Cohen's kappa, Gwet's AC1, PABAK; stratum A);
- calibration (Brier score, ECE with 10 bins, calibration slope and intercept, reliability diagram), before and after calibration;
- reproducibility: identical decisions between runs, Gwet's AC1 between runs;
- quality of rationales on a stratified random sample of 300 decisions: right criterion cited; quoted passage present word for word and supporting the decision. The tool also reports the share of quotes found automatically;
- cost and tokens per 1,000 references, and duration.

## 5. Analysis plan

### 5.1 Statistical models

- **Per review**: sensitivity and specificity with Wilson intervals.
- **Pooled**: generalised linear mixed model (logit link, random intercept for review). For stratum A, a bivariate sensitivity–specificity model. Cluster bootstrap over reviews as a confirmatory interval.
- **Comparisons** (default against simulated pilot; prompt strategies; providers): mixed models paired on references, with a McNemar test per review as a complement.

### 5.2 Transformations

None beyond the logit link. Decisions are made binary as kept against excluded.

### 5.3 Inference criteria

- **H1** is supported if the pooled sensitivity is at least 0.95 **and** the lower bound of its 95% confidence interval (mixed model) is at least 0.90.
- **[TO DECIDE]** The paired comparisons are two-sided at α = 0.05, without correction for the small number of pre-specified comparisons, and are reported with their effect sizes and intervals.

### 5.4 Data exclusion

- Reviews with a reconstruction gap above 20% are left out of the primary analysis (sensitivity analysis).
- Missed included studies classified as probable errors of the reference standard (category c, below) are kept in the primary analysis and left out in a sensitivity analysis.

### 5.5 Missing data

- References without title or abstract are kept: the tool treats them as « uncertain » by rule EF-SEL-07. Their number is reported.
- AI responses still unusable after one retry are counted as failures and reported. **[TO DECIDE]** In the primary analysis they count as **kept**, since the person would screen them anyway. A sensitivity analysis counts them as missed.

### 5.6 Error analysis

Every missed included study is classified by two assessors, at least one independent of the tool's development:

- (a) abstract missing or uninformative;
- (b) ambiguous criterion in the original article;
- (c) debatable inclusion in the original review (probable error of the reference standard);
- (d) AI error (criterion misapplied, made-up content, misreading);
- (e) other.

Inter-assessor agreement is reported, and disagreements are resolved by discussion.

### 5.7 Pre-specified subgroups

- domain;
- language of the reference (French against English);
- publication before or after the model's training cut-off;
- presence of an abstract;
- stratum A against B.

### 5.8 Exploratory analyses

- Full-text screening, after V2, for reviews with open-access PDFs.
- Any analysis not listed above is reported as exploratory.

## 6. Other

- **Software**: revue-portee at the frozen commit; analysis in Python (statsmodels) or R (lme4). The analysis code is published.
- **Open science**: published on OSF:
  - transcribed criteria;
  - prompt templates and exact model versions;
  - AI decisions with confidence and rationale;
  - raw responses without copyrighted text;
  - analysis code.

  Identifiers only (DOI, PMID, OpenAlex ID) for references, no titles or abstracts, except under open licences. A preprint, then a methods journal (*Research Synthesis Methods*, *JBI Evidence Synthesis*, *Systematic Reviews*).
- **Reporting**: STARD 2015 adapted to the context, the reporting items of RAISE 2 (§4), and the PRISMA extension on AI if published before submission.
- **Ethics**: no participant data; screening decisions obtained from authors are used with their consent and cited.
- **Conflict of interest**: the developer of the tool is on the team. Mitigations:
  - this preregistration;
  - the freeze before the test;
  - independent error assessors;
  - publication whatever the results.
- **Development history**: RAISE 2 checklist, tool sheet and prompt development journal of the repository; the prompt template was not tuned on any data before the test.

## References

- Bossuyt PM, et al. STARD 2015. *BMJ* 2015;351:h5527. **[TO VERIFY]**
- Cohen AM, et al. Reducing workload in systematic review preparation using automated citation classification. *JAMIA* 2006;13(2):206–219. **[TO VERIFY]**
- De Bruin J, et al. SYNERGY — Open machine learning dataset on study selection in systematic reviews. 2023. doi:10.34894/HE6NAQ
- Flemyng E, et al. Position statement on AI use in evidence synthesis across Cochrane, the Campbell Collaboration, JBI and the Collaboration for Environmental Evidence 2025. *JBI Evid Synth* 2025;23(11):2162–2166. doi:10.11124/JBIES-25-00480
- Gartlehner G, et al. Single-reviewer abstract screening missed 13 percent of relevant studies: a crowd-based, randomized controlled trial. *J Clin Epidemiol* 2020.
- Hair K, et al. The Automated Systematic Search Deduplicator (ASySD). *BMC Biology* 2023;21:189. doi:10.1186/s12915-023-01686-z
- Thomas J, et al. Responsible use of AI in Evidence Synthesis (RAISE 2026) 2: building and evaluating AI evidence synthesis tools. Version 4, 2026. OSF, doi:10.17605/OSF.IO/FWAUD
- Tran VT, et al. Sensitivity and specificity of using GPT-3.5 Turbo models for title and abstract screening. *Ann Intern Med* 2024. doi:10.7326/M23-3389
- Vembye MH, et al. GPT models can function as highly reliable second screeners of titles and abstracts. *Psychological Methods* 2025. doi:10.1037/met0000769
