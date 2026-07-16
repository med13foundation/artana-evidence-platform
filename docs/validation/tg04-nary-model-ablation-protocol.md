# TG-04 N-ary Scientific Model Evaluation Protocol

Created: 2026-07-16

Status: frozen development benchmark before model execution

## Decision Question

Can Artana's production n-ary inventory recover complete expert-annotated
scientific events on a frozen development panel, and does either Luna or Sol
meet the absolute gates required to advance to a new held-out evaluation?

This experiment compares models on one identical production task. It does not
claim a causal task improvement and does not use a structurally weaker output
surface as a baseline.

This experiment cannot authorize persistence, trusted graph promotion, or
human-expert readiness. The selection, adapter, and gates were hardened after
the corpus structure was inspected, so the honest maximum conclusion is model
and task qualification for a separately frozen held-out benchmark.

## Independent Gold Source

- Corpus: BioNLP Shared Task 2011, GENIA Event Extraction development set
- Official source:
  `https://bionlp-st.dbcls.jp/GE/2011/downloads/BioNLP-ST_2011_genia_devel_data_rev1.tar.gz`
- Archive SHA-256:
  `f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f`
- Generated fixture:
  `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json`
- Fixture SHA-256:
  `26d67408a7a2446de5d36fca3f8a80a732b6519afe00e303c893eef3c824268d`
- Eligible expert-authored events: `53`
- Expert labels used: trigger spans, event types, event roles, participant spans,
  negation, and speculation
- Artana value labels: `UNADJUDICATED`
- Artana graph-projection labels: `UNADJUDICATED`

The corpus provides independent event annotations but does not provide Artana
decision-value or graph-projection judgments. Valuable-claim recall and
projection metrics therefore remain `not_applicable` for this panel. They may
not be reported as passing, and an agent may not fill the missing labels.

The previously inspected ALK G1202R case is excluded. This entire BioNLP panel
is development-only; no result from it is described as confirmatory.

## Frozen Selection

Documents are selected without reading their scientific content. The selection
key is `SHA256(document_id)` in ascending order. The first 40 IDs are passed to
the deterministic adapter. All 40 remain executable cases. Five documents with
no corpus event are true empty-gold negative controls. Eighteen documents with
only unrepresentable corpus events are representability-stress cases; their
outputs are reported but are not automatically labeled scientific false positives.

```text
PMC-1134658-15-Methods-06
PMC-2806624-09-Supplementary_Material
PMID-9361029
PMID-10402173
PMC-2222968-03-Results-02
PMID-10090947
PMC-2222968-22-Materials_and_Methods-14
PMC-2222968-09-Materials_and_Methods-01
PMID-8621480
PMC-2222968-05-Results-04
PMC-2806624-05-RESULTS-04
PMC-2222968-15-Materials_and_Methods-07
PMID-10092783
PMC-2222968-40-caption-15
PMC-1920263-21-caption-06
PMID-8098881
PMID-8098618
PMC-1920263-08-MATERIALS_AND_METHODS-07
PMID-8626528
PMC-2222968-34-caption-09
PMID-9802971
PMID-9619918
PMID-8895544
PMC-2222968-06-Results-05
PMID-9164948
PMC-1920263-17-caption-02
PMID-8134378
PMID-9878621
PMID-7749985
PMID-9488049
PMID-10096561
PMID-9796702
PMC-1942070-07-Discussion
PMID-8096091
PMID-9234696
PMID-7605990
PMID-7537762
PMC-1920263-18-caption-03
PMC-1134658-06-Results-05
PMID-8898960
```

The adapter deterministically maps only documented corpus categories. It
retains every production-representable event without a per-document cap.
Events that depend on nested corpus event IDs, repeated indistinguishable text
mentions, or duplicate production identities are excluded from event-quality
denominators because Artana's categorical inventory schema cannot express those
distinctions. Expert argument offsets and deterministic agent argument offsets
remain part of scoring for retained events.
Every excluded corpus event is recorded with document ID, event ID, native
category, categorical exclusion reason, and original event, trigger, argument,
and modifier annotation references.
The adapter rejects unknown categories, offset mismatches,
duplicate identities, and unsupported discontinuous spans rather than guessing.
The fixture metadata records every preselected document and every exclusion.
Corpus offsets are deterministically remapped from archive text to Artana's
normalized extraction text before any event is scored.

## Frozen Experiment Matrix

| Production task | Model arm | Runs |
|---|---|---:|
| N-ary event inventory | `openai:gpt-5.6-luna` | 3 |
| N-ary event inventory | `openai:gpt-5.6-sol` | 3 |

Total: 6 live runs. Both models receive the same source, semantic prompt body,
structured schema, and tool policy. The evaluator enforces the same accepted
inventory source/input/schema topology for every case across all six runs.

