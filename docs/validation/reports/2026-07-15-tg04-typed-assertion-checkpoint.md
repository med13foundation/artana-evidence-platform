# TG-04 Typed Assertion Checkpoint

Date: 2026-07-15

Status: stopped before Graph persistence

Branch: `alvaro/trusted-claims-tg04-claim-persistence`

Evaluated commit: `45e3024b863be9d337bfa303d01575eaa441b13d`

Acceptance model: `openai:gpt-5.6-luna`

## Decision

The role-typed assertion experiment improved information preservation, but it
did not prove better scientific claim precision or recall. TG-04 therefore
stops before adding Graph persistence.

This is not a trusted-graph result. It is a useful representation result with
an unresolved semantic-projection problem.

## Falsifiable Hypothesis

Preserving typed arguments before selecting graph endpoints should prevent the
silent loss of population, variant, condition, intervention, and outcome seen
in TG-03 and should allow the agent to retain multiple defensible frames.

The diagnostic source was:

> Among Korean adults with ALK G1202R-positive lung adenocarcinoma, lorlatinib
> reduced intracranial lesions.

The case was selected from the fully validated sealed TG-03 fixture. Because
the prompt was subsequently changed while diagnosing this case, the case is now
a development case and cannot provide confirmatory merge credit.

## What Improved

The final strict Luna run completed the composed agent pipeline and preserved
six source-bound roles:

| Role | Exact source span |
|---|---|
| `POPULATION` | `Korean adults` |
| `VARIANT` | `G1202R-positive` |
| `GENE_OR_PROTEIN` | `ALK` |
| `CONDITION` | `lung adenocarcinoma` |
| `INTERVENTION` | `lorlatinib` |
| `OUTCOME` | `intracranial lesions` |

The framing agent returned `MULTIPLE_VALID_FRAMES` and two candidate
projections instead of silently selecting one. The runtime copied the
inventory agent's immutable argument tuple onto each projection without
reclassifying or inventing roles:

1. `lorlatinib TREATS lung adenocarcinoma`, with population, variant state, and
   outcome retained.
2. `lorlatinib MODULATES intracranial lesions`, with population, variant state,
   and condition retained.

Neither candidate escaped into a trusted lane. The first remained
`review_only` with `dropped_object_modifier`; the second remained `review_only`
with `support_not_entailed`.

Deterministic safety observations:

- strict usable extraction: `1/1`;
- fallback outputs: `0`;
- model invocation failures: `0`;
- agent-authored numeric values: `0`;
- negative or null leakage: `0` for this positive diagnostic case;
- output frames silently dropped after accepted framing: `0` when recomputed
  with the parity fix on the saved live artifact. The immutable historical
  report still contains the pre-fix value `2` and is not rewritten.

The immutable local run artifacts are:

- `/tmp/artana-tg04-alk-luna-45e3024b/claim_frame_feasibility_run.json`
- `/tmp/artana-tg04-alk-luna-45e3024b/claim_frame_feasibility_run.md`

The report records prompt
`document_extraction.claim_pipeline.v6:claim_inventory.v4+claim_inventory_completeness.v3+claim_inventory_recovery.v3+claim_framing.v6`,
fixture SHA-256
`b09c84fbc76642436a68c34ca9630636de36c78f077504e128a66662dc1b5888`,
and aggregate audited-output-envelope SHA-256
`bccd0697df4651c32b853fa2df21699a776c0ac16488ab16aef428bed5768753`.

## What Did Not Improve

The historical binary benchmark scored the run at:

- endpoint precision and recall: `0.0` and `0.0`;
- full-frame precision and recall: `0.0` and `0.0`;
- inventory-boundary precision and recall: `0.0` and `0.0`;
- unmatched output frames: `2`;
- unsupported positive output frames: `2`.

Those zeroes reveal two different problems and must not be explained away:

1. The sealed gold expects one binary object,
   `ALK G1202R-positive lung adenocarcinoma`. The new contract correctly keeps
   gene, variant, and condition as distinct typed roles, so exact binary
   endpoint matching no longer measures the new representation.
2. The candidate projections are not yet clearly trustworthy. `TREATS` may
   broaden a reported lesion-reduction finding and drops the ALK modifier from
   its disease object. `MODULATES` places the outcome in the object while
   marking the outcome qualifier `NOT_APPLICABLE`; it is generic, loses the
   directional `reduced` event semantics, and does not match the Graph
   dictionary's biological regulation meaning.

The preliminary inventory-preservation sub-check therefore passes: the
inventory agent authored the typed roles and deterministic code copied them
without semantic modification. Framing correctness, the TG-04 semantic
checkpoint, and the product-quality gate fail. No numeric precision credit is
assigned from this case.

## Adversarial Review Closure

Independent review found that legacy `ClaimFrame` construction could omit
typed arguments. Although that compatibility path is still needed to read old
records, absence of arguments was not itself a promotion rejection. The final
implementation closes both boundaries:

