# TG-04 V14 Completeness A/C Preregistration

## Decision

`AUTHORIZED_FOR_PROVIDER_FREE_IMPLEMENTATION`.

This is a visible development experiment. It does not qualify scientific
quality, authorize a hidden or confirmatory source, authorize graph persistence,
or permit trusted-graph promotion. No provider call may occur until the
provider-free implementation, focused tests, adversarial review, and full
service checks pass from a clean committed worktree.

## Frozen Hypothesis

The current three-agent path can produce a locally consistent representation
while every agent checks the same proposed inventory. An independent agent that
sees only the complete frozen source may identify a source-explicit event omitted
by that proposal path.

The changed variable is one independently verified source-only whole-unit
inventory. Keep three immutable representations:

```text
A: extraction -> normalization -> source-only proposal review
C: independent source-only completeness inventory
   -> independent source-only inventory verification
A_PLUS_C: deterministic metric-only union; never a trusted output
```

The completeness agent receives neither A's events nor any extraction,
normalization, review, benchmark, or reference rationale. It receives only the
frozen source, the categorical prompt, and its output schema.

The inventory verifier receives the frozen source and the completeness items in
source order. It receives no A output, benchmark, reference obligation, or
completeness-agent reasoning. It may categorize each item but cannot discover,
delete, merge, split, repair, or rewrite an event.

## Frozen Source

- fixture: `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json`
- fixture SHA-256:
  `26d67408a7a2446de5d36fca3f8a80a732b6519afe00e303c893eef3c824268d`
- case: `bionlp-ge-2011:PMID-10402173`
- source-unit index: `6`
- source-unit ID:
  `source-unit-5ef1f16712fdc52972162a846d08993bf655b5d7e62d7f0d87599637b0de2f4e`
- document offsets: `947:1123`
- document source SHA-256:
  `a3373f43f94b696ad2ac9830707eae96aa17e6e2e0bc4185f87d768169ca2272`
- source-unit text SHA-256:
  `96d4fc413d71b55675e7f5d2c08b0ce08df582d778af58170576d20485bcb641`
- bound input SHA-256:
  `77f478eba1d0ac017d889c7623b478c84d5f7c123baa4fb61e2b5ea0553771ac`
- preregistration parent commit:
  `867f35ec3bafafd59f7d5a8d333d301a0068b078`

Frozen text:

> RCC-S did not alter the cytoplasmic levels of RelA and NF-kappaB1 but did
> suppress their nuclear localization and inhibited the activation of
> RelA/NF-kappaB1 binding complexes.

This source was selected from the already visible development fixture before
any V14 provider call. Repository search found no prior V13/V14 execution or
result for this sentence. It is not a hidden or confirmatory case.

## Reference Boundaries

The BioNLP fixture contributes two expert-corpus localization events, one for
RelA and one for NF-kappaB1. Their canonical JSON SHA-256 is:

`45640859565caa77236df305bc2a8f848f6189ed88c5f5f9d1ab1e3365829979`

Those annotations are useful anchors, not complete scientific truth. The source
also explicitly contains a tested null result about cytoplasmic levels and an
inhibited activation statement. The BioNLP-to-Artana fixture does not encode
those as eligible events. Therefore:

- a returned item is not an invention merely because it lacks a fixture event;
- fixture matching alone cannot establish whole-source completeness;
- only the two localization participant obligations may receive frozen-reference
  recovery credit in this run;
- additional exact-span source-supported items remain visible, non-lossy, and
  review-only; and
- unsupported additions, contradictions, or unresolved items are failures or
  abstentions, never trusted facts.

The primary metric is `localization-obligation recovery`, not whole-source
completeness. The frozen scoring obligations are:

- `suppressed-nuclear-localization-rela`: RCC-S is the source-explicit cause of
  negative regulation controlling localization of RelA to the nuclear
  destination.
- `suppressed-nuclear-localization-nfkb1`: RCC-S is the source-explicit cause of
  negative regulation controlling localization of NF-kappaB1 to the nuclear
  destination.

A standalone asserted positive `LOCALIZATION`, a cytoplasmic destination,
positive regulation, missing participant, missing nuclear destination, or an
unlinked controlled target does not cover either obligation. The matcher accepts
faithful split or coordinated controlled-event representations; repeated RelA
cannot cover the NF-kappaB1 obligation, and duplicate events cannot increase
coverage.

Two additional frozen clauses are non-scoring completeness diagnostics:

- RCC-S did not alter cytoplasmic levels of RelA and NF-kappaB1; and
- RCC-S inhibited activation of RelA/NF-kappaB1 binding complexes.

Omitting either diagnostic prevents a `whole_source_complete` conclusion and
forces `STOP_AND_RECALIBRATE` even when the localization-obligation metric
improves. A source-entailed item that exactly satisfies either frozen diagnostic
is counted only as diagnostic coverage; unrelated C-only discoveries remain
`REVIEW_ONLY_DISCOVERY`.

## Frozen Contracts

- model: `openai:gpt-5.6-luna`
- A execution policy: `tg04.finite_source_unit.v13_execution.v3`
- experiment contract: `tg04.finite_source_unit.completeness_ab.v1`
- completeness prompt: `tg04.finite_source_unit.whole_source_inventory.v1`
- completeness schema: `SourceUnitCompletenessInventoryOutputV1`
- completeness verification prompt:
  `tg04.finite_source_unit.whole_source_inventory_verification.v1`
