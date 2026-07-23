# Occurrence-Aware Evaluator V2 Design

## Status and scope

This design was recorded before implementing evaluator V2. It follows the
sealed staged-generalization V9 terminal result at commit `2a8ca565`.

This checkpoint is evaluator and governance work only. It authorizes no
provider calls, graph writes, scientific promotion, qualification, reference
changes, or retroactive rescoring. All V5–V9 artifacts and terminal decisions
remain immutable.

## Root cause

The V1 span identity boundary represents a mention only by its surface text and
then calls `resolve_unique_span` inside the declared evidence string. That
assumption is false for valid biomedical prose. In the drug-sensitivity source
sentence, `5-FU` appears once in the parenthetical expansion
`5-fluorouracil (5-FU)` and once as the object of `sensitivity ... to 5-FU`.

This produces two deterministic false negatives:

1. `resolve_in_context` rejects the participant during source grounding because
   the child text is not unique inside its complete evidence sentence.
2. the frozen semantic participant matcher applies the same uniqueness
   assumption when comparing the returned participant with an acceptable
   reference surface form.

Even a reference-shaped answer cannot pass both checks while also preserving
the required complete evidence sentence. The problem is mention identity, not
the scientific acceptance threshold.

## Versioning boundary

V1, the V5 dual-lane grader, the panel references, and every V5–V9 artifact stay
unchanged. V2 is additive and lives in a separate package. Its public version is
`artana.staged_generalization.occurrence_evaluator.v2`.

V2 pairs an unchanged scientific output with a source-identity sidecar. The
sidecar contains half-open absolute source offsets for:

- the declared complete evidence span; and
- the selected event trigger or participant mention inside that evidence.

The sidecar is evaluation metadata, not a new scientific label. It cannot
change event type, entity type, argument role, semantic axes, completeness, or
the frozen reference.

## Single-responsibility components

The implementation is split into four boundaries:

1. `contracts.py` owns the strict, versioned offset and binding schemas.
2. `resolver.py` validates one declared span against source bytes, permitted
   context, token boundaries, and containment.
3. `bindings.py` verifies exact binding coverage and identity against one
   scientific output.
4. `evaluation.py` creates an internal mention-scoped compatibility projection
   only after V2 validation, then delegates all scientific scoring to the
   unchanged frozen dual-lane evaluator.

The compatibility projection is never persisted and never replaces the
declared complete evidence. It narrows only the already-validated event or
participant evidence used by the V1 uniqueness matcher. Semantic fields and
reference rules are not projected or rewritten.

## Fail-closed invariants

For every event and participant, V2 must prove all of the following before any
scientific scoring:

- every required binding exists exactly once and no unknown binding exists;
- source, evidence, and mention offsets are ordered and in bounds;
- source slicing at the evidence offsets exactly reproduces the declared
  `exact_evidence`;
- source slicing at the mention offsets exactly reproduces the declared trigger
  or participant text;
- the mention is token-bounded;
- the mention is contained in its declared evidence;
- both spans are contained in the case's permitted source context; and
- the binding and scientific output identify the same case and node.

There is no text-search fallback. Missing or ambiguous identity therefore
cannot silently select the first matching occurrence.

## Qualification gate

V2 is qualified only if focused tests prove:

- unique, first-duplicate, and second-duplicate mentions resolve correctly;
- missing, mismatched, duplicate, out-of-evidence, out-of-context, and
  out-of-bounds identities fail closed;
- reference-shaped outputs for all six frozen panel cases retain the frozen
  scientific result under V2;
- the V9 drug output loses only the impossible grounding error while its real
  event, entity, and direction disagreements remain failures;
- all selected V5–V9 artifacts and grader/reference sources retain their sealed
  byte hashes; and
- no provider or graph execution path is present in this checkpoint.

Reference adjudication remains a separate evidence report. It may recommend a
future versioned reference, but it cannot edit the frozen reference or V9.
