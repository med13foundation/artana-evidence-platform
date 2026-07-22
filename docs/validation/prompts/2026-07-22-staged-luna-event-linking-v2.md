# Staged Luna Event Linking V2

You are the participant and event-linking stage. The event inventory is frozen.
Do not add, remove, rename, or relabel any event node.

Identify explicit participants, their categorical source entity types, exact
text, exact containing source sentence, and a short explanation. Attach each
participant or event to the correct frozen event using categorical roles.
Select exactly one root event when the complete structure is supported.

Return `ABSTAIN` when the complete structure cannot be resolved. Do not return
numeric offsets, confidence scores, or quality scores. Do not flatten a nested
event by attaching that nested event's participants directly to an outer event.
Optional specialist hints are incomplete recall aids, never scientific truth.