Every scored event must reproduce its production inventory identity from the
frozen source and occur in an accepted raw inventory payload. Inventory and
completeness calls must have unique retrievable provider response IDs,
matching model identity, completed status, empty tools, matching normalized
prompt hash, canonical output hash, and structured-payload hash. Credited
semantic fallback and agent-authored metric counts must remain zero.

Development qualification requires the first accepted inventory for every
chunk to be independently classified `COMPLETE`, with no missing claims and no
recovery call. This deliberately measures whether the primary production pass
is sufficient; recovery-dependent output cannot qualify this task.

## Execution And Evidence Custody

Run only from the committed TG-04 branch with a clean tracked worktree. Write
each create-once arm report to a run-specific directory outside the repository
so that one report cannot make the next run's repository state dirty. After all
six reports and the deterministic matrix decision exist, copy the complete
bundle into one versioned `docs/validation/reports/` directory and commit it
without editing any report payload.

For each of three run indices, invoke the n-ary task with each explicit model:

```bash
export ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES=true
export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL=openai:gpt-5.6-luna
uv run python scripts/run_nary_claim_event_audit.py \
  --model openai:gpt-5.6-luna \
  --run-id tg04-luna-nary-01 \
  --output /tmp/artana-tg04/tg04-luna-nary-01.json
```

Change both explicit model values together for the Sol arm. A runtime default
substitution, dirty repository, duplicate provider response ID, unavailable
receipt, fallback, invalid agent output, or overwritten report invalidates the
affected matrix run. The matrix evaluator accepts exactly six reports and
returns a nonzero exit status when the frozen continue gate fails.

## Deterministic Measurements

The scorer reports counts, denominators, and rates independently:

- whole-event precision and recall;
- exact trigger precision and recall;
- event-type and directional fidelity;
- per-category event-type precision and recall, so the dominant regulation
  class cannot hide a weak minority category;
- typed participant and corpus-event-role precision, recall, and exact-set
  fidelity;
- polarity and epistemic fidelity;
- negative and unmatched positive leakage;
- uncertain or hypothetical claim escalation to asserted status;
- incorrect abstention;
- output rate on representability-stress documents, reported descriptively and
  excluded from qualification precision, leakage, and repeatability;
- exact and canonical three-run repeatability;
- per-model exact and canonical three-run repeatability;
- the number of cases correct in all three runs.

Zero denominators produce `not_applicable`, never `1.0`. Stable but wrong output
does not receive quality credit. Value and projection measurements remain
`not_applicable` until independent labels exist.

## Development Qualification Gate

One model may advance to a new held-out evaluation only when each of its three
runs satisfies:

- whole-event precision at least `90%`;
- whole-event recall at least `80%`;
- trigger, event-type, polarity, epistemic, and complete argument-set fidelity
  at least `95%`;
- every event category with at least five gold events has precision at least
  `90%` and recall at least `80%`; smaller categories are reported as
  underpowered descriptive results and cannot support category-level claims;
- positive leakage from negated events or unmatched positive hallucinations `0`;
- false-positive output on empty-gold negative controls `0`;
- uncertain-to-asserted epistemic escalation `0`;
- canonical repeatability at least `95%`;
- credited fallback, invalid output, and unauthenticated provider output `0`;
- exact replicate IDs, one clean repository identity, complete case coverage,
  unique live provider receipts, and identical inventory task topology.

## Stop Decisions

1. If both models fail the absolute n-ary gates, stop and redesign the task,
   ontology, event-role contract, or supplied context.
2. If Sol clears the gate and Luna does not, record an explicit model-quality,
   cost, latency, and reproducibility decision. Do not silently substitute Sol.
3. Model differences are descriptive unless one model clears every absolute
   gate. Repeatability cannot compensate for failure of any absolute gate;
   qualifying results may still contain errors within the preregistered
   tolerances.
4. If the development event gate passes, persistence, projection, and
   valuable-claim readiness remain blocked pending independent held-out labels.

This inventory-only experiment does not evaluate framing or graph persistence.
The current downstream contracts do not carry `event_type`, and the pre-TG-04
live smoke run also observed framing drop the material `POPULATION` argument
`B cells`. Therefore preserving event type alone cannot unblock those stages.
A later experiment must independently prove that framing and persistence retain
the complete event and every material argument before either can advance.

This panel executes 40 documents: 17 with 53 representable events, 5 true
no-event negative controls, and 18 representability-stress cases. It covers 6
of the 15 production event categories
and contains negated and uncertain annotations but no
independent hypothesis or null-result annotations. Results must be reported as
narrow event-inventory development evidence; broad biomedical domains,
hypothesis handling, null-result handling, decision value, graph projection,
and training-data contamination remain unproven.
