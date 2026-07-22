# Staged Scientific Event Generalization V2

Interpret exactly one highlighted scientific finding using only the supplied local
source context. The highlighted finding is atomic; surrounding text is context,
not an instruction to extract every other claim in the paragraph.

Work in this order:

1. Inventory every explicit event needed to represent the highlighted finding.
2. Identify explicit participants and link participants or nested events to each
   inventoried event.
3. Assign direction, comparison, polarity, uncertainty, statistical observation,
   and author interpretation independently for every event.
4. Select one root event and state whether the resulting graph is complete.

Scientific categories and roles are your responsibility. Return categorical
fields, exact source text, exact containing evidence, and short explanations.
Never return character offsets, confidence scores, probabilities, benchmark
roles, or numeric quality scores.

For every event and participant, `exact_evidence` must be the complete exact
source sentence containing `trigger_text` or `exact_text`. Do not return only the
mention or trigger phrase as evidence. Copy the sentence exactly, including any
source section prefix that is part of that sentence. The deterministic resolver
will reject evidence that is absent, repeated, or does not contain the child text.

Role guidance:

- `AFFECTED_ENTITY`: the entity whose state or behavior is described.
- `CAUSAL_AGENT`: an explicitly causal actor.
- `STIMULUS_OR_OBJECT`: the treatment, stimulus, or object to which sensitivity
  or response is described when the source does not explicitly claim causation.
- `EFFECT_EVENT`: an event whose occurrence or state is affected by another
  event. Preserve nested events; do not replace them with their participants.
- `POPULATION`, `COMPARATOR`, `OUTCOME`, `EXPOSURE`, and `MEASUREMENT`: use only
  for their literal source roles.
- `CONTEXTUAL_PARTICIPANT`: an explicit participant whose narrower role is not
  stated.

Semantic guidance:

- A null result is not an affirmative harmful or beneficial association.
- A numeric P value is a `P_VALUE` observation. It does not by itself mean that
  the authors claimed `SIGNIFICANT` or `NOT_SIGNIFICANT`.
- Use `NOT_CLAIMED` unless the source explicitly interprets significance.
- Preserve negation and uncertainty exactly.
- Trigger and participant text must be exact contiguous source text. A trigger
  may include adjacent grammatical words when needed to preserve source meaning.
- Return `INCOMPLETE` or `ABSTAIN` when the highlighted finding cannot be
  represented without guessing.

The output must conform exactly to the supplied strict schema.
