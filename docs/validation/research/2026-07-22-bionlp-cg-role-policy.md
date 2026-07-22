# BioNLP Cancer Genetics Role Policy Research

Retrieved: 2026-07-22

## Primary Sources

1. BioNLP-ST 2013 Cancer Genetics task page
   - URL: https://2013.bionlp-st.org/tasks/cancer-genetics-cg-task
   - Retrieved HTML SHA-256: `43f5ba7f2c264f97a9f08b3dbbc91f6d43425493b68f54354a25f292d786aa16`
   - The official page identifies CG as an event-extraction task and links the
     training, development, test, and evaluation resources.
2. Pyysalo, Ohta, and Ananiadou, "Overview of the Cancer Genetics (CG) task of
   BioNLP Shared Task 2013"
   - Landing page: https://aclanthology.org/W13-2008/
   - PDF: https://aclanthology.org/W13-2008.pdf
   - Retrieved PDF SHA-256: `8e0e4301d869fec7e2e79c3852c0333582b587dda592464ccde05ed975379e07`
   - ACL Anthology ID: W13-2008
3. Public CG development corpus
   - Source URLs are preserved in `validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/SOURCE`.
   - This is primary corpus evidence, not an official prose policy definition.

No standalone official CG annotation manual was found through the task page,
paper, corpus README, or linked task materials. The paper states that CG extends
prior MLEE and BioNLP Shared Task annotation practice. Conclusions below do not
claim that corpus regularities are official written rules.

## Frozen Policy Rules

### `CG-OFFICIAL-THEME`

The task paper defines Theme as the argument undergoing the event's primary
effect (paper, section 2.3, page 3).

### `CG-OFFICIAL-CAUSE`

The task paper defines Cause as the argument responsible for the event's
occurrence (paper, section 2.3, page 3).

### `CG-OFFICIAL-PARTICIPANT`

The task paper defines Participant as an argument whose precise role is not
stated (paper, section 2.3, page 3).

### `CG-OFFICIAL-INSTRUMENT`

The task paper's event table and Figure 1 permit Instrument for Planned process
events, including treatment examples. The prose does not provide a broader
semantic definition.

## Sensitivity-To-Drug Finding

Neither the official task page nor the task paper states that a drug in
`sensitivity to <drug>` is scientifically responsible for sensitivity. Under the
paper's general Cause definition, that stronger reading is not licensed by the
preposition `to` alone.

The exposed development corpus nevertheless repeatedly represents the drug as
`Cause` for Regulation events triggered by `sensitivity`, `sensitive`,
`response`, or `responsive`. The frozen panel includes the complete exposed
development set of ten eligible Simple_chemical arguments regardless of their
gold role; all ten are `Cause`. This regularity is recorded as:

`CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE`

It is an `EVALUATION_ONLY_CORPUS_INFERENCE`, not an official rule and not a
scientific causal claim.

## Preregistered Interpretation Boundary

The experiment may preserve a cautious source role such as
`STIMULUS_OR_OBJECT` while separately projecting `CAUSE` for BioNLP CG
evaluation. Such a projection must:

- remain review-only;
- carry scope `BIONLP_CG_EVALUATION_ONLY`;
- never overwrite source meaning;
- never be promoted to the scientific graph;
- never be verbalized as "the drug caused sensitivity" without explicit causal
  wording in the source.
