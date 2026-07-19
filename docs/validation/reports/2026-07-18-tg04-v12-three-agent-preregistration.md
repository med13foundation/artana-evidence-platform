# TG-04 V12 Three-Agent Scientific Preregistration

## Status

V12 is frozen for repository validation and adversarial review. No V12 provider
call has been made and no repeat reservation has been consumed.

This trial addresses the exact V11 workflow failure: the normalization schema
allowed a missing `local_event_id` while deterministic binding required stable
event identities. V12 also tests whether a coordinated source statement remains
scientifically complete when the imported corpus graph contains only one target.

## Frozen Source Identity

- archive SHA-256:
  `f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f`
- selection seed, the finalized V11 report SHA-256:
  `ac922afa3297dd94810ff8f96078357e36ab725efa1352c45f63f414d6a3f2e7`
- selection rule:
  `lowest_sha256_any_closed_graph_seeded_by_finalized_v11_report`
- eligible source-unit count: `44`
- case: `bionlp-ge-2011-holdout:PMID-10229231`
- unit index: `0`
- unit ID:
  `source-unit-58bfd6e4d47486aa4c39f5f7b542b92d06108bd490a074ffae85f8a31fbb8ace`
- source range: `0..78`
- source SHA-256:
  `1bd49ba3ef2ddcaaba8a26f16c9fb69479a946550bd37a60a71782123c651921`
- input SHA-256:
  `276f6c20c0fe7422111dc1d229ad1d03431449280fa4c645483ea42da85c7d87`
- authoritative article: `https://pubmed.ncbi.nlm.nih.gov/10229231/`

The content-blind winner was fixed before its source text and expert graph were
inspected.

## Source-Only Scientific Adjudication

The frozen title is:

> Regulation of Fas ligand expression and cell death by apoptosis-linked gene 4.

The expected category is `FINDING`. The title asserts direction-neutral
regulation by apoptosis-linked gene 4 of two coordinated targets:

1. Fas ligand expression, retaining `Fas ligand` as a separately typed
   `GENE_OR_PROTEIN` participant.
2. Cell death as a separately represented outcome.

It does not establish the direction of either regulation, assert that either
target occurred, equate cell death with apoptosis, or establish that Fas ligand
expression causes cell death.

The imported BioNLP graph contains the expression target but omits cell death.
That graph is valid but source-incomplete and cannot qualify the V12 result.

## Frozen Representation Contract

- canonical expert-graph SHA-256:
  `2ed9270cd4baae75ca69bb4308dd03d9fdc5b7ee0931fa9d6e7d2756cd708878`
- complete projection-set SHA-256:
  `7fefffec28dbfe70ce743afcdc413ca50f56d0093adfbc08f45014679693ef49`
- context-dimension SHA-256:
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`

Exactly four source-complete representation families are admitted:

1. split nested regulation;
2. joint nested regulation;
3. split direct regulation;
4. joint direct regulation.

Every family must preserve apoptosis-linked gene 4, Fas ligand as a typed
participant, Fas ligand expression, and cell death. A partial expression-only
graph or a direct event that hides the Fas ligand participant inside outcome
text receives no credit.

## V12 Provider Contract

The extraction prompt and schema remain frozen from V10 so V12 isolates the
normalization boundary. The second call uses
`SourceUnitNormalizationOutputV12`, which requires every normalized event to
have a nonempty, unique agent-authored ID matching
`^[A-Za-z][A-Za-z0-9_-]*$`.

- deterministic event-ID generation: unavailable;
- deterministic event-ID repair: unavailable;
- deterministic scientific completion: unavailable;
- deterministic extraction fallback: unavailable;
- schema retry: unavailable.

Controlled-event and context references must exactly match those agent-authored
IDs. Adding an ID to an otherwise unchanged source event is a categorical
`REFRAME`, not `UNCHANGED`.

## Frozen Three-Call Topology

1. `primary`: source-only extraction;
2. `structure_normalization`: complete direct, nested, or abstaining
   representation under the V12 schema;
3. `normalized_review`: independent source-only falsification of completeness,
   entailment, roles, topology, and references.

All roles use `openai:gpt-5.6-luna`. Each completed call must have a distinct
provider response ID and a live verified receipt bound to the prompt, schema,
source, invocation, model, and prior-stage dependency chain.

## Deterministic Go Gate

V12 authorizes two fresh replications only when all requirements are true:

- all three agent roles complete exactly once;
- all three agents identify the expected scientific category;
- every normalized event has valid, unique identity and source binding;
- source-to-normalized mappings are exhaustive;
- the reviewer covers every normalized event and all ten material axes;
- all candidates are source-entailed;
- scientific loss, unsupported addition, unresolved axes, and unmatched
  normalized candidates are all zero;
- exactly one complete acceptable projection is recovered;
- all event roles and both coordinated targets are recovered;
- prompt, raw output, model, schema, receipt, and repository custody replay;
- no deterministic fallback or scientific repair contributes to the result.

Any failure finalizes repeat `1` as a negative diagnostic. It does not authorize
retry, graph persistence, or a second hidden unit.

## Adversarial Review Closure

An independent scientific reviewer found that the first draft allowed direct
projections without a separately typed `Fas ligand` participant. Before any
provider call, those alternatives were removed, their positive and negative
regressions were added, and the projection-set hash was updated. The canonical
event graph did not change.

The next independent audit must challenge provider-schema custody, V11 replay
compatibility, content-blind selection, terminal-failure sealing, and any route
where a partial or malformed event could qualify.

That custody audit found four pre-execution defects. Before any provider call:

- all three raw agent payloads, including the independent review, became
  mandatory gate inputs;
- mapping-operation labels became structurally enforced, so false `SPLIT`,
  `REFRAME`, `MERGE`, or `UNCHANGED` provenance cannot pass binding;
- an untouched `RESERVED` sequence became identity-validatable and resumable,
  while any consumed execution lease remains create-once;
- every immutable provider-attempt record is now fsynced to an append-only,
  hash-chained journal at the audit boundary, before downstream parsing can
  continue. Cumulative stage snapshots remain separately journaled, and an
  attempt-only tail can produce a terminal report after interruption without
  another provider call; and
- transient provider-receipt unavailability was moved before final-report
  creation. Recovery rebuilds the one report from journaled agent evidence and
  fresh receipts; permanent receipt mismatches remain fail-closed.

The journal is experimental custody, not scientific credit. An interrupted run
finalizes `STOP_WORKFLOW_INVALID`; it cannot qualify or authorize replication.
No live V12 response was requested while these findings were open.

A final crash-window review found that stage-level snapshots alone left a
process-interruption interval between the in-memory audit append and durable
journal persistence. The attempt-boundary observer closes that interval. An
adversarial regression terminates execution immediately after the first
accepted attempt is fsynced and proves recovery preserves its raw payload,
records exactly one provider call, and remains scientifically non-qualifying.

## Stop/Go Sequence

1. Pass focused V11/V12 tests, strict typing, lint, architecture, and full
   repository service gates.
2. Commit and push the exact frozen implementation and this preregistration.
3. Run exactly one V12 provider-backed diagnostic.
4. If V12 passes, pre-register and run two fresh hidden replications.
5. If V12 fails scientifically, preserve the artifact and classify the failure
   as comprehension, completeness, ontology, binding, verification, or benchmark
   contract before changing code or testing a stronger model.
