# TG04 Recall-Only Discovery Comparison V1

Created: 2026-07-20

Formal execution status: `COMPLETED_RECALL_ONLY_COMPARISON`

Comparison validity: `PARTIAL_AGENT_LANE_VALID_SPECIALIST_LANES_UNSCORABLE`

Recommendation: `AGENT_ONLY_DISCOVERY`

This was an external, non-qualifying recall experiment. No candidate is
evidence, no graph relation was created, and no scientific interpretation was
promoted.

## Executive Result

The source-general `gpt-5.6-sol` lane produced the only valid scored result:

- formal scope recall: **29/31 = 93.55%**;
- formal trigger recall: **29/31 = 93.55%**;
- raw exact-passage and exact-trigger coverage before participant grounding:
  **31/31 = 100%**;
- resolved proposals: **92** from **94** raw proposals;
- duplicate proposals under the frozen key: **0**;
- exact passages or triggers invented by Sol: **0**;
- candidates outside the 31-scope inventory: **39**, all source-grounded but
  scientifically unadjudicated.

The formal two-scope loss was caused by the deterministic participant-grounding
rule, not discovery. Sol returned the exact null-result passage and trigger
twice, once for the unadjusted observation and once for the adjusted
observation. Both were rejected because repeated participant mentions were not
unique inside the passage.

The specialist scores of zero are **not valid scientific zeroes**. Their raw
tools ran, but the frozen adapters failed to normalize their real output
interfaces. No corrected score or replacement output was introduced after the
seal.

## Preregistration

- sources: **5 already-exposed abstracts**;
- adjudicated event scopes: **31**;
- corpus families: clinical comparisons and null findings, therapeutic
  outcomes, gene-therapy safety and uncertainty, human genetics, and molecular
  mechanisms;
- gold inventory SHA-256:
  `bef14f3b55d47bf41558f07a5c2da80a3f28686843aee097288f7f4f7408be61`;
- frozen code SHA-256:
  `533060875252873244f26620c4d4a01a9d2ccc6bf2dd200b31eeafab19de070a`;
- prompt SHA-256:
  `0d4bfbe10632a7d7b70458eb72d8246711f6df877924e2265447f9a223ca6cd7`;
- result SHA-256:
  `3c634fb7ce1bc229e370242e0a6a904ef95d2bf991eef904387a4e3e666d40fa`;
- retries: **0**;
- fallbacks: **0**;
- untouched sources: **0**;
- graph writes: **0**.

Gold scope passages, triggers, counts, and IDs were evaluator-only. They were
not present in Sol's input or either specialist input.

## Formal Metrics

| Lane | Scope recall | Trigger recall | Resolved | Unresolvable | Duplicates |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sol source-general agent | **29/31** | **29/31** | 92 | 2 | 0 |
| PubTator 3 / BioREx | 0/31 | 0/31 | 0 | 0 | 0 |
| DeepEventMine GE11 | 0/31 | 0/31 | 0 | 12 | 0 |
| Formal union | **29/31** | **29/31** | n/a | n/a | n/a |

The union contributed no formal scope beyond Sol because both specialist
adapters produced no normalized candidates. This union score must not be used
as evidence that hybrid discovery has no value.

### Sol By Family

| Family | Scope recall | Trigger recall |
| --- | ---: | ---: |
| Clinical comparison and null | 4/6 | 4/6 |
| Clinical therapeutic outcomes | 10/10 | 10/10 |
| Gene therapy, safety, uncertainty | 8/8 | 8/8 |
| Human genetics | 3/3 | 3/3 |
| Molecular mechanism | 4/4 | 4/4 |

The two formal misses are the same nested null-result passage, split by the gold
inventory into unadjusted and adjusted statistical scopes.

## Specialist Limitations

### PubTator 3 / BioREx

The official API completed in **0.399 seconds** with one request and no retry.
It returned:

- four of the five exposed publications;
- **84 entity annotations**;
- **16 relation annotations**.

The response envelope was `{"PubTator3": [...]}`, while the frozen adapter
accepted only a top-level list or `documents` key. The adapter therefore
normalized zero candidates. The API also omitted the exposed human-genetics
publication, making full-corpus coverage impossible in this run.

PubTator 3 is documented as providing entity and BioREx relation annotations,
but the official service output in this experiment could not be fairly scored
through the frozen adapter. The preserved raw response remains candidate-only.
See the [PubTator 3 API](https://www.ncbi.nlm.nih.gov/research/pubtator3/api)
and [PubTator 3 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11223843/).

### DeepEventMine GE11

The pinned container completed in **23.319 seconds** with one CPU run and no
retry. It produced:

- no events for the two clinical-comparison sources;
- four protein entities and no events for the genetics source;
- **nine postprocessed nested molecular events** for the molecular-mechanism
  source.

The frozen adapter read `ev-tok-ann`, whose offsets refer to tokenized text,
instead of the postprocessed `recall-panel-brat/*.ann` files containing
original-source offsets. All twelve raw event records were consequently marked
unresolvable.

This is an adapter-boundary failure, not evidence that DeepEventMine returned
no useful molecular candidates. DeepEventMine is designed for nested biomedical
events, but its GE11 training domain is molecular rather than broad clinical
abstracts. See the
[DeepEventMine paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7750964/).

## Calls, Tokens, Latency, Cost

| Lane | Calls | Input tokens | Output tokens | Reasoning tokens | Latency | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sol | 5 | 4,811 | 32,705 | 19,243 | 582.151 s | **$1.005205** |
| PubTator 3 | 1 HTTP request | n/a | n/a | n/a | 0.399 s | $0 API fee |
| DeepEventMine | 1 local run | n/a | n/a | n/a | 23.319 s | $0 API fee |

Sol cost uses the preregistered LiteLLM 1.83.0 pricing snapshot: $5 per million
input tokens, $0.50 per million cached-input tokens, and $30 per million output
tokens. It excludes local compute and network overhead.

All five stored Sol response IDs were retrieved after execution and their model
identity and token usage matched the sealed receipts.

## Interpretation

Sol demonstrated strong **discovery recall**, not scientific precision. It
returned 92 grounded candidates for 31 adjudicated scopes. Fifty-three
candidates overlapped at least one scope; 39 additional candidates were exact
source passages outside this inventory. Those additional candidates may be
useful findings, background, methods, hypotheses, alternate decompositions, or
noise. This experiment did not adjudicate them and grants them no credit.

The specialist lanes cannot be ranked from this run. Correcting their adapters
after seeing the outputs would violate the frozen comparison. Their raw
artifacts are preserved so a separate normalization-only replay could test the
mapping boundary without rerunning Sol or the tools.

## Recommendation

**Use agent-only discovery for the next bounded scientific step.**

This recommendation is operational and provisional:

1. Sol is the only lane with a valid measured result.
2. Its raw passage and trigger discovery covered all 31 exposed scopes.
3. It required no expected IDs, counts, gold phrases, or source-specific
   instructions.
4. Its candidates still require independent agent adjudication before they can
   become evidence.
5. Do not build the broader ontology yet.
6. Do not claim specialist inferiority or discard the preserved specialist raw
   outputs.

Before reconsidering a hybrid, run a separate **normalization-only replay** over
the already-sealed PubTator and DeepEventMine outputs. That replay must consume
no provider calls and must not alter this result.

## Safety Conclusion

The experiment supports source-general Sol as a high-recall candidate
discovery mechanism on the exposed corpus. It does **not** establish trusted
evidence precision, valuable-event precision, repeatability, untouched-source
generalization, or graph readiness.
