# PR-26 Graph Promotion Fail-Closed Enforcement

Date: 2026-07-06

Branch: `alvaro/evidence-pr26-graph-promotion-fail-closed`

Base branch: `alvaro/evidence-pr25-repeatability-model-ab`

Commit: pending

## Goal

PR-26 makes the Graph Service an independent trust boundary for trusted AI
evidence. A green audit or trusted-looking Evidence API payload is not enough:
Graph DB validation must reject unsafe trusted promotion attempts before they can
persist.

## What Changed

- Added a graph-owned review-lane trust floor in
  `services/artana_evidence_db/validation/trusted_evidence_floor.py`.
- Trusted AI evidence is now rejected when metadata contains:
  - `review_status == "review_only"`, or
  - any non-empty `review_reason_codes`.
- Graph endpoint linking now matches the verifier-owned floor: trusted evidence
  requires `status == "linked"`, a non-empty CURIE, and a verification marker
  such as `trusted_identifier == true` or `source == "verified_linker"`.
- Present but malformed non-empty `review_reason_codes` and
  `trust_floor_failures` metadata is treated as unsafe for trusted promotion.
- `/claims` now rejects trusted-floor validation failures even when
  `ai_provenance` is omitted, while preserving ordinary non-persistable review
  claims.
- Kept this rule inside the Graph Service instead of importing Evidence API
  review policy, preserving the service boundary.
- Added unit tests proving claimed trusted AI evidence is rejected for:
  fallback traces, incomplete agent extraction, review-only metadata, weak review
  reasons, unlinked subject/object endpoints, non-ENTAILED support, and failed
  trust floors.
- Added integration tests proving both `/validate/claim` plus `/claims` and
  direct `/relations` writes reject review-lane trusted AI evidence.

## Validation

RED unit test evidence before implementation:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  -q
```

Result: failed as expected. The review-only and weak/hedged reason-code cases
returned `None`, proving Graph validation accepted unsafe trusted-looking
metadata before this PR.

RED integration test evidence before implementation:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_rejects_trusted_ai_claim_with_review_lane_metadata \
  -q
```

Result: failed as expected. `/validate/claim` reported the malicious
trusted-looking review-lane payload as valid.

Focused GREEN validation:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py \
  -q
```

Result: passed, 71 tests. Only the existing Starlette/httpx deprecation warning
was emitted.

Changed-file lint:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m ruff check \
  services/artana_evidence_db/validation/trusted_evidence_floor.py \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py
```

Result: all checks passed.

Graph Service gate:

```bash
make graph-service-checks
```

Result after adversarial fixes: passed. Static checks, type checks, boundary
check, graph OpenAPI check, generated TypeScript contract check, release
contract, architecture checks, Alembic migration bootstrap, and the isolated
Postgres graph test suite all completed. The ephemeral test database was dropped
at cleanup.

Aggregate service gate:

```bash
make service-checks
```

Result after adversarial fixes: passed with 87.03% coverage against the 86%
floor. Static checks, type checks, boundary checks, contract checks,
architecture checks, isolated Postgres tests, and coverage gate completed. The
ephemeral test database was dropped at cleanup.

## Adversarial Review

Read-only adversarial review initially found three blockers:

- model-only CURIE hints could be relabeled as linked endpoints,
- malformed non-empty `review_reason_codes` or `trust_floor_failures` could hide
  weak/review-lane evidence,
- `/claims` could store unsafe trusted metadata as a non-persistable claim when
  `ai_provenance` was omitted.

All three blockers were fixed with additional RED/GREEN tests before the final
gate reruns.

## Interpretation

PR-26 does not make the system fully trusted-graph ready by itself. It closes
the Graph DB enforcement gap: review-only or weak-review AI evidence cannot be
promoted as trusted graph evidence simply because a caller labels it trusted.

Remaining trusted-graph readiness work still depends on repeated strict
live-agent evidence, PR-25 model/repeatability results, and final readiness gates
passing without fallback or safety failures.
