# Staged Generalization V1

## Decision

`PIVOT_WITH_EVIDENCE`

V1 made one Luna-high call on the exposed comparison canary and stopped before
the other five cases. The receipt, schema, usage, and budgets were valid. There
were no retries, fallbacks, graph writes, promotions, or untouched sources.

## Provider Evidence

- Response: `resp_093166904a81bd17006a6125cf0690819abcdd006840c68078`
- Input tokens: 1,596
- Output tokens: 3,089
- Total tokens: 4,685
- Latency: 54.941 seconds
- Cost: $0.020130
- Every frozen receipt budget: `PASS`

## Scientific Output

Luna returned the intended comparison event, both populations, the comorbidity
outcome, the three correct source roles, `GREATER`, `INCREASED`, `AFFIRMED`,
`ASSERTED`, and no invented statistical interpretation. It explicitly excluded
the adjacent claims from the highlighted finding.

## Why V1 Rejected It

The deterministic evaluator exposed two source-general contract defects:

1. The reference accepted `more comorbidities than`, while Luna returned the
   source-valid containing trigger `had more comorbidities than`. Exact lexical
   equality rejected the broader span.
2. The prompt asked for containing evidence, but the schema did not make the
   full-sentence requirement explicit enough. Luna returned `Patients with RA`
   as both mention and evidence. That phrase occurs more than once in the local
   context, so deterministic grounding correctly failed as ambiguous.

The downstream missing-event and semantic failures were cascading consequences
of those two validation failures. V1 remains immutable and is not rescored.

## Next Bounded Cycle

V2 may change only these source-general boundaries:

- accept a trigger span when it equals or contains a frozen literal trigger;
- require every event and participant evidence field to be a complete exact
  containing source sentence, while the child text remains exact.

V2 must be separately preregistered and may rerun the canary only as a new
scientific-improvement cycle. V1 receives no qualification credit.
