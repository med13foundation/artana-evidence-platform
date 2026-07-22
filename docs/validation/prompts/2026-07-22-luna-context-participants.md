# Participant Inventory

For every target event, identify only source-explicit participants needed for that event. Use the structured paragraph and document context to resolve references, but every returned participant must use exact text and an occurrence from the permitted evidence scope. Do not copy the broad class and its specific instance as separate participants unless the source asserts both roles independently. Return `ABSTAIN` when the reference remains ambiguous.

Synthetic examples:

- `Cells were treated. These cells died.`: the nearby antecedent may identify `These cells`; cite the exact local occurrence used by the event.
- `A activates A in A-positive cells.`: occurrence IDs distinguish repeated `A` mentions; choose the occurrence governed by the trigger.
- `It increased.` with two possible antecedents: `ABSTAIN`.

Do not infer roles, nesting, modifiers, or gold answers.
