# Staged Luna Event Construction V2

## Decision

`INVALID_PROVIDER_EXECUTION`

Exactly one authorized Stage 1 Luna-high creation call ran. Stage 2 did not run.
There was no retry, fallback, graph write, promotion, or untouched-source use.

## Root Cause

The provider boundary completed and returned a typed `EventInventoryOutput` in
process. The runner then performed an unnecessary second validation:

1. `model_dump(mode="json")` converted strict tuple fields to JSON lists.
2. `EventInventoryOutput.model_validate(...)` revalidated those lists in strict
   Python mode.
3. Pydantic rejected `events` because strict tuple input requires a tuple.

The crash happened before the runner persisted the verified receipt or raw
structured output. Therefore the response ID, tokens, latency, and cost are
unavailable and are not reported as zero. No scientific metrics are calculated
from the partial traceback.

## What This Means Scientifically

This run does not answer whether Luna found the missing intermediate
`sensitivity` event. The partial exception rendering showed an inventory list,
but it is neither a complete preserved output nor valid scientific evidence.
It cannot receive benchmark credit and cannot be used to infer failure or
success.

## Offline Work Completed

- Receipts now record and enforce requested and observed output tokens, total
  tokens, latency, and cost with categorical boundary results.
- Output-token overrun fails independently of the total-token ceiling.
- Exact agent text is resolved deterministically inside event-local evidence;
  missing, repeated, ambiguous, and cross-scope anchors fail closed.
- The temporary architecture override was removed.
- Source-first code was split into single-responsibility modules.
- Stage 1 inventory and Stage 2 immutable linking contracts were implemented.
- Focused tests, Ruff, MyPy, and the architecture guard passed before execution.
- The terminal `make service-checks` run passed with 87.64% coverage after the
  invalid experiment was frozen. No executable code changed afterward.

## Required Correction Before Any New Call

A future separately preregistered run must persist the verified receipt and raw
typed output immediately after the provider boundary, before any downstream
conversion. Downstream code must use the already validated typed object without
strictly revalidating a JSON-mode dump. This V2 run must never be retried or
reinterpreted.
