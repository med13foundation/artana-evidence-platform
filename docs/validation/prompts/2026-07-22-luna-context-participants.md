# Participant Inventory

For every target event, identify only source-explicit participants needed for that event. Use the shared source and adjacent sentences to resolve references. Every participant must include exact source text, absolute start and end offsets, an event-local occurrence ID, a categorical source entity type, and a short source-based explanation. New participants are allowed. Every span must remain inside the event's permitted evidence offsets. Return `ABSTAIN` when required evidence is absent or ambiguous.

Schema-shaped synthetic examples:

- Source `Kinase A was measured. It increased.` with local offsets may return `{"exact_text":"It","start":23,"end":25,"occurrence_id":"occurrence-0","candidate_target_kind":"PARTICIPANT","source_entity_type":"Gene_or_gene_product"}` when the adjacent antecedent is unique.
- Source `A activates A; it also activates B. It increased.` must use distinct offset-bound occurrences for repeated `A`; if `It` has multiple plausible antecedents, return an `ABSTAIN` inventory with no participants.

Do not infer roles, nesting, modifiers, or gold answers. Do not provide chain-of-thought or numeric confidence.
