# Luna V2 Offline Participant Adjudication

**Terminal decision:** `PIVOT_TO_SPECIALIST_CANDIDATES`

Both Luna context experiments remain terminally `INVALID_EXPERIMENT`. This report
uses the rejected V2 participant payload only as a non-creditable diagnostic. It does
not reinterpret the V2 experiment, award qualification credit, write to the graph, or
enable promotion.

## Retrieval custody

- Existing response: `resp_0909915ba5830325006a60620dbff88198adf8625d389c717e`
- Retrieval mode: existing-response retrieval; provider generation calls: `0`
- Model metadata: `gpt-5.6-luna`
- Response status: `completed`
- Canonical participant payload SHA-256: `df430cd9d3db4d87a9d7172ffb7d1c98d007011146bd60faf3cf8237b0dc8e1f`
- Retrieved envelope SHA-256: `1bfc93bf55e6a3ee18911537be529bda40aacc28979aacb72fc1a58a5a803b5b`
- Reasoning content was not copied into the adjudication artifacts.

## Deterministic participant result

- Inventories: `20`
- Proposed participants: `25`
- Exact public-gold participants: `7`
- Public-gold participant denominator: `15`
- Exact participant-span precision: `7/25 = 28.00%`
- Exact participant-span recall: `7/15 = 46.67%`
- Source text/offset failures: `2`; both remain non-creditable
- V2 wrong to Luna correct event transitions: `0`
- V2 correct to Luna wrong event transitions: `0`
- Correct controls preserved: `4/4`
- Required participant-bearing events complete: `3/13`
- Required participant-bearing events incomplete: `10/13`

## Blinded review

Two independent internal Codex subagents reviewed all 25 participants without external
provider calls or access to each other's answers. They agreed exactly on `14/25` and
disagreed on `11/25`. A third blinded subagent reviewed only those 11 cases. All 11
were resolved, leaving `0%` unresolved disagreement, below the 20% invalid-diagnostic
threshold.

Consensus labels include:

- `7` exact-gold participants
- `5` source-supported equivalents outside exact gold fidelity
- `12` wrong-participant findings
- `3` wrong-entity-type findings
- `2` unsupported extras

Reviewers used `OFFSET_MISMATCH` three times, including one gold-boundary mismatch on a
source-valid broader phrase. The deterministic source-custody metric remains the
authoritative count for exact source text/offset validity: two failures.

Reusing `occurrence-0` for different participant texts was not treated as a biomedical
error. Stable mention identity should eventually derive from source hash and exact
offsets, but that implementation was conditional on passing this scientific gate and
was therefore not made here.

## Gate decision

The micro-canary required at least two V2 participant errors to become correct, zero
control regressions, zero unsupported additions, and no lost primary participants.
Luna preserved the controls but repaired zero event participant sets, introduced two
unsupported extras, and left ten required participant-bearing events incomplete.

The offline gate therefore fails. No occurrence-identity production change, full
service-check run, preregistration, or provider micro-canary was authorized. The next
scientific direction is a specialized biomedical event extractor used only for recall
and structural candidate generation, while Luna retains final source-only categorical
adjudication.
