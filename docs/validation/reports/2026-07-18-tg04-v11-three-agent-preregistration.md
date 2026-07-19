# TG04 V11 Three-Agent Preregistration

## Purpose

V11 tests one specific root-cause hypothesis from the failed V10 scientific run:
source interpretation and graph projection were overloaded in one agent call,
and the verifier repeated that framing instead of falsifying it.

V11 separates those responsibilities into three live Luna calls:

1. source-semantic extraction;
2. `DIRECT`, `NESTED`, or `ABSTAIN` structure normalization;
3. role-separated categorical review of both structures against the source.

This is a one-unit, non-qualifying diagnostic. A pass authorizes only a small
replication set. It never authorizes graph persistence or trusted-graph status.

## Frozen Source

The content-blind selector uses the immutable V10 report hash
`a1347ca7588d7b1b83629f74406cadb294f65c091659daa64011b1d815018005`
as its seed, excludes every V1-V10 document, and selects the lowest SHA-256 rank
from the remaining `NEGATED_RESULT_GRAPH` candidates. Exactly one candidate
remains, so no semantic cherry-picking is possible.

- Case: `bionlp-ge-2011-holdout:PMC-2806624-08-MATERIALS_AND_METHODS-01`
- Unit: `source-unit-7c8d867e63ba86da5d69978529ab5ff25686efd7035d2ba50ac899cc8f89743d`
- Unit index: `141`
- Source offsets: `19662:19960`
- Selection rank: `ca698d8895284c653b4239293c028e33808352f023025a5207ac86294f7f5418`
- Source SHA-256: `e8516818fb002201c7ca53c487d114ceb71fae1f35bc4d972977e5e181af37b9`
- Input SHA-256: `d5242f5c0aae5bffc5874c486c5ef7d933a86c95bd7a9445ed32a80895e83b2f`

> Fig. S6 shows that endogenous IL-4 and IFN-gamma do not effect Foxp3
> expression in naive CD4+ T cells of CbfbF/F CD4-cre and CbfbF/F control
> mice, which were stimulated with anti-CD3 and anti-CD28 mAbs, IL-2 and
> TGF-beta in the absence or presence of anti-IL-4 and anti-IFN-gamma
> neutralizing mAbs.

The BioNLP standoff source contains two negated `REGULATION` events, caused by
IL-4 and IFN-gamma, that share one Foxp3 `Gene_expression` target.

## Acceptable Scientific Families

V11 accepts exactly one complete family per run. Partial or mixed families
receive no inventory credit.

1. `BIONLP_EXPERT`: two null `REGULATION` controllers, one for IL-4 and one for
   IFN-gamma, linked to one controlled Foxp3 `EXPRESSION` event.
2. `SOURCE_VALID_ALTERNATIVE`: one joint direct `NO_EFFECT` event with both
   agents, Foxp3 theme, Foxp3-expression outcome, and every source context.
3. `SOURCE_VALID_ALTERNATIVE`: two direct `NO_EFFECT` events, one per agent,
   with the shared outcome and complete context.

The population, both genotypes, anti-CD3/CD28, IL-2, TGF-beta, neutralization
condition, and neutralizing antibodies scope every measured event, including
the controlled expression target. `endogenous` qualifies the IL-4 and IFN-gamma
regulation or direct no-effect events.

Flat context arguments are insufficient for this source. The normalization must
also preserve two crossed context dimensions: the alternative CD4-cre/control
genotype levels and the absence/presence neutralizing-antibody treatment levels.
This prevents mutually exclusive experimental arms from being interpreted as
simultaneous conditions.

The source-equivalent cues `effect`, `not effect`, and `do not effect` are
pre-registered separately from scientific structure. Surface variation cannot
hide material role loss or create benchmark failure after the result is seen.

- Expert graph SHA-256: `a77aa47edb35008c9149e9ab92bc0f01dce32510c92e1adb4b2bbca8df310a15`
- Projection set SHA-256: `e74d4cce878d1e6894bbd82345f438df437bddfbe8663bb26f91b161ce687f1a`
- Context-dimension SHA-256: `76087eea2fbd96c919a81ee7baea486291b2501d3f96f9a08f736ffd3158874a`

## Agent Isolation

All three calls use `openai:gpt-5.6-luna`. No retry or fallback is permitted.
The roles are operationally separated but are not independent-model evidence;
correlated model-family errors remain possible. The reviewer can never override
the frozen expert projection gate.

