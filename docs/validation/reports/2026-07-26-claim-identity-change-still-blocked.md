# The claim-identity change would merge findings with their refutations, and there is nothing to measure it on

**Date:** 2026-07-26
**Issue:** #217 — "does removing the source span from claim identity let two papers be recognised as asserting the same fact?"
**Precondition:** the three persistence-side blockers found by the #217 measurement are fixed (`ab7b547b`, `fb3b98ac`, `73480637`)
**Provider calls:** none — every number here comes from replaying model outputs already paid for and persisted to `artana.kernel_events`
**Script:** `scripts/validation/claim_identity_merge/replay_framing_validators.py`
**Results:** `docs/validation/results/2026-07-26-claim-framing-validator-replay.json`
**Verdict:** do not make the change as specified — §2 is a defect in the proposal, not a scheduling problem

The #217 measurement found the identity question was third in a queue behind
three blockers. Those three are fixed. This report re-asks the identity question
with them gone and concludes: **do not make the change as specified.**

There are two independent reasons, and they are not the same kind of reason:

* **The change as literally specified is unsafe at any yield** (§2). Moving the
  frame branch onto `compute_claim_fingerprint(subject, relation, object)` drops
  `polarity` and `epistemic_status` out of the identity, so a finding and its
  own refutation receive the same fingerprint. This is demonstrated below, not
  inferred, and no amount of extra data makes it safe.
* **Nothing downstream is observable yet** (§1, §5). Three frames survive from
  nine documents, so there is no population on which any identity rule could be
  evaluated.

The first is a defect in the proposal. The second is a reason to wait.

---

## 1. The frame path is still not exercised end to end, and the fix could not have helped

The measurement reported that ten of eleven documents aborted "inside the
claim-framing validators". That abort is upstream of persistence, so widening a
fingerprint column could not move it. This is checkable rather than arguable:
none of the three blocker commits touches a single file under
`document_extraction*` or `document_extraction_support/`. They touch migrations,
`models/harness.py`, the two stores, the review-queue router and their tests.
The framing stage never sees them.

Replaying the recorded framing traffic against current code confirms it. Every
framing call persists both its prompt (`model_requested`) and its answer
(`model_terminal`), and the prompt carries the bound inventory item and the
frozen source region verbatim — the entire input to the validator chain. So the
chain re-executes exactly, at no cost:

| | |
|---|---|
| inventory claims replayed | 14 |
| relations in those answers | 17 |
| documents that reached framing | 9 |
| **documents yielding at least one frame** | **3** |
| **frames reaching the write path** | **3** |
| cross-document triple agreements | 0 |

Where the other 14 relations stop:

| first rejecting stage | count | dominant reason |
|---|---|---|
| `_require_inventory_consistency` | 9 | 7 × "framed relation endpoints must come from typed inventory arguments" |
| frame dropped in candidate build | 5 | 4 × "intervention qualifier cannot duplicate the claim subject" |
| survived | 3 | — |

Two properties of the replay matter, because both cut *against* the yield and
both are reproduced rather than glossed:

* The stage runs one first attempt per inventory claim and, on rejection, one
  schema retry whose value it returns. Both are persisted — 14 first attempts
  and 11 retries, so the retry fires for 79% of claims. Counting both would
  double-count. The retry supersedes its first attempt here.
* `_validate` raises out of the *whole call* on the first bad relation, so a
  call keeps its frames only if every relation in it passes. Scored that way,
  the answer is unchanged (each survivor was the only relation in its call), but
  the leniency is removed rather than assumed harmless.

**So: persistence is unblocked and supply is not.** B1 was real and had to be
fixed; it simply was not what was stopping frames. Three frames from nine
documents is not a population any identity rule can be evaluated on.

## 2. The change as specified would merge a finding with its own refutation

This is the decisive finding, it is independent of yield, and it was missed by
framing the question as "which labels go into the hash".

`ClaimFrame.dedupe_identity` (`claim_frames/contracts.py:296`) hashes the whole
serialized frame minus `extraction_rationale` and the qualifier `exact_span`s.
That payload includes `polarity` and `epistemic_status`, both declared fields on
`ClaimFrame` (`contracts.py:214-215`). `compute_claim_fingerprint`
(`claim_fingerprint.py:91`) takes exactly three arguments — subject, relation
type, object — and has no parameter that could carry either.

So the swap does not merely change *which labels* are hashed. It silently
discards the two fields that distinguish an assertion from its negation.
Constructing two real `ClaimFrame`s differing in nothing but `polarity`:

```
current  dedupe_identity  SUPPORT: ccbeaf60f95e1f11…   REFUTE: 8d73fe22cfd96cd6…   DISTINCT
proposed fingerprint      SUPPORT: a894c346d4ce395b…   REFUTE: a894c346d4ce395b…   COLLIDE
```

