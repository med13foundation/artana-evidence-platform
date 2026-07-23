# Fresh-CG V2 Root-Cause Adjudication

## Decision

The sealed V2 case has one confirmed independent model error: the direct-CG
participant occurrence was expanded from `osteonectin` at `[355,366)` to
`osteonectin gene` at `[355,371)`. This is a direct-CG exact-boundary failure.

The original V2 output does not establish four independent scientific failures.
Three source-semantic reference values were wrong, the role result was blocked by
the occurrence mismatch, the attachment evaluator contains an independent
double-iteration defect, and the unsupported count mixed root errors with
mapping cascades. V2 remains byte-identical, unrescored, and without
qualification credit.

## Independent adjudication

Two independent internet-enabled technical adjudicators received the same
anonymized packet:

- BioNLP occurrence and attachment specialist:
  `48cf32d087364de06ac411e520e92b5019465531b279683456a0f7e6f82401b5`
- Biomedical proposition semantics and Artana taxonomy specialist:
  `0beb713cd416bc3d9c261c6c32dfee8c60fa38ded3f54cf34e1402922934f95e`

Both verified the frozen sentence against the official
[NCBI PubMed record](https://pubmed.ncbi.nlm.nih.gov/2681013/). Both reported no
unresolved assigned issue and agreed on the two overlapping classifications, so
the preregistered condition for a third tiebreaker was not met.

## What Artana got right

- It recovered the correct `GENE_EXPRESSION` event and exact `expression`
  trigger.
- It identified the correct biomedical entity and assigned
  `AFFECTED_ENTITY`; exact direct-CG scoring was blocked only because the mention
  included the adjacent generic word `gene`.
- It represented the complete transformed-fibroblast context as one participant:
  `fresh BALB/c fibroblasts transformed by v-Ki-ras`, with
  `CONTEXTUAL_PARTICIPANT`.
- It correctly returned direction `NOT_APPLICABLE`, uncertainty `ASSERTED`,
  comparison `NOT_APPLICABLE`, polarity `AFFIRMED`, and no statistical claim.
- Its occurrence-binding sidecar was structurally valid and exact for the spans
  it selected.

## Root-cause classifications

| Issue | Classification | Independent? | Disposition |
|---|---|---:|---|
| Direct participant occurrence | `MODEL_ERROR` | yes | V10 named-biomedical-occurrence boundary |
| `role:T9` | `MODEL_ERROR` | no | blocked by occurrence mapping; no role-taxonomy change |
| Direct attachment | `EVALUATOR_MAPPING_ERROR` | yes | V3 single traversal; actual case remains blocked by occurrence |
| Contextual participants | `REFERENCE_ERROR` | yes | V3 complete participant, no contained split |
| Direction | `REFERENCE_ERROR` | yes | V3 `NOT_APPLICABLE` for study activity without a biological result |
| Uncertainty | `REFERENCE_ERROR` | yes | V3 `ASSERTED`; `PROVISIONAL` requires explicit status |
| Unsupported count | `EVALUATOR_MAPPING_ERROR` | yes | V3 separates roots from cascades |
| Composite terminal label | `TAXONOMY_AMBIGUITY` | no | human-expert terminal-taxonomy packet |

## Evaluator cascade

The sealed evaluator reported four unsupported items:

1. unmatched direct participant node;
2. unmatched contextual participant node;
3. link to the unmatched direct participant; and
4. link to the unmatched contextual participant.

After adjudication, the contextual node and link match the corrected reference.
The link to the direct participant is downstream of the same occurrence-boundary
failure. The exposed V3 diagnostic therefore records one independent unsupported
root and three cascaded structural misses; it does not retroactively replace the
sealed V2 count.

The attachment evaluator also traversed `link.arguments` twice with the same
loop variable. In a two-argument event it duplicated each target before checking
that the target occurred exactly once. V3 traverses the arguments once and has a
multi-argument regression test.

## Terminal label

`CONTRADICTION_OR_UNSUPPORTED` was mechanically selected by an OR condition.
`contradiction_count` was zero, so no contradiction was observed. Both
adjudicators found the union label ambiguous rather than mechanically incorrect.
The forward diagnostic exposes
`DIRECT_CG_PARTICIPANT_OCCURRENCE_MISMATCH` as the active reason. The remaining
taxonomy choice is isolated in
`2026-07-22-fresh-cg-v2-terminal-human-expert-review-packet-v1.json`.

## Forward-only corrections

### Fresh-CG V3

V3 contains a one-case, exposed-only adjudicated reference and diagnostic
evaluator. Its reference is built from the anonymized candidate packet and
adjudication consensus; the builder does not accept or read model output. The
replay:

- matches the corrected context, direction, and uncertainty;
- marks role and direct attachment `BLOCKED_BY_OCCURRENCE`;
- retains one genuine participant-boundary model error;
- separates one unsupported root from three cascaded structural misses;
- invokes neither the frozen V2 grader nor a provider; and
- recalculates no scientific pass/fail decision.

### Staged generalization V10

V10 is preregistered but not executed. Its only change from V9 is a
source-general participant-boundary rule: for a named gene or protein, do not
expand the lexicalized name with an adjacent generic entity-type word unless
that word is part of the name or is needed to distinguish the occurrence.

V10 must first be tested on existing exposed/public cases. It cannot consume a
fresh case or receive qualification credit before that gate.

The offline exposed/public boundary audit covered five existing V9 cases and 12
participants. It found one independent pre-existing example of the same generic
suffix expansion (`SLC12A3 gene`), produced the V10 boundary `SLC12A3`, and
verified that the existing containment-aware evaluator still recognizes the
same participant. The other 11 participant mentions were unchanged. This audit
made zero provider calls and is not evidence that the model already follows V10.

## Safety and case accounting

- Scientific provider calls in this adjudication: `0`
- Additional fresh cases consumed: `0`
- Remaining uncalled fresh cases: `7`
- Graph writes: `0`
- Trusted-graph promotion: `false`
- Qualification credit: `false`
- V1/V2 artifacts modified: `false`
