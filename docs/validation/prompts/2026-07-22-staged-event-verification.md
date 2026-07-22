# Stage 5: Blinded Source Verification And Completeness

Use only the supplied source and assembled event claims. You have not seen the
generator explanations. For every event ID, return ENTAILED, CONTRADICTED,
INSUFFICIENT, or ABSTAIN, with a short explanation and a concrete falsification
explanation. ENTAILED requires one exact source passage containing the trigger
and every direct participant.

Judge these axes independently as PASS, FAIL, or ABSTAIN: event type, trigger,
participants, roles, nesting, modifier, and evidence. Evaluate the complete
typed structure, not whether a loose paraphrase sounds plausible. ENTAILED is
allowed only when every axis is PASS. CONTRADICTED requires at least one FAIL.
INSUFFICIENT or ABSTAIN requires at least one ABSTAIN axis.

Independently inspect the source for complete supported events missing from the
assembled claims. For each missing event, return exact trigger text, exact event
passage, categorical source event type and statement kind, exact evidence, and
a falsification explanation. Do not repeat an existing event. Do not infer from
outside knowledge or benchmark expectations.
