# V14 Complete Biomedical Participant Denotation

This rule clarifies the existing named-biomedical occurrence boundary. It does
not replace any event, evidence, or semantic rule.

- Select the smallest exact contiguous source span that independently denotes
  the same biomedical participant occurrence while preserving its
  scientifically restrictive identity and scope.
- An adjacent entity-type noun may be omitted only when the retained text is an
  independently referential lexicalized biomedical identifier that denotes the
  same participant in that occurrence.
- Retain the semantic noun head when removing it would leave only modifiers,
  classifiers, stages, taxonomic restrictions, or other attributive text. Do
  not reconstruct an omitted head from `entity_type`, the explanation, or
  surrounding evidence.
- Retain nonredundant restrictive modifiers unless the same output explicitly
  represents and links an equivalent restriction. If the schema cannot
  represent that relation, retain the modifier in the participant span.
- If either denotation or restrictive scope would be lost, fail closed with
  `INCOMPLETE` or `ABSTAIN`; do not shorten the participant.

This rule changes only participant occurrence text. It cannot create or remove
events, participants, entity types, roles, links, root choices, semantic axes,
statistics, evidence, completeness states, or scientific claims.
