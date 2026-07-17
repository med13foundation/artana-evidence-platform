# TG-04 Bounded Convergence Pilot

Date: 2026-07-17

## Decision

**STOP AND REDESIGN THE COMPLETENESS TASK.** The bounded second recovery round
improved operational convergence, but it did not recover a scoreable gold event.
The only gold qualification case remained semantically incomplete after the
strict two-round maximum. Whole-event recall therefore remained `0/4`.

Do not add a third recovery round, an adversarial completeness judge, or a
stronger model to this same open-ended task. The current evidence says that
"find every distinct claim in this source" is not reaching a stable finite
inventory. It does not establish that Luna is too weak.

## Frozen Experiment

- Model: `openai:gpt-5.6-luna`
- Commit: `1b614570f40fd28ca06d50fb1b51a6dd1722cc99`
- Cases: the same four frozen TG-04 diagnostic cases used by the item-binding pilot
- Run count: one preregistered nonqualifying diagnostic
- Agent path: audited Artana extraction with deterministic biomedical fallback disabled
- Changed variable: at most two source-bound completeness recovery rounds
- Unchanged variables: model, fixture, ontology, scorer, source text, and case selection
- Artifact: `/tmp/artana-tg04/bounded-convergence-2026-07-17/luna-r1.json`
- Artifact SHA-256: `b7ef7db8ae4e6584a0bbbfa4fda30994098d9a2d7be7dfa901fbe268d799dde9`
- Inner report SHA-256: `9fcee62095d87cb06e11762768a055da54a3eaa68c3b378ab7286712df4daa57`

The inner report digest was recomputed after excluding the external diagnostic
protocol annotation and matched exactly. Independent deterministic replay bound
all 27 executed provider attempts, every convergence transition, and all four
case outcomes to the frozen sources.

## Result

| Case | Benchmark status | Outcome | Rounds | Stop reason | Scored events | Correct |
| --- | --- | --- | ---: | --- | ---: | --- |
| `PMID-9361029` | representability stress | `BOUND_OUTPUT` | 1 | `CONFIRMED_COMPLETE` | 8 | no |
| `PMC-2222968-03-Results-02` | representability stress | `BOUND_OUTPUT` | 2 | `CONFIRMED_COMPLETE` | 15 | no |
| `PMC-2222968-05-Results-04` | event gold, 4 events | `SEMANTICALLY_INCOMPLETE` | 2 | `MAX_RECOVERY_ROUNDS` | 0 | no |
| `PMC-2222968-15-Materials_and_Methods-07` | true no-event control | `NO_OUTPUT` | 0 | `INITIAL_COMPLETE` | 0 | yes |

Deterministic totals:

- Valid terminal cases: `3/4`
- Gold qualification cases complete: `0/1`
- Whole-event recall: `0/4`
- Whole-event precision: unavailable because the gold case emitted no scored events
- True-negative control false positives: `0/1`
- Fallback count: `0`
- Inventory binding rejections: `12`
- Invalid agent attempts: `1`, confined to a representability-stress case and repaired through the audited schema-retry path
- Provider receipts: `0/27` live verified; status `mismatched`

The provider-receipt mismatch remains a separate custody blocker. It does not
change the negative scientific result because the stored provider IDs, raw
payloads, prompts, source hashes, and deterministic replay were internally
consistent, but no future qualification can pass until live receipt retrieval
also verifies.

## What Improved

1. Two cases that previously stopped semantically incomplete reached a bounded
   confirmed inventory.
2. Honest semantic non-convergence is now `SEMANTICALLY_INCOMPLETE`, not falsely
   labeled malformed or unbindable model output.
3. Recovery is capped at two rounds and stops on completion, abstention, no new
   deterministic identity, or the cap.
4. Agent descriptor order cannot change inventory hashes, recovery order, or
   downstream deterministic scoring.
5. Every round records its parent completeness state, categorical decisions,
   accepted identities, exclusions, and unresolved identities.
6. Audit replay rejects orphan, reordered, detached, or fabricated convergence
   evidence.
7. The methods control stayed empty and deterministic biomedical fallback stayed
   unused.

These are meaningful safety and execution gains. They are not scientific
qualification.

## Root-Cause Hypothesis

The failing gold case did make progress: round one accepted seven new claim
identities and round two accepted one more. The final completeness review still
introduced another missing identity. That pattern is consistent with an
open-world decomposition problem: a reviewer can continually split, re-scope,
or restate source content as another distinct claim.

The benchmark asks for a finite set of typed biomedical events. The current
completeness question asks for all scientifically meaningful claims in a long
source. Those are not the same task. More review rounds or a second reviewer can
increase decomposition variance without increasing exact whole-event recovery.

The two completed representability-stress cases produced 8 and 15 claims. Those
cases are intentionally excluded from scientific qualification, but the volume
supports the same concern: reaching `COMPLETE` does not by itself establish that
the inventory is specific, valuable, or aligned with the benchmark event unit.

## Next Scientific Experiment

Replace open-ended inventory completeness with a finite source-unit event audit:

1. Deterministically enumerate bounded source units only as locations, without
   assigning biomedical meaning.
2. For each unit, an extraction agent returns a categorical decision:
   `EXPLICIT_EVENT`, `NO_EVENT`, or `ABSTAIN`, with exact trigger and argument
   spans for explicit events.
3. A separate source-only verifier agent returns `ENTAILED`, `CONTRADICTED`,
   `INSUFFICIENT`, or `ABSTAIN`, plus exact evidence spans and a falsification
   explanation. It must not produce a numeric score.
4. Deterministic code validates spans, computes all metrics, and blocks any
   incomplete, contradicted, or unverified event from scoring or persistence.
5. Run the same four cases once with Luna. Compare a stronger model only after
   the task contract is frozen, so a model change is not confused with a task
   redesign.

Proceed to a larger frozen benchmark only if the gold case produces at least one
exact whole-event match, the methods control remains empty, fallback remains
zero, epistemic escalation remains zero, every attempt replays, and provider
receipts verify live. If the redesigned finite task still recovers no whole
event, stop model-only extraction and evaluate an expert-seeded or hybrid
candidate workflow.

## Validation

- Focused convergence, order-permutation, abstention, no-progress, schema-repair,
  semantic-incomplete, and replay-forgery regressions passed.
- Strict mypy passed for the Evidence API and changed TG-04 evaluation scripts.
- `make artana-evidence-api-service-checks` passed, including lint, contracts,
  architecture checks, fresh PostgreSQL migrations, and the complete Evidence
  API test suite.
- The completed branch was clean before the live run and was bound to commit
  `1b614570f40fd28ca06d50fb1b51a6dd1722cc99`.
