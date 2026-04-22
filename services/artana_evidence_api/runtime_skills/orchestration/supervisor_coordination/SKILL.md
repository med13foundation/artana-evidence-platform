---
name: graph_harness.supervisor_coordination
version: 1.0.0
summary: Coordinate bootstrap, briefing, and curation steps while keeping child workflows scoped and auditable.
tools: []
---
Coordinate child workflows deliberately.

Decide which child step should run next, what question it should answer, and what artifact or
proposal should be handed off downstream.

Prefer clear sequencing, explicit stop conditions, and small child scopes over broad parallel
work.
