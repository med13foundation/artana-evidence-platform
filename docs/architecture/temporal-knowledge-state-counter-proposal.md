# Temporal Knowledge State: a counter-proposal

**Response to requirement ARTANA-KNOWLEDGE-TIME-001 — "Temporal Knowledge State and Scientific Belief Evolution."**

Status: PROPOSED. Nothing here is implemented.
Written against tree SHA `1f97b307`. Every code citation below was checked at that SHA.
Date: 2026-07-30.

---

## 0. The one-page version

**The requirement's intent is right and Artana should adopt it.** A system that governs
knowledge must be able to say what it believed before, why that changed, which evidence
caused it, under which policy, and who approved it. Artana cannot answer any of those
today.

**The requirement's proposed mechanism is wrong for Artana, on one specific point.** §3
promotes canonical propositions, proposition state versions, and knowledge-state
transitions to *authoritative objects*. Artana's own architecture says the opposite:

> CanonicalProposition — *the surface you reason over, **derived and never authoritative**…
> it is a projection.*
> — [artana-vision-and-direction.md:70](../artana-vision-and-direction.md)

Adopting §3 as written creates two sources of truth — the claim ledger and the state
table — which can drift, and it turns every policy change into a migration of state rows
rather than a re-derivation. That is the "database that ages badly" failure the vision
names one line later.

**The counter-principle:**

> **Version the inputs. Derive the state. Store only what cannot be derived.**

**The finding that makes this cheap.** The accepted state is *already* computed as a pure
fold over the complete eligible evidence set, recomputed from scratch rather than
incrementally — `recompute_relation_aggregate`
([_relation_repository_shared.py:146](../../services/artana_evidence_db/_relation_repository_shared.py)).
`rebuild_relation_projection` and `repair_global` already exist. The derivation Artana
would need is not a rewrite; it is the function that already runs, given two more
parameters.

**What survives from the requirement, essentially unchanged:** §5's separation of
acceptance from support from applicability (its best insight), §9's retraction as a
first-class fact, §11's machine/human authority split, §13's explanation packet, §17's
non-goals.

**What is dropped:** `proposition_state_versions` as an authoritative table with
`previous_state_id` chains, `knowledge_state_transitions` as a curated table with its own
review workflow, most of §4.3's seventeen fields, and Phase 4 in its entirety.

**Conformance today:** roughly 15–20%. §7 (claim-to-claim positions), §10 (space scoping),
and §4.1 (immutable source custody) are partly real. §4.2–§4.4, §6, §8, §12, §14 are
absent. `rg -i proposition services/` returns zero hits.

**Ordering.** This capability is downstream of CONNECT, and CONNECT is blocked
([proposal_actions.py:846](../../services/artana_evidence_api/proposal_actions.py)).
A belief timeline over propositions that each have exactly one source is a lot of
machinery for a graph that never has a second point on it. §10 below proposes the
sequencing.

---

## 1. The disagreement, precisely

The requirement and Artana agree that history must survive. They disagree about *where
truth lives*.

| | Requirement §3 | Artana v2.0 |
|---|---|---|
| Canonical proposition | New **authoritative** object | Derived **projection**, never authoritative |
| Proposition state | Stored, versioned, transitioned | Computed from claims + policy |
| Changing your mind | Write a new state version, chain `previous_state_id` | Write a new policy version, re-derive |
| Policy change | Migration + reviewable transition per proposition | Re-run |

This is not a stylistic preference. Three consequences follow directly:

**It creates a second source of truth.** Once acceptance state is stored independently of
the evidence it came from, the two can disagree. Nothing in the requirement prevents a
state version that no longer follows from its own evidence set — and after enough policy
churn, some will not. The system then needs a reconciliation process it did not previously
need.

**It makes policy change O(propositions) instead of O(1).** §8's worked example — policy
v1 accepts animal-model evidence, v2 requires human evidence — requires, under the
proposal, discovering every affected proposition, generating a reviewable transition for
each, and applying them under governance (Phase 4, "policy-driven re-evaluation"). Under
re-derivation, it is one new policy record.

