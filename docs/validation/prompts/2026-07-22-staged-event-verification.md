# Stage 5: Blinded Source Verification And Completeness

Use only the supplied source and assembled event claims. You have not seen the
generator explanations. For every event ID, return ENTAILED, CONTRADICTED,
INSUFFICIENT, or ABSTAIN, with a short explanation and a concrete falsification
explanation. ENTAILED requires one exact source passage containing the trigger
and every direct participant.

Independently inspect the source for complete supported events missing from the
assembled claims. For each missing event, return exact trigger text, exact event
passage, categorical source event type and statement kind, exact evidence, and
a falsification explanation. Do not repeat an existing event. Do not infer from
outside knowledge or benchmark expectations.
