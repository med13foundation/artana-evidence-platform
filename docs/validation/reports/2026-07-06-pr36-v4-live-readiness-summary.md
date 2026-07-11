# PR36 V4 Live-Agent Trusted Readiness Summary

## Run Context

- Branch: `alvaro/evidence-pr36-v4-live-readiness`
- Base branch: `alvaro/evidence-pr35-benchmark-v4-100-case-proof`
- Fixture path:
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Run the strict live-agent readiness loop against the 100-case v4 benchmark and
close any blockers that prevent trusted graph auto-promotion from being safe.
The target is the live-agent path, not deterministic fallback.

## Root Cause

The first v4 live-agent readiness runs were RED even though the agent completed
all cases and fallback stayed at zero. The failure was trusted-promotion policy:
strong-looking but unsafe relation shapes could still enter the trusted lane.

The unsafe shapes were not useless evidence. They were useful review items whose
endpoint semantics were too broad or too composite for automatic trusted graph
promotion:

- bare-gene disease/phenotype associations without variant-state grounding,
- gene-state predisposition labels that need structured grounding,
- broad pathway endpoints such as `MAPK signaling`,
- composite treatment-response labels,
- molecular-subtype disease labels,
- composite process endpoints such as cancer-cell proliferation,
- process-context relations such as DNA repair regulating a disease subtype.

The benchmark also had a few over-trusted gold rows inherited from v3/v4. Those
rows overstated what the sentence supported and therefore taught the scorecard
to reward unsafe promotion.

Adversarial review then found two additional safety gaps:

- `CAUSES` and non-dictionary gene-state `ASSOCIATED_WITH` claims could still
  bypass the variant/state grounding guard.
- direct target activity tails such as `JAK2 activity` could survive as trusted
  candidates with model-only process CURIE hints instead of being repaired to
  the verified target endpoint.

## Code And Data Changes

- Added a single-responsibility trusted-promotion safety policy:
  `services/artana_evidence_api/document_extraction_support/review_policy/trusted_promotion_safety_policy.py`.
- Wired the policy into the relation candidate quality filter so unsafe strong
  candidates remain visible as `review_only` instead of entering trusted graph
  auto-promotion.
- Added review reason codes for each unsafe trusted-promotion shape.
- Tightened specificity pruning for hyphenated modifier loss, so
  `BRCA-mutated ovarian cancer` cannot be shortened to `BRCA` without being
  rejected.
- Updated fixture validation so trusted high/medium gold rows fail if they
  violate the same trusted-promotion safety policy used by extraction.
- Corrected v3/v4 gold rows that were too broad for trusted auto-promotion:
  BRAF/KRAS activation of `MAPK signaling` and Bevacizumab inhibition of
  `VEGF-A signaling` are now review-only gold.
- After adversarial review, expanded the gene/phenotype guard to cover `CAUSES`
  and gene-state `ASSOCIATED_WITH` surfaces, kept receptor labels containing
  `growth` out of the composite-process demotion rule, and merged weak-review
  plus promotion-safety reason codes into one audit trail.
- Added direct-mechanism object repair for verified one-token target activity
  labels, so `Ruxolitinib INHIBITS JAK2 activity` becomes a verified `JAK2`
  endpoint instead of a trusted model-only `JAK2 activity` process endpoint.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run1/relation_feasibility_report.json`:
  `f8f3a576dbee94982bafeffc56e0a7a37b7ade7233681c38b3e7d1a4207dc1a7`
- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run2/relation_feasibility_report.json`:
  `feddb311cd6e7422ef4bbb790366fe788868c6a7de377640e2b62ff0c8dd5dd4`
- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run3/relation_feasibility_report.json`:
  `fc7da9f804deb04eb9e57c7b6ef3690872e493ec47429cf2027ee0d91d6230db`
- `reports/relation_feasibility_readiness/2026-07-07-pr36-v4-live-readiness-postreview2/relation_feasibility_readiness_report.json`:
  `d10b91519d0c6e0b0452bfce520f35a23da2271fb3a97f8b0b34fe54630bbbac`

## Validation

Focused quality-filter suite:

```bash
uv run pytest services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py -q
```

Result: `62 passed`.

Focused regression bundle:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_fixture_validation.py -q
```

