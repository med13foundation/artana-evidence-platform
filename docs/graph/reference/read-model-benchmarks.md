# Graph Read-Model Benchmarks

This document records the current benchmark comparisons for graph-core
read models and reasoning indexes.

## Command

Phase 4 generic read-model benchmark:

```bash
make graph-read-model-benchmark
```

Phase 5 reasoning-index benchmark:

```bash
make graph-reasoning-index-benchmark
```

Both targets run focused isolated-Postgres benchmark slices in
`tests/performance/test_graph_query_performance.py`.

## Latest Measurements

Measurement date: `2026-03-13`

Environment:

- isolated ephemeral Postgres test database
- deterministic graph seed with `600` claim-backed relations
- neighborhood workload executed through the normal application read path

Neighborhood comparison:

- fallback canonical traversal median: `50.62 ms`
- indexed `entity_neighbors` median: `11.42 ms`
- observed speedup: `4.43x`

Evidence drilldown:

- measured relation-evidence drilldown latency: `1.64 ms`
- the same benchmark slice enforces a `1.0 s` latency budget for that path

Reasoning index comparison:

- legacy reasoning-seed read median: `313.92 ms`
- indexed `entity_mechanism_paths` median: `5.93 ms`
- observed speedup: `52.92x`

## Interpretation

- The first generic read-model set is now justified by measured read latency,
  not just architectural intent.
- `entity_neighbors` is the clearest Phase 4 win because one-hop graph reads
  now avoid repeated canonical relation plus projection-existence traversal.
- The first reasoning index is also justified by measured runtime cost:
  hypothesis-style seed reads no longer fan out through `list_paths(...)`,
  `get_path(...)`, and per-endpoint lookups for every candidate path.
- Further benchmark work in later phases should focus on richer mechanism
  ranking and path-selection workloads rather than re-proving the same compact
  seed-read path.
