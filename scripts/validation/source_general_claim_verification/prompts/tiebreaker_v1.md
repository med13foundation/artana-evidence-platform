# Blinded Tiebreak Adjudication V1

Use only the exposed source text, disputed scope ID, and names of disputed
fields. Do not inspect either primary adjudicator's answer, generator output,
prior candidates, or reports.

Return the complete Source-Only Reference Adjudication V1 packet for disputed
scopes only. The field names identify what requires resolution but do not reveal
either prior answer. All V1 categorical, exact-span, statistical-separation,
and no-numeric-score rules apply unchanged.

`complete_event` must be a short source-grounded string describing the event.
