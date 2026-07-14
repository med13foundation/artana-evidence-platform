# Evidence Selection Independent Expert Pilot Runbook

Status: packet generation is implemented; independent human review has not
started.

This run is a diagnostic pilot over three distinct research questions, four
benchmark cases, and 33 candidate records. It can correct the benchmark and
support a new model-comparison decision. It cannot establish production
calibration or trusted-graph readiness.

## Frozen Inputs

- Protocol:
  `scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_protocol_v1.json`
- Benchmark:
  `scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json`
- Supplemental-source manifest:
  `scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_supplement_manifest_v1.json`

The historical v1 benchmark and its original source snapshots remain unchanged.
The pilot freezes content-addressed NCBI PubMed metadata and abstracts for all
29 unique sources used by the 33 benchmark records. Every reviewer candidate is
built from that independent source inventory; benchmark-authored excerpts are
never substituted into reviewer packets. These snapshots do not assert a label
or claim that a packet is sufficient; sufficiency remains a human categorical
finding.

## Generate Packets

Use a producer-held signing key that reviewers cannot access:

```bash
export ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY=...
uv run python scripts/build_evidence_selection_expert_pilot_packets.py \
  --protocol scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_protocol_v1.json \
  --output-dir reports/human-shadow-study/semantic-relevance-expert-pilot-v1
```

Publication is atomic and refuses to overwrite an existing directory. It emits:

- `reviewer_packets/<reviewer-slot>/<blinded-case-id>.json`: blinded editable
  packets with uniform source-section labels.
- `machine_sidecars/<reviewer-slot>/<blinded-case-id>.json`: signed candidate
  mappings to the private benchmark case and record identities.
- `publication_manifest.json`: inventory hashes for all 16 packet and sidecar
  artifacts. The signed machine sidecars, not the manifest, are the tamper
  boundary.

Distribute only each reviewer's own `reviewer_packets` directory. Keep machine
sidecars with the study operator. First-pass reviewers must not receive the
historical case identifiers, historical expected labels, AI diagnostics, model
identity, harness decisions, ranking values, other reviewer packets, or
sidecars.

## Human Findings

Each candidate requires these human-owned categorical findings:

- `selection_label`: `select`, `reject`, or `abstain`.
- `packet_sufficiency`: `sufficient` or `insufficient`.
- literal supporting spans from the bounded packet.
- a language explanation tied to the frozen inclusion and exclusion criteria.

Reviewers must not provide confidence, relevance, explanation-quality, or
readiness numbers. Agents may organize artifacts but cannot fill reviewer-owned
fields or act as the gold-label author.

Two externally authenticated, domain-qualified humans review every record
independently. A third qualified human adjudicates every disagreement. External
attestations must bind the real reviewer identity to reviewer slot, packet hash,
case, candidate inventory, source hashes, completion timestamp, and categorical
findings.

## Predeclared Evaluation

Deterministic code will compute metrics from categorical findings after
attestation. The frozen pilot thresholds are:

- adjudicated precision at least `0.80`;
- adjudicated recall at least `0.80`;
- first-pass percent agreement at least `0.80`;
- high-severity overclaim count exactly `0`.

No threshold may be changed after first-pass review begins. A threshold change
requires a new protocol version and new first-pass reviews.

## Scale Boundary

This pilot has three distinct research questions and 33 records. Production
calibration remains unavailable. A calibration study requires at least 20
questions and 200 records, with at least 12 questions frozen for training and 8
different questions held out before review begins.

The next PR must implement completed-packet import and external attestation
verification. Until that PR receives real reviewer artifacts, benchmark v2 must
continue to report zero expert-eligible records.
