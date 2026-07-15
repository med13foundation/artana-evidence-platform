# Trusted Claim Quality Improvement Research

Date: 2026-07-15

Status: active design evidence for TG-03 through TG-08

## Question

How can Artana materially improve biomedical claim precision, completeness,
and repeatability while keeping agents responsible for semantic decisions and
never counting deterministic fallback as agent evidence?

## Research Result

The evidence does not support relying on unconstrained, zero-shot relation
triplet generation as the complete product architecture.

- BioRED was built specifically for document-level biomedical relations across
  multiple entity and relation types, with separate novelty labels. Its original
  benchmark reported that novel relation extraction remained substantially
  harder than entity recognition.
- BioREx improved BioRED relation extraction from 74.4% to 79.6% F1 by
  harmonizing multiple expert-labeled biomedical corpora. This is evidence that
  task structure and biomedical supervision matter, not only general model
  strength.
- A 2025 benchmark across 61 biomedical corpora reported that no evaluated
  zero-shot model exceeded 0.5 F1 for relation-triplet extraction on any
  dataset. A separate OpenAI-model benchmark found particular difficulty with
  complex inputs containing multiple predicates.
- PubTator 3.0 combines dedicated entity recognition, normalization, and
  relation extraction and exposes entity and relation APIs. Its normalized
  candidates are useful tools for an Artana agent, but they are not independent
  proof that an Artana claim is correct.
- An ACL 2025 study found biomedical LLM judges usually below 50% judgment
  accuracy. Therefore Artana must not use an agent's numeric opinion as its
  precision measurement. Structured outputs helped judging, but did not turn
  an LLM judge into ground truth.
- Structured biomedical claim verification works better when claim
  comprehension, evidence analysis, an intermediate conclusion, and the final
  entailment decision are separate steps.
- Directional entity roles are important enough that BioREDirect added 10,864
  direction annotations to BioRED and jointly models relation, novelty, and
  role direction. Artana therefore cannot validate endpoints as an unordered
  pair when the relation is directional.
- Recent document-level systems improve relation extraction by separating
  entity, entity-pair, and relation reasoning and by combining local with
  document context. A source-local exact span remains the evidence anchor, but
  it may not contain all context needed to resolve a real cross-sentence claim.
- A 2026 biomedical entity-linking study identifies first-stage candidate
  recall as a fundamental ceiling on final linking quality. TG-06 must measure
  candidate-pool recall separately from the agent's categorical selection.

Primary references:

