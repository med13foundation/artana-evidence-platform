# TG-04 Finite Source-Unit Pilot Protocol

Created: 2026-07-17

Status: pre-registered before model execution

## Decision Question

Does replacing the open-ended request to find every meaningful claim with a
finite location-by-location event audit recover at least one exact expert event
without weakening Artana's source, safety, or provider-custody boundaries?

This is one non-qualifying diagnostic. It cannot authorize persistence,
trusted-graph promotion, or a larger benchmark by itself.

The pilot uses Artana's kernel, model adapter, structured invocation binding,
source binder, event contracts, scorer, and provider custody. It deliberately
tests a new finite experimental extraction task rather than the current
production document-extraction entry point. A positive result qualifies the
task design only. The unchanged task must subsequently pass through the real
production workflow before claiming improvement for an Artana user.

## Frozen Inputs

- Model: `openai:gpt-5.6-luna`
- Run count: one
- Source fixture:
  `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json`
- Panel: the same four cases used by the preceding TG-04 diagnostics:
  - `bionlp-ge-2011:PMID-9361029`
  - `bionlp-ge-2011:PMC-2222968-03-Results-02`
  - `bionlp-ge-2011:PMC-2222968-05-Results-04`
  - `bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07`
- Deterministic source-unit count: 32 sentence locations, respectively
  `7`, `9`, `11`, and `5` per case.
- Repository state: a clean committed branch descended from merged PR `#168`.

The title and every sentence remain visible units. Model-visible unit IDs are
opaque hashes; case identifiers containing `Results` or `Materials_and_Methods`
remain only in deterministic custody metadata. Unit enumeration assigns no
biomedical meaning and does not inspect benchmark labels.

## Agent Tasks

For each finite source unit, the extraction agent returns one category:

- `EXPLICIT_EVENT`
- `NO_EVENT`
- `ABSTAIN`

An explicit event must include an exact trigger, complete event span, typed
arguments, event type, polarity, and epistemic status. Existing deterministic
Artana binding validates every candidate independently. Invalid siblings remain
auditable and cannot remove valid candidates.

Every unit, including `NO_EVENT` and `ABSTAIN` extraction results, receives a
separate source-only call. It first returns one inventory-coverage category:

- `CANDIDATES_COMPLETE`
- `NO_EVENT_CONFIRMED`
- `MISSING_EVENT`
- `ABSTAIN`

For each bound candidate, the same call also returns:

- `ENTAILED`
- `CONTRADICTED`
- `INSUFFICIENT`
- `ABSTAIN`

The verifier receives no extractor reasoning or mention-selection rationale.
It must cite literal evidence inside the candidate covering the trigger and
every material argument, explain its decision, and state a falsification
condition. Extraction and verification are independent invocations of Luna,
not independent model families. Neither agent returns a numeric score. Code
computes every count, rate, and stop/go decision.

There are no model retries in this pilot. Schema-invalid, semantically invalid,
unidentified, unavailable, or timed-out calls fail closed for their source unit
and remain visible in the report instead of preventing artifact creation.

## Measurement Lanes

The report keeps two questions separate:

1. **Strict frozen benchmark:** exact whole-event precision and recall, trigger,
   event type, complete typed arguments, polarity, epistemic status, negative
   control leakage, and abstention.
2. **Non-lossy discoveries:** independently source-entailed events that do not
   exactly match the finite gold set, including representability-stress cases.
   They are counted directly from verified candidates, remain review evidence,
   and are not silently discarded, promoted, or used to rewrite frozen gold.

Representability-stress output remains descriptive and outside qualification
precision. The methods control remains a true negative.

## Custody And Safety

- The CLI refuses a dirty tracked worktree.
- Output is create-once and written outside the repository during execution.
- Every call uses Artana's structured model client and invocation binding.
- Prompt, input, source, schema, provider output, payload, invocation, run, and
  evidence-unit identities are recorded.
- Provider response IDs must be unique and retrievable.
- Deterministic biomedical fallback is absent and credited fallback is zero.
- No candidate is persisted or promoted.

## Restart Gate

Proceed to a larger frozen panel only when every condition is true:

- all four cases are executable;
- every source unit has independently confirmed inventory coverage;
- at least one exact whole event is recovered;
- the methods control has no event;
- negative or null leakage is zero;
- epistemic escalation is zero;
- deterministic item-binding rejections are zero;
- invalid agent output is zero;
- provider lineage is complete;
- live provider receipts verify.

Otherwise stop and inspect the categorical failure evidence. If exact recovery
is still zero but unmatched events are independently source-entailed, evaluate
benchmark coverage and event projection separately. If both exact recovery and
useful unmatched discovery remain weak, stop model-only extraction and compare
an expert-seeded or hybrid candidate workflow.

## Execution

After the harness commit is clean and the environment selects Luna:

```bash
export ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES=true
export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL=openai:gpt-5.6-luna
uv run python scripts/run_finite_source_unit_audit.py \
  --run-id tg04-finite-source-unit-luna-01 \
  --output /tmp/artana-tg04/finite-source-unit-2026-07-17/luna-r1.json
```

The result report must be generated from the immutable JSON without editing the
payload or changing the gates after model output is observed.

## Invalidated Orchestration Attempt

The first invocation on committed harness `2fe238a3f212b8f34a0f634b2adeb0c73fb29f2d`
is retained as an invalid experiment artifact:

- run ID: `tg04-finite-source-unit-luna-01`
- artifact:
  `/tmp/artana-tg04/finite-source-unit-2026-07-17/luna-r1.json`
- artifact SHA-256:
  `6b2876a1340516fedde918fd6549a60c5b99f27fc642977d4e24eb2157f2e2f4`
- provider payloads returned: `32`
- accepted extraction attempts: `0`
- terminal category: `StructuredModelInvocationTopologyError`

The experimental client used a pilot-specific kernel run namespace instead of
the run ID already bound into Artana's provider invocation envelope. Every
payload therefore failed custody before schema or semantic evaluation. The
artifact has no scientific interpretation and is not a failed model run.

The owning run-ID boundary is corrected and regression-tested before one
replacement execution named `tg04-finite-source-unit-luna-02`. The frozen
source panel, model, prompts, schemas, metrics, and stop/go thresholds remain
unchanged. The replacement writes create-once to `luna-r2.json`; the invalid
artifact is never overwritten or counted as a replicate.
