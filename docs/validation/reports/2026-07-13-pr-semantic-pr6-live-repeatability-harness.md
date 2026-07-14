# PR6 Semantic Selector Repeatability Harness

Date: 2026-07-13

Branch: `alvaro/evidence-semantic-pr6-live-repeatability`

Base commit: `d23b1dea194d7fc6f116de84738fdf720c536a71` from merged PR `#148`

## Goal

Measure whether semantic evidence selection is repeatable and whether a newer
candidate judge model creates enough real categorical improvement to justify its
cost and latency. The comparison must use identical frozen source records and
must not consume model-authored confidence or other numeric self-scores.

## Root Cause Addressed

The repository already had a relation-extraction model comparison and one live
semantic-selector evaluation, but no selector-specific repeated-run gate. A
single successful diagnostic could therefore hide run variance, one weak case,
artifact replay, or an unjustified stronger-model choice.

## Implemented Boundaries

- Typed protocol, run, telemetry, summary, disagreement, and adoption contracts.
- Protocol and source-lock digests frozen before model calls.
- Three-run minimum for quality comparison; variance remains diagnostic and
  cannot independently cause adoption.
- Exact fixture, baseline, commit, model, artifact, and execution identity
  binding.
- Reopening and hashing every run artifact before aggregation.
- Deterministic score recomputation from categorical record decisions and the
  frozen fixture.
- Assessment-to-prediction consistency checks.
- Worst-run and minimum per-case precision/recall floors.
- Worst-run and per-case coverage floors plus a hard zero-instability gate.
- Interleaved current/candidate execution to reduce time-order confounding.
- Ledger-derived token, cost, and model-latency observations plus independent
  wall-clock measurement, including failed validation retries.
- Exact terminal-event model binding and a digest over normalized ledger facts.
- Deterministic recomputation of token, cost, latency, and cost-provenance
  aggregates from the embedded terminal events.
- Deterministic adoption policy with fail-closed zero-denominator resource
  ratios and an absolute `10x` candidate cost/latency cap.
- Explicit unavailable calibration and `production_readiness_claim=false`.
- Required merged PR `#148` predecessor, trusted-mainline ancestry, and final
  repository/source-state verification.
- Staged all-or-nothing publication, exact bundled source copies, a complete
  file manifest, in-generation manifest digest, and deterministic bundle
  verifier. Publication uses one directory rename.
- Baseline predictions and every sanitized source snapshot are now frozen into
  the protocol source-lock digest, copied under repository-relative paths, and
  revalidated from bundled bytes before publication.
- Explicit failure receipts with no plausible partial evidence directory.
- Evidence API CI, lint, type-check, and Makefile wiring.

## Validation To Date

- Post-adversarial focused semantic, repeatability, telemetry, executor, CLI,
  source-provenance, and bundle-atomicity tests: `59 passed`.
- Postgres-backed runtime-ledger integration test: passed against an ephemeral
  migrated database.
- Focused Ruff checks: passed.
- Evidence API package mypy: passed over `551` source files.
- New comparison CLI mypy: passed.
- Full `make service-checks`: passed with `87.43%` coverage against the `86%`
  repository floor.

## Adversarial Findings Closed During Implementation

1. Numeric score envelopes could initially disagree with categorical run
   decisions. The gate now recomputes every score from the fixture and decisions.
2. Source-lock and run hashes could initially be self-asserted. The gate now
   recomputes the source lock, reopens every run artifact, verifies its digest,
   and checks all bound fields.
3. Good micro averages could initially hide one weak case. The adoption policy
   now enforces a minimum precision and recall floor for every primary case.
4. Incomplete resource telemetry could initially leave model adoption
   ambiguous. The decision is now explicitly inconclusive without complete
   token, cost, and latency observations.
5. Abstaining on difficult negatives could initially game precision and recall.
   Coverage floors now apply globally and per case.
6. Equal aggregate metrics could hide different decisions across runs. Any
   record-level instability now fails the quality gate.
7. A supplied in-memory fixture could diverge from the hashed source file. The
   executor now loads only verified protocol paths, rehashes them throughout the
   run, and embeds exact source copies.
8. A zero-cost or zero-latency current model could make resource ratios
   undefined and bypass safeguards. Positive-over-zero ratios now fail closed.
9. Validation retries could disappear from execution identity and cost. The
   runner now exposes every attempted Artana run ID and telemetry covers all of
   them.
10. Incremental writes could leave a plausible partial result. Evidence now
    remains staged until the manifest and deterministic verifier pass.
11. The comparison CLI could silently resolve a requested candidate back to the
    default model. A comparison-specific trusted resolver now pins exact enabled
    judge models without weakening production override policy.
12. Aggregate telemetry could be forged independently of its event snapshot.
    Every aggregate and its cost provenance are now recomputed from terminal
    events, and the telemetry model must equal the run model.
13. Absolute paths and symlinks could escape a published bundle. Bundle-context
    artifact references must now be relative and resolve beneath the bundle.
14. A material quality gain could justify an arbitrarily expensive model. The
    frozen policy now applies an absolute resource-ratio cap in both ordinary and
    only-passing-candidate paths.
