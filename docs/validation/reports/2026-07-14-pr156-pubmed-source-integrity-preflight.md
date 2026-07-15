# PR 156 PubMed Source-Integrity Preflight

## Goal

Add authoritative PubMed identity and publication-integrity facts before the
semantic selection agent judges a candidate. Preserve uncertain, corrected,
retracted, mismatched, and novel candidates for review instead of converting
absence or uncertainty into a false claim.

## Implemented

- The live PubMed gateway now retrieves bounded NCBI EFetch XML for preview
  records after ESearch and ESummary.
- The parser uses `defusedxml`, matches records by PMID, and captures canonical
  title, abstract, DOI, publication types, and `CommentsCorrectionsList`
  relationships.
- Source findings are categorical: identity is `matched`, `mismatched`, or
  `unresolved`; integrity is `clear`, `correction_review`,
  `expression_of_concern`, `retracted`, or `unresolved`.
- The agent still owns semantic relevance. Deterministic policy only converts an
  agent-selected candidate into a lifecycle state.
- A PubMed selection passes only when an allowlisted NCBI EFetch validation is
  bound to the same PMID and reports `matched` plus `clear`.
- Missing, invalid, mismatched, corrected, concerning, retracted, or unresolved
  validation becomes `source_integrity_review`. The original agent selection is
  retained as `shadow_decision=selected` and
  `would_have_been_selected=true`; it is not changed to `skipped`.
- EFetch failures and partial responses preserve the ESummary candidate with an
  explicit unresolved finding.

## Adversarial Findings Addressed

- Closed the legacy bypass where a PubMed record with no validation could still
  be selected.
- Bound clear validations to the same PMID so a finding from another article
  cannot be reused.
- Required the allowlisted `ncbi_pubmed` plus `efetch_xml` provenance categories
  before a clear result can pass.
- Replaced a broad exception catch with expected HTTP, rate-limit, Unicode, and
  hardened-XML failures; programming errors are no longer silently hidden.
- Avoided a new service-root module by placing PubMed integrity parsing in the
  existing source-authority package.
- Added reordered, missing, mismatched DOI, malicious XML, correction,
  expression-of-concern, retraction, unresolved, emerging-hypothesis, malformed
  contract, wrong-PMID, duplicate-PMID, and publication-type fallback regression
  cases.

## Validation Evidence

| Gate | Result |
| --- | --- |
| Focused PubMed and semantic-screening tests | PASS: 73 tests |
| Full Evidence API test suite with ephemeral PostgreSQL | PASS |
| Evidence API lint and strict type check | PASS: 582 typed source files |
| Boundary and generated-contract checks | PASS |
| Agent-output boundary check | PASS |
| Semantic baseline and benchmark integrity checks | PASS |
| Architecture size and structure checks | PASS |
| Live NCBI MED13 smoke test | PASS: 2 of 2 previews matched, clear, and contained abstracts |
| Live NCBI retracted-publication smoke test | PASS: 3 of 3 categorized retracted from `RetractionIn` |

The live MED13 smoke test resolved PMIDs `29773993` and `41130977`. The live
retracted-publication smoke test resolved PMIDs `41329731`, `41629425`, and
`40605964`; each carried an NCBI `RetractionIn` relationship and was categorized
as `retracted`.

## Safety Interpretation

This PR does not ask an LLM to produce a numeric source-quality score. NCBI
provides source facts, the agent provides categorical semantic judgment with
evidence, and deterministic code applies the lifecycle gate.

`not found` does not mean `false`. A new hypothesis with unresolved external
validation remains visible in review with its original semantic selection
preserved. It cannot enter the selected lane until its source identity and
integrity are resolved.

## Remaining Boundary

This is the PubMed discovery and semantic-selection slice only. It does not yet:

- validate ClinVar, ClinicalTrials.gov, PMC full text, or publisher correction
  metadata;
- revalidate a previously clear publication immediately before trusted graph
  promotion;
- establish the biomedical truth of a claim merely because its source is
  authentic and unretracted;
- replace independent expert review or the blocked trusted-graph readiness
  gates.

The next source-validation PR should add the same categorical, non-lossy policy
to ClinVar and ClinicalTrials.gov. A later promotion-boundary PR must recheck
freshness and correction status before trusted graph promotion.
