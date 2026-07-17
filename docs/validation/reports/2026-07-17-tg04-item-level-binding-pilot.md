# TG-04 Item-Level Binding Pilot

Date: 2026-07-17

## Decision

**STOP: the scientific gate still fails.** Item-level fail-closed binding fixed
the batch-collapse defect, but the reviewed inventory did not converge to
`COMPLETE` for any of the three scientific cases. Artana therefore emitted no
scored events from those cases.

This is a real safety and execution improvement. It is not evidence of improved
scientific accuracy or trusted-graph readiness.

## Frozen Experiment

- Model: `openai:gpt-5.6-luna`
- Branch: `alvaro/tg04-item-level-binding`
- Final commit: `96e9f572d1b3f5f798aeba47fc50e4062af194b1`
- Cases: the same four frozen TG-04 diagnostic cases used by the preceding pilot
- Execution: audited Artana agent path with deterministic biomedical fallback disabled
- Final artifact: `/tmp/artana-tg04/item-binding-2026-07-17/luna-r2.json`
- Artifact SHA-256: `3761f2fb60c2da4e654a2d40bea456a764d56c7e65848420051cf13ab6ff8688`
- Inner Artana report SHA-256:
  `d0a7f985e478ba3f75d1fc0198e02e836f07626838373923cb1ffd79208a7aaf`
  (verified after excluding the external diagnostic-protocol annotation)

## Before And After

| Measure | Contract recalibration | Item-level binding | Interpretation |
| --- | ---: | ---: | --- |
| Operationally complete cases | 1/4 | 1/4 | Scientific cases still fail closed |
| Bound scientific cases | 0/3 | 0/3 | No scientific recovery yet |
| Whole-event recall | 0/4 | 0/4 | No improvement established |
| Schema or semantic invalid attempts | 6 | 0 | Batch-collapse failure removed |
| Audited item-binding rejections | unavailable | 17 | Item failures are now visible and source-bound |
| True-negative methods control | correct `NO_OUTPUT` | correct `NO_OUTPUT` | Safety preserved |
| Fallback count | 0 | 0 | Agent-first invariant preserved |
| Provider receipts verified live | 0/8 | 0/22 | Separate custody blocker remains |

## What The Change Proved

1. One malformed claim no longer discards valid siblings from the same agent batch.
2. Empty inventory and all-rejected inventory are distinct audited states.
3. Rejected claim content never enters completeness prompts. The agent sees only
   opaque rejection IDs, batch positions, and categorical dispositions.
4. Every rejection remains linked to its provider invocation and raw payload.
5. Completeness descriptors are bound item by item. Duplicate or malformed
   descriptors cannot erase valid novel siblings.
6. Excluded and abstained recovery descriptors cannot enter scored predictions.
7. A semantically incomplete inventory cannot emit scored benchmark events.

## Adversarial Correction During The Pilot

The first run on commit `777a2a8e1172ca0101c19f575232130e832fa700`
exposed a benchmark-adapter defect. It scored 39 raw claims even though all three
scientific cases were marked `semantic_incomplete`. Those outputs had zero
whole-event matches out of 20 predictions and 20/20 negative or null leakage.

That run is not a scientific result. The adapter was fixed to require semantic
completeness before scoring, and the frozen four cases were rerun once on the
final commit. The corrected report contains zero scored events for incomplete
inventories.

## Remaining Scientific Blocker

The agent recovery path now executes, but one recovery round does not reach a
complete inventory:

| Scientific case | Initial completeness | Recovered descriptors | Final confirmation |
| --- | ---: | ---: | ---: |
| `PMID-9361029` | 2 missing | 1 recovered | 1 still missing |
| `PMC-2222968-03-Results-02` | 5 missing | 5 recovered | 2 still missing |
| `PMC-2222968-05-Results-04` | 6 missing | 5 recovered | 1 still missing |

The methods control reached `COMPLETE` and produced no scientific event.

The evidence does not yet show that Luna is too weak. Luna produced many
source-bindable claims and categorical recovery decisions. The current blocker
is that completeness review discovers additional claims after the single
recovery round, so the workflow stops before qualification.

## Next Controlled Experiment

Test a bounded completeness fixpoint without changing the model or ontology:

1. Recover only newly identified, source-bound missing descriptors.
2. Confirm the exact accepted, excluded, rejected, and unresolved state after
   each round.
3. Deduplicate by deterministic inventory identity.
4. Stop on `COMPLETE`, no new identities, any abstention, or a strict maximum of
   two recovery rounds.
5. Preserve every categorical decision and provider receipt.
6. Rerun these same four cases once.

Proceed only if all four cases complete, the methods control remains empty, at
least one gold whole event is recovered, fallback remains zero, and the accepted
claims do not increase negative or null leakage. If the bounded second round
does not converge, stop and redesign the completeness task or ontology before
testing a stronger model.

## Validation

- Two independent adversarial agent reviews were performed.
- All actionable findings from the first final-diff review were fixed.
- Focused source-binding, inventory, strict-discovery, audit-replay, and TG-04
  regressions passed.
- `make artana-evidence-api-service-checks` passed, including lint, type checks,
  service boundaries, OpenAPI, agent-output validation, architecture checks,
  fresh PostgreSQL migrations, and the complete Evidence API test suite.
