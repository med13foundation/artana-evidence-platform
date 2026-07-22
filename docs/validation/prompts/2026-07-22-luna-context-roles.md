# Roles And Nesting

Assign BioNLP Cancer Genetics roles to the supplied participants. Preserve event-to-event arguments when the complete nested event is affected or causal. Use only permitted event IDs. Return `ABSTAIN` when the connection is ambiguous.

Schema-shaped synthetic contrasts:

- `Drug inhibits protein.`: assign the protein participant as `Theme` and the drug as `Cause` only when the source states causation.
- `Protein reduction increases drug sensitivity.`: assign the complete reduction event as `Cause` of the sensitivity event; do not flatten the affected event into the protein entity. If the nested edge is unresolved, return `ABSTAIN`.

Do not change trigger, event type, participant text, or occurrence identity. Do not provide chain-of-thought or numeric confidence.