The extractor uses the unchanged V10 prompt and sees only the source. This keeps
V11 from teaching the extractor the selected case's expected solution. The
normalizer sees the source, original
structured output, and categorical binding failures. The reviewer sees the
source and stripped original/normalized structures, but not earlier reasoning.
No agent sees expert gold, projection IDs, prior decisions, numeric scores, or
promotion recommendations.

Call 2 is hash-bound to Call 1's raw provider payload. Call 3 is hash-bound to
both prior raw payloads. All three raw outputs remain independently auditable.
Finalization reconstructs both dependency keys and all provider-bound prompts
from the reservation-derived execution namespace. Output-schema identity is
required for every completed provider response.

## Categorical Review

The reviewer must cover these axes in fixed order:

1. event inventory;
2. event type;
3. direction;
4. polarity;
5. participants;
6. causal roles;
7. context scope;
8. assertion and epistemic scope;
9. controlled-event topology;
10. referent resolution.

Each result is categorical and accompanied by source evidence, reasoning, and
a falsification condition. The agent cannot return a confidence score,
probability, quality grade, GO decision, or promotion decision.
`NOT_APPLICABLE` and `ABSTAIN` both count as unresolved for this ten-axis trial;
neither can silently satisfy the adversarial-review gate.

## Deterministic Measures

Code calculates all numeric values from categorical output:

- normalization mapping coverage;
- frozen-projection event recall;
- normalized-event precision;
- scientific-loss count;
- unsupported-addition count;
- unresolved-axis count;
- recovered projection count;
- unmatched normalized candidate count;
- exact provider-call and receipt counts.

The gate uses exact counts, not model-generated scores or rounded thresholds.
Normalization mapping coverage is reported separately from scientific recall.
Frozen-projection event recall is computed against the sealed acceptable event
families, never against the extractor's own inventory.

## Stop/Go Outcomes

- `STOP_WORKFLOW_INVALID`: wrong call topology, schema or semantic failure,
  receipt failure, identity drift, retry, fallback, or missing raw output.
- `STOP_REMEDY_FALSIFIED`: any scientific loss, unsupported addition,
  contradiction, mixed family, or material cue mismatch.
- `STOP_UNRESOLVED`: the normalizer or reviewer abstains. This is not counted as
  scientific loss, but it cannot pass.
- `STOP_EXTERNAL_ADJUDICATION_REQUIRED`: same-model review calls an unmatched
  claim source-entailed, but the frozen expert projections do not establish it.
  The claim remains preserved in the report and cannot qualify or persist until
  an independent source-only adjudication resolves the disagreement.
- `GO_TO_SMALL_REPLICATION`: exactly three verified calls, zero loss, zero
  additions, zero unresolved axes, every normalized event entailed, and exactly
  one complete acceptable family recovered.

## Qualification Boundary

Even `GO_TO_SMALL_REPLICATION` is not scientific qualification. The same frozen
implementation must pass two additional content-blind fresh units before this
narrow event class has minimum repeatability evidence. Any failure stops that
sequence and starts a new root-cause cycle.

If V11 fails for representation loss, the next experiment must compare a
stronger model under this identical frozen protocol or reconsider the ontology.
Adding more prompt text, deterministic biomedical repair, or self-review inside
one call is not an accepted remediation.

## Pre-Execution Status

- V11 source selected and frozen: yes.
- Projection families and cue equivalence frozen: yes.
- Three categorical contracts implemented: yes.
- Exactly-three-call custody implemented: yes.
- Prompt-content, dependency-key, and schema custody implemented: yes.
- One-shot workflow failure reaches a terminal diagnostic seal: yes.
- Deterministic gate and replay implemented: yes.
- Offline known-correct path recognized: yes.
- Historical V8-V10 sequence regression suites green: yes.
- Scientific adversarial re-review completed: no remaining path was found for an
  incomplete or misleading result to receive `GO_TO_SMALL_REPLICATION`.
- Custody/replay adversarial re-review completed: `READY` after closing runtime
  lease ordering, terminal freshness, local failure category, receipt
  multiplicity, and binding-rejection replay findings.
- Focused V8-V11 regression suite, architecture gates, and Evidence API type
  checks: green.
- Residual risks recorded: this is one narrow null-result unit, all three roles
  use Luna, and an operational crash after provider activity remains fail-closed.
- Live V11 provider sequence made: yes; two provider responses were verified
  before Call 2 failed deterministic semantic binding.
- Scientific result available: finalized negative diagnostic. Meaning was
  materially preserved, but workflow qualification failed because normalized
  context dimensions referenced an event whose `local_event_id` was absent.
- Persistence authorized: no.
