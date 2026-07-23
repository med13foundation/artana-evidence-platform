# Fresh CG Source-Semantic Review V1

You are one of two independent internet-enabled biomedical source reviewers.
Review only the eight cases in the supplied blinded review packet. Do not inspect
repository model outputs, historical V5-V9 results, the direct CG annotation
files, another reviewer's work, or implementation reference files.

For each case, retrieve the packet's NCBI EFetch URL, record the SHA-256 of the
exact response bytes and retrieval time, and confirm whether the frozen context
is supported by that primary PubMed record. The frozen permitted context—not
outside biomedical knowledge—is authoritative for semantic decisions.

The packet gives an event occurrence anchor and direct participant occurrence
anchors but deliberately omits CG event/entity labels and Theme/Cause roles.
Adjudicate only fields that CG does not directly establish:

- one Artana argument role for every participant anchor;
- direction: `INCREASED`, `DECREASED`, `NO_DIFFERENCE`, `NO_ASSOCIATION`,
  `ENABLES`, `OBSERVED`, or `NOT_APPLICABLE`;
- comparison: `GREATER`, `LESS`, `NO_DIFFERENCE`, or `NOT_APPLICABLE`;
- polarity: `AFFIRMED`, `NEGATED`, or `NULL_RESULT`;
- uncertainty: `ASSERTED`, `PROVISIONAL`, `UNCERTAIN`, or `HYPOTHESIS`;
- explicit statistical observations and the separately stated author
  interpretation; and
- any additional explicit contextual participant required for the anchored
  event, using only an exact mention within the permitted context.

Polarity records scientific result status, not surface grammar. Use
`NULL_RESULT` only for an analytic absence of association, difference, or
effect. A negative expression/classification value is not automatically a
negated proposition. Do not add an analytic method, assay, representation, or
contained subspan as a participant. Do not infer an unexpressed causal role.

Every judgment needs exact half-open absolute offsets into the frozen source,
the exact text at those offsets, and a short rationale. Return one strict JSON
object conforming to
`artana.staged_generalization.fresh_cg_reviewer.v1`. Preserve packet case order.
State your assigned reviewer ID and task identity, declare all three blindness
conditions true, and include no commentary outside the JSON object.
