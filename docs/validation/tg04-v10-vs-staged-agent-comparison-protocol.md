# TG04 V10 Versus Staged-Agent Comparison Protocol

Created: 2026-07-20

Status: `SOURCE_1_EXECUTION_AUTHORIZED`

Offline controls are frozen in
`reports/2026-07-20-tg04-v10-staged-offline-controls.json`. The deterministic
selection gate is implemented in
`scripts/validation/claim_events/architecture_selection.py`. The source panel
is frozen in
`reports/2026-07-20-tg04-v10-staged-untouched-source-seal.json`. These artifacts
authorize only the preregistered source-1 paired execution. Sources 2 and 3
remain blocked until the immediate stop rule is applied.

## Decision Question

Does a staged scientific workflow recover more complete biomedical events than
the frozen one-shot atomic-event validator V10 without adding unsupported
claims?

This is a small architecture-selection experiment. It cannot qualify Artana for
trusted graph promotion, and it must not trigger graph writes.

## Frozen Arms

### Arm A: One-Shot V10

Use the immutable atomic-event validator V10 identified by:

```text
bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a
```

One extraction call receives the complete source and produces the V10 atomic
event inventory. Deterministic compilation and validation run unchanged.

### Arm B: Staged Agent

The staged arm separates scientific responsibilities:

1. **Discovery:** inventory candidate scientific propositions and exclusions,
   each anchored to exact source text. It does not construct graph relations.
2. **Event extraction:** identify atomic triggers, typed participants, and roles
   for every discovered proposition. It does not assign modifiers.
3. **Modifiers:** attach direction, polarity, uncertainty, analysis, context,
   comparison, and attribution to existing event identities.
4. **Independent falsification:** a source-only agent attempts to contradict each
   event, find missing participants or modifiers, and identify omitted events. It
   returns only `ENTAILED`, `CONTRADICTED`, `INSUFFICIENT`, or `ABSTAIN`, with
   exact supporting or falsifying spans and a language explanation.
5. **Graph projection:** deterministic code projects only complete,
   source-entailed events into review-only graph candidates. It performs no
   biomedical inference and no persistence.

The producing stages cannot see the common final adjudication or the other
arm's output. The falsification stage cannot repair an event; it can only accept,
reject, abstain, or report omissions.

## Controlled Inputs

- Model for every agent call: `openai:gpt-5.6-sol`.
- Reasoning effort: provider default, fixed identically for both arms.
- Sources: the same sealed untouched source units, hash-frozen before either arm
  runs. Each source is unsealed once and evaluated by both arms as a paired case.
- Source order: deterministic SHA-256 order, identical for both arms.
- Retrieval context: identical source text and metadata for both arms.
- Retries: none for semantic failures. Transport failures invalidate the paired
  case and do not permit selective reruns.
- Tools and browsing: disabled for producing and judging calls; the supplied
  source is the complete evidence boundary.
- Graph writes: zero.

Before unsealing untouched sources, both runners must pass schema and receipt
preflight on synthetic fixtures. Synthetic preflight cannot affect scientific
scores or prompts.

## Token And Call Budget

The comparison controls total model work rather than call count:

- Arm A has one producing call per source.
- Arm B may use one call for each of its four agent stages.
- Both arms have the same 60,000 cumulative input-plus-output-token ceiling per
  source. The staged ceiling is frozen across discovery (12,000), event
  extraction (14,000), modifiers (26,000), and falsification (8,000).
- Stage ceilings are frozen before execution; unused tokens cannot be moved
  after viewing an output.
- A shared final adjudication budget is applied equally to both arms and is
  reported separately from producing-arm cost.
- Actual input, output, reasoning, and cached tokens are recorded per call and
  summed per arm. An arm exceeding its ceiling is invalid, not truncated into a
  favorable score.

Prompt and schema overhead are included in each arm's budget. This prevents the
staged arm from buying improvement with materially more inference while still
allowing it to divide attention across responsibilities.

## Common Scientific Adjudication

Two independent source-only reviewers receive one source and one anonymized arm
output at a time. They do not know the arm, the other output, or the expected
winner. Each reviewer returns categorical findings with:

- event identity and exact source spans;
- `ENTAILED`, `CONTRADICTED`, `INSUFFICIENT`, or `ABSTAIN`;
- participant-role correctness for every participant;
- direction, polarity, uncertainty, context, and attribution correctness;
- omitted complete events supported by exact spans;
- a concise falsification explanation.

Reviewers never produce numeric scores. Deterministic code converts their
categorical records into counts and rates. Reviewer disagreement is
`UNRESOLVED` and receives no correctness credit; a separately frozen tie-breaker
may adjudicate it without seeing arm identity.

## Deterministic Metrics

For each arm, report counts, denominators, and rates for:

- complete-event precision and recall;
- whole-event exact recovery;
- typed participant-role fidelity;
- direction, polarity, uncertainty, context, and attribution fidelity;
- unsupported event count and rate;
- omitted complete-event count;
- exact evidence-span coverage;
- invalid output, fallback, and abstention counts;
- total model tokens and tokens per accepted complete event.

A complete event receives credit only when its trigger, all required typed
participants and roles, and every source-expressed modifier are correct as one
event. Correct fragments cannot be assembled across separate incomplete events.

## Small Paired Sequence

1. Freeze three untouched source hashes without reading their contents. Source
   order is ascending exact source SHA-256, making `pubmed:42454948` source 1.
2. Freeze prompts, schemas, model settings, per-stage token ceilings, common
   adjudication contracts, and deterministic scorer hashes.
3. Run both arms on untouched source 1, then perform blinded common adjudication.
4. Apply the immediate stop rules before spending on source 2.
5. If allowed, repeat the paired process for sources 2 and 3.
6. Publish all raw categorical judgments, deterministic metrics, receipts, and
   the decision. Do not revise contracts after any source is unsealed.

## Stop And Advance Rules

Stop the comparison immediately and retain V10 as the baseline when the staged
arm on the first source:

- produces any unsupported event that V10 did not produce;
- loses a complete event recovered by V10;
- worsens participant-role or modifier fidelity;
- violates schema, provenance, receipt, or token-budget constraints; or
- recovers no additional complete event.

After all three paired sources, the staged approach advances only if it:

- recovers at least one additional complete event and loses none recovered by
  V10;
- has strictly higher complete-event recall;
- adds zero unsupported events relative to V10;
- is no worse on complete-event precision, role fidelity, modifier fidelity,
  evidence coverage, invalid output, and abstention;
- remains within the comparable token budget; and
- passes independent source-only adjudication for every credited gain.

If neither arm satisfies those conditions, neither wins. The result is a stop
and architecture reassessment, not permission to expand contracts or tune the
benchmark. A winner advances only to a larger untouched qualification study;
this three-source comparison is not scientific qualification by itself.

## Required Result Artifacts

- source-hash seal and unseal record;
- immutable arm, prompt, schema, scorer, and model-setting hashes;
- provider receipts and token accounting for every call;
- raw outputs for every producing and reviewing stage;
- categorical common-adjudication records;
- deterministic per-source and aggregate metrics;
- explicit `ADVANCE_STAGED`, `RETAIN_V10`, or `NO_WINNER` decision;
- confirmation that fallback credit and graph writes remained zero.

No provider call is authorized by this protocol-writing step.
