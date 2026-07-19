# TG-04 V13 Visible Anaphoric Canary Result

## Decision

`STOP_WORKFLOW_INVALID`.

The one-shot visible canary is consumed. It does not authorize a retry, the
eight-case visible matrix, a hidden unit, replication, trusted-graph promotion,
or graph persistence.

This is a negative workflow result with a scientifically correct core and one
unsupported normalized addition. It is not a Gate B pass, a benchmark false
negative, or evidence that Luna failed to understand the nested biology.

## Frozen Execution Evidence

- repository head: `68bef452e5aeb61a7802b9333f95cb2a3549df4e`;
- code-under-test parent: `aa070603d6621d20c10b1d414ae568d28b614487`;
- model: `openai:gpt-5.6-luna`;
- execution contract: `tg04.finite_source_unit.v13_execution.v2`;
- configured calls: exactly three, stopped after the failed second stage;
- provider attempts: `2`;
- verified live provider receipts: `2/2`;
- retries: `0`;
- deterministic scientific repairs: `0`;
- fallback outputs: `0`;
- graph writes: `0`;
- embedded canonical report SHA-256:
  `eca2fd78fd4d875896b828f7b8397c66b23a76933049aab6279ec76b23354244`;
- serialized report SHA-256:
  `09f1a1611ff2b232fa0565c471758ebcf7ad3ea3c302d1475f582262776d7cf4`;
- journal SHA-256:
  `d5458f71078519d5b22a4a01baea154bd3067606af5b8183181a7a016d868f31`.

The embedded digest was independently recomputed after removing its own field
and matched. The journal terminal record seals the same embedded digest. The
durable reservation and result remain at the preregistered create-once path.

## What The Agents Recovered

The primary extraction was accepted. It returned exactly two independently
source-asserted scientific findings:

1. `EGF` positively regulates `ERK`, with cue `activated`, outcome `SUPPORT`,
   and epistemic status `ASSERTED`.
2. The `MEK1-null genotype` negatively regulates `that activation`, with cue
   `reduced`, outcome `SUPPORT`, and epistemic status `ASSERTED`.

The normalizer preserved those events, assigned distinct local IDs, retained
the anaphoric referent `EGF activated ERK`, and added exactly one outer-theme to
inner-event reference. This is the central scientific and topology content the
canary was designed to test.

## Exact Failure

The normalization agent also categorized the single causal genotype participant
as a multi-level `GENOTYPE` context dimension. The context schema requires at
least two distinct level spans. The agent therefore returned the real
`MEK1-null genotype` span plus a second malformed span containing non-source
text and an Arabic-script suffix.

The deterministic source binder rejected the output with:

`StructuredModelSemanticError: context dimension spans must be verbatim source evidence`

The source contains one genotype participant and no genotype-level comparison.
The addition was scientifically unsupported and correctly stopped the workflow
before the source-only falsifier ran.

## Root Cause

The smallest supported root cause is:

`causal participant/context factor conflation -> forced schema completion -> fabricated level`

The inherited normalization prompt says to represent mutually exclusive factor
levels, but it does not make the eligibility boundary explicit enough. It does
not state that a context dimension requires one source-explicit factor and at
least two distinct, mutually exclusive, verbatim levels. It also does not state
that a genotype or treatment already serving as an event participant is not
automatically a context factor.

This is not a reason to weaken the schema or delete bad context deterministically.
The fail-closed source check is correct.

## Non-Qualifying Counterfactual

A local diagnostic removed only the unsupported `context_dimensions` array from
the preserved raw normalization output. The unchanged agent-authored events then
passed source binding with two accepted events, one controlled-event link, and
family `NESTED`.

This isolates the terminal binder failure. It does not convert the run into a
pass or credit deterministic repair.

Two secondary exact-projection differences remain visible:

- the outer event used the complete sentence instead of the frozen minimal
  outer clause; and
- the variant cause used `MEK1-null genotype` rather than the full noun phrase
  `the MEK1-null genotype`.

They preserve the scientific meaning but would fail this exact canary. They
remain separate span-policy diagnostics rather than being retroactively
accepted or repaired.

## Independent Adjudication

Two independent post-run reviewers categorized the result as scientifically
correct core plus unsupported addition. Both rejected the interpretations that
this was a benchmark false negative, a complete scientific misunderstanding,
or merely an infrastructure failure. Both identified the same schema-pressure
root cause and required the same minimum remediation.

## Next Gate

Before opening a different visible source:

1. Version the normalization prompt.
2. Require `context_dimensions: []` unless the source explicitly contains one
   factor and at least two distinct, mutually exclusive, verbatim levels.
3. State that a participant is not automatically a context factor.
4. Prohibit inventing, translating, repairing, or duplicating level spans to
   satisfy cardinality.
5. Add provider-free regressions for a singleton causal genotype, a genuine
   two-level factor, and the exact consumed malformed payload.
6. Keep source binding, Gate B, no-fallback behavior, and no deterministic
   scientific repair unchanged.
7. Pre-register one genuinely different visible source and consume it once.

The eight-case visible matrix remains blocked until that different canary
passes all three agent stages and both deterministic gates.

## Validation

- The pre-run aggregate `make service-checks` gate passed with `87.48%`
  coverage.
- Focused runner, three-call execution, and controlled-link tests passed.
- Ruff and Mypy passed for the committed runner and focused tests.
- Commit and push hooks passed without skipping.
- Three adversarial pre-provider review rounds were closed before execution.
- Two independent post-run adjudications agreed on the root cause and stop
  decision.
