# Validating the Artana Evidence Platform: READ, GROUND, CONNECT

**A measurement plan for a system that cannot currently state its own accuracy.**

Status: PROPOSED. Nothing in this plan has been run against a provider.
Written against tree SHA `86ddb3cb`. Every code citation below was checked at that SHA.
Date: 2026-07-25.

---

## 0. The one-page version

**What the product owner asked for.** Asked what "validating the backend" means, the product owner answered: not "read a paper" but "read many papers and create evidence and connect it."

That sentence contains three distinct capabilities, and they need to be measured separately because they fail separately.

| # | Capability | Plain statement | Measurable today? |
|---|---|---|---|
| 1 | **READ** | Given one document's text, find the claims in it. | **Yes.** Blocked only by four known engineering defects (H1–H4). |
| 2 | **GROUND** | Bind each claim to an exact span of source text, with a receipt someone else can check. | **Yes.** The emitted offsets are absolute and comparable to gold. |
| 3 | **CONNECT** | Recognise that an entity in paper A and an entity in paper B are the same entity; merge or contradict claims across documents; end with *one* node supported by five papers rather than five nodes. | **Not end-to-end on the AI-authored path.** See below. |

**The honest headline, stated early because burying it would be the main way this document could mislead:**

> Capability 3 — the one the product owner named as the point — **cannot be measured end-to-end on the AI-authored document path today.** It is not that we would measure it and get a bad number. It is that the code path terminates in an HTTP 409 quarantine before any connecting is attempted (blocker **C1**), and on the path that does run, cross-document identity is **zero by construction** because the claim de-duplication key includes the source span (blocker **C3**). A span from paper A can never equal a span from paper B.
>
> The graph kernel itself is *not* inert. Human/curator-authored claims do resolve into canonical relations and read back correctly — I ran three integration tests against the real database this session and all three pass. The wall is specific to claims marked as agent-authored.
>
> Therefore **the most valuable deliverable of the first month is not a number.** It is a defensible statement of the form: *"the connecting capability is not wired end-to-end; here is exactly where it stops; here is what it costs to close."* A plan that promises a CONNECT accuracy figure in month one is promising something the code cannot produce.

**Why CONNECT is the capability that matters most.** If per-document extraction is correct with probability *p*, the naive expectation is that a fact appearing in *k* papers assembles onto one node with probability *p^k*:

| p | k=2 | k=3 | k=5 |
|---|---|---|---|
| 0.95 | 0.90 | 0.86 | 0.77 |
| 0.90 | 0.81 | 0.73 | 0.59 |
| 0.80 | 0.64 | 0.51 | 0.33 |
| 0.70 | 0.49 | 0.34 | 0.17 |

**This table is a lower bound under an assumption we know to be false, and it must be labelled as such wherever it is published.** It assumes each document's outcome is independent. Errors within a fact are strongly *positively* correlated in reality — five papers about the same gene fail to link for the same reason (the verified dictionary does not contain it). Under perfect correlation, assembly probability is *p*, not *p^k*. The one dataset in this program where the assumption is checkable violates it in the optimistic direction (§7.1). The table's role is to show that **assembly quality is not recoverable from per-document quality in either direction** — which is the argument for measuring CONNECT directly. It is not a prediction, and §14 forbids shipping it as one.

**Corpus decision, settled by measurement this session, not by literature review.**

- The previously selected corpus, **BioNLP-ST GENIA**, annotates only `Protein` and `Entity` and contains **zero** entity-normalization records. It never says what anything *is*, so it cannot score whether you linked it correctly. It stays for the READ estimand it is uniquely good at, and only that.
- **BioRED** was the leading replacement. I fetched it and measured it: **29 of 6,311 distinct facts appear in ≥3 documents (0.46%)**. The shipped auto-promotion gate requires `min_distinct_sources = 3`. Twenty-nine gold instances gives a 95% half-width of ±0.18. That is GENIA's mistake in a new costume — the right structural property, at the wrong density. **BioRED is disqualified as the merge corpus** and retained for entity identity and grounding, where its per-mention normalization is excellent.
- **BC5CDR** carries **122 facts at k≥3 and 325 at k≥2** — roughly 5× the recurrence density — and its licence is verified public domain from its own README. **BC5CDR is the merge corpus.**

**Merge yield is superlinear in corpus size.** Measured by subsampling: 300 documents yields ~6 facts at k≥2; 1,500 documents yields 325. **You cannot pilot the merge endpoint.** Halving the corpus more than quarters the denominator. This reshapes the tier design; it is not a caveat.

**The unpassable gate you should know about before setting any target.** The verified entity dictionary covers **0.46% of BioRED mentions and 0.28% of BC5CDR mentions** (94/20,419 and 81/28,785). Any entity-linking target must be published against that ceiling, or it is a target on a number that cannot move.