- completeness verification schema: `SourceUnitVerificationOutput`
- deterministic metric: `tg04.localization_obligation_recovery.v1`
- issued implementation manifest:
  `00d12f4647f6dfc127e6a1b6650ca45443ae964e240783d20b47eae7bb2cf481`
- network tools: none
- browsing: none
- retrieval: none
- fallback: forbidden
- retry or semantic repair: forbidden
- graph writes: forbidden

The completeness output schema contains only categorical fields:

- unit-level decision: `COMPLETE_INVENTORY`, `NO_EVENT`, or `ABSTAIN`;
- eligibility category;
- zero to sixteen complete normalized scientific events;
- zero to sixteen source-explicit context dimensions;
- exact evidence spans;
- reasoning; and
- a falsification condition.

Each event carries a source-local ID, event type, claim outcome, epistemic
status, assertion scope, trigger, typed participants, event roles, and explicit
controlled-event references where needed. It returns no confidence, score,
probability, rank, or trust decision.

The exact completeness prompt hash, generated JSON-schema hashes, source and
model identities, and callable fingerprints for prompt builders, binders,
verification, and comparison are committed in the issued implementation
manifest before the live call. Provider-free tests prove that prompt
construction exposes only the frozen source and that changing any source,
prompt, schema, model, role, obligation, diagnostic, or execution policy fails
the issued boundary.

## Call Budget

Exactly five Luna calls are permitted:

1. V13-v3 extraction;
2. V13-v3 normalization;
3. V13-v3 source-only proposal review; and
4. V14 source-only whole-unit completeness inventory; and
5. V14 source-only ordered verification of every completeness item.

Calls one through three must be durably persisted and their exact provider
outputs retrieved and verified before call four is authorized. A partial,
invalid, replayed, duplicated, transformed-only, or unverified A execution
leaves the call-four and call-five counters at zero.

The run stops after the first invalid response, transport failure, fallback,
retry attempt, unverified receipt, source-binding mismatch, schema mismatch, or
provider-lineage mismatch. A stopped run receives no scientific credit. No call
may be repeated to improve the answer.

Before call one, the runner must exclusively create a new experiment journal.
The append-only JSONL journal is hash chained, file- and directory-fsynced, and
read back after every stage. It stores complete A raw outputs and audit records,
C inventory and verification raw outputs and records, exact receipts, the final
deterministic comparison, and terminal failures. An existing or sealed journal
refuses a rerun.

The journal proves local ordering and integrity, not external authenticity by
itself. A scientific result exists only when the experiment runner has retrieved
all five provider responses, verified their exact invocation and output custody,
and then sealed the terminal record through the fixed journal state machine.
Reading a JSONL journal alone never qualifies scientific improvement.

## Deterministic Measures

Agents produce categorical evidence. Code calculates all counts and decisions.
The result records:

- A localization-obligation coverage;
- C localization-obligation coverage;
- A-plus-C localization-obligation coverage;
- C-only recovered localization obligations;
- C-only source-bound and entailed inventory count;
- C-only review-only or abstaining inventory count;
- C-only contradicted or insufficient inventory count;
- non-scoring diagnostic-clause coverage;
- unsupported or unbound inventory count;
- preserved A-correct obligation count;
- regressed A-correct obligation count;
- unresolved disagreement count;
- fallback count;
- unauthenticated provider-output count; and
- call count by role.

A scientific improvement requires all of the following:

1. C covers at least one frozen localization obligation that A does
   not cover.
2. A remains byte-for-byte immutable; C cannot overwrite, repair, or delete it.
3. C adds zero source-unbound, source-contradicted, insufficient, or unresolved
   events.
4. Every C item has exact evidence spans in the frozen source.
5. Direction, claim outcome, epistemic status, participants, roles, context,
   and controlled-event topology do not regress.
6. All five provider receipts verify against the committed model, prompt,
   schema, source, output, and audit identities.
7. Fallback, retry, deterministic semantic repair, hidden-source access, and
   graph writes remain zero.

If A already covers both localization obligations and C remains source-faithful,
the outcome is `NO_PAIRED_IMPROVEMENT`, not failure and not evidence that the
completeness role is useful. If C proposes a plausible non-gold source claim,
the independent verifier must first mark it `ENTAILED`. Even then the outcome is
`REVIEW_ONLY_DISCOVERY`; it is preserved but does not satisfy the frozen-reference
improvement hypothesis in this run.

`COMPLETE_INVENTORY` is an untrusted agent assertion. It never changes a metric
or decision by itself. C and A_PLUS_C remain experimental evidence and are never
silently merged into A, production output, or the trusted graph.

## Stop And Continue Rules

- `READY_FOR_CONFIRMATORY_RUN` only when every scientific-improvement condition
  passes.
- `CONTINUE_VISIBLE_ONLY` when the execution is valid but the paired result is
  unchanged, review-only, or abstaining.
- `STOP_AND_RECALIBRATE` on an unsupported addition, regression, invalid output,
  failed receipt, unauthorized call, or semantic repair.
- Hidden or confirmatory material remains prohibited unless the committed C5
  result explicitly records `READY_FOR_CONFIRMATORY_RUN`.
- Two consecutive visible cycles without a positive paired scientific change
  stop completeness-prompt iteration and trigger comparison of model, task
  decomposition, ontology, or expert-seeded alternatives.

## Next Authorized Work

Implement provider-free contracts, prompt isolation, deterministic comparison,
receipt custody, and regression/adversarial tests. Commit those checkpoints and
run the full service gate. Do not call Luna yet.
