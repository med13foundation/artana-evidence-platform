# TG-04 Fresh Hidden Discovery

Date: 2026-07-18

## Decision

**STOP AND RECALIBRATE THE SCIENTIFIC REPRESENTATION CONTRACT.** The first
fresh, previously unexposed source unit completed exactly one Luna extraction
and one independent Luna verification. Both calls were source-bound, both live
provider receipts were verified, and no fallback or transport-identity failure
occurred. The extractor returned two specific findings and the verifier judged
both `ENTAILED`.

The pre-registered gate nevertheless failed. Its expected target was a flattened
`INCREASE` or `POSITIVE_REGULATION` event with relation cue exactly `enhanced`.
The extractor represented the source as a `LOCALIZATION` event whose exact cue
was `enhanced nuclear translocation`. It also preserved the cause as the fuller
source span `tethering by P-selectin`, rather than the exact surface
`P-selectin`. These are not generic outputs or contradictions. They expose a
representation mismatch between a directional modification of an event and the
current flat target contract.

The failed pre-registered decision remains failed. This report does not alter
the gate after observing the answer, award benchmark credit, complete the
literature-review stage, prove scientific readiness, or authorize persistence.

## Frozen Experiment

- Harness commit: `f45e20dd0facef3eebce0b12c3c9b9bd30ebdbfd`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-fresh-hidden-discovery-luna-01`
- Agent calls: extractor `1`, verifier `1`
- Biomedical fallback: `0`
- Prior merged PR: `#176`
- Authorizing report SHA-256:
  `61b5ca507a26b6cfe20f02c28b29b71ac09ffcff2a58c056d149a18286823978`
- Frozen case: `bionlp-ge-2011:PMID-7537762`
- Frozen source unit:
  `source-unit-20ebe2019ebdd3e3651c8886f9f60c7d171883555237b2df667a47f90bab35f0`
- Source-unit input SHA-256:
  `517b4ab2c503e65ce9d1b11f6b77e2361215f642cd0c54eec6abbb785a88c905`
- Source SHA-256:
  `363b49c8071440e28f2d89c86814e1c9e370ffd27d0cc08969703eadea0922e4`
- Local expert events visible to the run: `0`
- Freshness scope: tracked TG-04 live reports through merged PR `#176`
- Live artifact:
  `/tmp/artana-tg04/fresh-hidden-discovery-2026-07-18/luna-r1.json`
- Live artifact SHA-256:
  `b547b677af93b36dc3f3a5c950f913b918d54cbfd9ed63c26c2ccc6fa07d5ffc`
- Embedded report SHA-256:
  `5c0062e24c67a9748bf9b6d44d4d545cc525bb8d0f1ace09076eb24da2b6f4b7`

The source case and unit identity were absent from the tracked report and local
artifact registry before execution. The output path was create-once and the run
was not repeated. The embedded digest was independently recomputed and matched.
This is a bounded freshness claim, not proof that the unit never appeared in any
untracked external context.

## Source Unit

The source states that P-selectin tethering enhanced nuclear translocation of
NF-kappa B and identifies NF-kappa B as required for expression of MCP-1,
TNF-alpha, and other immediate-early genes.

The first extracted event was:

- category: `FINDING`;
- type: `LOCALIZATION`;
- cue: `enhanced nuclear translocation`;
- polarity: `SUPPORT`;
- epistemic status: `ASSERTED`;
- cause: `tethering by P-selectin`;
- theme: `nuclear factor-kappa B (NF-kappa B)`.

The second extracted event was:

- category: `FINDING`;
- type: `REGULATION`;
- cue: `required for expression`;
- polarity: `SUPPORT`;
- epistemic status: `ASSERTED`;
- agent: `nuclear factor-kappa B (NF-kappa B)`;
- theme: `expression of MCP-1, TNF-alpha, and other immediate-early genes`.