**Readiness, not money, is the constraint.** Measured provider cost is $0.016861/call; a full run is on the order of $40. Engineering readiness is **~45–48 engineer-days plus an unscoped ClaimFrame-persistence contract**. Nobody can start a pilot on Monday. Phase 0 — roughly two weeks of zero-provider-cost work that can invalidate the design before money is spent — can and should start Monday.

---

## 1. What the three capabilities mean operationally

### 1.1 READ

Input: one document's text. Output: a set of claims, each with a predicate, participants, and a polarity.

This is what the existing validation program measures, and it is real work. It is also the *easiest* of the three and the one least in doubt: qualitatively the extractor performs well. The risk here is not that READ is broken; it is that a good READ number gets reported as though it answered the product owner's question.

### 1.2 GROUND

Input: a claim. Output: character offsets into the source document, such that a third party can re-read the span and see the claim in it.

Verified sound: `document_extraction_support/claim_frames/mentions.py` binds absolute offsets by adding the relative offset to `source_start_offset`. The emitted quantity is directly comparable to gold entity offsets in BioRED and BC5CDR. This estimand is well-posed.

### 1.3 CONNECT

Three sub-capabilities, which fail independently and must be scored independently:

1. **Entity identity across documents** — "TNF-alpha" in paper A and "tumour necrosis factor alpha" in paper B are one entity.
2. **Fact merge** — the same relation asserted by five papers becomes one canonical node with five supports, not five nodes.
3. **Contradiction surfacing** — paper A says X causes Y, paper B says it does not; the system must show both, not silently keep one.

**Why fact merge is zero by construction on the LLM path.** The claim de-duplication identity includes the source span. Two claims from different documents therefore never share an identity, regardless of how semantically identical they are. This is not a model quality issue and no amount of prompt work changes it. It is a design property, and whether it is deliberate document-scoped isolation of drafts or an oversight is **open decision 5** in §13 — that answer determines whether arm 3-P below measures a choice or a bug.

**Why the system parks rather than merges.** For a cluster of *k* coreferent claims, the shipped behaviour retains the first and marks the remaining *k−1* `identity_pending`. This matters enormously for how the metric must be defined; see §6.3.

### 1.4 The three arms of the CONNECT lane, with explicitly unequal claim strength

This separation is the single most important structural decision in the plan. Conflating these arms is how a program of this kind produces a flattering, meaningless number.

| Arm | What it exercises | Runnable at `86ddb3cb`? | Strength of claim it can support |
|---|---|---|---|
| **3-P** | The proposal layer: claims as proposed by the extractor, before promotion. | **Yes.** | Weak-to-moderate. Ceilinged by C3; see §6.3. Measures the proposal layer, not the product. |
| **3-K** | The graph kernel directly: does the canonicalization machinery behave correctly given resolved inputs? | **Yes**, with two privileged identities (§4, R4). | **Component-level only.** With gold entity IDs, one of its endpoints is a tautology — see §6.4. Must be rebuilt on system-produced entity IDs to say anything about the product. |
| **3-E** | End-to-end: document in, canonical multi-source node out. | **No.** Blocked by C1, C2, C5, C6. | This is the product. It is the arm that answers the product owner. It is blocked. |

**Say this plainly in any summary:** 3-E is blocked, 3-K as originally specified is guaranteed to return 1.0, and 3-P is structurally ceilinged. **There is currently no arm that can return an informative end-to-end merge number.** Fixing that is engineering work, described in §5, not measurement work.

---

## 2. Corpora: what was measured, and the licence position

All figures below were computed this session from the fetched corpora. They have been independently re-derived twice from the PubTator format specification, without reusing the extraction script, and reproduce to the digit.

### 2.1 The census

| Quantity | BioRED | BC5CDR |
|---|---|---|
| Documents | 600 | 1,500 |
| Entity mentions | 20,419 | 28,785 |
| Relation instances | 6,503 | 3,116 |
| Distinct facts (normalized triples) | 6,311 | 2,434 |
| Facts in ≥2 documents | 146 (2.31%) | **325 (13.35%)** |
| Facts in ≥3 documents | **29 (0.46%)** | **122 (5.01%)** |
| Facts in ≥5 documents | 4 | 43 |
| Max documents per fact | 7 | 25 |
| Instances in multi-doc clusters | 338 / 6,503 (5.20%) | 1,007 / 3,116 |
| Kish effective-size factor | — | 5.070 |
| k = 2 / 3 / 4 / ≥5 strata | — | 203 / 55 / 24 / 43 |

### 2.2 Why BioRED cannot be the merge corpus

The shipped auto-promotion gate is `min_distinct_sources = 3`. BioRED offers 29 gold facts that clear it. The 95% binomial half-width at n=29 is `1.96 × √(0.25/29) = ±0.182`. An endpoint whose confidence interval spans ±18 points cannot distinguish a system that works from one that does not.

This is exactly the failure mode that disqualified GENIA, arriving through a different door. BioRED has the right *kind* of annotation and the wrong *density* of the specific structure the estimand needs. It remains the right corpus for entity identity (Lane 3-A) and grounding (Lane 2), where it is measured per-mention and n is in the thousands.

