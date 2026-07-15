# TG-03 Qualified ClaimFrame Evidence Report

Date: 2026-07-15

Status: `runtime_complete_quality_not_demonstrated`

Decision: **TG-03 now has an inventory-first, direction-aware ClaimFrame path and
stronger fail-closed graph boundaries. A clean strict Luna smoke proves that the
real agent path completes without fallback, but its first simple case scored
zero endpoint and full-frame precision/recall. Scientific quality improvement is
not demonstrated, the 19-case run was stopped, and agent claim/relation
persistence remains quarantined.**

## Product Result

TG-03 replaces one-shot triplet generation with four source-local agent steps:

1. inventory every claim in the supplied source region;
2. independently review inventory completeness;
3. recover missing claims once;
4. frame one inventory item at a time as a typed `ClaimFrame`.

Each inventory item records explicit endpoint direction or `UNRESOLVED`.
`UNRESOLVED` direction can only abstain. A frame carries closed polarity and
epistemic status, material qualifier roles, exact source evidence, literal
source measurements, and an explanation. Agent-authored quality, confidence,
precision, recall, or readiness numbers are rejected.

The implementation also adds:

- sentence segmentation that preserves abbreviations, decimals, versions, and
  postposed qualifiers;
- deterministic inventory precision and recall, endpoint recall, full-frame
  recall, unmatched-claim counts, and fail-closed missing-metric behavior;
- one-to-one parity between accepted provider framing outputs and scored frames;
- provider-visible invocation IDs and kernel run IDs bound into every prompt;
- provider receipt checks for the outer response and contributing assistant
  message status, role, input topology, prompt, payload, output, and invocation;
- a graph-owned quarantine at claim, relation, projection, hypothesis, workflow,
  and batch boundaries;
- typed workflow actor context that keeps the authenticated user and effective
  AI principal distinct through nested dispatch;
- explicit `batch_auto_apply_low_risk` enforcement, human-only claim triage, and
  denial of AI `mark_resolved` shortcuts.

## What Is Proven

The following implementation and safety evidence is current for the working
tree:

- 225 focused ClaimFrame, inventory, provider-receipt, fixture, chunking, and
  attempt-audit tests pass;
- all Evidence API lint, type, boundary, contract, registry, architecture, and
  full isolated-PostgreSQL tests pass;
- all Graph DB lint, type, boundary, contract, architecture, and full
  isolated-PostgreSQL tests pass;
- focused adversarial graph tests prove that nested AI identity is preserved,
  disabled batch auto-apply is enforced, AI claim triage cannot impersonate a
  human UUID reviewer, and AI cannot mark a workflow applied without a
  server-owned application action;
- deterministic fallback cannot satisfy an agent evidence gate;
- missing or malformed quality metrics fail closed;
- abstention can no longer manufacture perfect precision while recall is absent;
- agent-authored claims and graph projections remain non-persistable.
- a clean detached-worktree `openai:gpt-5.6-luna` smoke completed the real
  inventory, completeness, and framing calls with three canonical provider
  response IDs, zero model invocation failures, zero fallback outputs, and no
  graph write;
- partial semantic failures now produce valid failing reports instead of losing
  earlier accepted attempt evidence or crashing the audit.

These results prove a stricter and more truthful system boundary. They do not
prove better biomedical extraction.

## What Is Not Proven

- The live smoke did not produce a correct frame on
  `holdout_variant_alk_g1202r`: endpoint/source and full-frame precision/recall
  were all `0.0`.
- No prospectively frozen external set has measured current claim precision,
  recall, direction, qualifiers, polarity, or stability.
- No authenticated human expert has validated the outputs.
- Lossless ClaimFrame persistence does not exist yet; TG-04 owns that contract.
- Independent source-only semantic verification and authoritative entity
  grounding remain TG-05 and TG-06 work.

## Historical Development Baseline

The v4 19-case holdout was used to diagnose and design the inventory-first
intervention. It is therefore a development and regression set, not independent
confirmatory evidence. Its historical `document_extraction.llm_extraction.v12`
results remain useful as the failure baseline:

| Deterministic measure | Historical result |
|---|---:|
| Agent invocation completion | 57/57 (100%) |
| Strict usable extraction | 53/57 (92.98%) |
| Fallback credited | 0 |
| Agent-authored scores | 0 |
| Negative/null positive leakage | 0 |
| Unsafe assertive upgrades | 0 |
| Measurement span violations | 0 |
| Endpoint/source match precision | 34/47 (72.34%) |
| Full-frame precision | 22/47 (46.81%) |
| Polarity concordance | 31/51 (60.78%) |
| Epistemic-status concordance | 31/51 (60.78%) |
| Required qualifier completeness | 20/33 (60.61%) |
| Full qualifier concordance | 22/51 (43.14%) |
| Source-measurement precision | 6/8 (75.00%) |
| Source-measurement recall | 6/12 (50.00%) |
| Canonical semantic stability | 5/17 (29.41%) |

