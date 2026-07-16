# TG-01 Truthful Safety Floor

Date: 2026-07-14

Plan: TG-01

Branch: `alvaro/trusted-claims-tg01-truthful-safety`

Foundation parent: `176e5fe2fdac15437ac6c97a0d1c1d9685694359`

Implementation commit: `3d2c06b03ef2d493ddcfd7d05b6d608312e4670d`

Model: `openai:gpt-5.6-luna`

## Decision

**TG-01 safety gate: PASS. Overall trusted-graph readiness: NOT READY.**

Heuristic support, unavailable verification, forged verifier-origin metadata,
symbolic ClinVar identifiers, and Unicode-digit identifier variants cannot
satisfy trusted evidence floors. A non-trusted candidate remains available for
human review, so fail-closed enforcement does not erase potentially useful
evidence.

Trusted candidates are intentionally quarantined at zero until a later PR adds
a server-owned, independently verifiable agent-verification receipt. Zero is a
truthful safety result here; it is not evidence that extraction quality is
ready. This work makes no human-expert or clinical-validity claim.

## Hypothesis And Root Cause

Hypothesis: if semantic verification origin and identifier authority are
enforced by both services, unsafe evidence will no longer receive trusted
credit even when caller-controlled metadata imitates a valid result.

Root cause: the previous trust checks accepted a result shape. They did not
prove who produced semantic verification, and fixture/local dictionary values
could make symbolic ClinVar placeholders appear authoritative. The benchmark
also credited heuristic entailment toward trusted metrics.

## Implementation

- Label support verification as `agent`, `heuristic`, or `unavailable` at the
  verifier boundary.
- Require `agent` origin for trusted semantic floors and trusted benchmark
  metrics.
- Quarantine Graph DB trusted promotion until Graph DB can verify a
  server-owned receipt; caller metadata alone cannot unlock it.
- Validate identifier syntax at both service boundaries, including ASCII-only
  ClinVar Variation IDs and accessions.
- Move symbolic ClinVar entries from the verified dictionary and gold fixtures
  into the review-only lane.
- Preserve non-trusted heuristic candidates for review and persistence.

TG-02 separately owns authoritative source identity and exact source locators.
Those concerns were not folded into this PR so each safety boundary remains
independently testable.

## Deterministic Test Evidence

The final adversarial matrix passed 327 tests. It covered verifier-origin
forgery, symbolic and Unicode identifier attacks, zero trusted credit from
heuristics, benchmark fixture validation, service validation, and live Graph DB
persistence of reviewable non-trusted evidence.

```bash
uv run pytest -q \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  services/artana_evidence_api/tests/unit/test_identifier_authority.py \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_db/tests/unit/test_identifier_authority.py \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_fixture_validation.py \
  tests/e2e/artana_evidence_api/test_live_graph_promotion.py::test_promote_proposal_persists_claim_through_live_graph_service

make service-checks
```

`make service-checks` passed with repository coverage of 87.55%, above the 86%
required floor. Pre-commit API/Graph lint and type checks also passed without
skipping hooks.

## Strict Luna Runs

The frozen v4 fixture contains 100 cases. The same model, extractor, fixture,
and no-fallback policy were used three times.

```bash
ARTANA_AI_EVIDENCE_EXTRACTION_MODEL=openai:gpt-5.6-luna \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-01
```

Runs 02 and 03 used the same command with only the output directory changed.
No run used `--allow-fallback`.

| Metric | Run 01 | Run 02 | Run 03 | Gate meaning |
|---|---:|---:|---:|---|
| Agent completion | 100/100 | 100/100 | 100/100 | PASS |
| Precision | 1.0000 | 1.0000 | 0.9714 | Diagnostic |
| Recall | 0.9333 | 0.9067 | 0.9067 | Diagnostic |
| High-value recall | 0.9200 | 0.9000 | 0.9000 | Diagnostic |
| Valuable rate | 0.5571 | 0.5588 | 0.5429 | Below target |
| Generic rate | 0.3571 | 0.3529 | 0.3571 | Above target |
| Verified CURIE match | 0.7532 | 0.7532 | 0.7532 | Below target |
| Entailment checked | 1.0000 | 1.0000 | 0.9787 | Below target in run 03 |
| Fallback / invalid / negative leakage | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Trusted candidates | 0 | 0 | 0 | Intentional quarantine |
| Verdict | RED | RED | RED | Overall system not ready |

Readiness aggregation:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-01 \
  --report reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-02 \
  --report reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-03 \
  --output-dir reports/relation_feasibility_readiness/2026-07-14-tg01-truthful-safety
```

The aggregate status is `not_ready`. All eight hard-failure counters are zero.
The blockers are the intentionally empty trusted lane plus valuable-rate,
generic-rate, grounding, and one-run entailment-coverage gaps. These become
inputs to TG-02 through TG-08; they are not reasons to weaken TG-01.

## Adversarial Review

An independent Codex reviewer found four bypasses in the first implementation:

1. Graph DB could accept caller metadata relabeled as agent verification.
2. Benchmark trusted metrics still used heuristic support.
3. Evidence API trust accepted symbolic CURIE metadata.
4. `\d` identifier matching accepted non-ASCII Unicode digits.

Each root cause was fixed and retested. The reviewer then returned no remaining
actionable finding and independently confirmed that forged trust is
quarantined, heuristic support receives zero trusted credit, CURIE protections
hold, and reviewable evidence remains persistable. Two attempts to obtain an
additional Claude CLI review did not return a result and were stopped; they are
not counted as review evidence.

## Artifact Manifest

Fixture:

- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`
  - SHA-256: `78f255fb0e842517c2c0a3155f224bf177797730a76142f24925cf2e8660350b`

Raw run JSON:

- Run 01: `reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-01/relation_feasibility_report.json`
  - SHA-256: `515f35d60ca069502f7d60518e29a90ab8adf6ddc3ce60b105bd749a126af12c`
- Run 02: `reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-02/relation_feasibility_report.json`
  - SHA-256: `0c0f6095f909021c7b6a4ebb69c02e1428d00fa5a85ce1f5afed4784742aa224`
- Run 03: `reports/relation_feasibility/2026-07-14-tg01-truthful-safety-run-03/relation_feasibility_report.json`
  - SHA-256: `d3a32e0c80cb20cc32be03e665043caaaad7f29a5edb2b2b4e26ca473d04179c`
- Aggregate: `reports/relation_feasibility_readiness/2026-07-14-tg01-truthful-safety/relation_feasibility_readiness_report.json`
  - SHA-256: `d0ac15fd3a532066aef0d42feabafaeff5b1fbf7a08072bcccf0f24e26ff2eb1`

Raw generated reports remain in the ignored `reports/` workspace tree. Their
content hashes are frozen here; this tracked report is the review record.

## Next Gate

TG-02 must establish authoritative source identity and an exact, resolvable
locator for every promotion-eligible claim. It must not make heuristic support
trusted or unlock the Graph DB quarantine introduced here.
