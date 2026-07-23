Return one wrapper object with constant `schema_version`
`artana.staged_generalization.fresh_cg_provider.v1` plus `scientific_output` and
`occurrence_bindings`.

`scientific_output` must conform exactly to the unchanged V9 scientific schema
and obey every preceding V9 instruction. The V9 instruction never to return
character offsets applies inside `scientific_output`; do not alter that object
or add offsets to it.

`occurrence_bindings` is a non-scientific identity sidecar conforming exactly to
`artana.staged_generalization.occurrence_bindings.v2`. Its `case_id` must equal
the V9 `scientific_output.case_id`. Use zero-based half-open absolute character
offsets into the full frozen source. The packet supplies `context_start`; add
local positions within `local_context` to that value.

Bind every V9 event and participant exactly once by its output node ID:

- `evidence_span` must resolve the complete exact evidence text;
- `mention_span` must resolve that event's exact `trigger_text` or that
  participant's exact `exact_text` within its evidence span;
- every semantic-axis `evidence_items` entry needs one ordered absolute span;
- every statistical observation needs one ordered absolute span, except a
  `NONE` observation must use `null`; and
- do not omit, duplicate, invent, or bind an unknown node ID.

All spans must remain inside the supplied source context, reproduce the exact
declared text, and use token boundaries for event/participant mentions and
non-null statistical observations. Binding work must not change the scientific
inventory, participant roles, links, axes, completeness, or explanations.
