# TG-03 Qualified ClaimFrame Evidence Report

Date: 2026-07-15

Status: `evidence_pending`

Decision: **TG-03 now has an inventory-first, direction-aware ClaimFrame path and
stronger fail-closed graph boundaries. The implementation is test-green, but no
current result yet proves that scientific precision or recall improved. Agent
claim and relation persistence therefore remains quarantined.**

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

These results prove a stricter and more truthful system boundary. They do not
prove better biomedical extraction.

## What Is Not Proven

- The current inventory-first pipeline has not yet completed its strict live
  `openai:gpt-5.6-luna` smoke run.
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

Historical artifacts remain under
`docs/validation/reports/tg03-qualified-claim-frame-runs/`. They may catch
regressions and prove runtime execution, but must not be relabeled as evidence
that the new architecture improved product quality.

## Current Runtime Contract

Model: `openai:gpt-5.6-luna`

Pipeline prompt:
`document_extraction.claim_pipeline.v4:claim_inventory.v2+claim_inventory_completeness.v2+claim_inventory_recovery.v2+claim_framing.v4`

The TG-03 live step is one strict Luna smoke on the development set. Its purpose
is limited to proving that the real provider path completes with the current
schemas, no semantic fallback credit, exact attempt audit records, and no graph
write. It cannot earn a scientific-quality merge claim.

## Adversarial Review

The first independent reviews found two high-severity classes of issue:

1. an incomplete nested provider output message could pass when only the outer
   response was complete;
2. nested batch actions could erase AI identity, ignore the batch auto-apply
   switch, resolve claims as a UUID-shaped human, or mark workflows applied from
   self-asserted evidence.

Both root causes are fixed and covered by regressions. A second independent
review of those fixes is required before the PR can be called review-ready.

## Stop Rule

TG-03 may merge as a safety and architecture improvement only if the strict live
smoke completes, credited fallback and graph writes remain zero, provider and
attempt lineage are intact, all service gates remain green, and the second
adversarial review has no unresolved high-severity finding.

Actual scientific progress is deferred to the prospectively frozen TG-08 set.
If two consecutive product experiments fail to produce a positive paired net
change in precision and recall without weakening safety, stop prompt iteration
and run a model/task ablation. Do not build another evaluation layer.

## Honest Next Decision

TG-03 is not trusted-graph ready and is not human-expert validated. Its current
value is that the system asks a better structured question, measures omissions
as well as false positives, and cannot silently promote an agent result through
a manual or fallback path. TG-04 may add lossless claim-ledger persistence, but
projection must remain disabled until TG-05, TG-06, and TG-07 gates pass.