### 2.3 Licences — the good news and the live exposure, stated together

**BC5CDR: verified public domain.** Its `README.txt` carries the NCBI notice verbatim, including that the U.S. Government has placed no restriction on use or reproduction. Safe to fetch on demand and to derive digests from.

**BioRED: verified.** The archive's SHA-256 is byte-identical to the hash recorded in the archived 2026-07-21 public gold intake receipt at `db96b23d`. The provenance record reproduces.

**BioNLP-ST GENIA: there is a live licence exposure in this public repository right now, and it is not prospective.** Two git-tracked fixture files under `scripts/validation/claim_events/fixtures/` (`tg04_bionlp_ge_development_v1.json` and `_v2.json`) each embed **54,834 characters of GE `source_text`** across 40 documents. The repository remote is public. GE's licence requires organiser permission for public use by a commercial or non-academic organisation.

This must not be reported as "licences verified, both public domain" without the qualifier, because that sentence is true of the two new corpora and false of the one Lane 1 actually runs on. Resolving this — removal, or written organiser permission — is **on the critical path**, not decoupled.

**Standing rule for this program:** licence-restricted corpora are fetch-on-demand. Only derived digests (counts, hashes, offsets) may ever be committed. Annotation content may not.

### 2.4 Merge yield is superlinear — you cannot pilot this endpoint

Subsampling BC5CDR documents, 40 draws per size, facts at k≥2:

| Documents | 100 | 300 | 500 | 750 | 1,100 | 1,500 |
|---|---|---|---|---|---|---|
| Facts at k≥2 | ~1 | 6.5 | 20.6 | 36.3 | 76.9 | 193.5 | 325.0 |

(Two independent implementations agree within Monte Carlo noise.)

The consequence is structural: **there is no cheap pilot of the merge endpoint.** A 300-document pilot has a denominator of ~6 and measures nothing. Piloting is still worthwhile — for cost, latency, and failure-mode discovery — but the pilot must be explicitly labelled as *not* producing a merge estimate, or it will be quoted as one.

### 2.5 The MeSH branch-aware retype proposal is wrong; do not implement it

A proposal in circulation suggested typing MeSH identifiers by leading letter — C-tree → DRUG, D-tree → DISEASE — to work around a taxonomy gap. **The leading letter is the MeSH record type, not the tree branch.** Measured on the corpora: chemicals are D 13,884 / C 1,955; diseases are D 12,937 / C 73. The rule would misroute 12,937 of 13,010 disease mentions. Struck. Use the MeSH tree numbers from the descriptor records, or accept the taxonomy gap and report it.

---

## 3. The entity-linking ceiling: publish it before setting a target

The verified entity dictionary contains 47 verified records (plus 31 review-only). Matching on `entity_label_key` against corpus mentions:

- **BioRED: 94 / 20,419 mentions = 0.46%**
- **BC5CDR: 81 / 28,785 mentions = 0.28%**

Any entity-linking endpoint is evaluated on that coverage or on nothing. Two consequences that must be stated wherever an EL number appears:

**3.1 The stated target is a zero-error gate.** A target of "accuracy ≥ 0.98 with 95% lower bound ≥ 0.95" at n=94 and n=81 admits exactly zero errors:

| Outcome | Wilson 95% lower bound | Passes? |
|---|---|---|
| 94/94 | 0.9607 | yes |
| 93/94 | 0.9422 | **no** |
| 81/81 | 0.9547 | yes |
| 80/81 | 0.9333 | **no** |

A target phrased as a 2% error tolerance is in fact "one mistake fails." Either restate it as a maximum error count at the achievable n, or preregister explicitly that the gate permits zero errors. Do not leave it ambiguous.

**3.2 The abstention loophole must be closed numerically, not typographically.** A linker that refuses to link anything scores perfectly on accuracy-among-linked. Enforcing this by a formatting convention ("accuracy and coverage always appear in the same sentence") is not a gate. **Gate on the joint quantity: linked-and-correct per gold normalizable mention**, or put a numeric floor on coverage. This is the single most likely mechanism by which this program produces a flattering meaningless number, and it needs a number, not a style rule.

---

## 4. Blockers: what stops a run today

Verified open at `86ddb3cb` unless marked otherwise.

### Carried forward (READ lane)

| ID | Defect |
|---|---|
| **H1** | Fixture builder crashes on doubly-modified events (`bionlp_import.py:653`). |
| **H2** | Runner pinned to a superseded fixture (`fixture.py:42`). |
| **H3** | Calibration gate asserts only 4 of 10 metrics, against the superseded fixture. |
| **H4** | One transport error aborts an entire arm and writes nothing (`runner.py:257`, `:290`). |

### CONNECT-lane blockers

