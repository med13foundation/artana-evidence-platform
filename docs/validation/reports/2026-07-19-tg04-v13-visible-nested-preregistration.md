# TG-04 V13 Explicit Anaphoric Nested Canary Preregistration

## Status

`FROZEN_BEFORE_PROVIDER_CALL`.

This is a synthetic, exposed, non-qualifying contract canary. It tests whether
the sealed V13 execution path can preserve an explicitly stated inner event and
an outer event that refers back to it. It cannot authorize a hidden unit,
replication, trusted-graph promotion, or graph persistence. A pass authorizes
only the complete eight-case V13 visible matrix.

## Frozen Repository And Contract

- branch: `alvaro/tg04-representation-invariant-contract`;
- code-under-test commit: `aa070603d6621d20c10b1d414ae568d28b614487`;
- model: `openai:gpt-5.6-luna`;
- execution contract: `tg04.finite_source_unit.v13_execution.v2`;
- execution contract SHA-256:
  `076878a72c9653d44f6f4bbedb5171194b8cb7599991c810ef374b26bd276776`;
- extraction prompt: `tg04.finite_source_unit.extraction.v22`;
- extraction prompt SHA-256:
  `250b7db39dc7fea3c03f3d0d56cd99598e3f792cfba5ca363a9377c0aef32314`;
- normalization prompt: `tg04.finite_source_unit.structure_normalization.v5`;
- normalization schema:
  `SourceUnitNormalizationOutputV13`;
- normalization schema SHA-256:
  `43418016713a4b848069e1a82babd0ab0706a5502889d14209ec371512456e0f`;
- source-only review prompt: `tg04.finite_source_unit.normalized_review.v5`.

The executable policy generates the extraction prompt internally and records
the v2 contract identity in the run evidence, every attempt record, and every
stage key. It does not accept a prepared-prompt override.

## Frozen Runner And Durable Reservation

The one-shot runner is an experiment artifact, not an Artana production path.
Its committed location and exact bytes are frozen before any provider call:

- runner path:
  `scripts/validation/claim_events/finite_source_unit/nested_holdout_trial/v13/visible_anaphoric_canary.py`;

- runner SHA-256:
  `24484c00dde1028e536235d5731ec1e3dbe78f50defa7d18c4c121315569ed84`;
- durable reservation key:
  `5d1925788702d15ded427cc8ec674242c876475377d28fc4b412ae43bd6e79bd`;
- durable create-once artifact directory:
  `/Users/alvaro/.codex/artana-evidence-experiments/tg04/v13-visible-anaphoric-5d1925788702d15ded427cc8ec674242c876475377d28fc4b412ae43bd6e79bd`.

The preregistration commit must be the direct child of the full code commit
above, and their diff must contain only this document. Preflight executes only
the committed runner path and hashes its bytes against this value before
runtime construction. The reservation key is derived from the contract
version, model, source hash, and input hash. The absolute reservation namespace
is fixed rather than derived from `HOME`. Reservation and result directory
entries are fsynced, survive temporary-file cleanup, and block every later
invocation of this exact experiment. Runtime configuration is checked before
reservation without making a provider call. After reservation, ordinary
errors, cancellation, keyboard interruption, and system exit all seal a
create-once negative report before returning or propagating.

## Frozen Synthetic Source

> EGF activated ERK, and the MEK1-null genotype reduced that activation.

- case ID: `v13-visible-explicit-anaphoric-nested`;
- source-unit ID:
  `source-unit-8f4110dc6f36311360f5b61f457fbf0e5a52551c415331d1a0c953bcb298d7d9`;
- source SHA-256:
  `5a9b163d436c6c64d8cc286f33a80a37d3821485165f9d010d7dc1a919e5e508`;
- source-unit input SHA-256:
  `1e4d51b0f100dec717645bef66f4b8edfb8e07980b935325354d4863c9555df5`;
- source offsets: `0..70`.

This source is deliberately synthetic. It tests source interpretation and
representation, not whether the statement is true in the wider literature. It
is one sentence because the finite-source-unit contract is sentence-bounded.
It differs from every prior Fas-ligand and Foxp3 canary and must not reuse prior
raw output.

## Frozen Accepted Scientific Projection

Gate B accepts exactly the following categorical projection. Local event IDs
may differ because they are agent-authored transport-safe labels; their graph
topology and source binding may not differ.

1. source eligibility category `FINDING`;
2. one source-asserted inner `SCIENTIFIC_FINDING` with event type
   `POSITIVE_REGULATION`, cue `activated`, claim outcome `SUPPORT`, and
   epistemic status `ASSERTED`;
