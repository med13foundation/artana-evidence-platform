# Roles And Nesting

Assign BioNLP Cancer Genetics roles to the supplied participants. Preserve event-to-event arguments when the complete nested event is affected or causal. Use only permitted event IDs. Return `ABSTAIN` when the connection is ambiguous.

Synthetic contrasts:

- `Drug inhibits protein.`: `protein` is the Theme; `Drug` may be Cause when explicitly supported.
- `Protein reduction increases drug sensitivity.`: the entire reduction event is Cause of the sensitivity increase. The protein alone is not the Cause.
- Wrong: `Theme = cell` when the trigger governs a sensitivity event. Correct: `Theme = sensitivity event`.
- A plausible event with an unsupported nested edge must abstain from that edge, not invent it.

Do not change trigger, event type, participant text, or occurrence identity.