| ID | Finding | Status |
|---|---|---|
| **C1** | Agent-authored claims are quarantined before promotion (`proposal_actions.py:843-852`). `_promote_to_open_graph_claim` has exactly one tree-wide reference: its own definition. **This is the wall that makes 3-E unrunnable.** | Verified |
| **C2** | ClaimFrame persistence contract does not exist. Larger than the rest of the readiness estimate combined. | Verified |
| **C3** | `dedupe_identity` includes the source span ⇒ cross-document claim identity is zero by construction. | Verified |
| **C5** | `POST /claims` hardcodes claim-evidence metadata and never propagates `request.metadata`, so `claim_evidence_tier()` returns `COMPUTATIONAL` for every claim-derived relation evidence and promotion short-circuits with `computational_only_not_promotable`. **There is no request shape from the claims API that avoids this.** | Verified — worse than previously stated |
| **C6** | `POST /relations` is **not** a dead path. It returns 403 for non-admins with a message identifying it as a graph-service admin escape hatch, and it is the only writer of `evidence_tier`. It is the route arm 3-K must use — which means **3-K requires a graph-service admin identity in addition to a CURATOR identity**, neither budgeted. | Verified |
| **C7** | `_source_family_key` returns `kind:authoritative_identifier`. On a one-abstract-per-PMID corpus, distinct sources ≡ distinct documents exactly, so this is harmless here. **The real exposure is the mirror image:** if one document is recorded under two identifier forms (`pubmed:123` *and* `doi:10.x/y`), it yields two source families and a single paper can partially satisfy `min_distinct_sources = 3`. This directly threatens the promotion-gate endpoint. | Restated |
| **C8** | Candidate extraction is wrapped in a hard 5.0 s timeout with no env override (`document_extraction.py:501-510`), plus a second, separate 2.0 s AI entity pre-resolution timeout at `:126`/`:1103` sitting directly on the entity-linking arm. Both silently degrade to non-LLM paths. | Verified |
| **C9** | `resolve_entity_label` calls `list_entities(..., limit=5)` with no `entity_type` filter, implemented as `ILIKE '%q%'` over labels and aliases, `ORDER BY created_at DESC`. **Seeding more entities makes this worse:** the correct canonical entity, seeded first and therefore oldest, falls out of the 5-row window. A window miss is a guaranteed non-merge, because endpoint resolution raises unless every participant resolves. | Verified |
| **C10** | Contradiction is order-dependent and permanently invisible if refute arrives first. `relation_projection_materialization_service.py:495` filters to active support claims into `valid_sources`; `link_relation` at `:602-606` is called only over `valid_sources`. A REFUTE claim never acquires a projection-source row — it is not pruned, it never enters the loop — **and there is no re-link path.** | **Confirmed by code trace**, not merely predicted |
| **C11** | `Association` is 3,387 of 6,503 BioRED relations (52%) with no faithful target in the 36-type taxonomy. Could cost that arm half its mass before a model is called. Settleable for $0 with the archived representability tooling. | Verified count; impact open |
| **C12** | `PATCH /claims/{id}` requires `MembershipRole.CURATOR` (`routers/claims.py:869-874`). An N-document merge experiment needs one resolution per claim — thousands of calls at BC5CDR scale. Scriptable, but scripting it is unbudgeted work. | Verified |
| **C13** | `ARTANA_CLAIM_VERIFICATION_EXPERIMENT` (`verification_loop.py:54`, default `False`) switches on a framing → falsification → repair → re-verification loop with `max_verifier_calls = 128`, `max_repairs = 32`, `max_cost_usd = 5.00`. Against a $1.00 per-document budget and a "1 call, maybe 4 more" cost model, that is a 5×–300× swing. **It must be pinned in the preregistration and asserted per document**, not left to the shell. | Verified |

**C8 is the blocker most likely to invalidate the pilot design.** A go/no-go criterion requiring `candidate_discovery.method == "llm"` on ≥95% of pilot documents is unsatisfiable if a full abstract does not round-trip in 5 seconds, and nothing currently makes the timeout configurable. The first thing built should be a 20-document timing probe.

---

## 5. Engineering work required before measurement, with honest estimates

| ID | Work | Days |
|---|---|---|
| Y1 | Per-document checkpointed driver with resumable state; records model id, reasoning effort, and C13 flag value per document | 2.0 |
| Y2 | Extraction-path audit and rejection accounting (see §10.3 — must not *remove* documents) | 1.0 |
| Y3 | Identifier crosswalk (MeSH/NCBI Gene/Taxonomy → internal namespaces) for both corpora | 3.0 |
| Y4 | Relation representability audit (settles C11) — uses archived tooling, **$0, runnable Monday** | 0.5 |
| Y5 | Clustering scorer: B-cubed, asymmetric denominators, fusion counts, error-attribution ledger, degenerate baselines | 4.0 |
| Y9 | Kernel harness for arm 3-K, **including graph-service admin + CURATOR identity provisioning** | 6.0 |
| Y10 | Entity seeding **plus the C9 window/type-filter fix** — this is a code change, not a seeding job | 3.0 |
| **NEW** | Make both C8 timeouts env-configurable | 0.5 |
| **NEW** | 20-document timing probe (informs the above and §11) | 0.5 |
| **NEW** | Curator bulk-resolution tooling (C12) | 1.5 |
| Y11 | Recover archived tooling from tag `archive/alvaro/tg04-source-general-claim-verification-v17` (`db96b23d`) onto a branch. Cheap and sensible; **not urgent** — it is a real tag ref and gc does not prune reachable objects. | 0.5 |
| — | Carried READ-lane readiness (H1–H4 and dependents) | 22.0 |

