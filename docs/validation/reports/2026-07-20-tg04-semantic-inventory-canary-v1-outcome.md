# TG04 Semantic Inventory Canary V1 Outcome

Runner decision: `SEMANTIC_INVENTORY_GAIN`

Scientific observation: `CASE_TAILORED_RECOVERY_CONFIRMED`

Experiment disposition: `VETO_GATE_INTEGRITY`

This was a non-qualifying one-call canary on the already-exposed PMID-7749985
source unit. It changed no Artana product code.

## Execution

- Model: `openai:gpt-5.6-sol`
- Model-generation calls: `1`
- Receipt verification used separate provider reads outside the generation
  limiter
- Provider receipts: `1/1` verified live
- Valid, distinct, non-replayed attempt lineage: `true`
- Fallback/replay: `0`
- Graph writes: `0`
- Provider response: `resp_00216ed7ec1be4f1006a5d979994c88198b30ad511e6afcb58`
- Result file SHA-256: `4401b9c045eac7dfc1800e8e0bf2a38db81bf4988abb769a6d7df9f097fd4e18`
- Internal report SHA-256: `409a8ab68028ae40b40351b537ada402e826f54db3d1121a93252a6cdc5b7ff0`

## Scientific Result

The provider did not assign graph roles or compose events. It inventoried the
affected gene/transcriptional target, distinct regulatory elements, genomic
locus, population, controller, controlled process, cues, event types, polarity,
and epistemic status.

Sol correctly returned `DR alpha`, separate `S` and `X2`, the `DR alpha proximal
promoter` as non-anatomical, `group II CID cells`, and `CIITA`. Deterministic code
compiled two views:

- BioNLP-compatible projection: exact required-event recovery `2/2`;
- source-complete Artana projection: two children plus one outer CIITA regulation
  event, with complete controlled topology.

An independent source-only agent judged every event and controlled edge
`ENTAILED`, found no unsupported addition, and returned overall `PASS`.

## Adversarial Limits

The post-run adversarial audit narrowed the claim:

- required inventory fields encode a regulatory-biology decomposition learned
  from this exposed failure, so the canary does not prove general role discovery;
- the exact gate did not explicitly reject extra corpus events, although this
  output contained exactly two events for two required events;
- the raw runner assigned gain before the later independent review, so only this
  post-review report may state the final interpretation; and
- the one-call count covers generation, while provider receipt reads must be
  reported separately.

A second benchmark-aware auditor recomputed the actual event multisets and
confirmed two genuine matches, no missing gold, and no extra predicted corpus
event. It still returned `VETO`: read-only counterfactuals with an extra child, a
negative outer relation, or the wrong controller could pass the implemented gate.
The veto concerns gate integrity, not the biomedical content of this response.

## Meaning

This is the first direct improvement response in the current loop whose actual
content reached `2/2` and later passed independent source-only review. It supports
the hypothesis that the main blocker is not absence of biomedical understanding
in Sol. The tailored schema and underconstrained gate prevent calling the
experiment or generalized architecture successful.

## Boundary And Next Gate

This result is one exposed regulatory-biology sentence and uses fields tailored
to that event family. It does not qualify Artana and does not release a holdout.

Next, compare a generic optional semantic-occurrence inventory against full-
composition Sol on a small exposed panel with varied event structures. Require
exact event-set equality so extras fail, and record independent source-only review
before assigning gain. If it does not generalize cleanly, stop and run the
established biomedical-parser hybrid before any untouched source.
