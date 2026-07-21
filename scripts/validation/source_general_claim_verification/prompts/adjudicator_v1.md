# Source-Only Reference Adjudication V1

Use only the exposed source text and the specified scope. Do not inspect
generator output, generator reasoning, prior model candidates, reports, or
another adjudicator's answer.

Return categorical event type, typed participants, direction, comparison,
polarity, uncertainty, quantitative observations, statistical observation,
author statistical interpretation, required modifiers, completeness,
acceptable exact evidence spans, ambiguity conditions, exact evidence, and a
short explanation. Never return a numeric score or confidence.

`SIGNIFICANT` or `NOT_SIGNIFICANT` requires explicit author language. A numeric
p-value alone is an observation and does not establish either interpretation.
Mark bundled, fragmentary, or non-self-contained scopes `AMBIGUOUS`; do not
invent one complete event.

Every exact span must occur inside the supplied source scope. `complete_event`
must be a short source-grounded string describing the event.
