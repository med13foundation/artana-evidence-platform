# TG04 V10 Versus Staged Source-1 Result

Created: 2026-07-20

Decision: `INVALID_EXPERIMENT`

This is not a scientific win or loss for either architecture. The frozen V10
baseline failed provider-output validation on source 1, so the staged arm was
not run and no paired scientific comparison exists.

## Execution Evidence

- Source: `pubmed:42454948`
- Source SHA-256: `91dc8584459752004de193cdaa40efd8024b943f8f841ca5653e42b8d535de5b`
- Model: `openai:gpt-5.6-sol`, provider-default reasoning
- Live provider attempts: 1
- Receipt: `verified_live`
- Replay: false
- Retries: 0
- Staged calls: 0
- Fallbacks: 0
- Graph writes: 0
- Raw output inventory: 10 events, 2 descriptive findings, 26 participants

The immutable result file SHA-256 is
`a4f062e076a30bed063f6dc4c702f128633dd3f620486a748f983b0033c3f105`.
Its separately retrieved provider-receipt artifact SHA-256 is
`03fcc2b15635e123b1aa2ceae818bdcf32467531ad2ad3aac59263f9daa20f89`.

## Exact Failure

The provider produced a substantial candidate inventory, but the frozen V10
model rejected two values:

1. Event `A6` used proposition family `ASSOCIATION` while also returning a
   contrast. V10 permits a contrast only for `COMPARISON`.
2. Study context `C1` used design `UNSPECIFIED`. V10 requires every returned
   source context to name a categorical study design.

These are semantic model validators that are not fully represented by the JSON
schema delivered to the provider. The prompt also did not enumerate these two
cross-field prohibitions. The response therefore satisfied the visible object
shape but failed the hidden deterministic contract.

## Custody Correction

The original runner reported `provider_call_count: 0` because its counter was
derived from successfully decoded `ModelResult` objects. A schema-invalid live
response raises before that list is appended. The immutable audit record and
retrievable receipt prove that exactly one live call occurred. A separate
correction artifact records the discrepancy without rewriting the raw result.

## Stop Decision

The preregistered rule requires a valid result from both arms before scientific
metrics can be compared. Consequently:

- do not score the raw V10 candidates;
- do not run the staged arm as part of this sealed comparison;
- do not retry source 1;
- do not expose sources 2 or 3;
- do not claim scientific improvement.

## Root-Cause Direction

The next experiment should not expand biomedical semantics. It should repair
the provider-contract boundary on exposed development fixtures:

1. Make every provider-visible categorical rule explicit in schema or prompt.
2. Separate provider-decodable shape from deterministic semantic compilation.
3. Count attempted live calls from the immutable attempt ledger, including
   schema-invalid terminals.
4. Prove schema-invalid fixtures stop with truthful call and receipt counts.
5. Freeze a new baseline version and select new untouched sources before any
   further paired provider experiment.

V10 remains frozen as the historical one-shot baseline; this failed execution
must not be erased or silently reclassified.
