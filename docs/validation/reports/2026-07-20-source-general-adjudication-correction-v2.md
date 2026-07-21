# Source-General Adjudication Correction V2

## Decision

`PIVOT`

The corrected adjudication checkpoint stopped before the exposed-source
verification experiment. Fifteen of 31 scopes remained scientifically unresolved
after the blinded tiebreaker (48.4%), exceeding the configured 20% ceiling.
No reliable frozen reference packet set was therefore created.

## What Was Run

The first adjudication attempt was invalid because one response violated the
categorical contract and another contained event-local evidence violations. It
was recorded as `INVALID_ADJUDICATION_CHECKPOINT`, not interpreted as scientific
disagreement, and consumed the first pass only.

The single permitted correction cycle introduced an exact source-local contract
with absolute offsets, defined event and role taxonomies, canonical participant
ordering, and separate statistical observation from author interpretation. Two
independent source-only adjudicators processed all 31 exposed scopes. A third
blinded adjudicator was supplied the 14 scopes disputed under the earlier
label-level comparison and their source text. The stricter evidence-bound
comparison later identified one additional disagreement, which the tiebreaker
did not evaluate and which therefore remains unresolved.

All three corrected artifacts passed schema, source-hash, exact-offset,
event-locality, ordering, and sealed-scope validation:

| Artifact | Adjudicated | Ambiguous | Valid |
| --- | ---: | ---: | --- |
| First adjudicator | 10 | 21 | Yes |
| Second adjudicator | 16 | 15 | Yes |
| Tiebreaker, disputed scopes only | 12 | 2 | Yes |

Initial and final evidence-bound scientific disagreement was 15/31 (48.4%). A
tiebreaker response is no longer allowed to resolve a scope merely by matching
labels: it must also preserve the original evidence-bearing scientific fields.
No disputed scope cleared that stricter rule.

## Experiment Status

The packet reliability gate failed, so framing, verification, repair, and fresh
reverification were not run. False acceptance, rejection, abstention, recall,
repair, fidelity, unsupported-claim, contradiction, token, latency, and cost
metrics are explicitly `NOT_RUN`; they are not represented as scientific zeros.

The checkpoint runner made no provider experiment call, graph write, fallback,
or promotion. The separate task dispatch record does not independently prove
runtime isolation or untouched-source non-access; that limitation is explicitly
recorded in the manifest. All planned outcomes remain review-only. Codex
adjudicator task token and cost telemetry was unavailable and is recorded as
unavailable, not guessed.

## Adversarial Findings Addressed

The deterministic harness now excludes unresolved scopes from scientific
denominators, requires a validated frozen packet set before preregistration can
authorize execution, compares complete repair payloads including evidence and
explanations, distinguishes failed repair attempts, and reports repaired and
unrepaired quality separately. Malformed controls cover role reversal, merged
participants, comparison and direction reversal, negation inversion,
unsupported uncertainty, both false interpretations of `P = 0.08`, cross-event
evidence, missing modifiers, invented evidence, and incomplete claims.

The configured ceiling is now enforced by the reusable packet-set validator and
future execution also requires a complete, non-empty preregistered case
inventory. This artifact was assembled after task completion, so it does not
prove that the ceiling was preregistered before the V2 outputs existed; the
report therefore treats it as a corrected diagnostic checkpoint, not a
prospective registered experiment.

## Root Cause And Next Architecture

The exposed discovery scopes are not yet reliable single-event gold units. Even
with a valid, explicit contract, independent source-only adjudicators frequently
disagreed about event boundaries, participant-role granularity, and whether a
scope contains one complete claim or requires categorical exclusion.

The next checkpoint should pivot to boundary-first reference construction:

1. Have independent adjudicators mark atomic event boundaries and core
   participants before assigning modifiers.
2. Resolve boundary disagreements separately from semantic-field disagreements.
3. Use a small human-expert adjudication pass for the remaining contested units,
   or declare those units excluded with an explicit reason.
4. Re-enter verification only after the resulting reference set clears the same
   20% reliability gate without another prompt-repair cycle.

This checkpoint does not establish verifier quality. It establishes that the
current 31-scope reference representation is not reliable enough to measure it.