15. The old publication sequence exposed the directory before its digest anchor.
    The anchor now lives inside the staged generation and one rename publishes
    the complete generation.
16. A clean but stale mainline could satisfy the generic ancestry check. The
    protocol now records and verifies merged PR `#148` commit `d23b1dea` as a
    required predecessor.
17. The first live bundle omitted baseline predictions and sanitized source
    snapshots. Protocol v3 now freezes all five repository source files, copies
    them into the bundle, and replays fixture-to-snapshot provenance validation.
18. A baseline report could carry a score inconsistent with its categorical
    predictions. The source verifier now recomputes the baseline score and
    rejects any mismatch.
19. Execution copied source inputs into staging but initially loaded the
    in-memory objects from their original paths. It now loads only staged bytes;
    a regression corrupts the originals after copying and proves they cannot
    influence the run.
20. Independent evidence review found one defective BRCA1 gold label and two
    canaries whose bounded input omits required population evidence. These are
    recorded as benchmark defects and cannot count for model adoption.

## Final Source-Complete Live Diagnostic

The branch was rebased onto merged PR `#148` and evaluated at commit
`71460f596b7efa19cf74a5e1d76710a7a75a3ab8`. The live matrix ran three
interleaved executions of current judge `openai:gpt-5.4-mini` and candidate
`openai:gpt-5.6-luna` over the same source-locked fixture.

Verified v3 bundle:
`docs/validation/reports/semantic-model-comparisons/2026-07-13-pr6-gpt-5.6-luna-v3/`

The bundle has 23 content-addressed entries, including the baseline prediction
artifact and all four sanitized source snapshots. Both the generic manifest
verifier and semantic recomputation verifier pass from the committed copy.

The deterministic decision is **INCONCLUSIVE**. No model is selected, the
selected-model repeatability proof fails, and no production-readiness claim is
made. This is the intended fail-closed result because neither model passed the
repeated quality gate.

| Metric | `gpt-5.4-mini` | `gpt-5.6-luna` |
| --- | ---: | ---: |
| Worst precision | 1.0000 | 1.0000 |
| Worst recall | 0.7692 | 1.0000 |
| Minimum primary-case recall | 0.3333 | 1.0000 |
| Worst decision coverage | 0.8667 | 1.0000 |
| Unstable records | 7 | 2 |
| Invalid-agent decisions | 0 | 0 |
| Deterministic fallbacks | 0 | 0 |
| Canary runs passed | 3 of 3 | 1 of 3 |
| Telemetry complete | no | yes |
| Total model latency | 175.697 s | 167.668 s |
| Total observed cost | unavailable | $0.19287720 |

### Failure Attribution

1. The apparent Luna recall gain is not trustworthy. Gold record
   `brca1:pmid:30191368` calls the structural variant pathogenic, while the
   underlying abstract classifies its significance as uncertain and potentially
   benign or reduced-penetrance. Luna selected it in all runs; the current
   model's one abstention creates the reported worst-recall delta.
2. `gpt-5.4-mini` had seven unstable records. Every run also required one retry
   after the live process logged a schema-invalid uncertain finding using a
   non-review decision. The bundle preserves the three failed terminal outcomes
   and their latency, but not failure cause, token use, or cost. Resource
   comparison is therefore undefined rather than estimated.
3. `gpt-5.6-luna` selected every canary in run 1, then abstained on
   `canary:pmid:27959700` and `canary:pmid:27393503` in runs 2 and 3. The bounded
   title and excerpt do not explicitly establish all required population and
   direct-clinical facts. This is benchmark/source-boundary ambiguity, not clean
   evidence that either the selection or abstention is correct.
4. Luna was stable on every primary record in this matrix and had complete
   telemetry, but its only two unstable records were the malformed canaries.
   It therefore still failed the frozen quality gate.
5. The models disagreed categorically on five records. The reported Luna
   worst-recall delta is `0.2308`, but the defective BRCA1 gold, ambiguous
   canaries, and current-model failed-attempt telemetry prevent treating that
   number as a valid model-quality or resource advantage. Luna's measured model
   latency was about 4.6% lower, but the cost ratio remains unavailable.

### Honest Conclusion

`openai:gpt-5.6-luna` was tested live and was not proven better. The result does
not justify changing the production judge. It does prove that the new harness
can preserve a negative result, expose model instability separately from
fixture ambiguity and runtime observability, and refuse model adoption without
complete deterministic evidence.

The source-complete v3 run proves the harness publication and verification
boundary. It does not repair the diagnostic gold. Independent expert
adjudication must correct the BRCA1 label and ambiguous canaries before a later
matrix can be treated as a valid head-to-head quality comparison.

The runtime must also retain usage and failure-cause data for failed local
output-validation attempts. None of these findings should be addressed by
prompt pressure or by weakening the deterministic gates.

Even a later passing matrix remains AI-adjudicated diagnostic evidence. It can
support a model configuration choice, but it cannot replace the independent
expert pilot or establish trusted-graph readiness.
