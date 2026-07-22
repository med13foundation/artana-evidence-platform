# Stage 2: Participant Inventory

Use only the supplied event-local passages. For every event ID, inventory every
explicit participant needed by that event. Copy exact participant text, assign
a local participant key, classify it as a direct source entity or a reference
to another discovered event, and give a short source-based explanation.

For direct entities, select the exact categorical source entity type. For event
targets, leave the entity type empty. Do not assign semantic roles. Do not use
text outside the event passage. Preserve distinct spans and repeated
participants. Return ABSTAIN for an event when a required participant is absent
or ambiguous; never borrow a matching mention from another passage.
