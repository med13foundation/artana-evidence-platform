# PR153 Independent Expert Pilot Validation

Date: 2026-07-14

Branch: `alvaro/evidence-pr153-expert-pilot`

## Result

PR153 implements a diagnostic-only, blinded expert-review handoff for benchmark
v2. It does not create expert labels, production calibration, or a trusted-graph
readiness claim.

The generated pilot contains:

- 3 distinct research questions;
- 4 blinded cases;
- 33 benchmark records;
- 29 content-addressed NCBI PubMed source snapshots;
- 2 independently ordered reviewer slots;
- 8 reviewer packets and 8 signed machine sidecars;
- 66 categorical candidate reviews awaiting qualified humans.

Every reviewer candidate is built from the frozen PubMed source inventory. The
builder has no benchmark-excerpt or agent-generated evidence fallback. Missing,
extra, hash-drifted, or identity-drifted source snapshots fail before packet
construction.

## Trust Boundaries

- Reviewer packets expose neutral case and candidate identifiers only.
- Historical case IDs, expected labels, model identity, AI diagnostics, harness
  decisions, rankings, and machine mappings remain outside reviewer packets.
- Free-text criteria fail closed on known blinded-context markers.
- Human findings are categorical. Agents cannot fill reviewer-owned labels or
  author numeric judgments.
- Signed sidecars bind the packet hash, protocol and source hashes, private case
  identity, candidate order, and every candidate-to-record mapping.
- Publication verifies every bundle, stages all artifacts, and uses an atomic
  no-replace rename so failure or a racing destination cannot expose partial or
  overwritten output.
- `publication_manifest.json` is an inventory. Signed sidecars are the current
  tamper boundary.

## Validation Evidence

- Focused benchmark, pilot, CLI, and CI-planner regressions: 59 passed.
- Live packet generation: 8 packet/sidecar pairs and 66 candidate reviews.
- Live packet parse, source binding, and signature verification: passed for all
  8 pairs and all 66 reviews.
- Reviewer blinding scan: no historical case IDs, expected-label keys, model or
  ranking keys, harness keys, or historical excerpt markers.
- Frozen benchmark v2 gate: passed; 33 visible records, 0 score-eligible records,
  expert study still pending.
- `make artana-evidence-api-service-checks`: passed, including Ruff, strict mypy
  over 567 source files, boundary and contract checks, architecture checks,
  migrations, and the full isolated-PostgreSQL Evidence API test suite.

## Adversarial Loop

The first independent review found historical case-name leakage, source-section
priming, missing pre-publication verification, and a destination-replacement
race. Those issues were fixed with reviewer-specific neutral case IDs, uniform
source presentation, bundle verification, and atomic no-replace publication.

The second review found that uniform presentation still mixed 30
benchmark-authored excerpts with 3 independent PubMed abstracts. PR153 then
replaced that mixed path with complete content-addressed PubMed coverage for all
29 unique sources and added a hard complete-inventory gate. It also added a
producer-side narrative leakage check.

The final independent review found no remaining merge blocker.

## Remaining Work

Two real, externally authenticated domain experts must independently review all
records, and a third qualified human must adjudicate disagreements. A follow-up
PR must verify external attestations, import completed categorical findings,
compute deterministic metrics, and keep benchmark records ineligible unless the
entire trust chain passes.

Shared-HMAC producer custody and external attestation verification remain
explicit next-boundary work. Until real human artifacts pass that boundary,
production readiness and production calibration remain false.
