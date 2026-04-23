# Local Identity Boundary

Status: implemented as v1.

The evidence API now treats identity and tenancy as an internal boundary, even
though the implementation is still local to the service process. This keeps the
testing flow low-friction while preserving a path to a future standalone
identity service.

## Rule

User, API-key, research-space, membership, and role decisions should go through
the identity gateway:

- `services/artana_evidence_api/identity/contracts.py`
- `services/artana_evidence_api/identity/local_gateway.py`
- `services/artana_evidence_api/dependencies.py:get_identity_gateway`

Workflow and router code should not create users, API keys, or memberships by
writing identity tables directly.

## Current Shape

The local gateway uses the existing tables:

- `users`
- `harness_api_keys`
- `research_spaces`
- `research_space_memberships`

The public API stays simple for testers:

- `POST /v1/auth/bootstrap` creates the first local user and key.
- `POST /v1/auth/testers` lets an admin create tester users and API keys.
- `X-Artana-Key` remains the low-friction API access path.

Space creation explicitly ensures the owner through the identity boundary.
SQL-backed member addition now requires the target user to exist first; callers
should create testers through the identity endpoint instead of relying on hidden
placeholder-user creation.

## Future Extraction Path

A future remote identity service should implement the same gateway contract:

- `LocalIdentityGateway`: current SQL-backed implementation.
- `RemoteIdentityGateway`: future HTTP/client implementation.

Evidence API workflow code should continue to depend on the gateway contract,
not on identity table layout. Graph service should remain user-agnostic and
receive only space-scoped service calls or snapshots.
