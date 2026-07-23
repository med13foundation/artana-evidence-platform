# Fresh CG Occurrence-V2 Experiment Proposal

## Status

`PROPOSED_NOT_AUTHORIZED`

This is a no-call proposal prepared only after occurrence evaluator V2 and the
PMID-21965773 reference adjudication were committed, pushed, and verified at
`fd5abb56f3756dfb918818b99e3e42b38bbc1e40`.

No provider call may be made from this document. A separate machine-readable
preregistration, frozen fresh-case reference, combined provider schema, and
pre-call verification commit are still required.

## Purpose and single change

The proposed experiment asks whether the existing V9 scientific extraction
contract generalizes to fresh public expert-annotated cancer-genetics cases when
evaluated with deterministic occurrence identity.

- Single scientific change: `NONE`.
- Evaluation instrumentation change:
  `ABSOLUTE_SOURCE_OCCURRENCE_BINDINGS_V2`.
- Scientific prompt: V9 semantic instructions remain unchanged. A separate
  non-scientific binding section must request half-open absolute source offsets
  for every event, participant, semantic evidence item, and statistical
  observation.
- Model: `openai:gpt-5.6-luna`.
- Reasoning effort: `high`.

Because there is no scientific prompt change, this experiment cannot establish
improvement over V9. It can establish—or fail to establish—fresh-case
generalization of the current contract.

## Frozen versions

| Boundary | Required version or hash |
| --- | --- |
| Occurrence evaluator | `artana.staged_generalization.occurrence_evaluator.v2` |
| Evaluator package SHA-256 | `610198ea76396485bf61bd16828402d1fd0ecb38e6565b3d0ce6367c110dd5d1` |
| Binding schema | `artana.staged_generalization.occurrence_bindings.v2` |
| Binding schema SHA-256 | `0db47c685c1d6e5dddf644891010cbda3b7694b2de55bf6052cb7856a8ecf68e` |
| Scientific output schema | V9, SHA-256 `02594c4ce1cb089e1b23da0495269a8b457f68b3e57396f345a2258a94eb57c1` |
| Scientific prompt | V9, SHA-256 `4ce450b6a79fdb0cb99c48a69eae1390beef21dcf0094099503c03bdb4dd9234` |
| Regression panel | V9 six-case panel, SHA-256 `00dad3d580755a1c2268e1db32e8ccd1d50771b4a8861138eb18f6593e8e188e` |
| Frozen context policy | V5 dual-lane policy, SHA-256 `7d045ccca6398ca10d3dfc3b8136fa871c9b118bfc05ed19d43daa905e518649` |
| Drug-reference adjudication | SHA-256 `1b85fe564786643bd7e28c9585298e9d93f61f7ff1cbfd82ff3f2e5b3a62a213` |

The fresh reference version is intentionally not invented here. It must be
created from the public CG annotations, reviewed independently, assigned a
version and SHA-256, and committed before preregistration. Until that occurs,
the experiment remains unauthorized.

## Untouched holdout reserve

The current six-case panel remains regression-only and cannot provide new
generalization credit.

The following reserve was selected from BioNLP-ST 2013 CG development documents
that contain public expert `.a1` and `.a2` annotations. Selection used only file
identifiers: documents already named anywhere in tracked repository content
were excluded, and the remainder were ordered by
`SHA256("artana-fresh-cg-holdout-v1:" + document_id)`. Neither source text nor
annotations were inspected during reservation.

1. `PMID-3287150`
2. `PMID-18165897`
3. `PMID-21963494`
4. `PMID-2681013`
5. `PMID-16098727`
6. `PMID-7904970`
7. `PMID-19648108`
8. `PMID-11306510`
9. `PMID-18841154`
10. `PMID-15268651`
11. `PMID-20448329`
12. `PMID-15967832`

An independent benchmark-curation step must choose exactly eight eligible
atomic events from this ordered reserve using preregistered mechanical criteria:

- event and direct entity types must be representable in the unchanged V9
  scientific schema;
- the event and all core arguments must be contained in one permitted source
  context without unresolved coreference;
- the first eligible event in document offset order is selected;
- ineligible documents are skipped with a recorded reason, continuing in the
  listed order; and
- the resulting eight case IDs, source hashes, reference hashes, and untouched
  case order are frozen before any model sees a case.

Curators may not inspect model outputs. The provider packet must omit references,
expected counts, labels, CG roles, and projections.

## Reference lanes

The fresh reference must keep two lanes separate:

1. The direct CG benchmark lane retains the public event/entity types, exact
   offsets, and `Theme`/`Cause` arguments.
2. The Artana source-semantic lane requires independent blinded adjudication for
   Artana roles and axes that CG does not annotate, including direction,
   comparison, polarity, and uncertainty.

No Artana axis may be presented as expert gold merely because it was derived
from CG. Disagreements require a blinded third reviewer. Unresolved fields stay
review-only and cannot be counted as model errors or passes.

## Fail-fast execution rules

- Run the existing six cases offline through evaluator V2 before provider use;
  any regression blocks execution.
- Call the eight fresh cases in their frozen order.
- Stop before the next call on the first invalid custody receipt, occurrence
  binding failure, budget failure, or scientific acceptance failure.
- Provider creations per case: exactly one.
- Silent retries: zero.
- Provider retries: zero.
- Fallback model or parsing path: none.
- Manual output repair: prohibited.
- Historical V5–V9 rescoring or mutation: prohibited.
- Graph writes, promotion, and qualification: prohibited.

## Budgets and custody

| Budget | Limit |
| --- | ---: |
| Calls | 8 maximum |
| Output tokens per call | 20,000 |
| Total tokens per call | 24,000 |
| Latency per call | 900 seconds |
| Cost per call | USD 0.15 |
| Global maximum cost | USD 1.20 |

Each call must produce an immutable attempt record, custody bundle, raw typed
output, and verified live receipt bound to the preregistration hash, provider
input hash, scientific schema hash, binding schema hash, response ID, model,
usage, latency, cost, and all per-call budget decisions.

## Measurable success criteria

Advancement requires all of the following across every called fresh case:

- valid occurrence binding coverage and exact source grounding;
- complete required event and participant recovery;
- exact source-semantic role fidelity on independently resolved fields;
- exact direction, comparison, polarity, uncertainty, and statistics fidelity
  only where those axes received independent resolved references;
- exact nested-event structure;
- zero unsupported claims, ambiguous accepted additions, and contradictions;
- valid receipts and budgets for every provider call; and
- zero graph writes, promotion, or qualification.

Direct CG benchmark projection is reported separately. A source-semantic pass
cannot conceal a benchmark miss, and a benchmark pass cannot substitute CG
`Cause` for an unsupported source-semantic causal claim.

Passing eight fresh cases would be independent benchmark evidence for the
current extraction contract, not production readiness. Failure would be a
valid fail-fast diagnostic. The six exposed regression cases alone can never
satisfy this gate.

## Required pre-call presentation

Before any provider call, the machine-readable preregistration must present and
hash-pin:

- scientific change `NONE` and instrumentation change
  `ABSOLUTE_SOURCE_OCCURRENCE_BINDINGS_V2`;
- the exact evaluator, binding schema, scientific schema, prompt, model, and
  policy versions above;
- the exact eight selected holdout cases and the four unused reserve documents;
- the independently frozen two-lane reference and reviewer identities;
- the fail-fast, zero-retry, no-fallback, budget, receipt, and success rules
  above; and
- evidence that the preregistration commit is present on the remote branch
  before the provider boundary can execute.

Until all of those artifacts exist and pass verification, the decision remains
`DO_NOT_CALL_PROVIDER`.
