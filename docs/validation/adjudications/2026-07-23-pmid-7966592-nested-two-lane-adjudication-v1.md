# PMID 7966592 Nested-Event Two-Lane Adjudication

Two blinded source-first reviews independently reached the same result.

The source-semantic graph contains two events. `responsible` is the outer root
and takes `elevating` as its nested effect. HCMV immediate-early proteins are the
causal agent; the focus-local p53 occurrence is the affected entity; infected
fibroblasts are mandatory contextual scope.

The measured public BioNLP-CG root-dependency chain projects three events:
`responsible -> elevating -> levels`, with `levels` typed as
`Gene_expression`. That third event is an exact benchmark projection, not a
scientifically universal claim that increased p53 protein abundance arose from
gene expression.

The official focus also contains the separate event E28 `Infection`, with
`fibroblasts` as a `Cell` Theme and `HCMV` as an `Organism` Participant. The V9
schema cannot represent `INFECTION`, `CELL`, or `ORGANISM`, so full-focus CG
projection is `NOT_MEASURED_UNREPRESENTABLE`. It is reported separately and is
nonblocking.

V12 therefore exposed a mixed boundary failure:

- promoting `elevating` over `responsible` was a real root-selection error;
- rejecting the focus-local p53 occurrence was an evaluator defect;
- rejecting infected fibroblasts was a reference-compilation defect;
- requiring `levels` as source truth was a benchmark-only mismatch;
- the reported axis failures were cascades, not five independent model errors.

V12 remains sealed and receives no retroactive credit. A forward V13 is
authorized only with a source-general compositional-root rule, a versioned
source-semantic lane, a separate review-only CG projection, and focus-aware
occurrence resolution.