**Total: ~45 engineer-days, plus the unscoped C2 ClaimFrame-persistence contract.** The previously circulated figure of 40 was arithmetically consistent with its inputs; those inputs omitted the timeout fix, the C9 window fix, the two privileged identities, and bulk curation.

**Unblocking 3-E requires C1 and C5 in addition to all of the above.** That is not scoped here, and any timeline that implies month-one delivery of an end-to-end CONNECT number is not honest.

---

## 6. Metric definitions

### 6.0 Why the metric layer needs this much care

The corpus work below is settled by measurement. The metric layer is where a plan of this kind usually fails, because a badly-chosen denominator can make a do-nothing system look good. Two of the definitions previously in circulation did exactly that. Both are corrected here.

### 6.1 The rule every metric must satisfy, with the numbers written in

**V7:** a metric that does not visibly collapse on both degenerate inputs is not shippable. The values are preregistered here rather than left to be filled in later, because an unspecified threshold is post-hoc freedom:

| System | B3 Precision | B3 Recall (restricted, §6.2) | fusion_mass |
|---|---|---|---|
| ALL-SINGLETON (merges nothing) | 1.000 | **0.323** | 0.000 |
| ALL-ONE-CLUSTER (merges everything) | 0.0007 | 1.000 | 1.000 |

A scorer that does not reproduce these on BC5CDR is broken and must not be used.

**Related standing rule, carried forward and non-negotiable:** the *gold-as-predictions* test. Feed the gold standard in as predictions; the scorer must return 1.0 by construction. This technique previously caught a scorer reporting 0.0000 precision on a perfect input. It gates every new scorer and every crosswalk in this plan.

### 6.2 Fact merge (primary CONNECT endpoint) — asymmetric denominators

The naive definition — B-cubed over all gold claim instances — is disqualified by its own numbers. Computed on real BC5CDR:

| System | B3P | B3R |
|---|---|---|
| **ALL-SINGLETON (merges nothing)** | **1.0000** | **0.7811** |
| ALL-ONE-CLUSTER | 0.000743 | 1.0000 |

The cause is arithmetic: 2,109 of 2,434 gold facts are single-document, and a do-nothing system clusters every one of them *correctly*. The floor is 2,434/3,116 = 0.7811. Because C3 makes the shipped system approximately the do-nothing system, running this metric today would produce the sentence *"placed 78% of gold claim instances on the correct canonical node."* That is a flattering, meaningless number describing a system that connects nothing.

**Definition adopted:**

- **B3 Recall** over gold instances in **k≥2 clusters only** (n = 1,007). All-singleton then scores **0.3227** and the metric discriminates.
- **B3 Precision** over **all projected system instances, unrestricted** — because fusing a singleton into a multi-document cluster is a real error that must stay visible, and a restricted precision denominator would hide it.
- **Both degenerate systems are published as reference rows in the results table**, not merely used as internal scorer checks. Every reported recall is read against 0.3227.

### 6.3 Coreference detection (MC-1) — denominator is parks, not pairs

Defining MC-1 over gold cross-document coreferent *pairs* caps a perfect detector below 1.0, because the system parks *k−1* rows per cluster of size *k*. The ceiling is `(k−1)/C(k,2) = 2/k`:

| k | 2 | 3 | 5 | 25 |
|---|---|---|---|---|
| Max achievable | 1.00 | 0.667 | 0.400 | 0.080 |

Pooled over BC5CDR: 682 parks / 2,049 pairs = **0.3328**. A perfect detector would score 0.33, and that pooled figure moves with the corpus cluster-size distribution rather than with system quality.

**Definition adopted:** denominator is instances that *should have parked*, `Σ(k−1) = 682`. Report per-k regardless of pooling.

### 6.4 Arm 3-K's merge endpoint is a tautology as originally specified

`_compute_canonicalization_fingerprint` (`relation_projection_materialization_service.py:41-56`) derives solely from scoping qualifiers and returns `""` when there are none. BC5CDR CID relations carry no qualifiers. The merge key `(source_id, relation_type, target_id, space, "")` therefore reduces **exactly** to the gold fact key. Feed it crosswalked gold entity IDs and it returns B3P = B3R = 1.0 deterministically — no model involved, no variance, no failure mode short of a database bug.

**Two acceptable resolutions, and the plan takes the first:**