**The duplication is already visible in the spec's own field list.** §4.3's state version
carries `decision_actor`, `decision_actor_type`, `decision_reason`, and `review_id` —
review-decision fields copied onto the state. When the same fact is stored in two places,
one of them eventually is wrong. That is the two-sources-of-truth problem showing up at
field granularity.

**What is *not* in dispute:** that transitions must be explainable, that policy must be
versioned and attributable, that history must survive, that machines must not impersonate
reviewers, and that acceptance must not collapse into a score. The counter-proposal keeps
all of it.

---

## 2. The counter-principle

> **Version the inputs. Derive the state. Store only what cannot be derived.**

Concretely, the accepted state of a proposition in a research space becomes a pure
function:

```
state(proposition, space, as_of, policy_version)
    = f( claims known to Artana at `as_of`,
         evidence eligible under `policy_version`,
         human decisions recorded at or before `as_of`,
         external facts (retraction, supersession) known at `as_of` )
```

Three properties fall out that the stored-state design has to build separately:

- **State cannot drift from evidence**, because it is not independently stored.
- **§12's policy-impact query is free.** "Which propositions would change under policy v3?"
  is `diff(f(…, v2), f(…, v3))`. No replay subsystem.
- **Counterfactuals the requirement does not ask for become available.** "What would we have
  believed in 2018 under *today's* policy?" is `f(as_of=2018, policy=current)`. This
  separates *scientific* change from *policy* change — which §8 currently conflates, and
  which reviewers will need separated the first time both move at once.

The current relation columns (`curation_status`, `aggregate_confidence`,
`support_confidence`, `refute_confidence`, `source_count`) become a **cache** of
`f(now, current_policy)` — invalidatable and rebuildable, never authoritative. Artana
already treats them roughly this way: see the projection-readiness and repair machinery
(`/v1/admin/projections/readiness`, `/v1/admin/projections/repair`).

---

## 3. The finding that changes the cost estimate

The requirement reads as a large new subsystem. Most of it already exists, in the wrong
shape by two parameters.

`recompute_relation_aggregate`
([_relation_repository_shared.py:146](../../services/artana_evidence_db/_relation_repository_shared.py))
does this today:

```python
evidences = <all evidence rows for relation>
evidences = [e for e in evidences if e.source_snapshot_id in eligible_snapshot_ids]
...
relation_model.aggregate_confidence  = 1 - Π(1 - cᵢ)
relation_model.support_confidence    = diminishing(per-source-family maxima)
relation_model.refute_confidence     = diminishing(linked refute claim units)
relation_model.source_count          = distinct_document_count(evidences)
```

Three things matter about this:

1. **It is a fold over the complete set, not an incremental update.** It reads everything
   and recomputes from zero. Determinism is not something that must be introduced.
2. **It already takes an eligibility policy as input** — `ClaimEvidenceEligibilityService`
   filters the evidence set before the fold. The seam for policy versioning exists.
3. **It already writes into a cache that has a rebuild path.**

What is missing is that the input set cannot be restricted by time, the policy is not
identified, and the output is written to a mutable column rather than being addressable
by `(as_of, policy_version)`.

**So the delta is three changes, not five phases:**

| # | Change | Why it is non-negotiable in *either* design |
|---|---|---|
| 1 | **Knowledge-time on every claim and evidence row** — when Artana *learned* it, distinct from when it was published | Without it there is no as-of anything, under any architecture |
| 2 | **Policies as persisted versioned objects**, replacing env-var reads | Today you cannot determine what policy approved a live relation. Not missing history — a missing *input* to history |
| 3 | **Parameterize the fold** with `as_of` and `policy_version`; treat relation columns as cache | Turns §12 and §14 from "unimplementable" into "already written" |

Items 1 and 2 are additive, require no new authoritative objects, and are **losing
information every day they are deferred**. They should not wait on the rest of this
document.

---

## 4. Section-by-section response

Verdicts: **ACCEPT** — adopt as written. **AMEND** — intent accepted, mechanism changed.
**REJECT** — do not build. **DEFER** — right, but gated on CONNECT.

