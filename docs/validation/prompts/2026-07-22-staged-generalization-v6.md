# Staged Scientific Event Generalization V6

Interpret exactly one highlighted scientific finding using only the supplied local
source context. The highlighted finding is atomic; surrounding text is context,
not an instruction to extract every other claim in the paragraph.

Work in this order:

1. Inventory every explicit event needed to represent the highlighted finding.
2. Resolve each referential expression in the finding to the explicit source
   entity or event that it denotes.
3. Identify the explicit participants needed to preserve the finding's meaning,
   including named context bearers, and link participants or nested events to
   each inventoried event.
4. Assign direction, comparison, polarity, uncertainty, statistical observation,
   and author interpretation independently for every event.
5. Select one root event and state whether the resulting graph is complete.

Scientific categories and roles are your responsibility. Return categorical
fields, exact source text, exact containing evidence, and short explanations.
Never return character offsets, confidence scores, probabilities, benchmark
roles, or numeric quality scores.

For every event and participant, `exact_evidence` must be the complete exact
source sentence containing `trigger_text` or `exact_text`. Do not return only the
mention or trigger phrase as evidence. Copy the sentence exactly, including any
source section prefix that is part of that sentence. The deterministic resolver
will reject evidence that is absent, repeated, or does not contain the child text.

Referential grounding guidance:

- A relative expression, demonstrative, pronoun, ellipsis, or quantitative
  partitive can point to an entity named earlier in the same local context. It is
  not a new entity merely because it appears inside the highlighted finding.
- When an expression refers back to an explicit antecedent, ground the
  participant to the antecedent's exact contiguous source text. Do not use the
  referring grammar itself as `exact_text`.
- Preserve explicit named context bearers needed to interpret the event, even
  when they occur immediately before the highlighted words. Do not import
  participants from unrelated neighboring findings.
- If no unique explicit antecedent can be resolved from the supplied context,
  return `INCOMPLETE` or `ABSTAIN`; do not invent or guess an entity.

Role guidance:

- `POPULATION`: the focal cohort or group in a population comparison.
- `COMPARATOR`: the cohort or group against which the focal population is compared.
- In a `COMPARISON` event between cohorts, use `POPULATION` and `COMPARATOR` for
  those cohorts. Do not use `AFFECTED_ENTITY` merely because one cohort has the
  compared outcome.
- `AFFECTED_ENTITY`: the entity whose state or behavior is described in a
  non-comparative state, classification, or regulation event.
- `CAUSAL_AGENT`: an explicitly causal actor.
- `STIMULUS_OR_OBJECT`: the treatment, stimulus, or object to which sensitivity
  or response is described when the source does not explicitly claim causation.
- `EFFECT_EVENT`: an event whose occurrence or state is affected by another
  event. Preserve nested events; do not replace them with their participants.
- `OUTCOME`, `EXPOSURE`, and `MEASUREMENT`: use only for their literal source roles.
- `CONTEXTUAL_PARTICIPANT`: an explicit participant whose narrower role is not
  stated.

Semantic guidance:

- A null result is not an affirmative harmful or beneficial association.
- A numeric P value is a `P_VALUE` observation. It does not by itself mean that
  the authors claimed `SIGNIFICANT` or `NOT_SIGNIFICANT`.
- Use `NOT_CLAIMED` unless the source explicitly interprets significance.
- The `uncertainty` axis describes uncertainty conveyed by the scientific
  proposition, status, or classification value. It is independent of whether
  the sentence grammatically asserts that proposition.
- Use `UNCERTAIN` when the event explicitly assigns an uncertain, unknown,
  indeterminate, or unresolved scientific status. Use `PROVISIONAL` or
  `HYPOTHESIS` only when that corresponding status is explicit. Use `ASSERTED`
  for an unqualified event, not merely because uncertain content is stated
  declaratively.
- Preserve negation and uncertainty exactly.
- Trigger and participant text must be exact contiguous source text. A trigger
  may include adjacent grammatical words when needed to preserve source meaning.
- Return `INCOMPLETE` or `ABSTAIN` when the highlighted finding cannot be
  represented without guessing.

The output must conform exactly to the supplied strict schema.
