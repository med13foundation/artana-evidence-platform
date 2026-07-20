# TG04 Valid Comparative-Degree V6.4 Checkpoint

## Decision

`EXPOSED_SCIENTIFIC_IMPROVEMENT_WITHOUT_SAFETY_REGRESSION`

V6.4 is the first fully valid live result on the exposed null-plus-positive
source that also received unanimous `COMPLETE_FRAME PASS` from two blind
source-only reviewers. This justifies moving to a preregistered untouched panel.
It is not itself a qualification result and remains review-only.

## Live evidence

- Model: `openai:gpt-5.6-sol`
- Reasoning effort: provider default
- Provider calls: `1`
- Provider receipt: `verified_live`
- Attempt lineage: `PASS`
- Schema validation: `PASS`
- Deterministic semantic validation: `PASS`
- Fallback or replay: `0`
- Graph writes: `0`
- Assertions: `2`
- Result SHA-256: `eee01820408155c2e34f861d19b63d1e4d990a09e9a936cf66fc1a20c3d12938`
- Contract adversarial suite: `58 passed`

## Scientific result

The ledger preserved all three preregistered propositions:

1. IL-4 did not differentially promote cell growth in FOXP3+ versus FOXP3-.
2. Both populations showed enhanced proliferation.
3. The enhancement was qualitatively similar across the populations.

It represented the third proposition as `SIMILAR_MAGNITUDE`, without asserting
formal statistical equivalence, an untreated baseline, significance, or
uncertainty absent from the source.

Both blind reviewers passed exact grounding, whole-claim completeness,
population cardinality, participant roles, direction, polarity, comparative
degree, null-positive separation, negative-leakage safety, and absence of
unsupported content.

Review packet SHA-256:
`5884a87a95661e0a153e04a9c154344b09f41862a343e891c9792e11526c0145`.

## Deterministic delta

The categorical reviewer outputs were converted to counts without asking an LLM
for a numeric score:

| Measure | V6.1 baseline | V6.4 candidate |
|---|---:|---:|
| Accepted live run | yes | yes |
| Required propositions recovered | 2 / 3 | 3 / 3 |
| Unsupported propositions | 0 | 0 |
| Safety failures | 0 | 0 |
| Whole complete frame | fail | pass |

The gain is the recovered comparative-degree proposition. Comparative null,
positive effect, roles, direction, polarity, unsupported-claim safety, and
negative-leakage safety did not regress.

Deterministic delta SHA-256:
`47270c736bfff0db0c5e6d14ca165e1c0e9584e54cd2c63271cd46906ac38fa8`.

## What changed

V6.4 accepts scientifically equivalent encodings while retaining structural
guards:

- explicit or role-compatible backward participant references;
- pooled or focal/comparator effect contexts only when nested comparison sides
  match the outer context sets exactly;
- qualitative similarity under a null relation only over exactly the same
  comparison sides;
- normalized directional semantics and cycle/conflict detection.

It still rejects forward and cross-role references, hidden contexts, mismatched
sides, contradictory relations/polarities/significance, unsupported null
polarity, fallback, replay, and graph writes.

## Next gate

Freeze an untouched three-source panel before inspecting candidate output. Run
V6.1 and V6.4 on identical sources, prompts, model, and provider-default
reasoning. Calculate whole-claim precision, valuable-claim recall, role/direction
/polarity fidelity, unsupported claims, leakage, and repeatability from
categorical reviews deterministically.

Do not modify V6.4 between panel cases. Stop the panel on any invalid run,
unsupported claim, negative leakage, unverified receipt, fallback, or graph
write. Trusted-graph promotion remains prohibited until all objective thresholds
pass across three independent untouched runs.