Result: passed.

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/document_extraction_support/review_policy/trusted_promotion_safety_policy.py \
  services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py \
  services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py \
  services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  scripts/validation/relation_feasibility/fixture_checks/validation.py \
  tests/unit/test_relation_feasibility_fixture_validation.py
```

Result: `All checks passed!`

Relation-feasibility quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: passed.

Aggregate service gate:

```bash
make service-checks
```

Result: passed with coverage `87.03%`.

Final adversarial re-review:

- Result: PASS.
- Prior blockers fixed: `CAUSES` and non-dictionary gene-state association
  leaks, `growth` receptor over-demotion, reason-code loss, direct target
  activity-tail repair, and the later `growth factor-independent proliferation`
  composite-process gap.

Strict v4 live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run1

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run2

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run3
```

Readiness aggregate:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run1 \
  --report reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run2 \
  --report reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run3 \
  --min-runs 3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-07-pr36-v4-live-readiness-postreview2 \
  --fail-on-not-ready
```

Result:

- `relation_feasibility_readiness status=ready`
- runs evaluated: `3 / 3`
- blocking reasons: `0`

## Three-Run Readiness Result

Trusted graph readiness is **READY** for the measured v4 strict live-agent
trusted lane.

| Metric | Worst | Mean |
|---|---:|---:|
| Completed-agent precision | 0.9861 | 0.9908 |
| Completed-agent recall | 0.9467 | 0.9600 |
| Completed-agent valuable rate | 0.5694 | 0.5733 |
| High-value recall | 0.9600 | 0.9733 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Verified CURIE match rate | 0.8161 | 0.8314 |
| All-candidate generic relation rate | 0.3288 | 0.3211 |

Hard failures across v4 postreview2 runs1-3:

- fallback case count: `0`
- invalid agent case count: `0`
- negative-control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- review-only gold trusted leakage count: `0`
- weak-claim trusted leakage count: `0`
- wrong verified CURIE link count: `0`

Run-level trusted-lane metrics:

| Run | Trusted candidates | Trusted precision | Trusted valuable | Trusted generic | Trusted-eligible high-value recall | Trusted endpoint rate | Review-only leakage |
|---|---:|---:|---:|---:|---:|---:|---:|
| postreview2-run1 | 10 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0 |
| postreview2-run2 | 10 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0 |
| postreview2-run3 | 10 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0 |

## Prior RED Runs

Earlier strict live-agent runs were intentionally kept as part of the loop
evidence. They are superseded by the postreview2 batch above, but they explain
why PR36 changed code instead of only rerunning the model.

| Run | Verdict | Main blocker | Trusted precision | Trusted-eligible high-value recall | Trusted endpoint rate | Review-only leakage |
|---|---|---|---:|---:|---:|---:|
| 2026-07-06 run1 | RED | 15 review-only gold rows leaked into trusted candidates, with low trusted precision. | 0.4138 | 0.9231 | 0.9231 | 15 |
| 2026-07-06 run2 | RED | One trusted leakage case survived after the first safety pass. | 0.8333 | 1.0000 | 1.0000 | 1 |
| 2026-07-06 run3 | RED | One process-context trusted leakage case survived. | 0.9091 | 1.0000 | 1.0000 | 1 |
| 2026-07-07 postreview-run2 | RED | `Ruxolitinib INHIBITS JAK2 activity` used a trusted model-only process endpoint and missed verified `JAK2`. | 0.9000 | 0.9000 | 0.9000 | 0 |

## Interpretation

PR36 is the first v4 loop where the 100-case strict live-agent benchmark passes
the repeated-run trusted-readiness gate. The improvement is code-level and
policy-level: the system no longer treats broad or structurally under-grounded
review evidence as trusted graph evidence.

This does not mean every future biomedical document is globally safe for
automatic graph promotion. It means the measured v4 trusted lane is ready under
the current strict live-agent readiness gate. The all-candidate lane still shows
useful review-lane work: verified CURIE match rate is below the trusted-lane
endpoint rate because many review-only and low-value candidates still lack
trusted endpoints, and all-candidate generic relation rate remains high. Those
are review usefulness and benchmark-expansion issues, not trusted auto-promotion
blockers for PR36.

The final phrase-aware composite-process hardening for
`growth factor-independent proliferation` was validated by focused tests and
adversarial re-review. That phrase does not appear in the v4 fixture or the
postreview2 live reports, so it does not change the postreview2 live-readiness
metrics above.
