# TG-04 Transport Identity Smoke

Date: 2026-07-18

## Decision

**TRANSPORT IDENTITY SMOKE PASSED.** Opaque source-unit and candidate identity
was removed from model-authored scientific output and bound by deterministic
orchestration instead. The exact #175 failure unit then completed one extractor
call and one independent verifier call with source binding, audit identity, and
provider lineage intact.

This was an adaptive replay of a previously observed unit. It is intentionally
non-qualifying and provides no scientific-accuracy score, benchmark credit,
literature-review authorization, or graph-persistence authorization.

## Contract Change

The provider-facing extraction output now contains only:

- categorical eligibility and event decisions;
- typed scientific event content;
- exact source spans;
- categorical reasoning.

The provider-facing verification output now contains only:

- categorical eligibility and coverage decisions;
- ordered categorical candidate decisions;
- exact evidence spans;
- reasoning and falsification conditions.

`unit_id`, source/input hashes, candidate IDs, and covered-candidate IDs are not
model fields or prompt payload. Pydantic rejects these fields if a model tries
to return them. Deterministic code binds every attempt to the frozen unit in the
audit context, checks each candidate's source hash, chunk index, and offsets,
and pairs verifier decisions to candidates by exact input order.

## Frozen Inputs

- Harness commit: `69335bcc`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-transport-identity-smoke-luna-01`
- Prior merged PR: `#175`
- Prior stop-report SHA-256:
  `fb77b85369c17adcd98c6d99a927ddcabe10b9e4ef9aa22c33299ea0f8a4a34a`
- Source unit:
  `source-unit-a1e6d72064289601fc6e82446a14036433e1b1bf32cd014de2c817bf7b4cfde9`
- Source-unit input SHA-256:
  `5461f6bf2aa1e22bd9d6e292ca3e6e21e896d898c4b194229aebe6ace6c3ad0a`
- Local expert events visible to the run: `0`
- Agent calls: extractor `1`, verifier `1`
- Biomedical fallback: `0`
- Live artifact:
  `/tmp/artana-tg04/transport-identity-smoke-2026-07-18/luna-r1.json`
- Live artifact SHA-256:
  `fe16724b1b07ae057d62113c56a886307d00174d5554fb0ae9d54003675dc95d`
- Embedded report SHA-256:
  `ecc6da85168ffdff3569a276f6d5a7882cf6d6abcf1f5bccf10550a4efc40e2a`

The output path was create-once and the smoke was not rerun. The embedded
report digest was independently recomputed and matched.

## Transport Result

Every deterministic transport requirement passed:

- agent execution complete: `true`;
- extracted source-bound candidates: `1`;
- ordered verifier decisions: `1`;
- entailed candidates: `1`;
- model-authored transport identity fields: `0`;
- audit identity mismatches: `0`;
- binding rejections: `0`;
- invalid agent outputs: `0`;
- distinct provider response IDs: `2`;
- verified live provider receipts: `2`;
- fallback count: `0`.

The extractor returned one `FINDING` with a `DECREASE` event. It preserved
`IL-4` as `CAUSE`, `iTreg-driving conditions` as `CONTEXT`, and the count of
FOXP3-positive cells as the affected outcome. The independent verifier returned
`CANDIDATES_COMPLETE` and `ENTAILED`, citing the trigger and all three material
arguments.

That semantic agreement demonstrates that the repaired transport path can carry
a candidate through both roles. Because the unit was replayed after its prior
output was observed, it cannot be used to estimate discovery quality.

## Receipt Limitation

Both receipts passed the repository's live verified-envelope policy: provider
status, invocation topology, prompt/input/source hashes, schema binding, and
response identity were verified. The provider retrieval representation still
did not byte-match the locally stored structured-output hash, and the provider
response schema remains marked unsupported. This known representation boundary
does not invalidate this transport smoke, but it remains a limitation to track
separately from scientific quality.

## Next Scientific Step

After this PR merges:

1. freeze a fresh hidden source unit that has not appeared in prior model output;
2. pre-register its source identity and deterministic stop/go gate;
3. run one extractor and one independent verifier with the repaired contract;
4. only if that fresh gate passes, perform independent source-and-literature
   validation;
5. continue to block benchmark credit and graph persistence until repeated
   fresh units establish scientific precision and valuable-claim recall.

The successful adaptive replay must not be counted as one of those fresh units.

## Validation

- `108` focused finite-unit, claim-event, and provider-receipt tests passed.
- Ruff passed on every changed file.
- Mypy passed for `612` Evidence API source files.
- The architecture structure ratchet passed.
- Commit hooks passed graph/evidence lint and type checks.
- `make service-checks` passed after restoring local PostgreSQL, including fresh
  migrations and the complete suite, at `87.47%` measured coverage.
- The external Claude review process returned no result and was stopped; it is
  not counted as approval.