1. **3-K consumes system-produced entity resolutions from real text**, not gold IDs. That is where the only real variance lives, and it makes the arm informative.
2. If gold IDs are retained for a component test, 3-K's claim is restricted to *"the canonicalization fingerprint does not spuriously differentiate equivalent claims"* and **all merge language is dropped from it.**

### 6.5 Error attribution

Because the merge key is a literal 4-tuple with a database uniqueness constraint behind it (`uq_relations_canonical_edge`), every merge failure can be attributed to exactly one differing component at near-zero cost. This ledger is required output, not optional: an aggregate merge number without it cannot be acted on.

### 6.6 What is not used

**F1 is not reported for any CONNECT endpoint.** Precision and recall fail in different places here and have different remedies; a harmonic mean of them hides which one moved.

---

## 7. Uncertainty

### 7.1 The noise floor is observed, not modelled

The reproducibility floor previously quoted as 0.425 was computed as a product of three per-case rates (0.95 × 0.85 × 0.526316). Two problems, both verified in the source replicate data:

1. The third factor is reproduction of a **sealed FAIL** verdict (10/19), not a pass rate (raw PASS was 9/19 = 0.4737). The product mixes two different events.
2. The product of marginal PASS rates is **0.3825**. The **observed joint all-PASS rate is 8/19 = 0.4211**.

The observed joint exceeds the product, which means **errors are positively correlated across cases within a replicate**. 

**Rule adopted:** quote **0.42, observed**. Do not describe it as a product. And note that this is the same mechanism that makes the §0 `p^k` table a lower bound: within-fact error correlation is real and measurable, and the run that produces the assembly number should publish the measured within-cluster correlation beside it — it is free.

### 7.2 Standing rule on single runs

**A single run is a record of what happened, never evidence about a configuration.** Any point estimate from one run is wrong on arrival. This is a program-wide rule, not a per-experiment caveat.

### 7.3 Interval method — one method, preregistered

Three mutually inconsistent intervals for the same endpoint were previously in circulation (±0.044 binomial on clusters; ±0.029–0.037 instance-level with a design effect; neither on the actual denominator). B-cubed recall is a **ratio of means**, not a proportion of clusters, so the binomial variance is simply the wrong formula — here it overstates the interval by roughly 50%.

**Adopted:** the **cluster bootstrap** is the single interval method for all B-cubed endpoints. Measured on BC5CDR with 4,000 draws: SE 0.0144, half-width **±0.028**. Binomial intervals are retained only for genuinely per-cluster binary endpoints (e.g. exact cluster assembly rate), where they are correct.

### 7.4 The bootstrap's validity has a precondition, and it is a real decision

Resampling clusters assumes clusters are exchangeable. They are not. Entity resolution is **stateful across documents** (`ORDER BY created_at DESC`, 5-row window, C9): document 900's outcome depends on which of documents 1–899 were ingested first, and lost-race flips are documented. So the merge stage does *not* contribute zero variance of its own, and a resample of clusters corresponds to no repetition of the actual experiment.

**Two options; this must be decided before the run, not after:**

- **(a)** Declare the estimand explicitly **conditional on one fixed ingestion order**, report no generalization claim, and drop any generalization standard error. Cheap, honest, narrower.
- **(b)** Replicate at the **whole-corpus level with shuffled ingestion order**. This is the only design under which a generalization interval means anything. It costs R× the corpus and must be priced before it is chosen.

### 7.5 Stability arm sizing

Estimating between-run variance per stratum at n=5 gives df=4 and a variance confidence multiplier of roughly [0.36×, 8.3×] — order-of-magnitude uncertainty. (This is the same objection that correctly disqualifies an existing n=3 estimate, whose multiplier is [0.27×, 39×].) Either accept that per-stratum variance stays order-of-magnitude uncertain and say so wherever it is used, or raise to ~15 clusters per stratum. The stratified allocation should be stated explicitly in the run design; do not quote a round document-run total that does not follow from it.

---

## 8. Lane gating — measure the gate on the corpus it gates

A rule of the form "if per-document read recall on BioNLP-GE events is below 0.60, then merge numbers on BC5CDR CID relations become diagnostics only" imports a number across corpora, tasks, annotation guidelines, and entity types. The *p* governing BC5CDR assembly is not the *p* measured on GENIA. A preregistered rule that licenses or denies a claim using a number from a different distribution is a category error with a commitment date attached.

**Adopted:** measure per-document read recall **on BC5CDR itself** — the CID gold is already present and it costs nothing extra — and gate the merge lane on that. GENIA is retained for the trigger-span estimand it is uniquely suited to, and for nothing else.

Similarly, a validation rule requiring the crosswalked k-distribution to reproduce §2.1's counts **exactly** is unpassable on BioRED, because three of its six entity types are unmappable and dropping them necessarily changes the distribution. **Restated:** recompute the k-distribution on the crosswalked slice, publish the delta against §2.1, and preregister a maximum tolerable recurrence loss. (The exact-reproduction form is fine on BC5CDR, which is single-namespace.)

---

## 9. Threats that specifically produce flattering numbers

