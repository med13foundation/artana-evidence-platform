# TG-04 V13 Context And Custody Checkpoint

## Decision

`CONTINUE_VISIBLE_ONLY`.

The consumed V13 anaphoric canary remains a scientifically negative workflow
result. This checkpoint fixes the unsupported context-dimension root cause and
prevents a locally consistent three-call run from being mistaken for scientific
qualification. It does not authorize a hidden unit, the visible matrix, graph
persistence, or trusted-graph promotion.

## What Improved

- The normalization agent must omit a context dimension unless the source names
  one explicit factor and at least two distinct, mutually exclusive, verbatim
  levels of that factor.
- The source-only review agent categorizes factor eligibility, level membership,
  event scope, crossing support, and the final context decision with separate
  evidence spans.
- Unsupported proposed dimensions deterministically produce `FAIL`; unresolved
  or provisionally supported dimensions produce `ABSTAIN`.
- Extraction, normalization, review, raw provider payloads, audit records, and
  source identity are tied through canonical replay envelopes.
- Official V13 execution uses a frozen component manifest and private copies of
  prompt functions and their captured dependencies. Public policy rebinding or
  mutation cannot alter the issued prompts.
- Raw-string enum injection, detached result substitution, copied binding
  rejections, and relabelled official component tuples fail closed.
- `local_review_passed` records only local consistency. The three-call evidence
  topology always reports `scientifically_qualified = false`.

## Why Qualification Is Still Blocked

The extraction and normalization agents can agree while both omit a real event
or a real source-explicit context factor. The current reviewer checks proposed
items, not an independent inventory of everything in the source. Also, local
audit records preserve provider response identifiers but do not themselves prove
later live retrieval and verification of those responses.

The next contract therefore needs evidence, not an unlock flag:

1. A source-only agent independently inventories scientific events and eligible
   context factors, returning categorical items, exact spans, reasoning, and
   falsification conditions.
2. Deterministic code binds that inventory to the same frozen source and compares
   it with extraction and normalization without making biomedical judgments.
3. Missing or disputed items stop at `FAIL` or `ABSTAIN`.
4. A verified-live receipt envelope binds retrieved provider output, model,
   schema, prompt, source, and audit hashes.
5. Only a later evidence-bearing contract may define scientific qualification.

## Validation Evidence

- Focused provider-free suite: `85 passed`.
- Ruff: passed for all changed source and test files.
- Mypy: no issues in seven changed source modules.
- Historical V13 canary runner: unchanged.
- New provider calls: `0`.
- Hidden units consumed: `0`.
- Graph writes: `0`.
- Full repository `make service-checks`: passed with `87.48%` coverage after
  clean ephemeral Postgres creation, migration, test execution, and teardown.
- Final independent adversarial closeout: `CLEAN` after three remediation rounds.

## Next Experiment

Pre-register one different visible source and compare two representations before
any hidden work:

- the current three-call event/normalization/review representation; and
- the same representation plus one independent source-only completeness
  inventory.

The experiment succeeds only if the completeness witness identifies omissions
without inventing events, all evidence binds to the source, repeated categorical
decisions are stable, live receipts verify, and deterministic comparison never
converts an agent disagreement into a scientific fact.
