# TG04 Role-First Exposed Probe V1 Outcome

Status: `STOP_ROLE_FIRST_V1`

This was a non-qualifying development regression on the already-exposed first
source from the V13-versus-V14 pilot. It changed no Artana product code.

## Execution

- Model: `openai:gpt-5.6-luna`
- Provider calls: `1` of a hard maximum of `2`
- Adapter retries: `0`
- Fallback/replay: `0`
- Graph writes: `0`
- Provider response: `resp_0381d16e3cc123e2006a5d916aa728819aad7b62b73b63f305`
- Result file SHA-256: `13e1089e382bdf4bc548da16f3d7095a138acee29eac024990ad85a6a27f5e7a`
- Internal report SHA-256: `a91dadd01931e09c1f29625c9a6e4cdd3a3458e149f3ff4c0ee3f3ee0ab891ff`

The primary output failed schema validation because its embedded child used
`CONTROLLED_TARGET` where the frozen exposed contract required a source-asserted
event. The audit observer preserved the failed payload and provider lineage. The
review call was not issued. Since the structured output was invalid, the artifact
has locally complete attempt custody but no retrieved-live provider receipt.

## Scientific Isolation

Changing only that child scope to `SOURCE_ASSERTED` made the raw payload
schema-valid in a provider-free diagnostic. Scientific reconstruction nevertheless
remained `0/2`, and the required outer regression remained false.

The generated child repeated the prior ontology error: it treated the cis-element
phrase as a transcription Theme, treated the DR-alpha promoter as Site, bundled S
and X2, and did not retain the cell context on the complete outer frame. The outer
CIITA-dependence idea was source-supported but controlled a malformed child.

## Decision

Role-first V1 did not earn the remaining untouched source, repeatability testing,
or product implementation. The bucketed schema removed invalid argument-level
event references but did not improve the underlying Theme/Site/event-multiplicity
decision.

This probe still asked one Luna call to compose complete events after generic
role-first instructions. It did not freeze a separate role-occurrence inventory
and deterministically expand role variants into events. The current prompt-level
architecture failed; the stronger two-stage role-inventory concept remains
untested.

The next experiment must use a genuinely different source-to-ontology mechanism
or a stronger-model arm on the identical categorical contract. It must pass on
exposed development sources before a new fresh holdout set is selected. The one
remaining frozen source remains untouched and cannot be reused as evidence after
any further adaptation based on it.