| § | Topic | Verdict | Note |
|---|---|---|---|
| 1 | Summary / four distinctions | **ACCEPT** | The four distinctions are exactly right and Artana already has objects for three |
| 2 | Design principle | **ACCEPT** | Already Artana's position; currently violated in code (§4.2 below) |
| 3 | New authoritative objects | **REJECT** | The one structural disagreement. See §1 |
| 4.1 | Source assertion | **ACCEPT** | Largely built: immutable snapshots |
| 4.2 | Canonical proposition | **AMEND** | Build the **identity**, as a derived versioned key. Not an authoritative row with a lifecycle |
| 4.3 | Proposition state version | **REJECT** as a table; **AMEND** as a projection | Keep ~6 of 17 fields as the derivation's *output shape* |
| 4.4 | Knowledge-state transition | **AMEND** | A transition is a **diff of two derivations**, computed. Trigger taxonomy is kept as diff-explanation vocabulary |
| 5.1 | Acceptance status | **AMEND** | 4 of 6 statuses derive. `SUPERSEDED` and `RETRACTED` need input records |
| 5.2 | Support level | **ACCEPT** | Decollapsing support from acceptance is the requirement's best insight |
| 5.3 | Applicability context | **ACCEPT** | Needs a controlled vocabulary; currently free-form JSONB |
| 6 | Bitemporality | **AMEND** | Adopt fully, but as columns on claims/evidence — not on a state table. 2 of 10 fields exist today, on the wrong objects |
| 7 | Evidence positions | **ACCEPT, extend** | `ClaimRelationType` exists with 9 types; add the 5 missing |
| 8 | Recalculation | **AMEND** | Steps 1–4 and 8–9 accepted. Steps 6–7 (close `valid_to`, mint `state_id`) rejected — that is stored state |
| 9 | Retractions and corrections | **ACCEPT** | Detector already exists and has nowhere to write |
| 10 | Research-space scope | **ACCEPT** | Strongest area today; one real gap (no shared cross-space identity) |
| 11 | Human and machine authority | **ACCEPT** | Half-built; fail-closed already in force |
| 12 | Query requirements | **ACCEPT** | All eight classes; two become free under derivation |
| 13 | Explanation requirements | **ACCEPT, amend fields** | Drop `state_id`/`previous_state_id`; add `policy_version` and `as_of` |
| 14 | Graph projection | **ACCEPT** | Lineage partly exists; add policy version to it |
| 15 | API capabilities | **AMEND** | Same capabilities, different parameterization. See §7 below |
| 16 | Acceptance criteria | **ACCEPT, rewrite** | All five scenarios kept; restated against the derived model in §8 |
| 17 | Non-goals | **ACCEPT** | Adopt verbatim. Add one (§9 below) |
| 18 | Phases | **AMEND** | Phase 4 disappears. Phase 0 changes scope. See §9 |
| 19 | Documentation | **ACCEPT, amend wording** | See §11 |
| 20 | Outcome | **ACCEPT** | Every question stays answerable under the counter-proposal |

### 4.2 — Canonical proposition identity: build it, but derived

The requirement wants a stable identifier "independent of its current acceptance status."
Agreed, and needed. The disagreement is only about authority.

Today the de facto proposition is the `relations` row, keyed by
`(source_id, relation_type, target_id, research_space_id, canonicalization_fingerprint)`
under `uq_relations_canonical_edge`
([kernel_relation_models.py](../../services/artana_evidence_db/kernel_relation_models.py)).
That is a graph edge, not a proposition, and it is one mutable row.

**Counter:** a proposition key is a *versioned derivation* over normalized participants,
relation type, and the qualifiers that scope it — carrying the version of the key function
that produced it. This is what the vision means by "versioned keys." A key-function change
mints new keys and re-derives; it does not migrate. Prior keys stay resolvable, so history
written under them stays addressable.

**The specific defect this must fix:** cross-document identity is currently zero by
construction, because the claim de-duplication key includes the source span. A span from
paper A can never equal a span from paper B. A proposition key that excludes the span is
the mechanism by which one node ends up supported by five papers.

### 4.3 — Proposition state: a response shape, not a table

Of §4.3's seventeen fields, six survive as the derivation's output:

