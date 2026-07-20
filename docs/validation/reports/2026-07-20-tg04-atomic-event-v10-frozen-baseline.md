# TG04 Atomic-Event Validator V10 Frozen Baseline

Created: 2026-07-20

Status: `FROZEN_NO_PROVIDER_CALL`

Decision: `BASELINE_ONLY_NO_GO`

## Scope

This report freezes the bounded atomic-event validator called V10. It is not the
provider-backed TG04 V10 experiment recorded on 2026-07-18. The unambiguous
identity of this implementation is:

```text
atomic-event validator V10
tree SHA-256: bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a
```

The repository receipt is
`reports/2026-07-20-tg04-atomic-event-v10-freeze.json`. A matching manifest is
stored beside the isolated implementation at
`atomic_event_contract_v10/freeze-manifest.json` in the TG04 experiment lab.

## Current Result

The validator split is complete and its offline verification is green:

| Check | Result |
|---|---:|
| V10 tests | 71 passed |
| Combined V8, V9, and V10 tests | 147 passed |
| Ruff | pass |
| MyPy strict | pass |
| Strict provider-schema audit | pass |
| V10 provider calls | 0 |
| Graph writes | 0 |

This is an engineering-quality result, not a scientific-quality result. No new
provider output exists for this frozen V10 implementation, so complete-event
recovery, unsupported-claim rate, role fidelity, and scientific precision are
all `NOT_MEASURED`. V10 cannot authorize graph persistence or trusted promotion.

## What The Split Establishes

- The provider proposes atomic anchors and categorical scientific content.
- Deterministic compilation owns exact spans, provenance, validation, and
  review-only routing.
- Validation has focused responsibilities for trigger and negation ownership,
  epistemic ownership, analysis ownership, category ownership, role topology,
  source context, anaphora, comparison order, and duplicate identities.
- The provider schema uses required nullable fields and closed objects suitable
  for strict structured output.
- Adversarial regressions cover the concrete bypasses found during review,
  including modifier laundering, coordinated-event collapse, context mismatch,
  anaphora inversion, and predicate-widening duplicates.

These checks show that known invalid shapes fail closed. They do not show that a
model will recover every scientifically complete event from an unseen source.

## Adversarial Decision

The final reviews disagreed at the decision boundary. A structural reviewer
returned `NO_GO` and supplied executable bypasses. A biomedical reviewer judged
the contract suitable for one diagnostic review-only call while still naming
residual scientific risks. The executable structural findings were converted
to regression tests and fixed. The stricter decision still controls: freeze the
baseline and do not spend another provider call merely to expand this contract.

Residual risks remain unmeasured for complex role inversions, unfamiliar
biomedical idioms, fronted comparisons, generic anaphora, cross-study context
assignment, and rationale claims. They are experiment questions now, not
reasons to keep growing the V10 validator.

## Stop Rule

V10 is immutable as the one-shot baseline. Any change creates a new candidate
identity. No V10 provider call or contract expansion is authorized by this
checkpoint. The next scientific action is the preregistered paired comparison
in `docs/validation/tg04-v10-vs-staged-agent-comparison-protocol.md`.
