# Stage 4: Event Modifiers

Use only each supplied event-local passage. For every event ID, return exactly
one categorical decision: NEGATED, SPECULATIVE, BOTH, NEITHER, or ABSTAIN.

NEGATED, SPECULATIVE, and BOTH require exact event-local evidence and a short
explanation. NEITHER requires no evidence text. ABSTAIN requires exact evidence
showing why the local wording is ambiguous. Do not infer modifiers from a
numeric value, general uncertainty, study design, or outside knowledge.
