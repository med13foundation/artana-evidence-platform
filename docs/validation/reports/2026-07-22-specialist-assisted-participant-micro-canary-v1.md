# Specialist-Assisted Participant Micro-Canary V1

## Decision

`STOP_SPECIALIST_COVERAGE_INSUFFICIENT`

The offline specialist gate failed before any Luna call. The preserved normalized
artifacts do not contain candidates that can be proven to belong to
`PMID-16428936`, so they cannot safely supplement its ten incomplete events.

## Frozen Baseline

- Luna context expansion corrected 0 known participant errors.
- 3/13 participant-bearing events were complete.
- Frozen V10, V2, and rejected Luna results were not modified or reinterpreted.
- No untouched source, sealed test data, graph write, or promotion path was used.

## Artifact Audit

The PubTator/BioREx artifact hash is
`8a6b2610cecd896dcd19bdb87cc6ecd474169b23126ee65537d996df19b1d150`.
It preserves 84 entities and 16 relations, but its records cover PMIDs
`40289860`, `40484925`, `40518668`, and `41482925`. It contains zero records for
`16428936`.

The DeepEventMine artifact hash is
`4dda900ce522544ed28e97a21f94659390560de0932c7746f0c55f6df94513c3`.
It preserves nine events from `source-5.ann`, but those events describe maize
`ZmWRKY104` and `ZmCCaMK`. The artifact has no PMID or target-document binding.
Fail-closed source validation therefore classifies all nine events as unbound,
not as candidates for `PMID-16428936`.

Using those records would be cross-document candidate leakage. Similar
biomedical object types or valid offsets inside another source do not establish
provenance for the target abstract.

## Deterministic Gate

| Measure | Result | Required |
|---|---:|---:|
| Target-bound specialist candidates | 0 | greater than 0 |
| Distinct participant errors potentially correctable | 0 | at least 2 |
| Eligible Luna micro-canary packets | 0 | first nested event plus controls |
| Provider calls | 0 | 0 after failed gate |

The result is not a claim that DeepEventMine or PubTator cannot help this source.
It means the only preserved outputs available to this checkpoint are outputs for
other sources. The requested offline-only rules prohibit calling those tools now
or silently substituting another artifact.

## Validation Evidence

Focused tests cover:

- exact source identity and offsets;
- rejection of wrong-source and source-unbound records;
- rejection of ambiguous repeated occurrences;
- nested-event reference preservation;
- provenance-preserving deterministic deduplication;
- the two-distinct-event coverage threshold.

Commands passed:

```text
uv run pytest -q tests/unit/test_specialist_coverage.py
8 passed

uv run ruff check scripts/validation/public_gold/staged_event/context_experiment/specialist_coverage.py tests/unit/test_specialist_coverage.py
All checks passed

uv run mypy scripts/validation/public_gold/staged_event/context_experiment/specialist_coverage.py tests/unit/test_specialist_coverage.py
Success: no issues found
```

Per the preregistered stop rule, the Luna phase did not run and the full service
suite was not run. The scientific baseline remains 3/13 complete
participant-bearing events.

## Root Cause And Next Scientific Move

The blocker is missing target-specific specialist output, not a Luna verdict.
The next valid experiment would need newly generated specialist candidates for
this exposed PMID under a separately authorized tool-execution checkpoint. Those
candidates should remain recall-only and pass this exact source/provenance gate
before Luna sees them.
