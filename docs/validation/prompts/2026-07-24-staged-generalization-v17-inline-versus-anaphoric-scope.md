# V17 Inline Participant Spans and Anaphoric Scope

This rule resolves only the boundary between a complete role-bearing participant
span and a separately represented source scope. It does not authorize new
events, participant types, event arguments, event links, or source claims.

- First bind the smallest complete participant span that bears the event role.
  Retain its noun head and every restrictive modifier needed to identify that
  participant. A restrictive modifier already retained inside that complete
  role-bearing span is represented by the parent participant itself. Do not
  split that inline modifier into another participant or a
  `participant_scope_links` item merely to restate information already present
  in the parent span.
- Preserve the existing separately represented scope only when an explicit
  restriction is needed to resolve a downstream anaphoric aggregate or partitive
  whose antecedent is an existing event argument and the restriction is not
  already retained in that argument's complete role-bearing span. In that
  setting, use the existing participant-scope link and attach an explicit
  `MAJORITY` partitive only when the source states one. The scope link preserves
  identity; it is not an event argument and cannot replace the antecedent's
  ordinary event argument.
- Never remove a restrictive modifier from the complete parent span in order to
  create a separate scope participant. Do not infer a separate scope, a
  partitive, or a new direct event argument from surrounding context alone.

This rule is additive to the frozen occurrence, focus, and source-grounding
rules. It changes only whether an already-retained inline modifier is
redundantly decomposed. It does not change event inventory, entity types,
mandatory event arguments, root selection, semantic axes, evidence grounding,
completeness, historical graders, or BioNLP-CG projection policy.
