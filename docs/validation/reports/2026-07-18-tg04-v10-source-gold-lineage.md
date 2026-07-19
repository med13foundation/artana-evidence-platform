# TG04 V10 Source-Gold Lineage

## Purpose

This receipt freezes the V10 source, two acceptable scientific representation
families, prompt identities, source custody, and adversarial decisions before
any V10 Artana or Luna execution. It authorizes at most one repeat-1 diagnostic.
It does not claim human-expert validation or trusted-graph readiness.

## Frozen Source

V10 is source unit 17 from `PMC-2222968-04-Results-03`:

> Similarly pre-existing iTreg cells did not decrease FOXP3 expression upon
> IL-4 exposure (Figure S3B).

The content-blind selector used the finalized V9 report hash as its seed,
excluded every V1-V9 document, found three eligible negated-result graphs, and
selected the lowest SHA-256 rank. No V10 agent output existed during selection
or source adjudication.

The authoritative BioNLP standoff records are:

- `T58 Protein 2674 2679 FOXP3`;
- `T59 Protein 2696 2700 IL-4`;
- `T84 Negative_regulation 2665 2673 decrease`;
- `T85 Gene_expression 2680 2690 expression`;
- `E30 Negative_regulation:T84 Theme:E31 Cause:T59`;
- `E31 Gene_expression:T85 Theme:T58`;
- `M11 Negation E30`.

## Scientific Contract

V10 accepts exactly two complete families. Partial claims cannot be assembled
across them.

1. `BIONLP_EXPERT`: a negated `NEGATIVE_REGULATION` event with IL-4 as `CAUSE`,
   a controlled FOXP3 `EXPRESSION` target, and the corpus-native cue `decrease`.
2. `SOURCE_VALID_ALTERNATIVE`: one noncausal `DECREASE` event with FOXP3 as
   `THEME`, `FOXP3 expression` as `OUTCOME/EFFECT`, no invented IL-4 cause, and
   the shortest source-only negated cue `not decrease`.

The pre-existing iTreg population scopes both BioNLP events and the direct
event. `IL-4 exposure` and `upon IL-4 exposure` scope only the tested change,
not the unasserted controlled expression target. `pre-existing` remains part
of the population identity rather than becoming an invented timeframe.

The immutable identities are:

- expert graph: `ddd564c4fc7a431358df7f193c4b0284ff5dcebc87a4fd6ce6f61d6b29f28cc5`;
- projection set: `4f6add86982fe4eabb9df893ee71af9b8cce60aa1b280d18edff9598004821cd`;
- extraction prompt: `13f5cb79aaa72d97b11628ed48847a562ca553a010131b47021d87ce8ccac4e7`;
- verification prompt probe: `bbd7aeb9e7365e2744ca843ca4425f4b57d79698b3362f7c8ce146c3ccdc7c0d`.

## Adversarial Review

The first scientific review returned `NO_GO`. It demonstrated that the initial
gold required causal `NEGATIVE_REGULATION` even though Artana's source-only
policy correctly forbids inferring causation from temporal exposure. It also
found process-role, cue-mode, and context-scope contradictions. The corrected
contract separates corpus-native and source-only families and adds explicit
negative tests for every counterexample.

The post-remediation scientific review returned `GO`. It rejected wrong IL-4
types and roles, wrong inner roles, cross-family cues, wrong outcome typing,
invented causes, missing timeframes, wrong polarity, duplicate claims, mixed
families, and extra trusted candidates. Exact offsets and both sealed hashes
matched the corpus.

The first execution review returned `NO_GO`. It proved that the same local
reservation could authorize repeated calls, and that source and prompt custody
was incomplete. V10 now uses an atomic create-once execution lease, consumes a
failed execution, binds lease and frozen identities into provider evidence,
and rejects source, graph, projection, prompt, model, receipt, stale-report,
and previous-repeat mutations.

The post-remediation execution review returned
`GO_WITH_DISCLOSED_GOVERNANCE_LIMITATION`. No counterexample remains under the
declared threat boundary: the repository administrator is trusted not to
delete or rewrite all custody records deliberately. Protection against a
malicious administrator requires an external append-only authority and is not
claimed by this local diagnostic.

## Stop/Go Boundary

V10 repeat 1 may run only from the committed clean tree represented by this
receipt. It must use `openai:gpt-5.6-luna`, the agent-only extraction and
verification path, two live provider receipts, and no deterministic fallback.

A scientific pass requires one and only one complete accepted family, all
candidates source-entailed, complete inventory coverage, zero unmatched trusted
candidates, zero link ambiguity or orphans, exact model and prompt lineage, and
verified provider receipts. Any failure finalizes the receipt as a negative
result and blocks repeat 2.

## Scope

- Artana V10 execution attempted: no.
- Luna V10 output available to reviewers: no.
- Numeric LLM scoring used: no.
- Human-expert gold established: no.
- Trusted-graph promotion authorized: no.
- One repeat-1 live diagnostic authorized after commit and clean-tree checks: yes.