- generic relation conversion marks an argument-less frame `review_only` with
  `missing_typed_assertion_arguments`;
- canonical promotion preflight rejects the same condition with the dedicated
  `missing_typed_assertion_arguments` reason;
- regression tests prove no Graph call occurs after that rejection;
- provider-to-candidate parity compares the same inventory-enriched frame on
  both sides, while still rejecting forged role changes.

Design resolution: unmapped inventory roles such as `GENE_OR_PROTEIN`
intentionally remain in the immutable n-ary assertion rather than being
invented as graph qualifiers. Framing validates only roles that have an
explicit projection qualifier; it does not own or rewrite inventory semantics.

## Research Interpretation

Biomedical event-extraction research supports representing one source event as
a trigger plus typed participants instead of forcing an early binary triple.
Complex biomedical relations can have more than two role-bearing arguments,
and binary factorization compounds error. Event systems also preserve argument
roles and event structure before deriving relations.

Relevant primary sources:

- [Biomedical Relation Extraction: From Binary to Complex](https://pmc.ncbi.nlm.nih.gov/articles/PMC4156999/)
- [Complex event extraction at PubMed scale](https://pmc.ncbi.nlm.nih.gov/articles/PMC2881365/)
- [TEES 2.2: Biomedical Event Extraction for Diverse Corpora](https://pmc.ncbi.nlm.nih.gov/articles/PMC4642046/)
- [Coreference based event-argument relation extraction](https://pmc.ncbi.nlm.nih.gov/articles/PMC3239306/)

Recent evaluation research also warns against treating an LLM judge as ground
truth for biomedical relation extraction. Structured outputs help, but numeric
precision must remain a deterministic calculation against frozen categorical
labels:

- [Improving Automatic Evaluation of LLMs in Biomedical Relation Extraction](https://aclanthology.org/2025.acl-long.1238/)
- [Structured biomedical claim verification](https://aclanthology.org/2025.bionlp-1.14/)

## Root-Cause Improvements

The next work should be an experiment, not another persistence slice.

1. **Make the event the scientific record.** Add an explicit source trigger and
   closed event type such as directional decrease, increase, association,
   treatment response, or explicit abstention. Keep all typed participants on
   that event. Candidate graph relations remain derived projections.
2. **Use set-valued n-ary gold.** Freeze independent labels for trigger, event
   type, typed arguments, polarity, epistemic status, and the allowed set of
   projections. Score exact role retention, event fidelity, candidate-set
   recall, and unsupported-projection rate separately.
3. **Reject broad projections independently.** A source-only agent verifier
   should categorically mark each candidate as `entails`, `contradicts`,
   `insufficient`, or `abstain`, with exact supporting spans and a falsification
   note. Deterministic code computes all rates.
4. **Use expert corpora before synthetic expansion.** Adapt cases from BioNLP
   event data, BioRED, Evidence Inference, and EBM-NLP so the labels come from
   existing expert annotation rather than from the extracting or judging
   agent.
5. **Run a frozen model/task ablation.** Run Luna and one stronger model on the
   same untouched event cases without changing prompts. A stronger-only win
   indicates model capacity; shared failure indicates the contract, ontology,
   context, or gold is still wrong. Luna remains the acceptance model unless a
   separate product decision changes it.

## Validation Evidence

The controlled-stop implementation passed the repository's production
guardrails after the argument-lineage, legacy-promotion, and stale-fixture
regressions were added:

```bash
python scripts/run_isolated_postgres_tests.py \
  tests/e2e/artana_evidence_api \
  services/artana_evidence_api/tests/integration \
  services/artana_evidence_api/tests/unit \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  tests/unit/test_agent_output_boundary_validator.py \
  -x -q --tb=short
make service-checks
```

Both commands completed successfully on 2026-07-15. The aggregate service
gate passed lint, typing, service boundaries, OpenAPI and generated-contract
checks, agent-output governance, architecture limits, isolated PostgreSQL
tests, and the `86%` coverage floor with `87.46%` measured coverage. Live
external-API and already-running-service tests remained explicitly skipped;
the strict Luna diagnostic described above supplies the live model evidence
for this checkpoint.

## Next Gate

Do not add Graph persistence or resume prompt tuning until one frozen untouched
panel satisfies all of these deterministic conditions:

- typed argument exact-span recall improves over TG-03;
- directional event-type fidelity improves;
- supported candidate-frame recall improves;
- unsupported positive projections do not increase;
- paired improvements exceed paired regressions;
- fallback credit, agent-authored numbers, and unsafe negative/null leakage stay
  at zero;
- the result repeats across three identical Luna runs.

If Luna and the stronger-model ablation fail the same cases, redesign the task
and relation ontology before writing more production code. If the stronger
model succeeds while Luna fails, decide explicitly whether cost and latency
justify changing the acceptance model or whether the feature should remain a
review-only lane.