"Drug A REDUCES outcome B" and "Drug A does **not** reduce outcome B" become one
identity. `epistemic_status` goes the same way, so an asserted finding and a
hypothesis collapse together too, as do the n-ary `assertion_arguments` and all
qualifier states.

This is not only a property of the contract. Applying the swap to
`document_extraction_drafts.py:244` for real and running two candidates
differing in nothing but polarity through `build_document_extraction_drafts`
returns **the same fingerprint for both** — `78cff936b98635629446f1ce7f31ed0e`
— where current code returns two distinct 64-char identities. The edit was
reverted; the two regression tests added alongside this report
(`test_frame_identity_separates_a_finding_from_its_refutation` and
`test_draft_fingerprints_separate_a_finding_from_its_refutation` in
`tests/unit/test_claim_frames.py`) were confirmed to fail under it and pass
without it.

One existing test, `test_draft_preserves_frame_and_does_not_split_qualified_object`,
also fails under the swap — but only because it pins the *mechanism*
(`claim_fingerprint == frame.dedupe_identity`). Anyone deliberately changing the
identity would have updated it as a matter of course. The new tests pin the
*safety property* instead, which is the thing that must survive any future
redesign.

The three landed blocker fixes make this *worse*, not better. Before them a
collision parked the whole batch and nothing could be actioned. Now a collision
parks precisely the second proposal as `identity_pending` and offers a reviewer
`resolve_as_duplicate` (`routers/review_queue/identity_adjudication.py:40`) — a
one-click path to discarding a refutation as a duplicate of the claim it
refutes, with the queue asserting the two are the same fact.

Any future version of this change must keep polarity and epistemic status in the
identity. That means it is not a swap to `compute_claim_fingerprint` at all; it
is a *new* identity function over (resolved subject, relation, resolved object,
polarity, epistemic status). That function does not exist today.

## 3. Moving onto resolved labels is a one-line change that does nothing *today* — for a fixable reason

`resolved_subject_label` and `resolved_object_label` are ordinary local
variables in `document_extraction_drafts.py`, assigned at lines 179 and 226,
both in scope at the fingerprint expression on line 244. Mechanically the change
is trivial.

For a frame-backed candidate those variables are currently byte-identical to
what the frame branch already hashes:

* `llm_relation_to_candidate` sets `subject = rel.subject.strip()` for
  frame-bearing relations (`llm_fulltext_extraction.py:294`) — no cleaning, no
  label repair, both of which apply only to the non-frame path — and passes that
  same string as both `subject_label` and the frame's `subject`. So
  `candidate.subject_label == frame.subject`, exactly.
* `resolved_subject_label` is `candidate.subject_label` **when resolution
  misses**, and the graph's display label only when it hits.

**But the reason resolution misses is not that the resolver is primitive.** An
earlier draft of this report claimed the only resolver here is an exact
case-folded match. That is wrong, and the correction matters for what to do
next. Both production callers — `research_init_document_extraction_runtime.py:745`
and `routers/documents.py:1010` — run `pre_resolve_entities_with_ai` first and
pass its output into `build_document_extraction_drafts` as
`ai_resolved_entities`, which `resolve_entity_label` consults *before* the
deterministic path (`document_extraction_entities.py:690-693`). That is a
semantic, agent-backed resolver with graph tool access.

It contributes nothing at present for a mundane reason:
`resolve_entity_with_ai` searches the graph for candidates first and, when that
search returns nothing, short-circuits to `CREATE_NEW` and returns `None`
without ever calling the agent (`relation_type_resolver.py:895-904`).
`graph_runtime.entities` currently holds **0 rows**. With an empty graph both
the deterministic and the AI resolver miss unconditionally, so the resolved
labels provably equal the frame body.

The practical consequence is that the precondition is **"populate the graph"**,
not **"build an entity resolver"**. The resolver already exists and is already
wired into both production paths. This is a materially cheaper prerequisite than
it appeared.

## 4. The 50-character cap is not the root cause, and lifting it would make things worse

The cap at `document_extraction_prompting.py:187,233` is real, but it is the
outermost of three constraints, and it is the *loosest*. A frame endpoint must
also:

* be a member of `{argument.exact_span for argument in item.arguments}` —
  enforced by `_require_inventory_consistency`; and
* those argument spans must literally occur in the source, because
  `_bind_inventory_argument_mentions` binds each one with
  `bind_source_mentions(canonical_span=argument.exact_span, source_span=item.exact_span)`.

**A frame endpoint is therefore a verbatim substring of the document, by
construction, at three independent layers.** It is not a canonicalized entity
name and cannot become one at this stage. The three frames that do survive show
what that produces:

```
'Synthesis of N-pyrimidinyl-2-phenoxyacetamides' | TARGETS   | 'adenosine A2A receptor'
'the dopaminergic system'                        | REGULATES | 'manipulation of the serotonergic system'
'rTMS of supplementary motor area'               | MODULATES | 'therapy-induced dyskinesias'
```