3. `EGF` as the inner `CAUSE` and `ERK` as the inner `THEME`, both categorically
   typed `GENE_OR_PROTEIN`;
4. one source-asserted outer `SCIENTIFIC_FINDING` with event type
   `NEGATIVE_REGULATION`, cue `reduced`, claim outcome `SUPPORT`, and
   epistemic status `ASSERTED`;
5. `the MEK1-null genotype` as the outer `CAUSE`, categorically typed
   `VARIANT`;
6. `that activation` as the outer `BIOLOGICAL_PROCESS` `THEME`, with a
   source-bound referent anchor to `EGF activated ERK`; and
7. exactly one outer-to-inner `controlled_event_ref`. The inner event's own
   arguments have null references.

Both events are independently `SOURCE_ASSERTED`. The family is `NESTED`
because of the explicit outer-to-inner event reference, not because either
event is forced into `CONTROLLED_TARGET` scope.

No direct, flattened, three-event, direction-neutral, participant-swapped, or
scope-changed projection is accepted by this canary. Such an output remains
available as preserved diagnostic evidence but fails Gate B.

## One-Shot Agent Topology

Run exactly:

1. one V13 extraction agent;
2. one independent V13 correction/normalization agent; and
3. one source-only V13 falsification agent.

No retry, deterministic scientific repair, fallback extraction, prior-answer
reuse, hidden gold, numeric agent scoring, browsing, or graph write is allowed.
If a stage fails, later stages are skipped. Agents return categorical decisions,
reasoning, exact evidence spans, and falsification conditions; deterministic
code computes every pass/fail result.

## Gate A: Execution-Contract Canary

Gate A contains no expected scientific answer. All requirements must be true:

- exactly three provider attempts in role order;
- every attempt records execution contract v2 and a distinct contract-bound
  stage key;
- every structured output is schema-valid and lexically source-bound;
- the review output addresses every required material axis and every returned
  normalized candidate without omitting a decision;
- fallback calls, retries, and deterministic scientific repairs are zero; and
- raw outputs, provider response IDs, prompt hashes, schema hashes, source
  hashes, execution-contract identity, and role-specific provider receipts are
  preserved and reverified.

The runner also deterministically re-derives every role's invocation-bound
prompt hash, contract-bound step key, schema identity, model identity, source
and input hashes, semantic-unit identity, evidence-unit hash, and kernel run
identity. Replayed, retry-marked, malformed, unidentified, or partially bound
attempts fail Gate A. Receipt-expectation construction is total: malformed
attempt evidence yields `STOP_WORKFLOW_INVALID`, never a favorable result or an
unsealed rerun opportunity.

Gate A answers only whether the sealed contract operated correctly. It does not
award scientific-quality credit and does not require a particular family,
event count, category, entailment result, or favorable reviewer decision.

## Gate B: Scientific Interpretation Observation

Gate B is evaluated only after Gate A passes. Deterministic code compares the
final agent-authored categorical structure against the seven frozen requirements
above. It also requires:

- family `NESTED`;
- eligibility category `FINDING` and exactly two source-asserted
  `SCIENTIFIC_FINDING` events;
- exactly one link from the outer biological-process theme to the inner event;
- self-references, missing targets, duplicate links, swapped targets, orphan
  controlled targets, procedural controllers, and unlinked references all zero;
- normalized inventory coverage `COMPLETE`;
- unsupported additions `ABSENT`;
- family validity `VALID`;
- every material-axis decision `PRESERVED` or `COMPATIBLE_REFINEMENT`; and
- both normalized candidates `ENTAILED`.

The exact canary additionally requires `NONE` normalization abstention, exactly
two exhaustive event mappings, no context dimensions, exact inner and outer
event spans, review eligibility `FINDING`, and cue alignment `EXACT`. Reviewer
abstention, surface-only equivalence, a material cue mismatch, or any extra
context dimension therefore fails Gate B even if another review field is
favorable.

The source-only agent supplies those categorical judgments, exact source
evidence, reasoning, and falsification conditions. It supplies no numeric score.
Deterministic code performs exact enum, role, span, count, topology, and
set-membership comparisons. There is no open-ended equivalence judgment.

This exposed result remains non-qualifying even if Gate B passes.

## Stop Rule

Any Gate A failure yields `STOP_WORKFLOW_INVALID`. Any Gate B contradiction,
missing event, unsupported addition, scientific loss, rejected topology, or
abstention yields `STOP_VISIBLE_CANARY_FAILED`. Do not retry this source.
Preserve the raw evidence and isolate one root cause before using a different
visible source.

Only `PASS_VISIBLE_CONTRACT_CANARY` authorizes the frozen eight-case V13 visible
matrix. No hidden unit may be opened from this canary alone.
