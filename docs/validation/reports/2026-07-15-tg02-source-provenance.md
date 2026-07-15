# TG-02 Authoritative Source Provenance And Exact Locators

Date: 2026-07-15

Plan: TG-02

Branch: `alvaro/trusted-claims-tg02-source-provenance`

Foundation parent: `5f1a6578f3f7e9ec6661e64432b1870b37baf6a0`

Implementation commit: `b56ffc1e94a7842d1c8c52c066b7259f1451df80`

Model: `openai:gpt-5.6-luna`

## Decision

**TG-02 source-provenance gate: PASS. Overall trusted-graph readiness: NOT
READY.**

Every evidence row eligible for canonical curation, auto-promotion,
materialization, or readiness must now reference an immutable Graph-owned
snapshot with an authoritative source identity and an exact locator. Graph DB
revalidates the attesting service, research space, upstream document, source
identity, content hash, locator bounds, exact quote, and quote hash from
persisted data. Missing, legacy, malformed, mismatched, or caller-forged
provenance remains readable but cannot become eligible.

This PR does not unlock the trusted lane introduced by TG-01 and makes no
human-expert or clinical-validity claim. The strict Luna audit remains `RED`
for later-stage claim completeness and entity-grounding gaps.

## Hypothesis And Root Cause

Hypothesis: if authoritative source identity and exact evidence location are a
single typed contract from Evidence API document storage through Graph DB,
internal proposal references and self-consistent forged metadata can no longer
count as promotion-eligible evidence.

Root cause: source identity, retrieval metadata, source text, and evidence
location previously crossed service boundaries as optional or unrelated
fields. Graph eligibility could not reconstruct and independently validate one
complete source-local proof.

## Implementation

- Freeze typed proposal-time provenance from the stored Evidence API document.
- Preserve PMID, PMCID, DOI, NCT ID, ClinVar accession, publisher identity,
  canonical URL, retrieval time, version, content hash, and artifact hash.
- Persist exact section/sentence/paragraph, character offsets, quote, quote
  hash, and available page/table/figure references.
- Mint a short-lived signed service token with a closed
  `source_provenance_submit` capability and attestation-service identity.
- Verify service, capability, space, document, source identity, text hash,
  locator bounds, exact quote, and quote hash before snapshot creation.
- Store immutable Graph-owned source snapshots. ORM and database triggers reject
  update/delete; proposal provenance fields are also immutable after insert.
- Bind each snapshot fingerprint to the exact upstream service, space,
  document, and full source identity. Different upstream documents cannot share
  a snapshot; source-family counting still collapses the same authority.
- Revalidate persisted evidence before manual curation, auto-promotion,
  projection materialization, source counting, and readiness reporting.
- Keep legacy and invalid evidence visible as `LEGACY_UNVERIFIED`,
  `UNVERIFIED`, or `INVALID` without granting canonical eligibility.

## TG-02 Gate Evidence

| Gate | Result | Evidence |
|---|---:|---|
| Eligible rows missing authoritative source identity | 0 | Eligibility fails closed unless snapshot identity parses and all columns match. |
| Eligible rows missing a valid exact locator | 0 | Locator hash, bounds, quote, and source-content hash are rechecked. |
| Quote/source hash mismatches accepted | 0 | Mutation, repeated-quote, Unicode, offset, and content-hash regressions pass. |
| Internal-only references counted as authority | 0 | Typed source authority validation rejects internal proposal identities. |
| Cross-space/document snapshot reuse accepted | 0 | Snapshot fingerprint and eligibility both bind service, space, and document. |
| Legacy evidence eligible | 0 | Migration defaults old rows to explicit ineligible provenance status. |
| Live API-to-Graph round trips | 1/1 | Verified PubMed identity and locator persisted; claim resolved and relation materialized. |

Focused validation:

```bash
uv run pytest -q \
  services/artana_evidence_api/tests/unit/test_source_provenance.py \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py \
  tests/unit/test_source_provenance_contract_parity.py

uv run pytest -q \
  services/artana_evidence_db/tests/unit/test_source_provenance.py \
  services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
  services/artana_evidence_db/tests/unit/test_persistence_models.py

uv run pytest -q \
  tests/unit/database/test_artana_evidence_api_alembic_migration_regressions.py

uv run pytest -q \
  tests/e2e/artana_evidence_api/test_live_graph_promotion.py::test_promote_proposal_persists_claim_through_live_graph_service
```

