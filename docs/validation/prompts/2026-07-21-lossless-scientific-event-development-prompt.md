# Lossless Scientific Event Development Prompt

You are extracting a complete scientific event graph from one biomedical
abstract. Use only the supplied abstract. Do not use outside knowledge.

Return every explicit scientific event, including unary events and events that
refer to other events. Do not flatten nested events into binary relations. Do
not merge participants that occupy separate source spans or repeated roles.

For every event, return:

- a local event annotation identifier;
- one source event type selected from the supplied categorical vocabulary;
- an optional Artana event family only when the source explicitly supports it;
- the exact trigger text and its half-open source character offsets;
- zero, one, or many arguments, each with its exact source role and a typed
  participant or event reference;
- each direct participant's exact text and half-open source offsets;
- event-local negation and speculation.

Permitted source event types:

`Acetylation`, `Amino_acid_catabolism`, `Binding`,
`Blood_vessel_development`, `Breakdown`, `Carcinogenesis`, `Catabolism`,
`Cell_death`, `Cell_differentiation`, `Cell_division`, `Cell_proliferation`,
`Cell_transformation`, `DNA_methylation`, `Death`, `Dephosphorylation`,
`Development`, `Dissociation`, `Gene_expression`, `Glycolysis`, `Growth`,
`Infection`, `Localization`, `Metabolism`, `Metastasis`, `Mutation`,
`Negative_regulation`, `Pathway`, `Phosphorylation`, `Planned_process`,
`Positive_regulation`, `Protein_processing`, `Regulation`, `Remodeling`,
`Synthesis`, `Transcription`, `Translation`, `Ubiquitination`.

Permitted source argument roles:

`AtLoc`, `CSite`, `Cause`, `FromLoc`, `Instrument`, `Participant`, `Site`,
`Theme`, `ToLoc`. Repeated roles remain separate arguments; append their source
ordinal when needed, such as `Theme2` or `Participant3`.

Return `ABSTAIN` for a proposed event when its trigger, type, participant, role,
or nested reference is not source-supported. Never invent a missing participant
to satisfy an arity requirement. Never use `OTHER_EXPLICIT` for an unsupported
or uncertain source category.

The execution harness supplies the abstract, source hash, document identifier,
schema, categorical vocabulary, and immutable lineage fields separately. It
calculates offsets, reference consistency, custody hashes, and exact metrics
deterministically; it never chooses or relabels scientific meaning.
