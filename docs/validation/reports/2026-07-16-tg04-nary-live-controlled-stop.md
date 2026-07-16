# TG-04 N-ary Live Controlled Stop

Date: 2026-07-16

Status: `INVALID_EXPERIMENT_DESIGN_CONFLICT`

Branch: `alvaro/trusted-claims-tg04-claim-persistence`

Evaluated commit: `dff7c66f`

Model: `openai:gpt-5.6-luna`

Run ID: `tg04-luna-nary-01`

## Decision

Do not run the remaining five model replicates and do not advance framing,
projection, or persistence. The first live arm did not produce a sealed score.
It exposed a representation-contract limitation on a frozen
representability-stress case, so it cannot establish Luna precision or recall.

This is a useful controlled stop, not a scientific-quality pass or fail. TG-04
v1 is invalid for model comparison and must not be resumed after patching.

## What Ran

The smoke run used Artana's production claim-inventory, zero-candidate retry,
independent completeness review, recovery, provider-audit, and exact-span
binding stages. It did not invoke binary relation framing and did not use a
deterministic extraction fallback.

Before the final run, two live-only audit-boundary defects were found and fixed:

1. the earlier binary framing stage rejected a valid n-ary `POPULATION`
   argument, so TG-04 was moved to the production inventory boundary;
2. provider receipt schema selection did not recognize an executed
   zero-candidate retry, so receipt binding was changed to use the canonical
   `pass_role` for every attempt.

Both fixes received focused regressions, adversarial review, and repository
validation. `make service-checks` passed with `87.47%` coverage before the
final live smoke run.

## Exact Live Failure

The run reached frozen case `bionlp-ge-2011:PMID-9361029`, which is explicitly
labeled `REPRESENTABILITY_STRESS` and is excluded from qualification precision,
leakage, and repeatability.

The initial inventory response contained four source-binding defects. The one
allowed agent repair corrected three of them. Its remaining claim used this
complete source span:

> Our unexpected observations of paternal or biallelic expression of WT1 in
> fibroblasts and lymphocytes, together with the previous findings of maternal
> or biallelic expression in placentae and brains, suggest that the
> allele-specific regulatory system of WT1 is unique

The claim's relation cue, `suggest that`, occurred exactly once. Its
`GENE_OR_PROTEIN` argument was `WT1`, which occurred twice in the complete
claim span. The production binder rejected the claim because it requires every
argument text to occur exactly once inside the event span.

Provider-backed audit runs retained in the Artana event store:

- initial inventory: `research-init-extraction:536f8488-ccbd-450c-b069-4749d5db704c`;
- schema/source-binding repair:
  `research-init-extraction:d02641f6-c2fb-4be8-8fe8-eb84a16c2e98`.

No JSON result was sealed at
`/tmp/artana-tg04-live/tg04-luna-nary-01.json`.

## Root Cause

The final failure is not enough to call Luna scientifically wrong. The source
contains two mentions of the same gene in one valid event statement, while the
claim schema supplies argument text but no mention-level anchor. The binder can
therefore detect ambiguity but cannot represent which mention, or that both
mentions refer to the same event participant.

This is also an experiment-design conflict. Representability-stress outputs are
declared descriptive and excluded from qualification metrics, but an
unrepresentable output currently terminates the entire run before any score can
be sealed. Continuing the matrix would measure this known contract limitation
six times instead of comparing model quality.

## Required Redesign

1. Separate semantic participant identity from source-mention localization.
   Agents should continue returning categorical roles and verbatim text, not
   numeric offsets or scores.
2. Add a verbatim mention-context anchor, or preserve every deterministic match
   when repeated text denotes the same participant. Deterministic code should
   calculate offsets from those text anchors.
3. Seal representability-stress failures as descriptive case outcomes rather
   than allowing them to disappear in a traceback. They must remain excluded
   from qualification metrics without hiding provider or validation failures.
4. Separate a qualification lane containing event-gold cases and true negative
   controls from a stress lane that reports categorical `NO_OUTPUT`,
   `BOUND_OUTPUT`, or `UNBINDABLE_OUTPUT` outcomes. Stress outcomes must not
   enter qualification precision, leakage, repeatability, or safety counts;
   provider receipt verification remains mandatory in both lanes.
5. Add regressions for repeated entity mentions, repeated triggers, coreferent
   mentions, and one participant expressed in multiple locations.
6. Because this changes the production output contract and prompt, freeze a new
   fixture and prompt identity. Run one operational pass over all 40 documents
   first; only then restart the three-Luna and three-Sol comparison on a new
   untouched panel.

## Stop Rule Applied

The protocol says to stop when a shared task, ontology, or representation
problem is discovered and to avoid building persistence around an unproven
scientific result. That rule applies here. Trusted-graph promotion remains
disabled, and no scientific-improvement claim is made from this aborted arm.
