# Source-Only Axis Verification

Verify each complete typed event using only the source packet. This is a fresh same-model independent call, not model-independent verification. Check event type, trigger, participants, roles, nesting, modifier, and evidence separately. Return `ENTAILED` only when every axis passes. One wrong role or unsupported edge requires `CONTRADICTED`; unresolved ambiguity requires `ABSTAIN`.

Schema-shaped synthetic examples:

- A plausible sentence with one reversed role: `CONTRADICTED` on the role axis.
- A complete event with exact trigger, participants, roles, nesting, modifiers, and evidence: every axis `PASS`, verdict `ENTAILED`.
- An ambiguous nested connection: nesting `ABSTAIN`, verdict `ABSTAIN`.

Return categorical findings, exact evidence, and short explanations. Never return numeric confidence.
Do not provide chain-of-thought.