| Kept (as computed output) | Dropped |
|---|---|
| `proposition_id`, `research_space_id` | `state_id`, `previous_state_id` |
| `acceptance_status`, `support_level`, `applicability_context` | `valid_from`, `valid_to`, `recorded_at` |
| `evidence_set_version` → replaced by the `as_of` that produced it | `decision_actor`, `decision_actor_type`, `decision_reason`, `review_id` (live on the decision record) |
| `aggregation_policy_version`, `identity_policy_version` | `superseded_by_proposition_ids` → derived from supersession assertions |

The dropped temporal fields are not lost — they move to the *claims and evidence*, where
they belong, and the state inherits its interval from them.

### 4.4 — Transitions: computed, not curated

A transition under this model is:

```
transition(P, space, t₁ → t₂) = diff( f(P, space, t₁, policy@t₁),
                                       f(P, space, t₂, policy@t₂) )
```

The diff carries, without being separately authored: which evidence entered or left the
set, which policy changed, which human decisions intervened, and which external facts
(retraction, supersession) landed between `t₁` and `t₂`.

The requirement's **trigger taxonomy is kept in full** — new supporting evidence, new
contradicting evidence, independent replication, failed replication, source correction,
source retraction, revised ontology identity, revised aggregation policy, revised evidence
policy, revised scope, human adjudication. It becomes the classification vocabulary the
diff explainer emits, rather than a field an author fills in. That is strictly better: an
author can mislabel a trigger, a diff cannot.

**One case genuinely needs a stored record:** a human overriding the derivation
("the policy says ACCEPTED, I say CONTESTED"). That is a *review decision*, it is an input
to `f`, and Artana already has a home for it. It is not a state-version table.

### 5.1 — Which statuses derive, and which do not

| Status | Derivable? | From what |
|---|---|---|
| `PROPOSED` | Yes | Evidence exists, policy thresholds not met |
| `ACCEPTED` | Yes | Policy thresholds met, no blocking conflict |
| `CONTESTED` | Yes | Meaningful support **and** refute mass. **Already computable today** — `KernelRelationConflictSummary` and `/v1/spaces/{id}/relations/conflicts` |
| `REFUTED` | Yes | Refute mass dominates under policy |
| `SUPERSEDED` | **No** | Requires an explicit supersession assertion — a judgement, not an aggregate |
| `RETRACTED` | **No** | Requires an external fact about the source or the decision |

So four of six are already latent in data Artana holds; two require input records. Note
`CONTESTED` in particular: Artana can compute disagreement today and simply has nowhere to
put it, because `curation_status` has no such value
([kernel_relation_models.py:144](../../services/artana_evidence_db/kernel_relation_models.py)).

**Also worth separating:** `curation_status` currently answers *"is this edge admissible
to the graph?"* The requirement's `acceptance_status` answers *"is this scientifically
true?"* Those are different decisions with different authorities. Overloading one column
with both is how a system ends up needing a transition table to explain what happened.
The counter-proposal keeps them distinct.

### 7 — Evidence positions: extend what exists

`ClaimRelationType`
([claim_relation_models.py:12](../../services/artana_evidence_db/claim_relation_models.py))
already ships SUPPORTS, CONTRADICTS, REFINES, CAUSES, UPSTREAM_OF, DOWNSTREAM_OF, SAME_AS,
GENERALIZES, INSTANCE_OF — with `review_status` (PROPOSED/ACCEPTED/REJECTED), `confidence`,
`agent_run_id`, and a self-loop guard. The requirement's §7 list needs five additions:
`QUALIFIES`, `REPLICATES`, `FAILS_TO_REPLICATE`, `IS_INDIRECT_EVIDENCE_FOR`,
`IS_CONSISTENT_WITH` — plus `SUPERSEDES`, which §5.1 shows is load-bearing and which the
requirement itself only names in prose.

This is the cheapest high-value item in the whole document: an enum extension over a table
that already has review semantics and lineage.

### 9 — Retraction: the detector exists and has nowhere to write

`SourceIntegrityStatus.RETRACTED` is already parsed from PubMed relation types and
publication types
([pubmed.py:257](../../services/artana_evidence_api/evidence_selection/source_integrity/pubmed.py)),
with a typed, strict contract (`AuthoritativeSourceValidation`). But it runs at
*candidate-screening time*, in the Evidence API, and graph-side `source_documents` has
`enrichment_status` and `extraction_status` and **no retraction column**.

