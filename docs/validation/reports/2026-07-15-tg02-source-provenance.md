# TG-02 Authoritative Source Provenance And Exact Locators

Date: 2026-07-15

Plan: TG-02

Branch: `alvaro/trusted-claims-tg02-source-provenance`

Foundation parent: `5f1a6578f3f7e9ec6661e64432b1870b37baf6a0`

Implementation commit: `b56ffc1e94a7842d1c8c52c066b7259f1451df80`

Model: `openai:gpt-5.6-luna`

## Decision

**TG-02 implementation safety gate: PASS. TG-02 experimental evidence:
NOT EVALUABLE. Overall trusted-graph readiness: NOT READY.**

Every evidence row eligible for canonical curation, auto-promotion,
materialization, or readiness must now reference an immutable Graph-owned
snapshot with an authoritative source identity and an exact locator. Graph DB
revalidates the attesting service, research space, upstream document, source
identity, content hash, locator bounds, exact quote, and quote hash from
persisted data. Missing, legacy, malformed, mismatched, or caller-forged
provenance remains readable but cannot become eligible.

The July 16 consolidation added a server-owned ingestion-lineage requirement.
User-submitted text and PDFs may retain claimed PMID, DOI, registry, or
publisher metadata for review, but those claims cannot establish authoritative
identity. Authority requires a document ingested through the matching
server-owned source path. This closes a forged-metadata gap found during the
post-merge adversarial review.

Research-init replay bundles are also categorically review-only, including
bundles prepared by the server, because the current replay contract does not
carry a provider-verifiable retrieval receipt. Direct source handoffs remain
eligible. Replay authority may be reconsidered only after upstream retrieval
identity and content are independently verifiable.

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
| Raw text/PDF metadata accepted as source authority | 0 | Server-owned document source type must match the claimed authority family. |
| Replay-derived PubMed content accepted as source authority | 0 | Replay remains review-only without a verifiable upstream retrieval receipt. |
| Live API-to-Graph trusted writes | 0 | The consolidated TG-03 boundary returns HTTP 409 and verifies zero claim or relation writes until qualified-claim persistence exists. |

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
  tests/e2e/artana_evidence_api/test_live_graph_promotion.py::test_promote_qualified_claim_fails_closed_without_live_graph_writes
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

## Historical Strict Luna Diagnostic

The following run was reported during TG-02 development. Its raw outputs remain
under the ignored `reports/` tree and are not part of a protocol-compliant,
retrievable artifact bundle. The values therefore identify diagnostic
hypotheses only and receive no scientific-improvement, readiness, or merge
credit.

```bash
uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-15-tg02-run-01
```

| Metric | Result | Interpretation |
|---|---:|---|
| Agent completion | Reported 30/30 | Not independently reproducible |
| Fallback cases | Reported 0 | Not a current safety proof |
| Invalid agent cases | Reported 0 | Not independently reproducible |
| Negative leakage | Reported 0/5 | Diagnostic hypothesis |
| Precision / recall | Reported 0.9600 / 0.9600 | Diagnostic hypothesis |
| High-value recall | Reported 0.9500 | Diagnostic hypothesis |
| Grounded / both arguments present | Reported 1.0000 / 1.0000 | Diagnostic hypothesis |
| Generic relation rate | Reported 0.1200 | Suggests a later-stage gap |
| Verified CURIE match rate | Reported 0.7143 | Suggests a TG-06 gap |
| Trusted candidates | Reported 0 | Consistent with TG-01 quarantine |
| Overall verdict | Reported RED | Trusted CURIE recovery remained blocked |

The `RED` result is not repaired by weakening a threshold. TG-03 owns qualified
claim completeness and generic-output reduction. TG-06 owns authoritative
entity and variant grounding. TG-05 and TG-07 must complete before the trusted
lane can become non-empty.

## Adversarial Review

The original independent Luna review is a historical note because its raw
response is not committed in the protocol-required artifact bundle. A July 16
post-merge adversarial code review identified one additional valid finding:
raw text or PDF metadata could claim an authoritative identifier because the
identity builder did not distinguish user-controlled metadata from
server-owned ingestion lineage. The root fix requires the document's
server-owned source type to match the authority family; focused regressions
prove `text` and `pdf` records remain review-only even when they claim a PMID.
A second review found that client-supplied research-init replay data could still
receive `source_type=pubmed`. The final boundary therefore quarantines all
replay-derived source content until a provider-verifiable retrieval receipt is
available.

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

The current implementation and full repository gate confirm that direct
relation creation and projection materialization fail closed without eligible
provenance. No agent review is counted as scientific ground truth.

## Artifact Manifest

Fixture:

- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
  - SHA-256: `3f4b5fb4622475c39c13f1c29368defeb6a909ae9c533424640862aecda1acba`

Raw run artifacts:

- `reports/relation_feasibility/2026-07-15-tg02-run-01/relation_feasibility_report.json`
  - SHA-256: `534f0ee6071d542184074f5f7b75ae437f27f0621b32e481d1c47d27f1826e2a`
- `reports/relation_feasibility/2026-07-15-tg02-run-01/relation_feasibility_report.md`
  - SHA-256: `042f5de03d26a6a92930de23fbaa427fad6ca87e324944b51ec6dc44d257b64e`

Raw generated reports remain in the ignored `reports/` workspace tree and are
not retrievable from this commit. Their recorded hashes do not satisfy the
current evidence protocol and cannot support recalculation or scientific merge
credit. This tracked report preserves the historical claims without validating
them.

## Next Gate

TG-03 must replace triple-first extraction with a qualified categorical
`ClaimFrame` that preserves polarity, epistemic state, variant/biological
state, population, intervention, comparator, outcome, study context, and exact
source spans. It must not unlock canonical projection or ask agents for numeric
quality scores.
