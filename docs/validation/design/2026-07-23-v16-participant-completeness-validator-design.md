# V16 Mechanism Design: Per-Claim Participant Completeness Validator

**Status:** preregistration draft — no execution authorized until sealed.
**Parent experiment:** `staged-generalization-v15-exposed-run-v1` (sealed at `e606fcb8`).
**Failure classification driving this design:** `06fd697b` (V15 post-run independent classification).

## 1. Problem statement

V15's exposed-panel run produced:

- comparison: PASS
- drug-sensitivity: PASS
- uncertainty: FAIL

The uncertainty case failed on exactly two sealed dimensions:

1. `mandatory_participant_completeness` — the mandatory `SLC12A3` gene symbol was missing from the extracted event arguments.
2. `participant_role_fidelity` — the contextual gene argument was absent from the event's typed role map.

The V15 system prompt already contained source-general rules that, if followed, would have produced the `SLC12A3` participant. Independent adjudication concluded:

> The failure is model-adherence brittleness, not evidence supporting another answer-shaped prompt patch.

Therefore a **prompt patch** is scientifically ruled out. What is needed is a **mechanism change** that makes "model dropped a mandatory participant" a caught, recoverable event rather than a silent failure.

## 2. Why a mechanism change — not a wording change

Prompt-patch interventions (V12 → V15) have each repaired one visible failure at the cost of one more simultaneous constraint. The V15 uncertainty failure is the first observed case where the model satisfied most constraints but lost one under load. This is the signature of **constraint-load brittleness**, which no additional wording can fix without either:

- making the prompt heavier (amplifying the very brittleness that caused it), or
- adding answer-shape cues that bias the model toward the reference shape rather than toward a source-general procedure.

A mechanism change is justified only when both conditions hold:

- (a) the failure is reproducible in the sealed exposed panel, and
- (b) the existing prompt already encodes the rule that should have prevented it.

Both conditions are met here.

## 3. Proposed mechanism

Introduce a **per-claim participant-completeness validator** and a **bounded one-shot repair** in the existing claim-framing extraction path. This is not a new extraction step — it is a validation gate between the initial framing call and the downstream normalization/promotion path.

### 3.1 Validator scope

After each single-claim framing call returns a validated `FramedClaimResult` (see `services/artana_evidence_api/document_extraction_support/llm_extraction/claim_framing.py`), run:

```
validate_claim_participant_completeness(
    framed_claim,
    source_region,
    event_type_schema,
) -> ParticipantCompletenessDecision
```

The validator is deterministic, source-only, and schema-driven. It:

1. Enumerates the **mandatory argument roles** for the frame's event type (e.g., for a classification event: gene, variant, condition, directionality).
2. Walks each mandatory role and checks whether the frame binds at least one source-anchored participant with an `exact_span` inside the claim's source region.
3. For each unmet role, returns `INCOMPLETE` with the missing role names and the shortest source-text snippet (≤ 160 chars) that mentions a candidate span the model could bind on repair.

The validator never invents participants. It never consults external dictionaries. It only reports: "this role is mandatory by schema and has no source-anchored participant in the current frame."

### 3.2 Repair policy

If `validate_claim_participant_completeness` returns `INCOMPLETE`, the harness issues exactly one repair call:

- Same model, same temperature.
- Same output schema.
- A repair prompt that **does not** include any answer-shaped hint. It says only: "your previous framing omitted the following mandatory roles: [role names]. Re-frame the same claim. Bind a source-anchored participant to each listed role from the claim's source region. Preserve everything else verbatim."
- The repair output replaces the original only if it passes both schema validation AND the same completeness validator.

If repair fails or returns `INCOMPLETE` again, the frame is emitted with its original completeness status preserved (no silent promotion, no silent retry, no fallback to a different model call). The failure is durably recorded in the attempt audit record under a new `participant_completeness` telemetry field.

### 3.3 Provider-custody invariants preserved

The repair call is:

- exactly one additional provider call per incomplete frame,
- receipt-logged with the same hash/receipt/cost/fail-fast custody V15 already enforces,
- counted against the same per-run budget,
- never silently retried.

No other V15 invariants are modified. No prompt content is changed. The V15 system prompt (including its source-general rules) is reused verbatim.

## 4. Internal precedent

This design reuses a pattern already present in this repository:

| Subsystem | File | Pattern |
| --- | --- | --- |
| Claim framing | `document_extraction_support/llm_extraction/claim_framing.py` | `_SCHEMA_RETRY_SUFFIX` / `_SCHEMA_RETRY_INSTRUCTION` — one-shot repair after schema/source-binding validation failure |
| Shadow planner | `full_ai_orchestrator/shadow_planner/runtime.py:333` | `_REPAIRABLE_VALIDATION_ERRORS` — one-shot repair after a deterministic validation predicate, with a bounded repair prompt |
| Inventory completeness | `document_extraction_support/claim_frames/completeness.py` | Deterministic, source-bound completeness review at the chunk level |

The new validator composes these existing patterns: a deterministic validation predicate over the claim-frame output, followed by a bounded one-shot repair using the same prompt-and-schema contract.

## 5. Hypothesis

Under the same provider, temperature, and prompt, adding the per-claim completeness validator with bounded one-shot repair:

- **H₀:** does not change the comparison or drug-sensitivity PASS outcomes, and converts the V15 uncertainty FAIL into a PASS, allowing the full exposed panel to pass in one run.
- **H₁:** does not produce a full-panel PASS (repair either fails or introduces a regression on a previously passing case).

If H₀ holds, the project's stated authorization condition — "full exposed panel passes in one run" — is met, which lifts the current stop condition and authorizes fresh-case validation.

If H₁ holds, the evidence supports one of:

- repair did not fire (validator too permissive),
- repair fired but failed (validator too strict, or repair prompt unhelpful),
- repair fired and introduced a regression on another case (repair prompt overcorrected).

Each sub-outcome has a different follow-on design implication. All are recorded durably; none authorizes ad-hoc prompt patching.

## 6. Scope of this design

- One new module: `document_extraction_support/claim_frames/participant_completeness.py` containing the validator, decision type, and repair-decision contract.
- One new module: `document_extraction_support/llm_extraction/claim_framing_repair.py` containing the bounded repair call, prompt builder, and telemetry record.
- One integration point: a post-framing validation call in the existing `claim_framing.py` runner.
- One unit-test tree: `services/artana_evidence_api/tests/unit/test_participant_completeness_validator.py` covering:
  - COMPLETE returned when all mandatory roles have source-anchored spans,
  - INCOMPLETE returned when any mandatory role is unbound,
  - repair replaces original only when repair output passes both schema and completeness,
  - repair failure preserves the original frame and records telemetry,
  - no silent retry, no extra provider calls beyond the single bounded repair.

## 7. Out of scope

- No change to the V15 system prompt or any existing prompt content.
- No new event types, no new source-general rules, no new relation types.
- No change to the shadow planner, inventory completeness reviewer, or claim-adjudication contracts.
- No modification of the exposed-panel case set.
- No access to the 7 preserved fresh cases until full-panel PASS is demonstrated.