1. **Do-nothing scores 0.78.** Neutralised by §6.2 and by publishing degenerate baselines as result rows.
2. **3-K returns a guaranteed 1.0.** Neutralised by §6.4.
3. **Abstention gaming of entity linking.** Neutralised only by a numeric joint gate (§3.2) — a formatting rule does not neutralise it.
4. **Outcome-conditioned analysis set.** See §10.3.
5. **`p^k` published as a prediction.** Neutralised by §0's labelling and §14's prohibition.
6. **A single-run point estimate quoted as a property of the system.** Neutralised by §7.2.
7. **Filtered denominators escaping into headlines** — including the plan's own showcase sentence; see §14.
8. **C7's mirror image** — one document yielding two source families and partially satisfying a 3-source promotion gate. Preregister the assertion "each ingested document yields exactly one source family" and verify it with a `GROUP BY` in the pilot before any promotion-gate number is quoted.

---

## 10. Preregistration discipline

### 10.1 Every threshold carries a number

An unspecified threshold is post-hoc freedom. The following were previously unspecified and are now fixed, or are explicitly flagged as owing a number before Phase 0 ends:

- Degenerate-input values: **fixed in §6.1.**
- Relation-representability floor (C11): **owes a number before Phase 0 ends.**
- Crosswalk recurrence-loss tolerance (§8): **owes a number before Phase 0 ends.**
- Go/no-go conditions: enumerated individually, never as "all validation rules pass."

### 10.2 Configuration pinned per document

Model id, reasoning effort, `ARTANA_CLAIM_VERIFICATION_EXPERIMENT` (C13), and both timeout values are recorded in each document's checkpoint record and asserted against the preregistration. A configuration that is not asserted per document is not pinned.

### 10.3 Rejected documents stay in the denominator

Rejecting documents whose extraction path fell back off the LLM (C8) conditions the analysis set on a **system outcome** — plausibly correlated with document length and extraction difficulty. Every downstream rate then silently becomes "conditional on documents the extractor found easy."

**Adopted:** retry rejects with an extended timeout. Documents that still fail are **counted as extraction failures in the denominator**, never removed from it. Publish the length distribution of rejected versus retained documents.

---

## 11. Cost and time

**Provider cost.** The anchor is $0.016861/call, from 59 costed observations totalling $0.99479, with a per-call spread of $0.0070–$0.0387 (5.5×). **That anchor was measured on a different model at a different reasoning effort** (a frontier reasoning model at high effort) than the configured extraction model (a mini model). It therefore almost certainly *overstates* cost. This changes no decision, but the model and effort must be stated alongside the figure, and the band widened downward.

Order of magnitude: pilot ~$2, full run ~$40. **Money is not the constraint.**

**Wall clock is not yet established.** A 30–120 s/document estimate implies 20–80 hours for a full corpus, but the model-call budget per document is bounded by the code's own timeouts at roughly 5 s + 4 × 2 s ≈ 13 s. Either the estimate is 3–10× high or time is going somewhere unidentified. A 20-document timing probe resolves this for essentially nothing, and it must run before anyone commits to a schedule — a 20–80 hour unresumable process is not a runnable experiment, and Y1's checkpointing exists precisely because of that.

---

## 12. Phase 0 — what can start Monday, at zero provider cost

Everything here is real work with real decision value, costs no provider money, and can invalidate the design before money is spent.

| Item | Why it matters |
|---|---|
| **20-document timing probe** | Highest-value single item. Could invalidate the entire pilot design (C8) and settles §11's wall-clock question. |
| **Relation representability audit (Y4)** | Settles C11's 52% for $0. Could halve the BioRED relation arm before a model is called. |
| **C10 confirmation run** | Free. The code trace already says refute-before-support is permanently invisible; confirm and file. |
| **Crosswalk build (Y3) + gold-as-predictions validation** | The load-bearing infrastructure for both corpora. |
| **Scorer build (Y5) with degenerate baselines from §6.1** | Cannot be validated after the fact. |
| **C7 source-family `GROUP BY` check** | One query. Gates the promotion-gate endpoint. |
| **GENIA fixture licence resolution (§2.3)** | Live public-repo exposure. Not decoupled. |
| **The open decisions in §13** | Free, and several of them change what gets built. |
| **Archive recovery (Y11)** | Cheap and sensible. Not urgent. |

---

## 13. Open decisions requiring a human

1. **Is `dedupe_identity`'s span inclusion (C3) deliberate isolation of document-scoped drafts, or an oversight?** This determines whether arm 3-P measures a design choice or a bug — and therefore how its result should be written up. I could not settle it from the code and will not guess.
2. **Is the merge estimand conditional on a fixed ingestion order (§7.4a), or does it need shuffled-order replication (§7.4b)?** This changes the cost model materially and is not a reporting detail.
3. **Is unblocking C1/C5 in scope?** Without it there is no end-to-end CONNECT number, this quarter or any quarter.
4. **The GENIA fixture licence exposure (§2.3)** — remove, or obtain written permission?
5. **Numbers owed before Phase 0 closes:** C11's representability floor; §8's crosswalk recurrence-loss tolerance.