The compact deterministic comparison is
`docs/validation/reports/2026-07-15-tg03-qualified-claim-frame-holdout-v4.json`
with a Markdown companion. Raw historical provider dumps are intentionally not
kept in this PR because the contaminated development set cannot earn
confirmatory credit. The fixture and comparison are sufficient for regression
and audit-contract tests.

## Current Runtime Contract

Model: `openai:gpt-5.6-luna`

Pipeline prompt:
`document_extraction.claim_pipeline.v4:claim_inventory.v2+claim_inventory_completeness.v2+claim_inventory_recovery.v2+claim_framing.v4`

The TG-03 live step is one strict Luna smoke on the development set. Its purpose
is limited to proving that the real provider path completes with the current
schemas, no semantic fallback credit, exact attempt audit records, and no graph
write. It cannot earn a scientific-quality merge claim.

The smoke ran from clean commit `de4e9a6c` as
`tg03-one-case-luna-smoke-final`. Runtime results were:

| Deterministic measure | Result |
|---|---:|
| Provider-bound executed attempts | 3 |
| Agent invocation completion | 100% |
| Composed pipeline completion | 100% |
| Strict usable extraction completion | 100% |
| Model invocation failures | 0 |
| Fallback outputs | 0 |
| Endpoint/source precision and recall | 0% / 0% |
| Full-frame precision and recall | 0% / 0% |

The compact evidence packet is
`docs/validation/reports/2026-07-15-tg03-luna-one-case-smoke-summary.json`.
Single-run provider receipts remain `not_verified` by policy because live
retrieval is a comparison-only gate; the report nevertheless contains three
canonical provider IDs and exact attempt/output bindings.

## Root-Cause Finding

The source says that, among Korean adults with ALK G1202R-positive lung
adenocarcinoma, lorlatinib reduced intracranial lesions. The frozen target treats
`lorlatinib` and `ALK G1202R-positive lung adenocarcinoma` as the primary
`TREATS` endpoints, with population, variant state, and intracranial lesions as
typed qualifiers. The inventory agent instead selected the grammatical clause
`lorlatinib reduced intracranial lesions`, treated the lesions as the second
endpoint, and declared the disease and population to be context. Framing then
received only that shortened claim-local span, so it could not recover the
discarded roles.

This is a claim-representation failure, not merely a stronger-model question.
The sentence can support an intervention-disease assertion and an
intervention-outcome assertion. A binary untyped endpoint inventory forces an
early lossy choice. The next product experiment must preserve the full source
sentence and classify `INTERVENTION`, `CONDITION`, `POPULATION`, `VARIANT`, and
`OUTCOME` roles before selecting graph endpoints. When more than one assertion
is defensible, the agent must emit categorical `MULTIPLE_VALID_FRAMES` or
`AMBIGUOUS` output and retain both candidates for verification rather than
silently collapsing one.

## Adversarial Review

The first independent reviews found two high-severity classes of issue:

1. an incomplete nested provider output message could pass when only the outer
   response was complete;
2. nested batch actions could erase AI identity, ignore the batch auto-apply
   switch, resolve claims as a UUID-shaped human, or mark workflows applied from
   self-asserted evidence.

Both root causes are fixed and covered by regressions. Follow-up adversarial
review also required provider accounting for schema-invalid attempts,
case-specific evidence-unit binding even when source text is identical,
independent conflict/risk tests, and canonical AI actor coverage for official
batch mutations. Those fixes are now implemented and test-green; final reviewer
closure remains required before the PR is review-ready.

## Stop Rule

TG-03 may merge as a safety and architecture improvement only if the strict live
smoke completes, credited fallback and graph writes remain zero, provider and
attempt lineage are intact, all service gates remain green, and the second
adversarial review has no unresolved high-severity finding.

The stop rule was applied after the first clean live case produced `0.0`
endpoint/full-frame precision and recall. The remaining 18 development cases
were not run, because they would add cost without changing the architectural
finding.

Actual confirmatory scientific progress is deferred to the prospectively frozen TG-08 set.
If two consecutive product experiments fail to produce a positive paired net
change in precision and recall without weakening safety, stop prompt iteration
and run a model/task ablation. Do not build another evaluation layer.

## Honest Next Decision

TG-03 is not trusted-graph ready and is not human-expert validated. Its current
value is real but limited: the provider path is truthful and auditable, and it
cannot silently promote an agent result through a manual or fallback path. The
current binary claim inventory is still scientifically lossy.

TG-04 should therefore persist a role-typed, n-ary clinical assertion rather
than freezing the current binary mistake. TG-05 should independently verify
each role and proposed frame from source-only evidence. TG-06 should ground the
condition, intervention, variant, and outcome independently. Projection stays
disabled until those gates pass and TG-08 shows a positive paired precision and
recall change on prospective cases.