The verifier returned `CANDIDATES_COMPLETE` and one `ENTAILED` decision for each
candidate, with exact source evidence and explicit falsification conditions.
This is materially specific behavior, not a generic relationship summary.

## Deterministic Result

The following requirements passed:

- agent execution complete;
- extractor and verifier both classified the unit as a `FINDING`;
- extractor and verifier categories agreed;
- two source-bound candidates were within the pre-registered inventory bound;
- both candidates were independently entailed;
- generic event-role count was zero;
- binding rejection count was zero;
- model-authored transport identity field count was zero;
- audit identity mismatch count was zero;
- invalid agent output count was zero;
- two distinct provider responses and two verified receipts were present;
- fallback count was zero.

The following target requirements failed:

- `one_specific_target_event`;
- `target_direction_preserved`;
- `target_polarity_asserted`;
- `target_arguments_preserved`.

The latter three failed transitively because target selection required
`relation_cue_span == "enhanced"`; no event was selected after the extractor
returned the more complete cue `enhanced nuclear translocation`. Even if cue
selection had accepted that span, the pre-registered type set excluded
`LOCALIZATION`, and exact argument matching excluded `tethering by P-selectin`.

## Root Cause

The sentence describes positive regulation of a localization event. The current
flat event representation forces a choice:

1. use `LOCALIZATION`, preserving what happened but leaving positive direction
   only in free source text; or
2. use `INCREASE` or `POSITIVE_REGULATION`, preserving direction but flattening
   the regulated localization event into an argument span.

The gate pre-selected the second projection while the agent selected the first.
Exact cue and exact argument equality then turned a plausible alternate frame
into a false target miss. This repeats the class of representation issue already
identified by the prior adjudication work, although this fresh result cannot be
retroactively passed.

There is also a genuine scientific typing weakness that the failed target gate
did not measure. In the second event, the full process span `expression of
MCP-1, TNF-alpha, and other immediate-early genes` was assigned the base role
`GENE_OR_PROTEIN`. The relation is textually entailed, but the argument's entity
type is not precise enough for trusted graph projection. The independent
verifier checked source entailment, not ontology-type correctness.

The combined diagnosis is therefore:

- extraction specificity: promising on this one unit;
- source grounding and independent entailment: passed;
- transport, identity, and receipts: passed;
- event decomposition and typed graph projection: unresolved;
- scientific qualification and persistence: blocked.

## Controlled Stop

The pre-registered protocol allowed source-and-literature validation only after
the deterministic fresh gate passed. Because it did not pass, no internet or
literature qualification was performed. Doing that work now and counting it as
part of this experiment would change the protocol after seeing the result.

This one convenience sample also cannot estimate precision, recall,
repeatability, novelty detection, or expert agreement.

## Next Minimal Step

Do not run another fresh unit yet. First freeze a representation-invariant
scientific comparison contract that separates:

- the core event (`LOCALIZATION`);
- its directional modifier (`POSITIVE` or `NEGATIVE`);
- the regulating cause or condition;
- typed event participants;
- exact supporting source spans.

The contract must accept semantically equivalent source-explicit spans such as
`P-selectin` and `tethering by P-selectin` without accepting unrelated or generic
arguments. It must also validate argument entity types separately from textual
entailment. The next experiment should replay this artifact only as a diagnostic
test of that contract, then evaluate a different pre-registered fresh unit
exactly once. The replay must receive no discovery or benchmark credit.

## Validation

- `42` focused fresh-unit, transport, finite-unit, and discovery tests passed.
- `113` broader TG-04 claim-event and provider-receipt tests passed.
- Ruff passed on every changed file.
- Mypy passed for all `612` Evidence API source files.
- The architecture structure ratchet passed.
- `make service-checks` passed before the frozen run, including fresh PostgreSQL
  migrations and the complete runnable suite, at `87.47%` measured coverage.
- Commit hooks passed graph/evidence lint and type checks.
