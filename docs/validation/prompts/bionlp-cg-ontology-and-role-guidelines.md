# BioNLP Cancer Genetics Annotation Contract

Apply the public BioNLP-ST 2013 Cancer Genetics event policy. These are generic
annotation rules, not gold answers for the supplied source.

## Event Identity

Every event is a complete typed structure containing a minimal contiguous
trigger, zero or more typed arguments, nested event references when required,
and event-local negation or speculation. Unary events are valid. Do not add an
argument merely because an entity appears in the same sentence.

Use only these source event types:

Acetylation, Amino_acid_catabolism, Binding, Blood_vessel_development,
Breakdown, Carcinogenesis, Catabolism, Cell_death, Cell_differentiation,
Cell_division, Cell_proliferation, Cell_transformation, DNA_methylation, Death,
Dephosphorylation, Development, Dissociation, Gene_expression, Glycolysis,
Growth, Infection, Localization, Metabolism, Metastasis, Mutation,
Negative_regulation, Pathway, Phosphorylation, Planned_process,
Positive_regulation, Protein_processing, Regulation, Remodeling, Synthesis,
Transcription, Translation, and Ubiquitination.

Use Regulation when direction is not explicitly positive or negative.
Positive_regulation requires explicit increase, activation, induction, or an
equivalent positive effect. Negative_regulation requires explicit decrease,
inhibition, prevention, resistance, or an equivalent negative effect. A noun
that names a method, analysis, strategy, identity, or general concept is not by
itself evidence of a scientific event of another type.

## Roles And Nesting

- Theme: the entity or event undergoing the event's primary effect.
- Cause: the entity or event causally active in a regulation event.
- Participant: involved without a more specific role supported by the text.
- Instrument: used to carry out a Planned_process.
- AtLoc, FromLoc, and ToLoc: location, origin, and destination respectively.
- Site and CSite: physical or causal sites only when explicit.

Use numbered roles such as Theme2 or Participant3 only for additional distinct
fillers of the same role. Never use role numbering to encode sequence, emphasis,
or a different semantic role. Preserve an event-to-event argument when the
affected or causing object is itself an event. Do not flatten it into one of the
nested event's entities.

## Occurrences

Participant text is not an occurrence identity. For each participant, return a
zero-based occurrence index among exact matches of that text inside the supplied
event passage, counted from left to right. Return occurrence_id as
`occurrence-N`, where N is that same index. This is required even when the text
occurs once. Never choose an occurrence outside the event passage.

## Modifiers

Assign NEGATED or SPECULATIVE only when the wording modifies that exact event.
Do not transfer uncertainty from a surrounding proposal, conclusion, method, or
different event. Numeric values do not imply either modifier.

## Verification

Verify the proposed event type, trigger, participants, roles, nesting, modifier,
and evidence as separate categorical axes. ENTAILED is permitted only when every
axis passes for the complete typed event. General plausibility is insufficient.
