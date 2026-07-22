# Staged Generalization V6 Final

Date: 2026-07-22

Terminal decision: **PIVOT_WITH_EVIDENCE**

## Scope

V6 preserved the V5 panel, output schema, Luna-high model, independently frozen
dual-lane grader, budgets, and fail-fast custody. Its only scientific change was
the source-general prompt guidance for referential antecedent grounding and the
separation of grammatical assertion from uncertainty content.

The preregistration was committed and pushed at `f6a350af` before execution.
It contains no V5 output, failing case identifier, source-specific entity, gold
label, expected role, or benchmark projection in the agent inputs.

## Result

The comparison canary passed. The null-statistics case failed, and the runner
stopped before the remaining four cases exactly as preregistered.

- provider calls: 2;
- valid receipts: 2/2;
- duplicate creation calls: 0;
- retries: 0;
- passed cases: 1/2 executed;
- required-core completion: 2/2;
- unsupported claims: 4;
- contradictions: 0;
- total tokens: 20,883;
- latency: 325.975 seconds;
- cost: USD 0.104078;
- graph writes: 0;
- qualification credit and trusted promotion: `false`.

Result SHA-256:
`3c397d860c07e6f65a6e1ff7b11b6d1e43d0403fd9a9216c313627794e972867`.

## Scientific diagnosis

V6's referential rule did not reach the intended uncertainty case because the
broader instruction to preserve named context bearers changed behavior on the
earlier null-statistics case. Luna split `NSCLC` out of the already complete
`non-RA NSCLC` cohort span as an additional cancer participant and promoted
`Kaplan-Meier survival curves` from the analytic representation into a
measurement participant. The unchanged frozen grader independently classifies
the curves as forbidden and does not list the extra cancer node, yielding two
unsupported nodes and two unsupported links.

This is prompt overreach, not a receipt, schema, core-recovery, grounding, or
grader defect. The next correction must narrow antecedent repair to findings
that actually contain dependent referring grammar. It must also state that a
subspan already contained in a complete participant is not a separate context
participant, and that analytic methods or representations are not participants
unless they have an independent event role.

V6 is immutable and will not be patched, rescored, or retried.
