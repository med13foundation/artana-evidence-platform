# Source-General Claim Verification Checkpoint

Date: 2026-07-20

## Decision

The bounded claim-verification loop is implemented as an opt-in scientific
qualification experiment. It is not enabled by default, it makes no fallback
calls, and every terminal outcome remains review-only. Untouched-source testing
and trusted-graph promotion remain blocked.

Feature-disabled extraction retains its existing trust behavior. The new
qualification floor applies only when verification-experiment lineage is
present, so the bounded experiment does not silently redefine legacy claims.

## Implemented Control Path

Each single framed claim now supports this bounded path:

```text
FRAMED
  -> blinded source-only categorical verification
  -> VERIFIED_UNREPAIRED, or
  -> one typed axis-limited repair
  -> fresh blinded reverification
  -> VERIFIED_AFTER_REPAIR, REVIEW_ONLY, or INVALID_VERIFICATION
```

The implementation separates responsibilities:

- `claim_falsification.py` owns the blinded source-only agent invocation.
- `claim_frames/falsification.py` owns deterministic hashes, exact spans,
  event-local scope, categorical consistency, repair authorization, and patch
  application.
- `claim_repair.py` owns one typed semantic patch invocation.
- `verification_budget.py` owns document-level call, repair, token, latency,
  cost, and receipt accounting.
- `verification_loop.py` owns the finite state machine and terminal lineage.

Deterministic code does not infer biomedical meaning. It rejects invalid
spans, inconsistent categories, unauthorized fields, changed event identity,
changed primary participants, unsupported evidence, and incomplete receipts.

## Scientific Safety Invariants

- `CONTRADICTED`, `INSUFFICIENT`, and `ABSTAIN` are not repairable.
- Wrong core events, missing primary participants, unsupported evidence,
  ambiguous scope, and new-event discovery are not repairable.
- Repair may change only fields authorized by the verifier's `failure_axes`.
- Direction repair may only swap the two existing endpoints.
- Participant repair cannot add, remove, merge, or change primary participants.
- Reverification is a fresh invocation and records whether it used the same
  configured model or a different configured model.
- A fresh same-model call is labeled `SAME_MODEL_FRESH_CALL`, never independent.
- A fresh different-model call is labeled
  `DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED`; it is not described as
  model-independent without provider-confirmed model identity.
- A claim can be repaired at most once.
- Budget exhaustion preserves the claim as review-only without fallback.
- `VERIFIED_UNREPAIRED` and `VERIFIED_AFTER_REPAIR` are qualification labels,
  not trusted-graph admission labels.
- Candidate, proposal, trust-ladder, and promotion boundaries reject experiment
  outcomes until scientific qualification is explicitly complete.

## Statistical Semantics

Observed statistical evidence and author interpretation are independent agent
categories:

```text
observed_statistical_evidence:
  P_VALUE | CONFIDENCE_INTERVAL | EFFECT_ESTIMATE | NONE

author_statistical_claim:
  SIGNIFICANT | NOT_SIGNIFICANT | NOT_CLAIMED
```

Therefore `P = 0.08` can be represented as `P_VALUE / NOT_CLAIMED`. Deterministic
code does not convert the numeric value into a significance conclusion.

## Exposed 31-Scope Corpus

The preserved exposed corpus contains 31 adjudicated discovery scopes across
five sources:

| Family | Scopes |
| --- | ---: |
| Clinical | 24 |
| Genetic | 3 |
| Molecular | 4 |
| Total | 31 |

The corpus contains source passages and triggers. It does not contain 31
production `ClaimFrame` outputs, expected participant-role frames, labeled
malformed claims, verifier verdicts, or repair expectations. The preserved Sol
result of 29/31 is discovery recall, not framing recall or verifier precision.

That means the requested scientific rates cannot be calculated honestly from
the current offline corpus:

| Requested metric | Current status |
| --- | --- |
| Framing precision before verification | Unavailable: no 31 emitted-frame set |
| Framing recall before verification | Unavailable: discovery scopes are not complete claim frames |
| Verifier acceptance/rejection/abstention | Unavailable without a provider execution |
| Verifier false-pass rate | Unavailable: no labeled incorrect-claim denominator |
| Repair attempt/success rate | Unavailable without framed failures and provider execution |
| Quality before versus after repair | Unavailable without adjudicated complete frames |
| Unsupported claims and contradictions | Unavailable at framed-claim level |
| New calls/tokens/latency/cost | 0 calls / 0 tokens / 0 seconds / USD 0 |

Scripted fixtures prove state transitions and safety controls. They do not prove
that an agent verifier makes correct scientific judgments.

## Offline Test Evidence

Focused regressions cover:

- wrong and merged participant roles;
- reversed comparison and direction;
- negation/polarity and uncertainty;
- nested or newly required events;
- `P = 0.08 -> P_VALUE / NOT_CLAIMED`;
- explicit author significance categories;
- unsupported, invented, cross-event, and ambiguous evidence;
- core-event and primary-participant protection;
- unauthorized repair fields and repair laundering;
- failed reverification and exactly one repair;
- same-model versus different-model provenance;
- budget exhaustion and complete usage receipts;
- original and repaired claim hashes reported separately;
- complete invocation lineage; and
- verified/repaired qualification terminals blocked from promotion.

The existing extraction, claim-frame, draft, trust-ladder, and promotion suites
also run to protect feature-disabled behavior.

Final repository validation passed `make artana-evidence-api-service-checks`,
including lint, type checking across 619 source files, boundary and contract
checks, architecture checks, migrations, and the complete database-backed API
test suite. The focused source-verification file contains 35 passing adversarial
regressions.

Three independent adversarial passes targeted false acceptance, cross-event
evidence, repair laundering, missing context, replayed verification, budget
accounting, and lineage bypasses. The findings were converted into regressions;
the final two reviewers returned `GO` with no remaining actionable findings.

## Required Next Scientific Step

Before a provider comparison, extend the exposed corpus with an adjudicated
claim packet per scope:

1. Complete expected claim frame and primary participants.
2. Expected direction, comparison, polarity, uncertainty, statistics, and
   material modifiers.
3. A labeled malformed-claim set for false-pass measurement.
4. Explicit repairable and non-repairable axes.

Then run one preregistered exposed-source provider experiment and calculate all
rates deterministically. Advance to one untouched canary only if verification
reduces scientific errors without reducing valuable-event recall or accepting
unsupported repaired claims.

Current terminal decision: `CONTROL_PATH_READY_SCIENTIFIC_EVALUATION_BLOCKED`.
