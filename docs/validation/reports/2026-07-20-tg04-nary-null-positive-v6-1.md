# TG04 N-ary Null-Positive V6.1 Checkpoint

## Decision

`COMPLETE_FRAME_FAIL`

This exposed, nonqualifying run improved structural validity but did not preserve
the complete scientific meaning. It must remain review-only and cannot count
toward trusted-graph qualification.

## Reasoning-effort context

Explicit Sol reasoning effort was already tested in a controlled exposed probe:

- `medium` reached the provider but returned schema-invalid structure;
- `xhigh` exceeded the preregistered 90-second one-shot timeout;
- neither arm produced an accepted scientific ledger, so no reasoning-effort
  improvement was established.

The V6.1 run therefore used provider-default reasoning to isolate one variable:
the non-redundant n-ary assertion contract. Raising reasoning effort and changing
the representation together would make the result uninterpretable.

## Live result

- Model: `openai:gpt-5.6-sol`
- Provider calls: `1`
- Live receipt: `verified_live`
- Attempt lineage: `PASS`
- Schema and deterministic semantic validation: `PASS`
- Fallback or replay: `0`
- Graph writes: `0`
- Result SHA-256: `70801018a9443eccf5d7d6494247e7491c50e78bc2064ab42f5498f3caf66520`
- Contract adversarial tests: `30 passed`

The ledger correctly separated:

1. `NO_DIFFERENCE / NULL_RESULT`: IL-4 did not differentially promote cell
   growth in FOXP3+ versus FOXP3- populations.
2. `INCREASES / SUPPORT`: both populations showed enhanced proliferation.

## Scientific failure

Two independent source-only reviewers unanimously passed exact evidence,
comparative-null recovery, positive-effect recovery, population cardinality,
role fidelity, null-positive separation, negative-leakage safety, and absence of
unsupported additions.

Both failed whole-claim completeness. Grouping FOXP3+ and FOXP3- under one
`INCREASES` assertion says that both increased, but does not say their degree of
enhancement was similar. The structured ledger could still be true if one
population increased strongly and the other weakly; the source word `similarly`
excludes that interpretation.

Review packet SHA-256:
`e5a0b12c030fadbe503bfe77008a05e6627a734dfff849ee79109723219683e7`.

## Root cause and next experiment

The remaining defect is not generic relation extraction and is not currently
shown to be insufficient reasoning effort. It is loss of a comparison over the
degree of a positive effect.

The next small exposed experiment should keep the model, source, prompt, and
V6.1 safety invariants fixed while making comparative modifiers such as
`similarly` an explicit categorical structure. It should advance only if the
ledger preserves both the positive effect and its between-population equality,
with zero unsupported statistical-equivalence claims. A stronger reasoning arm
is worth retesting only after the latency budget and accepted contract are held
constant, so its causal contribution can be measured.
