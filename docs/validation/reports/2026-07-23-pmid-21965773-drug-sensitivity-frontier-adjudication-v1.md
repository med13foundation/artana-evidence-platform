# PMID-21965773 Drug-Sensitivity Frontier Adjudication V1

## Decision

The existing frozen reference mixes source-semantic truth with exact BioNLP-CG
projection. A separately versioned two-lane contract is justified.

V11 run 2 remains byte-identical, failed, non-qualifying, and sealed at
`V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION`. This adjudication is an offline
diagnostic and grants no retroactive credit.

Two independent reviewers first assessed source semantics without seeing model
output or the frozen answer. They then independently reconstructed the exact CG
projection from the public task files. Only after those judgments were sealed
did they compare V9 and V11. A tiebreaker resolved the five narrow labeling
disagreements; no disagreement remains.

## Authoritative evidence

- [PubMed PMID-21965773](https://pubmed.ncbi.nlm.nih.gov/21965773/)
- [BioNLP-ST 2013 CG task definition](https://2013.bionlp-st.org/tasks/cancer-genetics-cg-task)
- [BioNLP-ST 2013 standoff format](https://2013.bionlp-st.org/file-formats)
- [CG overview paper](https://aclanthology.org/W13-2008/)
- public CG [source text](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.txt),
  [entities](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.a1),
  and [events](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.a2)

The checked-in public files remain byte-identical to the reviewed files:

| File | SHA-256 |
| --- | --- |
| `.txt` | `0bba2db9971b512abac2bf0a0c40627432b9f63fc8f090cc4d3590b08df52880` |
| `.a1` | `d6f0d526567bfc689d7d4c6ea63e9ba0345ee29b83126edf58f9e317fb624ebe` |
| `.a2` | `e554de689b08b2b4db29cae32893459eef6ffe0b11860cfa8f7313584537b0e8` |

## Two lanes

### Source-semantic lane

- root trigger: `sensitivity`
- event kind: qualitative drug sensitivity
- acceptable Artana types: `ASSOCIATION` or `REGULATION`
- mandatory bearer: `POPULATION/carcinoma patients` as `AFFECTED_ENTITY`
- mandatory drug: the focus-local second `5-FU` as
  `SIMPLE_CHEMICAL/STIMULUS_OR_OBJECT`
- permitted optional context: TS and DPD as `GENE_OR_PROTEIN`
  `CONTEXTUAL_PARTICIPANT` nodes
- direction: nondirectional; `NOT_APPLICABLE` and `OBSERVED` remain acceptable
  taxonomy alternatives
- comparison `NOT_APPLICABLE`, polarity `AFFIRMED`, uncertainty `ASSERTED`,
  statistics `NONE`, author interpretation `NOT_CLAIMED`
- complete exact source sentence required as evidence

### Exact CG projection lane

```text
E9 Regulation:T63 Cause:T14 Theme:T12
T63 Regulation 354 365 sensitivity
T12 Cancer 369 378 carcinoma
T14 Simple_chemical 391 395 5-FU
```

The outer dependency context is:

```text
E7 Regulation:T62 Theme:E9 Cause:T6
E8 Regulation:T62 Theme:E9 Cause:T8
```

CG splits `carcinoma patients` into `Cancer/carcinoma` and
`Organism/patients`, but only carcinoma is E9's Theme. Its Cause roles are
benchmark projection labels; they do not establish universal source causality.
The CG lane remains separate and review-only.

## Field-level V9 and V11 diagnosis

| Field | V9 | V11 run 2 |
| --- | --- | --- |
| Focus/root | Raw root is sensitivity; frozen root failure is `EVALUATOR_ERROR` cascade | `GENUINE_SOURCE_SEMANTIC_ERROR` |
| Trigger | Correct sensitivity | `GENUINE_SOURCE_SEMANTIC_ERROR` for `are involved in` |
| Event type | `CG_PROJECTION_ONLY_MISMATCH` | `CG_PROJECTION_ONLY_MISMATCH` |
| Patient representation | `REFERENCE_POLICY_AMBIGUITY` | `REFERENCE_POLICY_AMBIGUITY` |
| Drug occurrence | `EVALUATOR_ERROR` in the old repeated-text resolver | `GENUINE_SOURCE_SEMANTIC_ERROR` |
| TS and DPD nodes | Optional omission; no disagreement | `PERMITTED_SOURCE_CONTEXT` |
| Argument attachment | Raw source roles correct; frozen failure is `EVALUATOR_ERROR` cascade | `GENUINE_SOURCE_SEMANTIC_ERROR` because all roles attach to the wrong root |
| Direction | `REFERENCE_POLICY_AMBIGUITY` | `REFERENCE_POLICY_AMBIGUITY` |
| Polarity | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade |
| Uncertainty | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade |
| Statistics | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade | Correct raw value; frozen failure is `EVALUATOR_ERROR` cascade |
| Exact evidence | `EVALUATOR_ERROR` for repeated `5-FU` | Textually grounded, but grounds the wrong occurrence |
| Context additions | None | `PERMITTED_SOURCE_CONTEXT` |
| Unsupported count | `EVALUATOR_ERROR` if read as five independent scientific claims | `EVALUATOR_ERROR` if read as seven independent scientific claims |

No reviewed node is an `UNSUPPORTED_EXTRACTION`. The real V11 errors are focus,
root, trigger, direct drug occurrence, and the resulting flattened attachment.

## Why five became seven

The frozen evaluator computes unsupported material as unsupported events plus
participants plus links:

```text
V9  = 1 event + 2 participants + 2 links = 5
V11 = 1 event + 2 participants + 4 links = 7
```

V11's two extra units are links from the two permitted TS/DPD context nodes to
an unmapped event. They are not two new unsupported biomedical claims. The
frozen count regression and terminal remain formally unchanged.

## V12 decision

V12 is authorized for one source-general scientific change:
`FOCUS_EVENT_ANCHORING`.

The prompt may clarify that an explicit event-denoting noun or phrase inside
the highlighted finding must remain the root and may not be replaced by a
surrounding association predicate. No PMID-specific entity, expected answer,
benchmark label, or output-tailored example is authorized.

Before any provider call, the wording, two-lane contract, exposed-panel audit,
prompt, schema, references, acceptance, case order, and operational policy must
be independently reviewed, frozen, committed, and pushed.

Fresh cases consumed: `0`. Graph writes: `0`. Trusted promotion: `false`.