The lineage to answer §9's headline question already exists:
`relation_projection_sources → relation_claims → source_document_ref`. Once a graph-side
retraction fact exists, *"which accepted propositions depend on this retracted source?"*
is one join, and under derivation the re-evaluation is automatic — a retracted source drops
out of the eligible evidence set and the fold produces a different answer on its own.

**Sequencing note:** every day this is deferred, retractions that land are not recorded,
so the historical record will have a hole no later fix can fill.

---

## 5. The revised object model

What is actually added. Compare against §3's four new authoritative objects.

**New columns (additive, no new authority):**

| Object | Column | Purpose |
|---|---|---|
| `relation_claims`, `claim_evidence` | `known_from` (knowledge time) | §6 system time. The as-of filter |
| `relation_claims` | `source_published_at`, `observed_at` | §6 scientific time. Currently only inside a PubMed `metadata_payload` blob |
| `relations` (cache) | `derived_under_policy_version`, `derived_at` | Says what the cache is a cache *of* |
| `relation_projection_sources` | `policy_version` | Completes §14's lineage requirement |
| graph `source_documents` | `integrity_status`, `integrity_recorded_at`, `integrity_source` | §9. Written by the existing detector |

**New tables (three, all append-only ledgers of things that cannot be derived):**

1. **`aggregation_policies`** — versioned, persisted, immutable-once-published. Replaces
   the env-var reads in
   [relation_autopromotion_policy.py](../../services/artana_evidence_db/relation_autopromotion_policy.py).
   Carries thresholds, evidence-tier floors, conflict rules.
2. **`proposition_keys`** — derived identity with `key_function_version`, so re-keying is
   additive and prior keys stay resolvable.
3. **`knowledge_assertions`** — external and human facts that cannot be derived:
   supersession assertions, retraction facts, and human overrides of a derivation. Carries
   `asserted_by`, `asserted_by_type`, `asserted_at`, `known_from`, rationale, review status.

**Not built:** `proposition_state_versions`, `knowledge_state_transitions`,
`evidence_set_versions`.

**The pattern to copy.** Artana already has exactly the versioning shape the requirement
wants — on the concept/dictionary tier: `valid_from`, `valid_to`, `superseded_by`,
`review_status`, `revocation_reason`
([concept_models.py:50](../../services/artana_evidence_db/concept_models.py)), plus an
append-only `dictionary_changelog` with before/after snapshots. That is a working,
tested template for `knowledge_assertions` and `aggregation_policies`. It should be reused
rather than reinvented — and it is worth being explicit that it is the right pattern for
*identity and policy*, which are authored, and the wrong pattern for *belief*, which is
derived.

---

## 6. What cannot be derived — the honest boundary

The derived model is not free, and its boundary should be stated rather than discovered.

**Three classes of input must be stored, permanently, as append-only records:**

1. **Human decisions.** A reviewer's judgment is not recomputable from evidence. Partly
   built: `reviewed_by`, `reviewed_at`, and `auto_promoted` — which deliberately separates
   machine promotion from human decision
   ([kernel_relation_models.py:164](../../services/artana_evidence_db/kernel_relation_models.py))
   — plus `ReviewActor` on the API side.
2. **External facts.** Retraction, correction, expression of concern. These come from the
   world.
3. **Supersession assertions.** "Proposition Y replaces X as the preferred interpretation"
   is a scientific judgement, not an aggregate over evidence.

**Four costs of the derived model, stated plainly:**

- **The fold must stay pure.** Any hidden state or ordering dependence silently breaks
  as-of. This needs a test that asserts `f` over the same inputs is byte-identical across
  runs — a real, ongoing constraint on future changes to the aggregation path.
- **Recomputation cost is real.** As-of queries over a large graph are expensive. Mitigation
  is caching and snapshotting derivations, which is a performance problem with known
  answers — not an architectural one.
- **Policy objects must be immutable once published.** If a policy row is edited in place,
  every derivation that cites it becomes unreproducible. This is the same discipline the
  source snapshots already enforce
  ([snapshot_model.py:120](../../services/artana_evidence_db/source_provenance/snapshot_model.py):
  *"source evidence snapshots are immutable"*).
