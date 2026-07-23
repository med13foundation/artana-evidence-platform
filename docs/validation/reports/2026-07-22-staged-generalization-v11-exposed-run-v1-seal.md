# Staged Generalization V11 Exposed Gate Seal

## 1. Root-cause finding

The V10 failure is classified as
`SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP`. V10 returned complete exact evidence
for its event and participants but returned semantic-axis fragments. In the full
source, `steroid dose before ICI initiation` occurs twice and `OS` occurs six
times; `OS` also occurs twice in the evaluator's local context. The frozen
unique-span evaluator therefore rejected the ambiguous semantic evidence
correctly. The named biomedical occurrence rule was not involved.

## 2. V11 change

The only scientific change was
`UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING`. The V9/V10 schema, exposed panel,
references, evaluator, grader, occurrence boundary, receipt policy, and custody
machinery remained frozen.

## 3. Execution frontier

The first comparison-canary response was acknowledged but remained incomplete
through the 900-second polling budget. V11 sealed at
`BACKGROUND_POLLING_TIMEOUT` before any output was admitted. No scientific case
result exists, and the first scientific failure frontier was not reached.

## 4. Evaluator and grader

The evaluator and frozen grader were not invoked on a scientifically admitted
provider output. There is no V11 score, no SLC12A3 boundary result, no negated
grounding result, and no basis for a pass or scientific fail classification.

## 5. Provider custody and retry evidence

- Provider creation calls: `1`.
- Acknowledged response IDs: `1`.
- Automatic provider retries: `0`.
- Duplicate creation calls: `0`.
- Polling retrieval requests before seal: `170`.
- Polling duration: `900.0100377080016` seconds.
- Cases attempted after the canary: `0`.

A single read-only late retrieval found the same response still `queued`, with
no usage object, provider error, or incomplete details. It did not create or
retry a response and did not alter the sealed invalid result.

## 6. Token and cost accounting

The provider supplied no completed usage telemetry. The sealed ledger therefore
records `0` input, cached-input, output, reasoning, and total tokens and `$0.00`
observed cost. This is observed telemetry at seal, not a claim about eventual
billing for a response that remained queued. The recorded operational budget
remaining at seal is `$5.00`; no further provider call was made.

## 7. Exposed-case accounting

The comparison canary has one acknowledged but unadmitted attempt. The SLC12A3
target, negated grounding regression, null-statistics case, drug-sensitivity
case, and explicit nested-cause case were not called.

## 8. Fresh-case accounting

Fresh cases consumed: `0`. The seven untouched fresh cases remain preserved.
The optional consumed-case diagnostic was not run.

## 9. Graph and promotion state

Graph writes: `0`. Trusted-graph promotion: `false`. Qualification credit:
`false`.

## 10. Sealed historical state

V1, V2, V3, V9, and V10 remain byte-identical. V10 remains sealed as
`V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED`; V11 did not reinterpret or
rescore it.

## 11. Terminal decision

`INVALID_V11_EXECUTION`
