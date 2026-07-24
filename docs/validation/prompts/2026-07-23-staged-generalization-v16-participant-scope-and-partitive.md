# V16 Participant Scope and Partitive Meaning

This rule adds a source-semantic representation for a condition that narrows a
participant set used by a focused event. It does not authorize additional
events, participants, event arguments, or source claims.

- When a named participant restricts the identity or scientific scope of a
  participant set used by a focused event, emit both participant nodes and one
  `participant_scope_links` item from the restricted set to its restrictor with
  relation type `IDENTITY_OR_SCOPE_RESTRICTION`. Ground the link to the complete
  source sentence that expresses the restriction.
- When an existing event argument denotes a stated partitive subset of its
  participant set, retain the ordinary argument and attach `partitive_scope` to
  that argument. Use kind `MAJORITY` only for an explicit majority expression,
  copy its exact text and complete evidence sentence, and bind its antecedent to
  the same participant target as the argument.
- A scope link preserves participant identity; it is not a new event argument.
  Do not add a direct event-to-restrictor argument merely to restate the scope.
  If such a direct argument is independently explicit in the source, retain it
  only under the existing role and occurrence rules.
- Bind every scope participant to its exact source occurrence before minimizing
  its text. The existing complete-participant-denotation rule remains unchanged:
  an independently referential lexicalized biomedical identifier may omit an
  adjacent generic entity-type word, but the complete evidence sentence must
  still anchor the source occurrence.
- Use empty `participant_scope_links` and no `partitive_scope` when the focused
  finding contains no source-stated scope or partitive condition. Never infer a
  restriction or a majority from surrounding context alone.

This rule changes only the representation of explicit participant scope and
partitive meaning. It does not change event inventory, entity types, mandatory
event arguments, root selection, semantic axes, evidence grounding,
completeness, historical graders, or BioNLP-CG projection policy.