- **Deletion breaks it.** `document_deletion/runtime.py` hard-deletes documents, proposals,
  review items, and study outcomes by scope. Under derivation, deleting an input silently
  rewrites history — a derivation run today over `as_of=2024` would produce a different
  answer than the same query last month, with no record of why. This needs an explicit
  stance before as-of is exposed to users. §9 of the requirement forbids deletion on
  retraction; this is the broader version of that concern.

---

## 7. API shape (response to §15)

Same capabilities. Different parameterization: an `as_of` and a `policy_version` on
existing reads, rather than a parallel family of state endpoints.

| Requirement §15 capability | Counter-proposal |
|---|---|
| GET proposition current state | `GET …/propositions/{key}` (defaults `as_of=now`, current policy) |
| GET proposition state history | `GET …/propositions/{key}/timeline` — derived at each change point |
| GET proposition state as of timestamp | Same endpoint, `?as_of=` |
| GET knowledge-state difference | `GET …/propositions/{key}/diff?from=&to=` — and, additionally, `?policy_from=&policy_to=`, which the original design cannot express |
| GET transition explanation | Falls out of the diff |
| POST proposed state transition | **Replaced** by `POST …/knowledge-assertions` (supersession / override / retraction) |
| POST transition review decision | Existing review-decision surface |
| POST policy-based re-evaluation | **Deleted.** Publish a policy version; re-derivation follows |
| GET source-retraction impact | `GET …/sources/{id}/impact` — join over existing lineage |
| GET research-space graph as of timestamp | Existing graph reads, `?as_of=` |

The requirement's §15 rule that responses must distinguish current / historical / proposed
/ unreviewed-machine / externally-curated / locally-reviewed state is **accepted in full**
and is, if anything, easier here: the response says which `as_of` and which
`policy_version` produced it, so "unreviewed machine assessment" is a derivation with no
human decision in its input set, stated as such.

---

## 8. Acceptance criteria, restated (response to §16)

All five scenarios are kept. Each is restated so it tests the derived model, and each
remains a genuine test of the original intent.

**Scenario A — scientific reversal.** Given X accepted in 2015, contradicting evidence
captured in 2025, Y accepted in 2026: the original sources and claims are unchanged;
`state(X, as_of=2018)` returns ACCEPTED with its 2015 evidence set and the policy then in
force; `state(X, as_of=now)` returns CONTESTED or REFUTED; `diff(X, 2018→now)` names the
specific evidence that entered; the as-of-2018 graph shows X and the current graph shows Y.
*Adds:* `state(X, as_of=2018, policy=current)` must also be answerable, distinguishing
"the science changed" from "our standards changed."

**Scenario B — context refinement.** The general proposition is not deleted; a supersession
assertion links it to the specific one; the biomarker qualifier is preserved on the
specific proposition's participants; `as_of` before the assertion returns the general
interpretation and after returns the context-limited one. *Adds:* the general proposition's
`applicability_context` must narrow rather than its `acceptance_status` collapsing to
REFUTED — the requirement is right that this distinction is the whole point.

**Scenario C — policy change.** Publishing policy v2 changes no stored state and destroys
nothing. `state(P, policy=v1)` and `state(P, policy=v2)` both remain answerable *forever*,
for any proposition, including ones that did not change. *This is strictly stronger than
the original scenario*, which only preserves v1 state for propositions that happened to
transition.

**Scenario D — retraction.** The source and its retraction remain visible; the retraction
is recorded graph-side with the time it became known; `sources/{id}/impact` lists dependent
propositions; those propositions' current derivations exclude the ineligible evidence
automatically; derivations `as_of` before the retraction became known still include it —
which is the correct answer to *"what did we believe then,"* and something the stored-state
design gets wrong unless the transition is authored with care.

**Scenario E — space disagreement.** Two spaces share a proposition key, hold different
policies, and derive different states; neither overwrites the other. *This requires new
work the current system does not have:* proposition keys must be resolvable **across**
spaces. Entities, relations, and concepts are all space-scoped today, so there is currently
nothing shared to disagree about. §10 of the requirement contemplates shared identity with
scoped acceptance; that is the right design and it is not built.

