# TG04 Paired Stronger-Model Probe V1 Outcome

Status: `STOP_LLM_EVENT_COMPOSITION`

This was a non-qualifying comparison on the already-exposed first source from
the V13-versus-V14 pilot. It changed no Artana product code.

## Execution

- Luna: `openai:gpt-5.6-luna`, one generation call
- Sol: `openai:gpt-5.6-sol`, one generation call
- Provider calls: `2`
- Provider receipts: `2/2` verified live
- Valid, distinct, non-replayed attempt lineage: `true`
- Fallback/replay: `0`
- Graph writes: `0`
- Result file SHA-256: `b2591f8d9d5fecda8d8c55ffc6cbbf119b71d80203e3192cdf3efc8c55059ee6`
- Internal report SHA-256: `e0393756bb5b2cb616e1b0662a67da571cc1b1d85d3a082d2285d275cb2c0e3f`

## Scientific Result

Neither arm recovered either frozen event exactly. Luna emitted one flat event,
merged `S` and `X2`, and omitted the distinct outer CIITA-dependence frame.

Sol was materially closer. It:

- preserved `S` and `X2` as separate participants;
- generated one child event for each site;
- retained the `group II CID cells` context; and
- generated an outer CIITA-dependence event controlling both children.

Sol still used `multiple cis elements` as the child Theme and added the promoter
as a Site. The expert corpus requires `DR alpha` as the gene/protein Theme and
`S` or `X2` as Site. Exact required-event recovery therefore remained `0/2`.
The source-supported outer claim did not compensate for malformed required child
roles.

An independent source-only review judged Sol scientifically better, judged its
outer CIITA event `ENTAILED`, and judged both children `INSUFFICIENT` because of
role errors. No generated Sol event was judged contradicted.

The exact score also exposed a benchmark-contract defect. The scorer compares a
complete operand tuple as one indivisible key, while the imported BioNLP events
are explicitly unadjudicated and omit source-explicit population and promoter
context that the generation prompt requires. Sol therefore mixed:

- substantive errors: missing `DR alpha` as gene/protein Theme, promoter typed as
  `ANATOMY`, and plural cross-contamination between the two children;
- a projection disagreement over cis-element versus gene-centered Theme; and
- valid source additions absent from the sparse corpus projection.

Thus `0/2` is correct for corpus-exact recovery, but it is not evidence of zero
biomedical recovery.

## Decision

Model strength improved event topology, multiplicity, and participant separation,
but did not solve semantic decomposition. The exposed comparison therefore earns
no fresh holdout call and no product implementation.

The next bounded experiment is a true semantic inventory rather than another
complete-event prompt. One Sol call returns separate affected gene/product,
regulatory element, genomic locus, population, controller, and controlled-process
fields. Deterministic code compiles a BioNLP-compatible projection and a
source-complete Artana projection. Advance only on exact `2/2`, a complete outer
frame, no plural cross-contamination, zero unsupported claims, and independent
source-only review.

If that canary fails, stop LLM-only composition and run the established
biomedical-parser hybrid.
