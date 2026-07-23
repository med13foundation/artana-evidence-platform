# V13 Compositional Focus Root Selection

Compositional focus root selection:

- Select the root only after constructing event links.
- In the focus-internal event subgraph, when exactly one inventoried event is
  not the target of another focus-internal inventoried event, choose it as root.
- Predicates outside the highlighted finding cannot disqualify or replace that
  root, and a nested effect cannot replace its explicit focus-internal parent.
- Otherwise apply the existing root and completeness rules unchanged; do not
  alter inventory or links to force uniqueness.
- This rule changes root selection only. Preserve inventory, trigger
  boundaries, participants, links, roles, semantic axes, evidence, and
  completeness rules unchanged.
- The rule does not prescribe an event count, event type, participant, role,
  semantic-axis value, benchmark label, or expected answer.

Non-scientific transport clarification for this exposed V13:

- Every preregistered focus is upstream-eligible because it contains at least
  one explicit source-supported event. An input with no such event is outside
  this experiment and must not be sent to the provider.
- When `completeness` is not `COMPLETE`, `root_event_id` is a required transport
  anchor, not an asserted scientific root. Set it to the earliest
  source-supported focus-internal inventoried event in source order.
- Do not add, delete, relabel, or link events to create that transport anchor.
  The universal schema still cannot represent a truly eventless abstention;
  V13 does not claim to solve that residual limitation.
