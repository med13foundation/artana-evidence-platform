# Semantic Selector Repeatability And Model Comparison

- Evaluated commit: `71460f596b7efa19cf74a5e1d76710a7a75a3ab8`
- Protocol SHA-256: `12835761c37cb4514f84c6abd813ca47bdca09a39c754ed9516f30393fe82cf4`
- Source lock SHA-256: `c1c6a65c05570c44e6a4cd8a3abf27b36e7d28223e29c4a2f6036596635282f6`
- Decision: **INCONCLUSIVE**
- Selected model: `none`
- Selected-model repeatability proof: **FAIL**
- Calibration: **UNAVAILABLE** (no independent held-out expert corpus)
- Evidence provenance: **AI-adjudicated diagnostic**
- Production readiness claim: **NO**

## Repeated Quality

| Metric | Current | Candidate |
| --- | ---: | ---: |
| Runs | 3 | 3 |
| Quality gate | FAIL | FAIL |
| Worst precision | 1.0000 | 1.0000 |
| Worst recall | 0.7692 | 1.0000 |
| Minimum case precision | 1.0000 | 1.0000 |
| Minimum case recall | 0.3333 | 1.0000 |
| Worst decision coverage | 0.8667 | 1.0000 |
| Minimum case coverage | 0.6250 | 0.3333 |
| Mean abstention rate | 0.1111 | 0.0000 |
| Mean precision | 1.0000 | 1.0000 |
| Mean recall | 0.8205 | 1.0000 |
| Precision variance | 0.000000 | 0.000000 |
| Recall variance | 0.001315 | 0.000000 |
| Unstable records | 7 | 2 |
| Invalid-agent decisions | 0 | 0 |
| Deterministic fallback | 0 | 0 |

## Runtime Observations

| Metric | Current | Candidate |
| --- | ---: | ---: |
| Telemetry complete | no | yes |
| Total tokens | unavailable | 82583 |
| Total cost USD | unavailable | 0.19287720 |
| Model latency seconds | 175.697000 | 167.668000 |
| Wall latency seconds | 178.505661 | 170.256892 |

## Decision Evidence

- Reason code: `current_and_candidate_quality_gates_failed`
- Neither model passed the repeated source-locked quality gate.
- Worst precision delta: `0.0000`
- Worst recall delta: `0.2308`
- Combined variance delta: `-0.001315`
- Cost ratio: `unavailable`
- Model latency ratio: `0.9543`
- Cross-model categorical disagreements: `5`

This report compares categorical decisions over identical frozen source records. All quality and adoption numbers are deterministic computed metrics or runtime observations; neither model supplies a score used for adoption. This diagnostic cannot substitute for the independent expert pilot or trusted-relation proof.
