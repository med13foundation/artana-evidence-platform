# TG-04 Contract-Recalibration Pilot

Date: 2026-07-17

## Decision

**STOP: the scientific gate failed.** The contract recalibration removed the
procedural false positive, but it did not recover a bound scientific event. This
four-case run is diagnostic only and does not support trusted-graph promotion.

## Frozen Comparison

- Model: `openai:gpt-5.6-luna`
- Branch: `alvaro/tg04-contract-recalibration`
- Commit: `6aeac4f29fd7faf29712450a69ffb08507698627`
- Cases: the same four frozen TG-04 cases used by the baseline run
- Execution: audited Artana agent path; deterministic biomedical fallback disabled
- Baseline artifact: `/tmp/artana-tg04/pilot-2026-07-17/luna-stage1-r1.json`
- Recalibrated artifact: `/tmp/artana-tg04/recalibration-2026-07-17/luna-r1.json`
- Recalibrated artifact SHA-256:
  `849a68e8e22d8bbca0aad36682331fffa908cc90b35c32e4ca9f2ca9872d174c`
- Inner Artana report SHA-256:
  `5564acfcfb151c7f6414a016ce474671b604cd0d1d08bcf300e882a635088601`
  (verified after excluding the external diagnostic-protocol annotation)

## Before And After

| Measure | Baseline | Recalibrated | Interpretation |
| --- | ---: | ---: | --- |
| Executable cases | 1/4 | 1/4 | No execution improvement |
| Bound scientific cases | 0/3 | 0/3 | Scientific blocker remains |
| True-negative methods control | False positive | Correct `NO_OUTPUT` | Meaningful safety improvement |
| Whole-event recall | 0/4 | 0/4 | No scientific recovery |
| Whole-event precision | 0/2 | No predictions | Cannot claim precision improvement |
| Fallback count | 0 | 0 | Agent-first invariant preserved |
| Invalid agent outputs | 6 | 6 | Batch rejection remains the blocker |
| Epistemic escalation | 0/2 | 0/2 | No observed escalation |
| Provider receipt verification | 0/8 | 0/8 | Separate custody issue remains |

## What Improved

1. Procedure and measurement statements now receive categorical kinds and are
   preserved for audit without entering relation framing.
2. Polarity and epistemic status are independent. Asserted null results and
   provisional hypotheses no longer require contradictory category pairs.
3. Anchor context may extend outside a claim while every selected mention must
   remain inside the claim itself.
4. Production and TG-04 use the same deterministic claim-kind partition, so the
   benchmark cannot count an item that production would exclude.
5. Completeness review fails closed when it proposes a non-relation item as a
   missing scientific claim.
6. Excluded recovery descriptors remain available as structured audit records
   with a categorical disposition and rationale.

## Root Cause Evidence

The remaining failure is primarily an **all-or-nothing semantic binding
boundary**, not evidence that Luna found no useful claims. Each inventory batch
is discarded when any one claim has an invalid exact span or mention anchor.

| Case | Retry claims | Individually valid | Valid relation-eligible | Batch result |
| --- | ---: | ---: | ---: | --- |
| `PMID-9361029` | 11 | 8 | 7 | Entire batch rejected |
| `PMC-2222968-03-Results-02` | 16 | 12 | 11 | Entire batch rejected |
| `PMC-2222968-05-Results-04` | 22 | 14 | 13 | Entire batch rejected |

Observed item-level defects were categorical and source-checkable:

- anchor context did not identify one occurrence;
- an anchor selected a mention outside the claim span;
- an anchor omitted the canonical argument span;
- an agent used an abbreviated span containing `...` that was not verbatim source.

The long result case still contained individually valid claims for the main
IL-4/FOXP3 inhibition result, null growth effect, negative findings, and the
GATA3 hypothesis. Artana discarded these valid items together with the invalid
ones, preventing framing and deterministic scoring.

## Model Conclusion

This pilot does **not** establish that Luna is strong enough, but it also does
not support replacing Luna yet. The pipeline currently hides valid model output
behind batch-level rejection. A stronger model or a blanket second Luna review
would add cost without fixing that owning boundary.

The one methods control suggests the new `claim_kind` contract can work, but one
case is not sufficient to trust the model's self-classification. Independent
claim-kind adjudication remains a later experiment after valid items can survive
the inventory boundary.

## Next Experiment

Implement item-level fail-closed inventory binding:

1. Parse the agent batch under the governed schema.
2. Bind each claim independently using deterministic source checks.
3. Preserve accepted and rejected items with categorical dispositions and exact
   validation evidence.
4. Send the accepted inventory plus rejected-item evidence to the existing
   independent completeness/recovery agents.
5. Frame only accepted relation-eligible items. Never infer or repair biomedical
   meaning deterministically.
6. Rerun these same four cases once. Proceed only if all four are executable,
   the methods control remains empty, at least one gold event is recovered, and
   fallback remains zero.

Only after that gate passes should the study compare Luna with a stronger model
or add an independent source-only claim-kind adjudicator. Cache keys should also
be hardened to include governed schema and complete semantic-input hashes before
repeatability qualification, although unique run namespaces and bumped prompt
versions prevented cache reuse in this pilot.

## Validation

- Two independent Luna adversarial code reviews were completed.
- Reviewer findings that could invalidate this pilot were fixed before execution.
- Focused source-binding, claim-routing, schema-governance, and TG-04 regressions
  passed.
- `make artana-evidence-api-service-checks` passed, including lint, mypy over 605
  source files, service boundaries, OpenAPI, agent-output registry, architecture
  checks, fresh PostgreSQL migrations, and the complete Evidence API test suite.
