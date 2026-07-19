# Scientific Reliability Local Commit Loop

## Decision

Scientific iteration advances through validated commits on one durable branch.
A pull request is a publication and review checkpoint. It is not permission to
start the next provider-free change or the next preregistered visible
experiment.

The durable branch is:

```text
alvaro/tg04-local-scientific-loop
```

Do not rebase this branch after a report or receipt cites one of its commits.
Frozen commit identities are scientific custody. Reconcile upstream changes by
merge, and record any GitHub squash mapping without rewriting the local
history.

## Two Independent Lanes

### Scientific lane

The scientific lane owns hypotheses, source snapshots, prompts, agent calls,
deterministic metrics, result artifacts, and stop or continue decisions. It may
advance while any publication PR is awaiting review, CI, approval, or merge.

### Publication lane

The publication lane cuts a branch from a validated scientific checkpoint and
opens a PR for maintainability, integration, and external review. A pending PR
may block release to `main`; it does not block the scientific lane.

Reviewer fixes that affect scientific meaning or safety must exist on the
durable scientific branch before the next live experiment. Prefer implementing
the fix there and cherry-picking it into the publication branch. If a fix is
made on a PR branch first, cherry-pick it back immediately and rerun the
affected local gate.

## One Scientific Cycle

Each cycle has at most six commit checkpoints. A checkpoint may combine steps
only when no provider call or frozen artifact separates them.

1. **C0 - Reconcile:** fetch `origin/main`, inspect divergence, and merge at a
   clean experiment boundary. Never rewrite a cited commit.
2. **C1 - Preregister:** commit the source snapshot, case identity, parent
   commit, model, prompts and schemas, allowed tools, call budget, hypothesis,
   deterministic metrics, and stop rules. No provider call occurs before C1.
3. **C2 - Expose failure:** add provider-free unit, regression, contract, and
   adversarial tests that reproduce the root cause. Tests must distinguish
   source entailment, completeness, trust eligibility, and graph projection.
4. **C3 - Implement:** make the smallest single-responsibility product change.
   Run focused tests plus lint, type, boundary, and contract checks. Commit only
   after they pass.
5. **C4 - Challenge:** run an independent adversarial review against the frozen
   hypothesis. Fix valid findings in new commits and run `make service-checks`.
6. **C5 - Execute and decide:** with a clean committed worktree, run the exact
   preregistered visible experiment. Freeze provider receipts and outputs, then
   commit a deterministic decision of `CONTINUE_VISIBLE_ONLY`,
   `STOP_AND_RECALIBRATE`, or `READY_FOR_CONFIRMATORY_RUN`.

Push the durable branch after every C1, C4, and C5 checkpoint as a backup. A
push does not require or create a PR.

## Gates That Block Science

GitHub review state does not block the scientific lane. These conditions do:

- the worktree is not clean at a live-call boundary;
- no committed preregistration names the exact source, model, prompt, schema,
  call budget, scorer, and stop rules;
- no create-once durable journal has reserved the experiment before call one;
- focused tests, service checks, or adversarial review have an unresolved
  failure relevant to the experiment;
- agent fallback, deterministic semantic repair, or unverified provider output
  would receive scientific credit;
- the previous visible result is failed or unresolved and the next step tries
  to consume a hidden or confirmatory case;
- the proposed work adds evaluation infrastructure without measuring a product
  field changed in the same cycle;
- two consecutive cycles fail to produce a positive paired scientific change.
  At that point, stop prompt iteration and compare a different model, task
  decomposition, ontology, or expert-seeded workflow.

## Scientific Progress Rule

Agents return categorical findings, exact evidence spans, reasoning, and
falsification conditions. Deterministic code computes every count and rate.

A cycle counts as scientific improvement only when all applicable statements
are true:

- at least one previously incomplete source-supported whole event becomes
  complete;
- no previously correct whole event regresses;
- invented or unsupported event count does not increase;
- polarity, event type, typed participants, context, and epistemic status do
  not regress;
- source-entailed claims remain distinct from trusted projections;
- negative, null, uncertain, and hypothesis lanes do not leak into established
  positive graph relations;
- fallback credit and unauthenticated provider output remain zero.

Safety improvements are valuable, but report them separately from scientific
improvement. More tests, more fields, or more candidates are not scientific
progress by themselves.

## PR Publication Policy

Cut a PR only at C4 or C5. The PR description cites the exact checkpoint commit
and evidence report. While it is open:

- continue provider-free work on the durable branch;
- start another visible experiment only if the prior C5 decision authorizes it;
- do not consume hidden cases merely to keep work moving;
- do not call the PR merge-ready until threads, checks, conflicts, and approval
  are all clear;
- do not make future scientific commits descendants of the PR branch.

After merge, record the GitHub merge or squash commit in the next C0 checkpoint.
The local experiment commits remain the canonical custody lineage.

## Current Cycle

The current scientific cycle compares one visible source under two frozen
representations:

```text
A: extraction -> normalization -> source-only proposal review
C: independent whole-source completeness inventory
   -> independent source-only inventory verification
A_PLUS_C: deterministic metric-only union; never trusted output
```

The completeness agent sees the frozen source, not extractor or normalizer
reasoning. It returns a finite categorical inventory of source-explicit events
and eligible context factors with exact spans and falsification conditions.
Deterministic code compares that inventory with the proposed representation; it
does not make biomedical judgments.

The comparison succeeds only when C finds a real omission that A misses while
adding zero invented events, preserving every already-correct event, producing
verified provider receipts, and keeping disagreement at `FAIL` or `ABSTAIN`
rather than converting it into trusted knowledge. Otherwise record
`STOP_AND_RECALIBRATE` and reconsider the task or model before another live
case.

Current checkpoint: C5 controlled stop. The committed visible run made two
calls, then stopped because normalization labeled two changed representations
`UNCHANGED`. Arm C was never authorized and no scientific comparison occurred.
The sealed result is recorded in
`docs/validation/reports/2026-07-19-tg04-v14-completeness-live-stop.md`.

The next cycle must derive procedural mapping operations deterministically,
keep agent output categorical and explanatory, and preregister a different
visible source before another scientific run.

## Commit Naming

Use the scientific checkpoint, not a future PR number:

```text
docs(evidence): preregister <cycle>
test(evidence): expose <root cause>
feat(evidence): implement <single responsibility>
test(evidence): challenge <safety boundary>
docs(evidence): record <visible result>
```

Each result report records the parent commit, execution commit, model, source
hash, prompt and schema hashes, provider response identities, deterministic
metric version, before and after categorical outcomes, and the next authorized
action.
