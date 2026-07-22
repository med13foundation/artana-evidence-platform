# Source-First Scientific Event Construction

Read the permitted source passage independently. Construct every explicit
scientific event needed to represent the highlighted finding. Treat specialist
proposals only as fallible hints: accept, reject, correct, or extend them when
exact source evidence supports doing so.

For each event, identify its exact trigger and categorical event type. Create
separate participant nodes with source ontology entity types. Assign typed
arguments. When one event is an argument of another, target the event node rather
than attaching all of its entities directly to the outer event. Select exactly
one root event representing the complete highlighted finding.

Never add an event or participant that is plausible but not explicit in the
permitted passage. Return `ABSTAIN` when the complete structure cannot be
resolved. Do not return confidence, numeric quality scores, benchmark labels,
graph promotion decisions, or expected-answer commentary.

## Source-General Example: Simple Event

Source: `Protein A binds Protein B.`

Represent `binds` as one Binding event. Create separate Protein participants for
`Protein A` and `Protein B`, and attach both to the event with explicit
participant roles. The Binding event is the root.

## Source-General Example: Nested Event

Source: `Loss of regulator R causes expression of gene G.`

Keep three event nodes separate: the loss event, the expression event, and the
outer causal regulation event triggered by `causes`. The outer event points to
the loss and expression event nodes. It must not attach `regulator R` and
`gene G` directly as substitutes for those inner events.

The examples illustrate structure only. Their entities, wording, and event
inventory are unrelated to the experiment source.
