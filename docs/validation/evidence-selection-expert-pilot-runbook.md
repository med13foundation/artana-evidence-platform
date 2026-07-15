# Evidence Selection Independent Expert Pilot Runbook

Status: packet generation and the fail-closed signed-review import path are
implemented; independent human review has not started.

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
- Pre-registered evaluation protocol:
  `scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_evaluation_protocol_v1.json`

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
attestations must bind a stable verified natural-person subject, qualification,
conflict-of-interest declaration, reviewer slot, Ed25519 public key,
credential-validity period, packet-publication hash, evaluation-protocol hash,
completion timestamp, and categorical findings. Reviewer private keys and the
issuer private key must remain outside Artana.

The externally signed reviewer registry is the study authorization. It contains
exactly three distinct subjects and keys: reviewer slots A and B plus
adjudicator/safety slot C. Artana receives only the signed registry, the pinned
issuer public key, and the issuer key ID.

## Import Workflow

Run every stage against the original no-replace packet publication. Artana
recomputes all intermediate artifacts; it never trusts uploaded gold or numeric
scores.

1. Verify both signed first-pass completions and generate only disagreements:

```bash
uv run python scripts/import_evidence_selection_expert_pilot_reviews.py \
  prepare-adjudication \
  --pilot-protocol scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_protocol_v1.json \
  --evaluation-protocol scripts/validation/evidence_selection/fixtures/semantic_relevance_expert_pilot_evaluation_protocol_v1.json \
  --packet-publication reports/human-shadow-study/semantic-relevance-expert-pilot-v1 \
  --reviewer-registry /secure/path/signed-reviewer-registry.json \
  --issuer-public-key-hex "$EXPERT_PILOT_ISSUER_PUBLIC_KEY_HEX" \
  --issuer-key-id "$EXPERT_PILOT_ISSUER_KEY_ID" \
  --first-pass-completions /secure/path/first-pass-completions \
  --output-dir reports/human-shadow-study/pilot-v1-adjudication-request
```

2. After slot C signs the generated adjudication request, freeze gold and
generate the post-gold safety request:

```bash
uv run python scripts/import_evidence_selection_expert_pilot_reviews.py \
  prepare-safety-audit \
  <the same common arguments> \
  --adjudication-completion /secure/path/adjudication-completion.json \
  --output-dir reports/human-shadow-study/pilot-v1-safety-request
```

Omit `--adjudication-completion` only when the generated request contains zero
items. Slot C cannot see model claims until the adjudicated gold hash is frozen.

3. After slot C signs categorical safety findings, recompute and publish the
diagnostic result:

```bash
uv run python scripts/import_evidence_selection_expert_pilot_reviews.py \
  finalize \
  <the same common arguments> \
  --adjudication-completion /secure/path/adjudication-completion.json \
  --safety-completion /secure/path/safety-completion.json \
  --output-dir reports/human-shadow-study/pilot-v1-verified-result
```

Every output directory is atomic and no-replace. A modified packet, sidecar,
manifest, roster, signature, completion inventory, timestamp, literal span,
adjudication item, gold hash, model-run artifact, or safety item fails before
result publication.

## Predeclared Evaluation

Deterministic code will compute metrics from categorical findings after
attestation. The frozen pilot thresholds are:

- adjudicated precision at least `0.80`;
- adjudicated recall at least `0.80`;
- first-pass percent agreement at least `0.80`;
- high-severity overclaim count exactly `0`.

No threshold may be changed after first-pass review begins. A threshold change
requires a new protocol version and new first-pass reviews.

The evaluation protocol also preserves the stricter PR150 diagnostic gates:
worst-run decision coverage, per-case precision/recall/coverage, canary safety,
and exact three-run repeatability. It binds all six existing PR150 live-agent
run hashes before human review. Embedded PR150 scores are ignored; predictions
are rescored against signed expert gold. Because agents saw sanitized source
snapshots while experts receive complete PubMed abstracts, this is an
end-to-end diagnostic re-score, not an isolated same-input model comparison.

PR154 never selects a production model. A real result can correct the benchmark
and show which diagnostic gates pass, but model adoption requires a later live
comparison with the corrected benchmark, complete runtime telemetry, and the
existing adoption policy.

## Scale Boundary

This pilot has three distinct research questions and 33 records. Production
calibration remains unavailable. A calibration study requires at least 20
questions and 200 records, with at least 12 questions frozen for training and 8
different questions held out before review begins.

Until real externally signed reviewer, adjudication, and safety artifacts pass
this importer, benchmark v2 continues to report zero expert-eligible records.