Repository validation:

```bash
make architecture-size-check architecture-structure-check
make graph-service-static-checks-core
make artana-evidence-api-static-checks-core
make graph-service-test
make artana-evidence-api-test
make service-checks
```

Both complete service suites passed against fresh PostgreSQL databases with all
migrations applied. Graph and Evidence API lint, type, boundary, generated
contract, and architecture gates passed. Commit hooks ran without skips.

## Strict Luna Audit

The frozen 30-case v2 fixture was run once because TG-02 changes provenance and
projection eligibility, not extraction semantics. No run used
`--allow-fallback`.

```bash
uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-15-tg02-run-01
```

| Metric | Result | Interpretation |
|---|---:|---|
| Agent completion | 30/30 | PASS |
| Fallback cases | 0 | PASS |
| Invalid agent cases | 0 | PASS |
| Negative leakage | 0/5 | PASS |
| Precision / recall | 0.9600 / 0.9600 | Diagnostic |
| High-value recall | 0.9500 | Diagnostic |
| Grounded / both arguments present | 1.0000 / 1.0000 | PASS |
| Generic relation rate | 0.1200 | Above later-stage target |
| Verified CURIE match rate | 0.7143 | Below TG-06 target |
| Trusted candidates | 0 | TG-01 quarantine remains active |
| Overall verdict | RED | Expected; trusted CURIE recovery remains blocked |

The `RED` result is not repaired by weakening a threshold. TG-03 owns qualified
claim completeness and generic-output reduction. TG-06 owns authoritative
entity and variant grounding. TG-05 and TG-07 must complete before the trusted
lane can become non-empty.

## Adversarial Review

An independent Luna reviewer tested service forgery, cross-boundary reuse,
immutability, and canonical projection paths.

One finding was valid: snapshots were deduplicated by authority and content,
so a second upstream document could reuse the first document's snapshot. The
root cause was loss of the exact persisted document-to-snapshot binding. The
fingerprint now includes the complete upstream and source identity, eligibility
rechecks that binding, and regressions prove different documents cannot share a
snapshot.

Three concerns did not represent trust bypasses:

- Attestation is authenticated by a signed, issuer-checked, expiring service
  token with a closed capability. Anonymous callers cannot mint it.
- A proposal may be marked promoted when it is preserved as an `OPEN` claim;
  it receives no canonical relation and remains ineligible. This is the plan's
  claim-before-edge rule, including for hypotheses and uncertain knowledge.
- Explicit source/document deletion may remove an unpromoted proposal. This is
  an intentional user-data deletion workflow. Once evidence reaches Graph DB,
  the independent source snapshot cannot be updated or deleted.

The reviewer confirmed that direct relation creation and projection
materialization fail closed without eligible provenance. An attempted Claude
CLI review did not return a completed finding set and is not counted as review
evidence.

## Artifact Manifest

Fixture:

- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
  - SHA-256: `3f4b5fb4622475c39c13f1c29368defeb6a909ae9c533424640862aecda1acba`

Raw run artifacts:

- `reports/relation_feasibility/2026-07-15-tg02-run-01/relation_feasibility_report.json`
  - SHA-256: `534f0ee6071d542184074f5f7b75ae437f27f0621b32e481d1c47d27f1826e2a`
- `reports/relation_feasibility/2026-07-15-tg02-run-01/relation_feasibility_report.md`
  - SHA-256: `042f5de03d26a6a92930de23fbaa427fad6ca87e324944b51ec6dc44d257b64e`

Raw generated reports remain in the ignored `reports/` workspace tree. Their
content hashes are frozen here; this tracked report is the review record.

## Next Gate

TG-03 must replace triple-first extraction with a qualified categorical
`ClaimFrame` that preserves polarity, epistemic state, variant/biological
state, population, intervention, comparator, outcome, study context, and exact
source spans. It must not unlock canonical projection or ask agents for numeric
quality scores.
