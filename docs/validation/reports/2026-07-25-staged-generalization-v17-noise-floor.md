# V17 Noise Floor: the exposed panel does not reproduce its own verdicts

**Date:** 2026-07-25
**Experiment:** 20 replicates × 3 cases = 60 provider calls, $0.9948
**Prompt:** the sealed V17 provider input, verified byte-identical against the
`provider_input_sha256` recorded in the sealed run before any call was issued
**Model:** `gpt-5.6-luna`, reasoning effort `high` — unchanged from the sealed run
**Raw data:** `docs/validation/results/2026-07-25-staged-generalization-v17-noise-floor-v1.json`

---

## Result

| Case | Sealed verdict | Observed | Reproduced | 95% CI |
|---|---|---|---|---|
| `generalization-comparison-canary` | PASS | 19 PASS, 1 FAIL | 19/20 = 0.95 | [0.76, 0.99] |
| `generalization-drug-sensitivity` | PASS | 17 PASS, 3 FAIL | 17/20 = 0.85 | [0.64, 0.95] |
| `generalization-uncertainty` | FAIL | **10 FAIL, 9 PASS** (1 error) | **10/19 = 0.53** | **[0.32, 0.73]** |

**Probability the complete sealed panel verdict reproduces: 0.425.**

The sealed V17 outcome — PASS, PASS, FAIL — is a **minority result**. Replaying
the identical prompt reproduces it less than half the time.

## The uncertainty case is a coin flip

`generalization-uncertainty` is the case the entire V17 → V18 cycle was built
around. V17 was sealed as failing it; the failure was independently classified
as a model/prompt completeness gap; a blinded adjudication was commissioned; and
a complete V18 package was written to repair it.

That failure reproduces **10 times in 19**. Its 95% confidence interval spans
0.5. The result is statistically indistinguishable from a coin flip.

Nine times out of nineteen, the exact prompt sealed as *failing* **passed** —
producing the cohort-to-locus scope link whose absence V18 exists to fix.

## What this invalidates

Every version-to-version comparison in the V6 → V18 series is a comparison of
single draws from overlapping distributions.

- **V16 → V17.** V16 was sealed failing the comparison case; V17 passed it. The
  comparison case reproduces at 0.95, so a single V16 failure is roughly a
  1-in-20 event — consistent with V17 having fixed something, and equally
  consistent with V16 having been unlucky once. One sample cannot separate them.
- **V17's uncertainty failure.** Reproduces at 0.53. The sealed result carries
  almost no information about the prompt.
- **V18.** Built, reviewed, preregistered, and pushed to repair a failure that
  occurs about half the time. Running it would have produced a verdict with a
  ~50% chance of "passing" regardless of whether its rule helps.

The series was not measuring prompt quality. It was sampling.

## What a valid experiment would have cost

Detecting a genuine improvement against this noise floor, at 80% power and
α = 0.05, per case:

| True effect | Replicates per arm |
|---|---|
| 50% → 70% pass rate | ~96 |
| 50% → 80% pass rate | ~42 |
| 50% → 90% pass rate | ~22 |

The series used **one**. Even the most generous assumption — that a prompt fix
lifts the pass rate from 50% to 90% — requires 22 runs per version to detect.
Thirteen versions at 22 runs × 3 cases would have been roughly 860 calls, about
$17. The information was affordable; it was simply never collected.

## What this does not say

- **It does not say the extractor is bad.** Two of three cases reproduce at 0.85
  and 0.95. The model is largely consistent; one hard case is not.
- **It does not say the V17 or V18 rules are wrong.** It says the experiment
  could not tell. The rules remain untested, not disproven.
- **It does not generalise beyond this panel and model.** Variance was measured
  for `gpt-5.6-luna` at high reasoning effort on three cases.

## Corroboration

This is the second replicate study run in this repository and the second to fail.
[PR6, 2026-07-13](semantic-model-comparisons/2026-07-13-pr6-gpt-5.6-luna-v3/semantic_model_comparison_report.md)
measured the same model family on a different task and returned
`Selected-model repeatability proof: FAIL`, with 7 unstable records and minimum
case recall swinging 0.3333 → 1.0000 across identical inputs. The instability is
a property of the setup, not of this panel.

## Consequences

1. **The V6 → V18 retirement is now empirical.** It was argued from n=1 and a
   floating model alias; it is now measured. V18 must not be run as a scientific
   experiment: its result would be uninterpretable.
2. **No sealed result in the series may be cited as evidence about a prompt.**
   The sealed artifacts remain valid records of what happened on one draw. They
   are not evidence about prompt quality and must not be reinterpreted as such.
3. **Replication is a precondition, not a Phase 4 nicety.** The direction
   document places the noise floor in Phase 4. This experiment shows it belongs
   before any comparative claim, because without it a comparison is undefined.
4. **Operational note.** One call in sixty returned a provider error (1.7%).
   Any future harness needs typed error handling separate from scientific
   failure, or errors will be silently scored as failures.

## Method

The harness (`run_noise_floor.py`, run from a worktree at the sealed V17 commit)
reproduces the V17 provider input through the frozen prompt module, verifies its
SHA-256 against the digest recorded in each sealed case evaluation, and refuses
to issue any call on mismatch. All three matched. Each call goes through the
unmodified V17 provider and exactly-once custody path; each response is scored by
the unmodified `evaluate_v17_case`. No prompt, evaluator, fixture, or sealed
artifact was changed, and all output was written outside the repository.
