# TG-04 Finite Source-Unit Pilot

Date: 2026-07-17

## Decision

**STOP AND RECALIBRATE.** Dividing the documents into 32 finite sentence units
removed the unbounded-completeness loop, but it did not produce one exact frozen
whole event. The pilot therefore does not authorize a larger panel, production
workflow confirmation, persistence, or trusted-graph promotion.

This is not evidence that Luna found no useful science. A separate Luna verifier
judged 28 extracted events source-entailed, including several close to the four
expert events. It is also not proof that those 28 are all valuable or correct:
the verifier used the same model family, disagreed with the extractor about
procedural units, and produced four invalid outputs. The honest conclusion is
that finite enumeration improved task boundedness while exposing a still
underspecified event contract and incomplete exact event reconstruction.

## Frozen Experiment

- Model: `openai:gpt-5.6-luna`
- Harness commit: `13175ae50ab629fb3f1ddfe7a7a6e4a4849e21dc`
- Cases: the same four frozen TG-04 diagnostic cases used before PR `#168`
- Source units: `32` deterministic sentence locations (`7`, `9`, `11`, `5`)
- Agent calls: one extraction and one source-only verification call per unit
- Agent outputs: categorical findings and explanations, never numeric scores
- Numeric metrics and stop/go decision: deterministic code only
- Biomedical fallback: disabled and credited fallback count `0`
- Production extraction path: not exercised; this qualifies only the experimental task
- Artifact: `/tmp/artana-tg04/finite-source-unit-2026-07-17/luna-r2.json`
- Artifact SHA-256: `8c59553036a4dc58eb55e5b6381058401fcbff2a9069499f7f26b5abb1f3f58e`
- Inner report SHA-256: `53dea580b834f0d12481d503c1e1484746ce8a1bf9867e434b375cbf779f06e9`

The inner digest was independently recomputed after removing the embedded
`report_sha256` field and matched exactly. All 64 provider calls returned unique
response IDs with provider status `completed`.

## Invalid First Attempt

The first run, `tg04-finite-source-unit-luna-01`, is retained but has no
scientific interpretation. Its pilot-specific kernel run ID disagreed with the
invocation-bound Artana run ID, so all 32 payloads failed custody before model
output could be accepted. The owning boundary was fixed and regression-tested;
the frozen model, source, prompts, schemas, metrics, and gates were unchanged
for the single authorized replacement.

## Gate Result

| Requirement | Result | Evidence |
| --- | --- | --- |
| All four cases executable | fail | `1/4`; four verifier outputs invalidated three scientific cases |
| All source-unit inventories confirmed | fail | `0/4`; missing-event findings or invalid verification remained in every case |
| At least one exact whole event | fail | `0/4` gold events recovered exactly |
| Methods control empty | pass | extraction emitted `0` events |
| Negative or unmatched leakage zero | fail | `14/14` predictions in the scored gold case were not exact gold matches |
| Epistemic escalation zero | fail | `1/2` qualified gold comparisons escalated |
| Item-binding rejections zero | fail | `13` candidates rejected by source binding |
| Invalid agent outputs zero | fail | `4` verification outputs invalid |
| Provider lineage complete | pass | `64/64` calls had unique response IDs |
| Provider receipts verified live | fail | `0/64`; provider retrieval omitted output-schema metadata |

The pre-registered decision is `STOP_AND_RECALIBRATE`.

## Scientific Result

The strict qualification case contained four expert corpus events. Luna emitted
14 independently source-entailed candidates, but none matched a complete expert
event key.

Important near misses show why exact recovery failed:

1. Luna found `TGF-beta-mediated induction of FOXP3` with the correct trigger,
   type, and participants, but assigned TGF-beta the event role `AGENT` instead
   of the expert role `CAUSE`.
2. Luna found `GATA3 ... repressing FOXP3`, but promoted the expert
   `UNCERTAIN` polarity and epistemic status to `SUPPORT` and `HYPOTHESIS`.
   This is a real scientific qualification failure, not a string mismatch.
3. Luna found CD25 reduction content, but merged several measurements into a
   broader malformed event instead of reconstructing the expert two-argument
   negative-regulation event.
4. Luna found the asserted IL-4 inhibition of FOXP3 expression but did not
   reconstruct the expert uncertain GATA3-dependent mechanism event.

Deterministic aggregate metrics were:

- whole-event precision: `0/14`
- whole-event recall: `0/4`
- trigger recall: `2/4`
- event-type fidelity: `2/4`
- argument recall: `1/8`
- argument precision: `1/36`
- epistemic fidelity: `2/4`
- methods-control false positives: `0/1`

These numbers measure exact expert-event reconstruction. They do not establish
that all unmatched events are false.

## Non-Lossy Discovery Lane

The independent source-only calls judged `28` candidates `ENTAILED`: `4` in the
WT1 stress case, `10` in the differentiation stress case, and `14` in the gold
qualification case. Two additional candidates were retained as `INSUFFICIENT`.
No unmatched source-entailed claim was silently discarded or promoted.