---

## 14. Publication rules

Any external statement of results must obey these, without exception.

1. **State the arm.** "The graph kernel merged X% under component test with system-produced entity resolutions" is a different sentence from "the platform assembled X%." Never let the second stand for the first.
2. **State the predicate coverage.** BC5CDR contains exactly one relation type. The showcase sentence must read *"placed X% of gold **chemical-induced-disease** claim instances on the correct canonical node"* — not the unqualified form. This plan spends considerable effort preventing filtered denominators from escaping into headlines; its own headline must not commit that error.
3. **Publish the degenerate baselines beside the result.** Every recall figure is read against 0.323.
4. **Publish the entity-linking coverage beside every entity-linking accuracy** — and gate on the joint quantity.
5. **Label the `p^k` table a lower bound under an independence assumption known to be violated**, and publish the measured within-cluster error correlation beside it.
6. **Never quote a single run as evidence about a configuration.**
7. **State the model and reasoning effort alongside any cost figure.**

---

## 15. Bottom line

The corpus question is settled by measurement: **BC5CDR for fact merge, BioRED for entity identity and grounding, GENIA for trigger spans and nothing else.** That work is solid and reproducible, and it removes the largest source of wasted effort in the previous plan.

The metric layer is now specified so that a system which connects nothing scores 0.32, not 0.78.

**But the honest conclusion stands, and it is the conclusion, not a caveat:** the capability the product owner cares about — reading many papers and *connecting* them — cannot be measured end-to-end today. C1 quarantines the agent path; C3 makes cross-document claim identity zero by construction; C5 makes the evidence tier unsettable from the claims API. Those are engineering facts, verified in the tree, not measurement choices.

So the first month should not promise a CONNECT accuracy number. It should deliver: **the connecting capability is not wired end-to-end, here is precisely where it stops, here is what it costs to close, and here — with published baselines and a scorer that provably collapses on degenerate inputs — is the measurement apparatus that will produce a real number the day it is unblocked.**

That is a smaller promise than "we validated the backend." It is the one the code supports.

---

## 16. Decisions taken

Recorded 2026-07-26 by the product owner, after review of §13.

### 16.1 Fund the CONNECT work in full — now

Committed, rather than gating on Phase 0's result. **Phase 0 still runs first**; what changed is the commitment, not the order. Its purpose is unchanged and remains load-bearing for two reasons:

1. It sizes the ClaimFrame-persistence contract, which is the one component in the estimate that is genuinely unscoped. The ~45 engineer-day figure excludes it.
2. It can still show the design is wrong, at zero provider cost. Committing the budget does not make an invalid design valid, and §12 should still be run as an early warning rather than as a gate.

**Reporting obligation this creates:** because the go/no-go checkpoint has been removed, Phase 0's output must be escalated explicitly when it lands, not folded into a status update. If it returns a ClaimFrame estimate materially above the placeholder, that is a re-decision point even though the funding decision is already made.

### 16.2 Drop BioNLP-ST GENIA — use freely-licensed corpora only

BC5CDR (verified public domain) and BioRED (provenance verified) only.

**This is remediation, not a forward-looking choice.** §2.3 records a live exposure: `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json` and `_v2.json` each embed 54,834 characters of GE `source_text` across 40 documents, git-tracked in a public repository. Verified independently: 40 `source_text` fields per file.

Consequences to work through, none of them free:

- **Lane 1 (READ) loses the corpus it was designed around.** GENIA was selected for READ precisely because its event annotation suits that estimand. BC5CDR and BioRED carry relations rather than the multi-argument event structure Lane 1 scores, so Lane 1's estimand must be redefined against what the remaining corpora actually annotate. This is a design change to §1.1 and §6, not a substitution.
- **The existing scorer and gold panel were built against GENIA.** The two-sided calibration (`2026-07-24-tg04-two-sided-scorer-calibration.md`), the 7 polarity adjudications, and the preregistered protocol all target the GE fixture. What survives re-targeting must be re-established, and the gold-as-predictions gate must be re-run on whatever replaces it.
- **Blockers H1–H3 concerned the GE fixture** and may be moot rather than fixed. Re-check before counting them as closed.
- **Removing the files does not remove them from git history.** The repository is public, so the content stays retrievable from prior commits. Full remediation requires rewriting published history — force-pushing a shared repository — which is a separate decision with its own cost, and is not taken here.

### 16.3 Production environment — deferred

Prove the system's value first. Recorded on issue #215. Staging is the environment; it runs current `main` via CI and is traceable to a commit.

### 16.4 Partner communication

Lead with what is demonstrable: source-linked claims, and every decision carrying its reviewer and their written reason. State plainly that extraction accuracy is not yet measured and is being measured. Do not quote an accuracy figure — §14's publication rules apply to partner-facing material exactly as they apply to reports.