- [BioRED dataset](https://pmc.ncbi.nlm.nih.gov/articles/PMC9487702/)
- [BioREx](https://pubmed.ncbi.nlm.nih.gov/37673376/)
- [PubTator 3.0](https://pmc.ncbi.nlm.nih.gov/articles/PMC11223843/)
- [PubTator 3.0 API](https://www.ncbi.nlm.nih.gov/research/pubtator3/api)
- [GNorm2](https://pubmed.ncbi.nlm.nih.gov/37878810/)
- [Zero-shot biomedical relation extraction benchmark](https://aclanthology.org/2025.wasp-main.6/)
- [Cross-corpus zero-shot relation-triplet benchmark](https://aclanthology.org/2025.bionlp-1.9/)
- [Biomedical LLM-judge evaluation](https://aclanthology.org/2025.acl-long.1238/)
- [Structured biomedical claim verification](https://aclanthology.org/2025.bionlp-1.14/)
- [BioREDirect directionality annotations](https://pmc.ncbi.nlm.nih.gov/articles/PMC12306822/)
- [HTGRS document-level decomposition](https://pmc.ncbi.nlm.nih.gov/articles/PMC11629692/)
- [Generative relevance feedback for biomedical entity linking](https://academic.oup.com/bioinformatics/article/42/2/btag011/8426181)

## Product Architecture

The recommended path is an agent-centered, tool-assisted pipeline:

```text
source snapshot
  -> sentence and local-context claim inventory
  -> authoritative entity candidates from biomedical tools
  -> Luna selects or abstains on entity identity
  -> Luna emits one complete qualified ClaimFrame at a time
  -> independent Luna verifier checks the complete frame against source only
  -> deterministic authority, schema, provenance, and policy checks
  -> claim ledger
  -> optional safe projection
```

Dedicated biomedical systems may propose spans, identifiers, and relation
candidates. They may not satisfy Artana's semantic gate. The agent must make a
categorical selection or abstain, and deterministic code must verify the
selected identifier against the authoritative record.

## Ordered Quality Experiments

### Q1: Decompose Complex Extraction

Replace one unconstrained request for all relations with two semantic agent
steps:

1. inventory each source-local claim and its exact supporting sentence or
   local context;
2. frame one inventoried claim at a time with closed polarity, status, roles,
   qualifiers, and source measurements.

This directly targets the TG-03 failures where endpoints and qualifiers trade
roles, multiple predicates are conflated, or no usable frame is returned.

The inventory must also emit one closed endpoint-role category:
`A_SUBJECT_B_OBJECT`, `B_SUBJECT_A_OBJECT`, or `UNRESOLVED`. Framing must follow
the resolved direction exactly and may only abstain when direction is
unresolved. This keeps semantic responsibility with the agent while making a
reversed graph edge deterministically detectable.

Success evidence: paired improvement on the same sealed holdout in full-frame
correctness, polarity, qualifier fidelity, measurement recall, and canonical
stability. Safety counts must not regress.

If the paired transition ledger shows misses caused specifically by
cross-sentence context, run a separate bounded-context experiment. Give the
agent the exact evidence span plus adjacent source regions with immutable
offsets, while requiring it to identify which spans support endpoints,
relation, direction, and qualifiers. Do not widen context for source-local
failures or allow document context to replace the exact evidence anchor.

### Q2: Give The Agent Biomedical Candidates

For each mention, retrieve a small typed set of candidates from authoritative
biomedical systems such as PubTator 3.0, GNorm2, NCBI Gene, MeSH, ClinVar, and
ClinicalTrials.gov. Ask the agent to return `selected`, `ambiguous`,
`unresolved`, or `not_applicable` with a source-grounded explanation.

Deterministic code verifies identifier syntax, entity type, record existence,
record version, and content hash. It does not choose the biomedical meaning.

Success evidence: wrong-link count remains zero while verified endpoint
coverage improves; ambiguity is preserved instead of forced to the nearest
identifier.

### Q3: Independent Full-Claim Verification

The verifier must see the frozen source, locator, and complete ClaimFrame, but
not extractor rationale, downstream trust state, fixture labels, or external
facts. It returns closed support, argument-grounding, qualifier-fidelity, and
polarity-fidelity categories plus exact spans and a falsification note.

Success evidence: unsupported broad claims, wrong polarity, and missing
qualifiers are categorically rejected. No heuristic result or external fact
can repair missing source-local support.

### Q4: Error-Directed Examples Without Holdout Leakage

Build prompt examples only from a sealed development set and organize them by
observed failure class: endpoint-versus-qualifier role, negation/null result,
variant state, population/intervention/comparator/outcome, measurement role,
and multi-claim sentences. Never select examples after looking at a holdout
answer.

Success evidence: improvement transfers to untouched holdout and real-source
cases. Development-only gains receive no merge credit.

### Q5: Model Ablation Only After Architecture Tests

Keep `openai:gpt-5.6-luna` as the required acceptance model. If two properly
implemented architecture experiments fail the paired progress rule, run the
same frozen inputs through one stronger model as a diagnostic ablation. A
stronger-model win means model capacity is a plausible bottleneck; a shared
failure means the task contract, context, or evidence is still wrong.

No stronger-model result may be substituted for the required Luna gate without
an explicit product decision and a new frozen baseline.

## How Precision Is Measured

An agent does not produce a numeric precision score.

1. A frozen case contains expert-corpus or independently adjudicated
   categorical labels and exact evidence.
2. An agent emits categorical fields, exact spans, and an explanation.
3. Deterministic code compares fields and spans to the frozen labels.
4. Code counts true positives, false positives, and false negatives and derives
   precision, recall, and stability.
5. Agent reviewers explain disagreements and failure mechanisms; they do not
   overwrite the metric or become the sole gold standard.

For small sealed sets, report exact paired case transitions as well as rates:
`wrong -> correct`, `correct -> wrong`, `unchanged wrong`, and `unchanged
correct`. A percentage increase without the case transition ledger is
insufficient evidence.

The benchmark must also prove a one-to-one path from provider output to scored
claims. A run is not valid when the provider response is incomplete, carries
hidden instructions or prior-response context, or contains accepted claims
that disappear before scoring. The scored ClaimFrame multiset must equal the
provider-bound accepted framing multiset. These checks prevent local filtering
from improving precision by silently removing false positives.

## Progress And Stop Rules

Each semantic PR must satisfy all of the following:

- no regression in fallback credit, negative/null leakage, unsafe promotion,
  source binding, or agent-authored numeric values;
- at least one predeclared product metric improves on untouched cases;
- paired improvements exceed paired regressions;
- no failure class is hidden by removing it from the denominator;
- three-run worst-case results improve or meet the final gate;
- all remaining failures are listed by case and category.

If two consecutive product experiments fail to produce a positive paired net
change, stop editing prompts. Perform the model ablation and re-evaluate the
task decomposition, source context, candidate tools, and gold labels before
opening another implementation PR.

## New Knowledge And Hypotheses

External corroboration is not required for a source-local finding to be
preserved. Artana separates three records:

- `ESTABLISHED`: source-local support plus required verification and grounding;
- `NOVEL_FINDING`: explicitly presented by its source as a new result, with the
  same source-local fidelity requirements;
- `HYPOTHESIS`: an author hypothesis or an Artana cross-document inference that
  is traceable to its supporting paths but is not asserted as established.

A hypothesis may be valuable precisely because no external source already
states it. The correct response is to preserve its provenance and falsification
conditions, route it for review, and block established-positive projection.
Absence of corroboration is not evidence of falsehood; it is evidence that the
claim belongs in a different epistemic lane.

## PR Mapping

| Experiment | Owning PR | Required proof |
|---|---|---|
| Q1 claim inventory and one-frame-at-a-time extraction | TG-03 | Paired full-frame and stability improvement on the sealed holdout |
| Lossless storage of every result, including hypotheses | TG-04 | Zero field loss through both services and Postgres |
| Q3 independent source-only verifier | TG-05 | Unsupported or qualifier-wrong claims eligible: zero |
| Q2 authoritative candidate tools and abstention | TG-06 | Wrong links zero, verified coverage at least 95% |
| Deterministic policy over persisted facts | TG-07 | Unsafe or lossy projection zero |
| External expert-corpus and real-source validation | TG-08 | Every frozen agent-readiness gate passes in all three runs |

This mapping improves the product without adding a new PR or a parallel
evaluation program.
