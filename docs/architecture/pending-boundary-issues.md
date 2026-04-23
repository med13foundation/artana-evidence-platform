# Pending Boundary Issues

Status date: April 23, 2026.

The repo is now an extracted two-service backend, but a few architecture issues
remain too large for a narrow patch.

## Evidence API Identity Ownership

Status: partially addressed.

The Evidence API now routes identity and tenancy through
`IdentityGateway`, which gives the codebase a real boundary. The current gateway
is still backed by local Evidence API SQL tables.

Current state:

- low-friction tester access uses `X-Artana-Key`;
- admin tester creation lives at `POST /v1/auth/testers`;
- owner/member checks use the gateway;
- direct identity ORM imports are blocked outside the allowlist by
  `scripts/validate_artana_evidence_api_service_boundary.py`.

Open decision:

- keep identity local while testing remains small, or
- replace `LocalIdentityGateway` with a future remote identity service when
  external-user onboarding, account recovery, audit, or SSO requirements grow.

## Runtime To Router Imports

Status: partially addressed.

The full AI orchestrator no longer imports the private
`research_init_runtime._build_source_results` helper. Shared source-result
construction lives in:

- `services/artana_evidence_api/research_init_source_results.py`

Remaining cleanup:

- move PubMed query/candidate/relevance helpers below router code;
- move PDF enrichment helpers below `routers/documents.py`;
- then add a validator rule that prevents production runtime imports from
  `artana_evidence_api.routers.*`.

## Large Runtime Modules

Status: open.

The largest modules still mix several responsibilities:

- `services/artana_evidence_api/research_init_runtime.py`
- `services/artana_evidence_api/full_ai_orchestrator_runtime.py`
- `services/artana_evidence_db/graph_workflow_service.py`

Target split:

- research-init: source discovery, replay, document preparation, extraction
  staging, state finalization;
- full AI orchestrator: planner, action executor, guarded policy, artifact
  writer;
- graph workflows: command-family modules once current service gates stay
  stable.

## Deployable Artifact Boundary

Status: guarded by checks, still worth watching.

The intended boundary is HTTP-first: the Evidence API should consume graph
contracts and graph HTTP endpoints, not graph internals. Keep this protected
with:

- `make artana-evidence-api-boundary-check`
- `make graph-service-boundary-check`
- `make graph-service-contract-check`
- `make artana-evidence-api-contract-check`