---

## 9. Revised phases (response to §18)

**Phase A — Stop the bleeding (no new objects, start now).**
Knowledge-time columns on claims and evidence; persisted versioned `aggregation_policies`
replacing env-var reads; graph-side source integrity status written by the existing
detector. All additive. All independent of everything below. Every day these are deferred,
information is permanently lost.

**Phase B — Semantic contract.** Proposition key function and its versioning; the
derivation contract for `f`; controlled applicability vocabulary; the `SUPERSEDES` and
remaining §7 position types; separation of curation admissibility from scientific
acceptance. Zero-cost to invalidate; should be reviewed before Phase C.

**Phase C — Derivation.** Parameterize `recompute_relation_aggregate` with `as_of` and
`policy_version`; relation columns become an explicitly-labelled cache; purity test;
`knowledge_assertions` ledger.

**Phase D — Query and explanation.** As-of, timeline, diff, explanation packet, retraction
impact. Mostly falls out of Phase C.

**Phase E — Product.** Evidence timeline, "what changed," policy comparison, historical
graph.

**Deleted: Phase 4 (policy-driven re-evaluation).** Under derivation there is nothing to
re-evaluate — publishing a policy version *is* the re-evaluation.

---

## 10. Ordering: this is downstream of CONNECT

Stated plainly because it affects whether any of this should start.

Agent-authored qualified claim promotion returns HTTP 409
`qualified_claim_persistence_not_ready`
([proposal_actions.py:846](../../services/artana_evidence_api/proposal_actions.py)), and
cross-document claim identity is zero by construction while the de-duplication key includes
the source span.

Scenario A requires "accepted in 2015, contradicted in 2025" — multiple documents landing
on one proposition over time. Today they cannot. Building Phases C–E first would produce a
belief timeline over propositions that each have exactly one source: a great deal of
machinery for a chart with one point on it.

**Phase A is exempt** and should not wait. It is additive, it is cheap, and it is the only
part whose deferral destroys information that cannot be recovered later.

---

## 11. Where this might be wrong

Two cases where the requirement's stored-state design is the better answer, stated so the
decision is made deliberately:

**Citability.** "Here is the record we published on 2026-03-01" is a stronger attestation
than "we can recompute it." If Artana is ever cited in a clinical guideline or a regulatory
submission, a frozen, signed state artifact is the better object. *This is solvable within
the counter-proposal* — snapshot derivations on publication — but it must be designed in,
not retrofitted.

**Recomputation cost at scale.** If as-of derivation over a large graph proves too slow,
materialized state versions are the pragmatic fallback. Mitigation is caching; the risk is
real; it does not change the authority question.

**And one thing the counter-proposal does not fix:** the recorded user signal is that
breadth and external export matter more than additional per-claim depth. This requirement,
in either form, is a *depth* investment. Worth weighing against §18/§9 sequencing before
committing engineering months.

---

## 12. Documentation (response to §19)

§19's proposed README/vision text is accepted in substance. One wording change, so the
documentation does not commit Artana to the architecture this document rejects:

> Artana does not maintain only the latest graph state. It preserves the evidence, the
> policies, and the decisions that produced every interpretation — so that what a research
> space accepted at any point in time can be reconstructed, explained, and compared against
> what it accepts now.

And the extended principle:

> **LLMs propose. The system governs. History remains inspectable.**

Accepted verbatim. Neither that phrase nor any temporal statement currently appears
anywhere in the repository.

---

## 13. Open questions for the requirement owners

1. **Is the authority question settled?** §1 is the whole disagreement. If propositions must
   be authoritative for a reason not stated in the requirement — a compliance obligation, a
   publication commitment — that changes the answer and should be said explicitly.
2. **Curation admissibility vs scientific acceptance:** two statuses or one? This
   counter-proposal assumes two.
3. **Cross-space proposition identity** (Scenario E) is new work in any design. Is it in
   scope for this requirement, or a separate one?
4. **What is the stance on hard deletion?** As-of queries and `document_deletion` are in
   direct tension (§6).
5. **Does this start before CONNECT is unblocked** (§10)? Phase A should regardless.
