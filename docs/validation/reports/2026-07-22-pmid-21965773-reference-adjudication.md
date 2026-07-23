# PMID-21965773 Drug-Sensitivity Reference Adjudication

## Decision

The frozen drug-sensitivity reference is defensible as a BioNLP Cancer Genetics
(CG) benchmark projection, but two parts of its source-general acceptance policy
are not uniquely determined by the public expert annotation:

- rejecting `POPULATION/carcinoma patients` in favor of only
  `CANCER/carcinoma`; and
- requiring direction `NOT_APPLICABLE` rather than `OBSERVED`.

Those are reference-policy judgments, not CG gold fields. The frozen reference
and V9 result remain unchanged. Any broader source-semantic acceptance rule must
be separately versioned and independently reviewed; this report does not grant
qualification credit and does not rescore V9.

## Primary evidence reviewed

The review used the following primary or task-authoritative sources:

- the [PubMed record and abstract for PMID-21965773](https://pubmed.ncbi.nlm.nih.gov/21965773/);
- the public CG development-set [source text](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.txt),
  [entity annotations](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.a1),
  and [event annotations](https://raw.githubusercontent.com/openbiocorpora/bionlp-st-2013-cg/master/original-data/devel/PMID-21965773.a2);
- the official [BioNLP-ST 2013 CG task definition](https://2013.bionlp-st.org/tasks/cancer-genetics-cg-task)
  and [standoff file-format specification](https://2013.bionlp-st.org/file-formats);
  and
- the task authors' [CG overview paper](https://aclanthology.org/W13-2008.pdf).

The checked-in local source is byte-identical to the public openbiocorpora
mirror for all three relevant files. Their SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `PMID-21965773.txt` | `0bba2db9971b512abac2bf0a0c40627432b9f63fc8f090cc4d3590b08df52880` |
| `PMID-21965773.a1` | `d6f0d526567bfc689d7d4c6ea63e9ba0345ee29b83126edf58f9e317fb624ebe` |
| `PMID-21965773.a2` | `e554de689b08b2b4db29cae32893459eef6ffe0b11860cfa8f7313584537b0e8` |

The task specification defines text-bound annotations by half-open character
offsets and event arguments by typed roles. The CG overview states that events
have typed triggers and entity or event arguments in roles such as `Theme` and
`Cause`; it defines `Theme` as the argument undergoing the primary effect and
`Cause` as responsible for occurrence. It also records that entity annotations
were manually revised and event annotations were manually created and revised.

## Exact public annotation

The relevant CG annotations are:

```text
T12 Cancer 369 378 carcinoma
T13 Organism 379 387 patients
T14 Simple_chemical 391 395 5-FU
T63 Regulation 354 365 sensitivity
E9 Regulation:T63 Cause:T14 Theme:T12
```

The `T14` offsets select the second `5-FU` in the sentence, not the parenthetical
abbreviation. This independently confirms the occurrence identity exposed by
V9.

## Field-by-field adjudication

| Frozen requirement | Primary-source assessment | Verdict |
| --- | --- | --- |
| `REGULATION` for `sensitivity` | The CG gold event is explicitly `Regulation:T63`; the nominal sensitivity state is more specific than a generic correlation. | Defensible benchmark requirement. V9's `ASSOCIATION` is a genuine semantic mismatch under the frozen contract. |
| `CANCER/carcinoma` | CG explicitly marks `carcinoma` as `Cancer` and uses it as event `Theme`. It separately marks `patients` as `Organism`. | Defensible benchmark node. However, treating the composite `carcinoma patients` as a clinical population is also source-semantically plausible, so exclusive rejection is a policy choice rather than a uniquely compelled scientific fact. |
| `SIMPLE_CHEMICAL/5-FU` | CG explicitly marks the second `5-FU` as `Simple_chemical` and uses that exact entity in the event. | Strongly defensible. V9 produced the correct type and text; its V1 failure on this node was an evaluator defect. |
| direction `NOT_APPLICABLE` | CG has no Artana direction axis. The sentence asserts a sensitivity state but states no increase, decrease, comparison, or measured direction. | Conservative and defensible, but not an expert-annotated gold field. `OBSERVED` is a taxonomy disagreement, not independently proven scientific fabrication. |
| `AFFECTED_ENTITY` for carcinoma | CG uses `Theme:T12`; the affected entity role is a faithful source-semantic rendering of the entity whose sensitivity is described. | Defensible. V9 used this role correctly, although on a broader population span. |
| `STIMULUS_OR_OBJECT` for 5-FU | CG uses `Cause:T14`, but the surface construction is sensitivity *to* a drug and does not itself assert that the drug caused the sensitivity. Artana deliberately keeps the corpus `Cause` projection review-only. | Defensible source-semantic role. V9 used it correctly. The direct CG `Cause` label belongs only to the separate benchmark projection. |

## Three distinct findings

### 1. Evaluator implementation defect

V1 identified children only by surface text and required uniqueness inside the
complete evidence sentence. Because `5-FU` occurs twice, it rejected a valid
explicit entity even though CG identifies the intended occurrence at absolute
offsets 391–395. This is the defect corrected by occurrence evaluator V2.

### 2. Reference-policy ambiguity

The public annotation does not establish the Artana direction axis and does not
prove that a source-general extraction must reject the composite clinical
population. `NOT_APPLICABLE` and `CANCER/carcinoma` remain defensible frozen
choices, but their exclusivity should not be presented as independent expert
consensus.

A future reference contract may separate:

- an exact CG benchmark projection requiring `Regulation`, `Cancer/carcinoma`,
  `Simple_chemical/5-FU`, `Theme`, and `Cause`; from
- a source-semantic lane that can independently adjudicate whether the explicit
  patient population and `OBSERVED` state are acceptable alternatives.

That future contract would require a fresh version, blinded independent expert
review, and untouched holdout cases. No frozen reference should be edited in
place.

### 3. Genuine V9 semantic error

After occurrence-aware grounding, V9 still calls `sensitivity` an
`ASSOCIATION`. That conflicts with the expert CG `REGULATION` event and prevents
the event, root, semantic axes, and links from matching the frozen graph. V9
also fails the exact CG entity segmentation by returning the combined
`POPULATION/carcinoma patients` instead of isolating `CANCER/carcinoma`.

The `5-FU` entity and the two source-semantic argument roles are not genuine V9
errors. The direction disagreement remains an under-adjudicated reference
policy issue, not evidence of fabrication.

## Governance conclusion

- Scientific extraction improvement: not established by this evaluator and
  adjudication checkpoint.
- Evaluator/governance correctness: occurrence identity now has a justified
  absolute-offset basis; reference uncertainty is explicitly separated from
  the implementation defect.
- Production or trusted-graph readiness: not established. No graph writes,
  promotion, qualification, or provider calls are authorized by this report.
