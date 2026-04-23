# Local Identity Boundary

Status: implemented as v1.

The Evidence API owns a local identity boundary for the current testing phase.
The implementation is SQL-backed and in-process, but workflow code talks to an
`IdentityGateway` contract instead of writing user, API-key, space, or
membership tables directly.

This keeps current testers on a simple API-key flow while leaving a clean path
to a future remote identity service.

## Rule

All user, API-key, research-space, membership, and access decisions should pass
through:

- `services/artana_evidence_api/identity/contracts.py`
- `services/artana_evidence_api/identity/local_gateway.py`
- `services/artana_evidence_api/dependencies.py:get_identity_gateway`

Routers and workflow runtimes should not create users, issue API keys, or edit
space membership rows directly.

## Current API

The public tester flow is:

- `POST /v1/auth/bootstrap`: create the first self-hosted user and initial API
  key using `X-Artana-Bootstrap-Key`.
- `POST /v1/auth/testers`: admin-only tester creation with an initial API key.
- `GET /v1/auth/me`: resolve the current API key or bearer-token identity.
- `POST /v1/auth/api-keys`: create an additional API key for the current user.
- `GET /v1/auth/api-keys`: list API-key summaries.
- `DELETE /v1/auth/api-keys/{key_id}`: revoke one key.
- `POST /v1/auth/api-keys/{key_id}/rotate`: revoke and replace one key.

Normal requests can use `X-Artana-Key`. Bearer JWTs are also supported by the
auth layer.

## Current Tables

The gateway currently uses Evidence API tables:

- `users`
- `harness_api_keys`
- `research_spaces`
- `research_space_memberships`

Space creation explicitly ensures an owner through the gateway. SQL-backed
member addition requires the target user to exist first; admins should create
testers with `POST /v1/auth/testers` instead of relying on hidden placeholder
users.

## Future Extraction Path

If external testing grows beyond the local setup, add a `RemoteIdentityGateway`
that implements the same contract and talks to a separate identity service.

Evidence API workflow code should continue to depend on the gateway contract.
The graph service should stay identity-light: it should receive space-scoped
service calls and synchronized membership snapshots, not own end-user auth.
