# Final Staged Comparison V2 Adjudication

**Terminal decision:** `PIVOT_TO_SPECIALIST`

## Experiment Integrity

The frozen exposed-source comparison executed without retries, fallbacks, graph writes, promotion, receipt mismatches, or token-budget violations. Five provider calls completed for discovery, participants, roles, modifiers, and verification. The optional completion call was not launched because deterministic assembly failed closed first.

- Provider calls: 5
- Total tokens: 382,546
- Total latency: 925.981 seconds
- Total cost: $9.592405
- Discovered candidates: 39
- Candidates reaching every semantic stage: 39
- Verifier verdicts: 32 `ENTAILED`, 7 `CONTRADICTED`

## Exact Failure

Event `E-2773996d557442a07d58` represented c-myc downregulation and was assigned `SPECULATIVE`. The source says:

> Moreover, the downregulation of c-myc oncogene by an antisense strategy might represent a useful goal for improving the efficacy of this anti-neoplastic drug family.

The verifier correctly found that `might` modifies whether the downregulation represents a useful goal. It does not make the downregulation event itself speculative. The modifier axis therefore returned `FAIL` and the event was `CONTRADICTED`.

Event `E-faf304d73050cfefee5c`, the proposed improvement in efficacy, used that rejected downregulation event as a nested `Cause`. Fail-closed assembly rejected the parent with `nested target did not pass all stages`.

## What Improved

The corrected verifier no longer accepted every generally plausible event. It rejected seven events through explicit axis failures, including unsupported nesting, merged or overlapping participants, incorrect roles, an unsupported release origin, and the misplaced speculation modifier. This is evidence that axis verification is stricter.

## What Is Not Proven

The experiment was structurally invalid before final event assembly and deterministic gold scoring. Therefore it cannot establish:

- improved exact-event, role, nesting, or modifier fidelity;
- a reduced verifier false-acceptance rate;
- benchmark superiority over V1;
- scientific qualification.

The 32 `ENTAILED` candidates have not received the complete post-run source-validity adjudication required by the preregistration. They must not be counted as correct or trusted.

## Decision

The preregistered advance gate was not reached. Do not retry or expand the LLM-only staged architecture. The next bounded experiment should use a specialized biomedical event extractor only as a recall candidate generator. Agents must retain final axis-by-axis scientific adjudication, and every output must remain review-only.

This result separates the causes clearly: the receipt and budget infrastructure worked; the remaining blocker is semantic scope and dependency consistency across agent-owned stages.
