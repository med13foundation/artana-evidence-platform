# Staged Scientific Event Generalization V10

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

Named biomedical occurrence boundary:

- For a named gene or protein participant, use the exact lexicalized name that
  identifies the entity occurrence. Do not expand that name merely to include an
  adjacent generic entity-type word such as `gene` or `protein`.
- Include an adjacent generic word only when it is part of the lexicalized name
  or is required to distinguish the occurrence in the supplied sentence.
- This boundary rule changes only participant occurrence text. It does not
  change entity type, event role, scientific meaning, or the requirement that
  every returned span be exact contiguous source text.

Focus-gated referential grounding:

- Apply antecedent resolution only when the highlighted finding contains a
  referring expression that cannot identify its entity or event without earlier
  words in the supplied local context.
- For such an expression, resolve one unique explicit antecedent and ground the
  participant to the antecedent's exact contiguous source text. Do not use the
  pronoun, relative phrase, demonstrative, ellipsis, or partitive grammar itself
  as `exact_text`.
- Preserve an explicitly named entity that restricts the antecedent only when
  that relation is necessary to identify or interpret the focused event. Do not
  add general paragraph context or participants from neighboring findings.
- A source subspan already contained in a complete participant mention is not a
  separate contextual participant unless it has an independent role in the
  focused event.
- An analytic method, model, curve, assay, or representation is not an event
  participant merely because the finding was measured or displayed through it.
  Include it only when the focused event independently predicates a state,
  relation, or value about that item.
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

Classification argument boundary:

- In a `CLASSIFICATION` event, link the classified entity as `AFFECTED_ENTITY`.
- If a named entity explicitly restricts the identity or scope of that
  classified entity set, link the restricting entity as
  `CONTEXTUAL_PARTICIPANT`.
- A classification label or value belongs in the classification event trigger
  and semantic axes. Do not duplicate it as `OUTCOME` unless it independently
  participates in another event.

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
- Polarity records scientific result status, not surface grammar, and is
  independent of direction and uncertainty. Use `NULL_RESULT` when a study or
  analysis reports absence of an association, difference, or effect, regardless
  of negative grammatical form. Use `NEGATED` only for direct denial or
  non-occurrence outside an analytic null finding. Use `AFFIRMED` for other
  non-null findings.
- Preserve scientific negation and uncertainty exactly.
- Trigger and participant text must be exact contiguous source text. A trigger
  may include adjacent grammatical words when needed to preserve source meaning.
- Return `INCOMPLETE` or `ABSTAIN` when the highlighted finding cannot be
  represented without guessing.

The output must conform exactly to the supplied strict schema.
