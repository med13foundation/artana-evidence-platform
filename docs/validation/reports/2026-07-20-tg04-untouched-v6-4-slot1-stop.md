# TG04 Untouched V6.4 Slot 1 Stop

## Decision

`STOP_BEFORE_BASELINE`

The first preregistered untouched-panel slot was a live, one-shot V6.4 call on
PMID 40289860. It failed structured schema validation. The stop rule therefore
forbids the paired V6.1 call and all later panel slots. This result does not
qualify Artana and does not establish a V6.4 improvement on untouched sources.

## Sealed execution

- Branch head: `ee5578a2badd278fe5d049cc411b45ad504fafa7`
- Model: `openai:gpt-5.6-sol`
- Reasoning effort: provider default (`null`)
- Provider calls: `1`
- Retries: `0`
- Fallback or replay: `0`
- Graph writes: `0`
- Result SHA-256: `ab9d3a9e977d264c7a04a5425adbe313f4498acf7aeb64a5e97cc3bfd69eba00`
- Provider output SHA-256: `2db7b746c4a5cca89fd8485e3bb900e2e8d37ea0b13976134cb88bc9831a96b4`
- Preregistration SHA-256: `35ec027afa72f91cf1d6c467e8516ffd7900e4bdc23955c1d3da28b4edeb7955`
- V6.4 contract SHA-256: `80f9feb17a58dd60b1e6f58b1022dd28904bec375dd88ecbdf109414f27e44ec`

The external one-shot artifacts are under
`/Users/alvaro/.codex/artana-evidence-experiments/tg04/untouched_v6_1_v6_4_panel_v1`.

## Exact failure

The raw payload failed two deterministic contract rules:

1. A dexamethasone null comparison used `EQUAL_TO + NULL_RESULT`; V6.4 permits
   `NULL_RESULT` only with `NO_DIFFERENCE`. The source reported 27% versus 28%,
   so literal equality would also be scientifically too strong.
2. A sensitivity-analysis non-association used `NO_DIFFERENCE` without a
   comparator context. The source states that steroid dose was no longer
   associated with worse survival, which is not a group-comparison relation.

## Scientific diagnostic

The invalid raw payload nevertheless recovered most explicit source content:

- all four descriptive between-group findings;
- the overall-survival null evidence;
- all three worse-survival associations; and
- the sensitivity-analysis null evidence.

It did not preserve the complete scientific frame:

- unadjusted Kaplan-Meier and adjusted-model survival findings were merged into
  one assertion rather than represented as distinct analysis frames;
- the sensitivity-analysis result used the wrong relation family;
- observational exposures were placed in intervention slots;
- worse survival was represented as a second outcome entity rather than an
  outcome direction; and
- small unsupported normalizations appeared in rationale text.

Two independent source-only reviewers both returned `INCOMPLETE` and
`UNSUPPORTED_ADDITIONS_PRESENT`. Their disagreement about whether the
sensitivity-analysis prose was semantically adequate does not alter the result:
the deterministic contract rejected its structure.

The reviewers counted analytic-cohort enrollment as missing, but the frozen
gold scope explicitly excludes enrollment. That reviewer finding is therefore
not included in deterministic recall.

## Reasoning-effort evidence

Reasoning effort has already been isolated on an exposed source with Sol:

- explicit `medium`: provider output was schema-invalid;
- explicit `xhigh`: the one permitted call timed out at the fixed limit; and
- neither arm reached blinded scientific comparison.

Therefore higher reasoning effort is not proven to improve extraction. This
untouched slot used provider-default reasoning because the paired experiment
was designed to isolate the representation contract, not reasoning effort.

## Root cause

The current output language is narrower than common observational biomedical
claims. More reasoning cannot reliably select categories that do not exist.
The missing first-class distinctions are:

- `NOT_ASSOCIATED_WITH` versus between-group `NO_DIFFERENCE`;
- intervention versus observational exposure;
- unadjusted, adjusted, post-hoc, and sensitivity analysis frames; and
- outcome identity versus direction such as better or worse.

The absence of an atomic analysis-frame field also allows one assertion to
merge independently falsifiable analyses.

## Next controlled hypothesis

Build and adversarially test a new external contract on exposed sources only.
It should add:

1. a categorical association-null relation;
2. separate intervention and exposure roles;
3. exactly one categorical analysis frame per atomic assertion; and
4. a categorical outcome-direction field.

Do not modify this stopped panel or rerun PMID 40289860 as untouched. After the
new contract passes exposed adversarial tests, freeze a new source and compare
it once against V6.4. Do not spend another call merely by increasing reasoning
effort unless a separately preregistered timeout-safe effort experiment is the
sole variable.