Only one of the six endpoints (`adenosine A2A receptor`) is plausibly a graph
entity label. `'the dopaminergic system'` carries an article;
`'manipulation of the serotonergic system'` and
`'Synthesis of N-pyrimidinyl-2-phenoxyacetamides'` are clause fragments naming
an activity, not an entity.

This answers the sufficiency question directly: resolution *consumes* the
surface string, so the resolved label is a function of it, not independent of
it. And raising the 50-character cap would admit *longer* verbatim spans, which
agree across documents less often, not more. The cap is a symptom. The
source-verbatim constraint is the cause, and it is deliberate — it is what makes
a frame auditable.

## 5. What is now measurable, what is not, and what it would cost

**Newly measurable, at $0:** where framing answers die, per stage and per
reason, against any version of the code. That is what the replay script does,
and it is the number to drive down first. It reproduces against the local
`artana.kernel_events` without a provider call.

**Still not measurable: the false-merge rate.** This is the number that protects
against fusing two different findings, and it remains out of reach for two
independent reasons:

1. **Yield.** Three frames from nine documents. There is no denominator.
2. **Nothing for the resolver to resolve against.** `graph_runtime.entities`
   holds 0 rows, so both resolvers miss unconditionally (§3) and the
   resolved-label variant is provably identical to the frame-body variant. The
   earlier measurement's "perfect entity resolution" arm sidestepped this by
   setting the labels to the gold MeSH ids — which is why that arm's recall of
   1.0 is a tautology and must not be quoted.

**Cost is not the constraint.** From the recorded run, the extraction stages
cost $0.5357 across the 9 documents that reached framing — about $0.06 per
document, so the full 1500-document BC5CDR corpus is roughly $90. That is
affordable. But at the current yield it would buy ~500 frames whose endpoints
are verbatim source spans, and what it would measure is the framing stage's
abort behaviour, not the identity rule. Spending it now would produce a precise
number about the wrong thing.

## 6. What would have to be true before the change is worth making

0. **A replacement identity that retains polarity and epistemic status.**
   Non-negotiable and independent of everything below (§2). The target is not
   `compute_claim_fingerprint`; it is a new function over (resolved subject,
   relation, resolved object, polarity, epistemic status). Until that exists
   there is nothing safe to move the frame branch *onto*.
1. **Framing yield above a floor worth measuring.** The dominant abort —
   7 of 17 relations — is the model choosing endpoints that are not among the
   typed inventory arguments. That is a prompt/contract mismatch between the
   inventory and framing stages, not a validator that is too strict, and it is
   fixable without touching identity.
2. **A populated graph, so the resolver that already exists can do its job.**
   Corrected from the earlier draft: the semantic resolver is already built and
   already wired into both production paths (§3). It is inert only because
   `graph_runtime.entities` is empty, which makes it short-circuit before the
   agent call. Until something maps `'the dopaminergic system'` and
   `'dopaminergic signalling'` to one entity, no identity rule downstream can
   recognise them as the same fact — but the missing piece is entities, not code.
3. **A false-merge measurement that does not compute identity from the answer
   key.** With (2) in place the resolver's output is no longer the label set
   that defines ground truth, and the measurement stops being circular.

Only then does the identity expression matter. Making the change as specified
today would drop polarity and epistemic status out of the identity, move the
frame branch onto labels byte-identical to the ones it already hashes, and widen
collisions with nothing to show for it. The measured cross-document agreement,
both before this work and after, is zero.

---

## Numbers in this report that must not be reused out of context

* **3 surviving frames, 9 documents.** A single recorded run on BC5CDR
  abstracts with one model. It establishes that the yield is far too low to
  measure an identity rule; it does not establish a rate.
* **$0.06 per document.** Derived from one run's `cost_usd` totals, dominated by
  stages whose call counts depend on how many claims each document inventories.
* **79% retry rate.** 11 retries over 14 claims in one run.
* The three surviving endpoint strings are quoted because the *shape* of the
  labels is the finding. They are short entity-level spans within the extraction
  prompt's own 50-character cap; the replay script refuses to write anything
  longer or anything carrying a sentence boundary, and redacts source spans that
  validator messages quote back.

**§2 is not in that category.** It is a property of two functions in this repo,
demonstrated by construction and pinned by two tests. It does not depend on the
recorded run, on BC5CDR, or on any yield, and it holds however the framing stage
is later fixed.

## Corrections to the earlier draft of this report

An earlier draft of this file made two claims that verification did not support.
Both are corrected above and recorded here so the change is auditable:

* It stated the only resolver on this path is an exact case-folded match. There
  is in fact a semantic, agent-backed resolver (`pre_resolve_entities_with_ai`)
  wired into both production callers. It is inert because the graph is empty,
  not because it is primitive — which changes precondition (2) in §6 from
  "build a resolver" to "populate the graph".
* It concluded only that the change was premature. It missed that the change as
  specified is independently unsafe (§2), which is a stronger and different
  conclusion.
