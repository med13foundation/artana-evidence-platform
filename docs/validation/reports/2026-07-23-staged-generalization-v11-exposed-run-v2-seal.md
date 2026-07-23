# Staged Generalization V11 Exposed Run 2 Seal

## 1. Execution validity

Run 2 was a valid scientific execution of the preregistered V11 contract over
direct OpenAI foreground Responses. It was not an operational-invalid terminal.

## 2. Scientific frontier

Five exposed cases were called in frozen order. The comparison canary,
uncertainty, negated-association, and null-statistics cases passed. The
drug-sensitivity case failed, and execution stopped before the explicit
nested-cause case.

## 3. Targeted V11 repairs

- Exact `SLC12A3` occurrence: passed.
- Complete, exact, unique semantic evidence: passed for every admitted case.
- Negated complete supporting sentence: passed.
- V10 exact-evidence grounding on the negated case: improved.

## 4. First failure

The drug-sensitivity output missed the required `sensitivity` core event and
required core participants, added unsupported claims, and increased the V9
`unsupported_claim_count`. The frozen grader and acceptance policy therefore
classified the failure as `UNRELATED_SCIENTIFIC_REGRESSION`.

## 5. Provider custody

- Transport qualification calls: `3` (`2` rejected diagnostic calls and `1`
  qualified call).
- Scientific provider calls: `5`.
- Total provider creation calls: `8`.
- Provider retries: `0`.
- Duplicate creation calls: `0`.
- Response IDs: `8`, all unique and recorded.

## 6. Usage and budget

- Input tokens: `18471`.
- Cached input tokens: `2710`.
- Output tokens: `12609`.
- Reasoning tokens: `8524`.
- Total tokens: `31080`.
- Cumulative latency: `111.61969845898025` seconds.
- Cumulative provider cost: `$0.09168600000000002`.
- Remaining operational budget: `$4.908314`.

Token volume, latency, and cost were record-only telemetry and did not alter
scientific scoring.

## 7. Fresh cases

Fresh cases consumed: `0`. Seven fresh cases remain untouched. No next-fresh
preregistration was produced because the exposed panel did not pass.

## 8. Graph state

Graph writes: `0`. Trusted promotion: `false`.

## 9. Frozen inputs

The V11 prompt, schema, evaluator, grader, exposed panel, references, case
order, and acceptance rules remained unchanged. The shared historical receipt
validator was not modified.

## 10. Artifact hashes

- Preregistration SHA-256:
  `6157de1e1cb59042a6f532caa3b5f91e248ab8d7e09919fd0a2d98ec2e8b3a6a`.
- Result SHA-256:
  `5b7e3d2e3827d640878de4d156bb509229bd0c3f35cf10358f1d886ed15950d1`.
- Final report SHA-256:
  `6907eebeb84cad8c34615b92c2012909de6af3a845c1e0b51119311d48f20117`.
- Aggregate SHA-256 over the sorted SHA-256 manifest of the 28 run-2
  preregistration, receipt, raw-output, evaluation, result, and final-report
  artifacts:
  `0e4e8607be0b13bd7ef891e09fe5022afc6106d7606ffdd8a7e016cf526f145f`.

## 11. Interpretation

The complete six-case acceptance contract did not pass. The targeted SLC12A3
and semantic-grounding corrections did pass. The separate interpretation
addendum records this distinction without changing the sealed result.

## 12. Terminal decision

`V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION`
