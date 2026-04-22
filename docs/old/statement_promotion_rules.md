# Statement Promotion Rules

Statements of Understanding capture evolving hypotheses. Promotion is the explicit step that turns a well-supported statement into a canonical Mechanism node.

## When promotion is allowed
A statement can be promoted only when **all** of the following are true:
- Status is `well_supported`.
- Evidence tier is **moderate** or stronger.
- At least one phenotype is linked.
- The user has curator (or higher) permissions in the research space.

## What promotion does
- Creates a **Draft** Mechanism in the same research space.
- Prefills Mechanism fields from the statement (title → name, summary → description, evidence tier, confidence, phenotypes, domains, source).
- Opens the Mechanism editor so a curator can review and finalize.

## What promotion does NOT do
- It does **not** auto-approve or publish mechanisms.
- It does **not** add new evidence or edges without human review.
- It does **not** bypass the Mechanism lifecycle (Draft → Reviewed → Canonical).

## UI placement
- Promotion is a contextual action on a Statement card.
- It is not a global navigation action.

These rules keep "thinking" (statements) separate from "memory" (mechanisms) while preserving a reviewable, auditable promotion path.