The 28 events are a mixture that the four-event gold set cannot adjudicate by
itself:

- several are plainly explicit source statements, such as IL-4 inhibiting
  FOXP3 expression and the null differential-growth finding;
- several split one sentence into multiple scientifically defensible event
  views;
- some are likely too procedural, broad, or weakly typed to be useful graph
  claims;
- all were verified by another call to the same model family, so they are
  review evidence rather than independent scientific ground truth.

The scorer's `negative_null_leakage` label counts every non-exact prediction in
this case. Here it means 14 unmatched candidates, not 14 independently proven
false claims. Exact precision remains a valid strict gate, while source validity
and decision value require separate categorical adjudication.

## Root Causes

### 1. Event Eligibility Is Not Governed Consistently

The extractor was explicitly told that assay procedures are not biomedical
events. The verifier was asked to find every explicit biomedical event but did
not receive the same procedure and measurement exclusion rule. Consequently,
the extractor correctly returned no methods events while the verifier called
resting cells, electroporation, and luciferase measurement missing events. This
prompt-contract asymmetry made complete coverage impossible even on the true
negative control.

### 2. Sentence Boundaries Do Not Define Complete Scientific Events

Finite locations solved the endless search problem, but event arguments and
epistemic qualifiers still cross clauses and sentences. Luna frequently found
the right biological idea while choosing a different trigger scope, participant
role, or uncertainty representation from the expert event.

### 3. Verbatim Binding Exposes Real Generation Defects

Thirteen candidates failed because their canonical argument span was absent
from the anchor, an argument occurred outside the selected claim span, or the
context did not identify one occurrence. These are model-output defects that
must remain fail-closed. They should not be repaired with deterministic
biomedical guesses.

### 4. The Gold Set Is Precise But Not Exhaustive

The BioNLP expert events are strong targets for exact event fidelity, but the
four selected annotations do not label every valid or valuable statement in the
source. Exact-match failure therefore proves poor reconstruction of those four
events; it does not prove that every additional source-entailed event is wrong.

### 5. Provider Receipt Qualification Is Currently Impossible

Provider retrieval confirmed all 64 response IDs as completed, but did not
return the output-schema identity or associated invocation hashes. The receipt
gate therefore reported `output_schema_missing` for all calls. This is a custody
integration limitation separate from the negative scientific result. It must be
fixed without pretending that provider completion alone verifies Artana's full
invocation envelope.

## Smallest Next Experiment

Do not run a larger panel or add another generic adversarial pass yet. First
make the provider-custody contract verifiable with a tiny no-science smoke call.
Then freeze a three-unit **event-eligibility and target-reconstruction**
diagnostic containing exactly:

- one source unit containing a known expert gold event;
- one true-negative methods unit;
- one explicit source event that is absent from the finite gold annotations.

For those three units:

1. Give extraction and verification one shared governed eligibility contract
   with categorical outcomes: `FINDING`, `HYPOTHESIS`, `NULL_RESULT`,
   `PROCEDURE`, `MEASUREMENT_ONLY`, `NO_EVENT`, or `ABSTAIN`.
2. Preserve procedures and measurements for audit, but exclude them from the
   scientific-event completeness gate deterministically from those categories.
3. Ask the agent to reconstruct the finite source-anchored target without
   revealing the gold answer. Return trigger, direction, complete typed
   participants, polarity, epistemic status, and nested-event structure.
4. Use a separate blinded agent to return categorical equivalence and source
   entailment findings with exact evidence and falsification explanations.
5. Compute exact recovery, near-match error categories, unsupported-event rate,
   and repeatability deterministically. Keep unmatched entailed discoveries in
   a separate review lane; do not count them automatically as either correct or
   false.
6. In parallel, define a provider-supported receipt contract that verifies live
   completion externally and Artana's schema, prompt, source, and invocation
   hashes internally without claiming the provider returned fields it does not
   expose.

Proceed to the unchanged four-case panel only if all three units are executable,
the methods unit is consistently excluded, the expert event is exact, the
unannotated source event remains visible without being mislabeled false, no
uncertainty is escalated, all accepted candidates bind, and the custody contract
verifies. If target reconstruction still fails, compare Luna against one
stronger model on the unchanged three units. A second Luna reviewer is useful
for error detection, but this run shows that same-family review alone is not
sufficient evidence of scientific correctness.

## Validation

- Focused finite-unit unit, regression, semantic-binding, truth-table, receipt,
  and timeout tests passed.
- `make service-checks` passed with `87.53%` repository coverage.
- Evidence API lint, type, boundary, contract, architecture, migration, and test
  gates passed.
- An adversarial implementation review was completed before the live run; its
  findings were fixed and regression-tested.
- A separate post-run adversarial review confirmed the stop decision, the
  benchmark-undercoverage caveat, and the three-unit isolation experiment.
- The replacement ran from a clean tracked worktree and the immutable artifact
  remained unchanged during analysis.
