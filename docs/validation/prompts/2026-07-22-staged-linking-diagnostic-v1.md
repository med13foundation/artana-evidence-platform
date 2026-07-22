# Staged Linking Diagnostic V1

You are the participant and event-linking stage. The supplied event inventory is
immutable. Do not add, remove, rename, or relabel event nodes.

Using only the supplied source passage:

1. Identify every explicit participant needed by each frozen event.
2. Assign each participant a categorical biomedical entity type.
3. Attach participants to the correct event with categorical roles.
4. Attach events to other events when the source expresses nesting.
5. Keep inner-event participants attached to the inner event.
6. Select exactly one root event.
7. Return `ABSTAIN` if the complete structure cannot be established.
8. Never add unsupported participants or relations.

Return exact participant text and its exact containing source evidence. Do not
return numeric offsets, confidence scores, or numeric quality scores.

## Source-General Structural Example

Source: "Loss of enzyme E increases bacterial resistance to drug D."

`Loss` is one event involving enzyme E. `resistance` is another event-state
involving bacteria and drug D. `increases` is the outer event connecting the
loss and resistance event nodes. The outer event must not directly flatten
enzyme E, bacteria, and drug D into its own participant list.

The example is structural only. Use no entities, IDs, or answers from it in the
supplied source packet.
