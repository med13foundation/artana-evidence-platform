# Staged Generalization V5 Independent Internet Grader

You are a blinded, source-only biomedical graph grader. Work only from:

- `docs/validation/adjudications/2026-07-22-staged-generalization-v5-blinded-context-packets.json`
- `docs/validation/adjudications/2026-07-22-staged-generalization-v5-primary-source-evidence.json`
- the primary-source URLs embedded in those files
- `docs/validation/adjudications/2026-07-22-staged-generalization-v5-context-review.schema.json`

Do not inspect any Artana provider output, historical result, frozen core reference,
expected event count, benchmark annotation, other grader artifact, evaluator code, or
test expectation. Do not search the repository for the case IDs. Internet research is
limited to the supplied PubMed/NCBI primary-source URLs. Search snippets and automated
entity annotations are not evidence.

For every case, enumerate participant nodes beyond the indispensable focus-event core
that a faithful scientific graph could include. The core normally contains the focus
event's essential population, comparator, outcome, exposure, affected entity, or
explicit causal agent. Do not repeat those indispensable participants as context.

Classify each additional node:

- `PERMITTED_CONTEXT`: explicit, correctly typed, nonduplicative in scientific
  meaning, useful to interpreting the focus event, and attachable through the stated
  role without altering the source claim.
- `AMBIGUOUS_REVIEW_ONLY`: explicit but its node identity, type, relevance, or
  attachment is reasonably disputable.
- `FORBIDDEN`: neighboring-event, procedural, inferred, redundant, contradictory, or
  otherwise unsuitable as a contextual node for the focus event.

Use exact source text. `event_trigger_text` must be the smallest exact trigger for the
focus event, not an internal ID. Every case must be present and set
`inventory_complete` to true. Empty judgment lists are valid after a full review.

Copy the matching evidence records from the committed primary-source evidence
manifest. Use your own unique reviewer and task identities. Set all three blinded-state
fields to false. Return only schema-valid JSON in your assigned artifact file.
