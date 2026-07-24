# V18 Inline Participant Spans and Mandatory Anaphoric Locus Scope

This rule resolves the boundary between a complete role-bearing participant
span and a separately represented source scope, and it makes the anaphoric
scope requirement unambiguous. It does not authorize new events, participant
types, event arguments, event links, or source claims.

- First bind the smallest complete participant span that bears the event role.
  Retain its noun head and every restrictive modifier needed to identify that
  participant. A restrictive modifier already retained inside that complete
  role-bearing span is represented by the parent participant itself. Do not
  split that inline modifier into another participant or a
  `participant_scope_links` item merely to restate information already present
  in the parent span.
- Separately and independently of the inline-modifier prohibition above: when a
  downstream anaphoric aggregate or partitive depends on a restriction that the
  source states outside its antecedent's own complete role-bearing span (a
  non-inline restriction), you must represent that restriction as its own
  participant and emit one `participant_scope_links` item connecting the
  antecedent to it, and attach an explicit `MAJORITY` partitive only when the
  source states one. This is mandatory whenever the source supplies such a
  restriction; it is not weakened, excused, or made optional by the inline
  prohibition above, which governs a different structural configuration. Do
  not omit the restrictor participant or scope link because the restriction
  seemed inferable, minor, or already implied by nearby context. The scope
  link preserves identity; it is not an event argument and cannot replace the
  antecedent's ordinary event argument.
- Never remove a restrictive modifier from the complete parent span in order to
  create a separate scope participant. Do not invent a restrictor participant,
  scope link, or partitive that the source does not state.
- Before finishing, check every anaphoric aggregate and partitive against its
  complete source sentence and confirm any non-inline restriction on its
  antecedent is represented by a grounded participant and scope link.

This rule is additive to the frozen occurrence, focus, and source-grounding
rules. It changes only whether an already-retained inline modifier is
redundantly decomposed and whether a required non-inline anaphoric restriction
is completely represented. It does not change event inventory, entity types,
mandatory event arguments, root selection, semantic axes, evidence grounding,
completeness, historical graders, or BioNLP-CG projection policy.
