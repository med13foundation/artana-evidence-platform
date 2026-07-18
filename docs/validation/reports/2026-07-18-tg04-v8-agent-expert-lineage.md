# TG04 V8 Agent-Expert Gold Lineage

## Purpose

This receipt records how V8 gold was created before any Artana or Luna output
existed. It does not claim human-expert validation.

## Candidate Review

Two independent `gpt-5.6-sol` reviewers inspected all five remaining hidden
source units and their local BioNLP graphs. Both classified every corpus graph
as `INCOMPLETE`. The omissions included populations, treatment context,
comparators, directional trends, and statistical-significance scope.

The deterministic lowest-ranked source was selected before new gold was
authored:

`Although there was a trend, the transfection of CD4+ T cells with RUNX3 did not lead to statistically significant increase in FOXP3 (Fig. S5).`

## Independent Gold

Both reviewers independently required two claims:

1. A positive directional trend presented provisionally.
2. An asserted null result scoped only to statistical significance.

They also required RUNX3 as cause, FOXP3 as theme, CD4+ T cells as population,
the transfection as intervention context, and `statistically significant` as a
measurement argument.

A third `gpt-5.6-sol` adjudicator resolved categorical serialization against
Artana's actual closed schema. The only accepted projection difference is the
leading determiner in the intervention span.

## Scope

- Artana execution attempted: no.
- Luna output available to reviewers: no.
- Numeric LLM scoring used: no.
- Human-expert gold established: no.
- Trusted-graph promotion authorized: no.
- V8 repeat 1 authorized after code, lineage, and sequence gates pass: yes.

The machine-readable record contains reviewer run identities, candidate
decisions, source hashes, repository identity, adjudicated claims, and prohibited
interpretations.
