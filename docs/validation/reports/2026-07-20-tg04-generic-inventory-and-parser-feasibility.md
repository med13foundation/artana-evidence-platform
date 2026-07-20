# TG04 Generic Inventory And Parser Feasibility

Generic-inventory disposition: `INVALID_FOR_SCIENTIFIC_COMPARISON`

Parser-feasibility disposition: `USEFUL_PROPOSAL`

Qualification eligibility: `false`

This checkpoint records two exposed development probes. Neither changed Artana product code, wrote to the graph, or released an untouched source.

## Generic Inventory V1

The generic-inventory panel stopped after its first Sp1/Sp3 binding source. Both Sol calls completed with verified provider receipts and no fallback. Both arms preserved `Sp1` and `Sp3` as separate binding participants.

The comparison is not valid scientific evidence:

- execution began before the independent preflight completed;
- the candidate and baseline were scored on asymmetric representations;
- the candidate contract narrowed the event label space to the exposed panel; and
- an invalid baseline could still permit the runner's readiness outcome.

The source-only content review remains operationally informative. It judged the baseline events entailed and role-valid. It vetoed the inventory projection because the compiler demoted the source-explicit `A3G promoter` from a site to opaque context. The exact benchmark failure primarily reflected BioNLP's gene-centered projection and an exact-boundary scorer, not invented biology.

The honest result is `STOP_GENERIC_INVENTORY`. No gain is claimed from this run.

## Established Parser Feasibility

The next lane used the official pretrained DeepEventMine GE11 model, not a new Artana schema or deterministic biomedical extractor.

### Lineage and execution

- official source commit: `e1c56013b4241e06c1cbe00992546367e4699036`;
- GE11 archive publisher/local MD5: `27a6fd0a40cac4610646560971db8c8b`;
- Docker image: `sha256:84aecdb25d2336d3ae48514dcc75fc7e2e075c42a9276763895192909e973100`;
- Python `3.6.15`, PyTorch `1.1.0`, scikit-learn `0.21.3`;
- raw-text and end-to-end entity modes enabled;
- supplied gold/entity annotations: `0`;
- scientific predictions: `1`;
- retries: `0`;
- exit status: `0`.

The historical scikit-learn pin was required only to deserialize the publisher checkpoint. A model-load smoke passed before the scientific prediction; official parser logic was not modified.

### Raw result

```text
T1 Protein 0 3 Sp1
T2 Protein 8 11 Sp3
T3 Binding 12 16 bind
E1 Binding:T3 Theme:T1
E2 Binding:T3 Theme:T2
```

The parser recovered the exact trigger and kept the two proteins separate. It omitted the GC-box target/site and the A3G promoter context.

An independent source-only reviewer, blind to Luna and benchmark gold, assigned `USEFUL_PROPOSAL`: both events were entailed, all spans were verbatim, roles did not contradict the sentence, and unsupported claims were zero. The proposal is useful for an agent to correct or extend.

## Decision

The generic semantic-inventory branch does not advance. The established-parser hybrid does advance to one controlled exposed comparison.

The next experiment uses identical Sol contracts on both arms. Only the candidate receives the parser proposal. It must improve complete-event recovery or participant-role fidelity without increasing unsupported claims. This feasibility result is not scientific qualification and does not change Artana's review-only status.
