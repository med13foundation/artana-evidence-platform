# Artana Resource Library – Security Assessment & Remediation Plan

_Generated: 2025-01-09_
_Updated: 2025-11-18_

This document captures the historical security posture of the Artana Resource Library, highlights priority issues, and prescribes a remediation plan. The assessment spans backend (FastAPI), frontend (Next.js), infrastructure, and delivery pipelines.

## Executive Summary

The platform demonstrates solid foundations (strict typing, layered architecture, basic rate limiting, automated QA). However, multiple critical gaps allow unauthenticated access, default credential reuse, and unrestricted data exposure. Immediate action is required to enforce authentication on legacy modules, eliminate hard-coded secrets, and tighten least-privilege controls.

## High-Risk Findings

| # | Finding | Impact |
|---|---------|--------|
| 1 | **[Resolved] Curation API unauthenticated** – `/curation` routes are enforced by JWT middleware, permission-checked, and regression-tested so API keys alone can no longer mutate queue state. | Critical integrity risk |
| 2 | **[Resolved] Data Discovery endpoints impersonate a system user** – repository-level owner filters and per-request access checks ensure sessions can only be read or mutated by their owners (admins must opt-in). | High confidentiality/integrity risk |
| 3 | **[Resolved] Admin seeding now requires explicit passwords** – operators must pass `ADMIN_PASSWORD`/`ARTANA_ADMIN_PASSWORD` and minimum length is enforced at runtime. | — |
| 4 | **[Resolved] API keys now require explicit secrets**; local-only bypass available via `ARTANA_ALLOW_MISSING_API_KEYS=1`. | — |
| 5 | **[Resolved] `/users` list/stat endpoints require `user:read` / `audit:read` permissions**, preventing unprivileged enumeration. | — |
| 6 | **[Resolved] `/auth/debug` removed** to prevent unauthenticated data reflection. | — |
| 7 | **Token storage hardened** – sessions now store SHA-256 token digests and refresh tokens never leave the server; residual risk limited to short-lived access tokens required for client API calls. | Medium |
| 8 | **[Resolved] Frontend now emits CSP + HSTS headers**, shrinking XSS impact surface. | — |
| 9 | **[Resolved] CI runs Next.js lint/type-check/test/audit tasks** before deploy. | — |
|10 | **[Resolved] Production boot disallows default DB creds and FastAPI container runs as non-root.** | — |
|11 | **Audit logging now records every high-risk curation and discovery event.** | Low |
|12 | **[New] Storage credentials handling** – Storage provider plugins must resolve credentials from Secret Manager rather than storing them in the database configuration blob. | High (Credential Leakage) |
|13 | **[New] Preset sharing access control** – Shared presets must verify that the viewing user is a member of the target research space. Currently, scope validation is primarily at the presentation layer. | Medium (Unauthorized Access) |

## Remediation Plan

### Phase 0 – Immediate Containment (same sprint)

1. **(Completed) Lock down Curation routes**
   - `/curation` endpoints remain inside the JWT middleware chain; API keys alone no longer satisfy authentication and regression tests assert 401 responses when JWTs are absent.
   - Each handler demands `get_current_active_user` + permission checks and emits append-only audit logs for queue mutations.

2. **(Completed) Enforce real user context in Data Discovery**
   - Repository filters (`find_owned_session`) and route-level helpers ensure sessions are only returned when `owner_id` matches (admins must explicitly override).
   - All mutating endpoints log actions and require authenticated users; unauthorized access now returns 403 without leaking metadata.

3. **Disable default credentials/secrets (Completed)**
   - Application startup now requires explicit API keys; seeding/resetting admins requires supplied passwords.
   - Rotate existing secrets in Secret Manager and invalidate prior keys.

4. **(Completed) Restrict `/users` and `/auth/debug`**
   - User listing and statistics endpoints now enforce `user:read`/`audit:read` permissions with explicit 403 responses when missing.
   - The legacy `/auth/debug` route is fully removed from the middleware bypass list, so internal tools must authenticate via JWT.

### Phase 1 – Token & Client Hardening (next sprint)

5. **Secure session storage (Completed)**
   - Access and refresh tokens are hashed with SHA-256 prior to persistence; repositories only compare digests.

6. **Reduce browser token exposure (Completed)**
   - Refresh tokens never leave the server; the browser retains only short-lived access tokens.
   - CSP + HSTS headers shipped via `next.config.js`.

7. **Strengthen CI/CD (Completed)**
   - `.github/workflows/deploy.yml` now runs `npm ci`, linting, type-checking, unit tests, and `npm audit` for the web app before deployment.

### Phase 2 – Infrastructure & Observability (following sprint)

8. **Centralize rate limiting & audit logs (Completed)**
   - High-risk curation and data-discovery routes now record append-only events in `audit_logs`, satisfying the audit traceability requirement.
   - **[Update]** Storage operations (CRUD, test, store) and advanced discovery workflows (search, PDF download) now emit structured audit logs.

9. **Harden containers & databases (Completed for current scope)**
   - FastAPI container runs as non-root, is pinned to `python:3.12.8-slim`, and CI executes Trivy scans on every image build.
   - Database URL resolver now forces `sslmode=require` whenever `ARTANA_ENV` is `staging`/`production`, unless `ARTANA_ALLOW_INSECURE_DEFAULTS=1` is explicitly set for local debugging.

10. **Security regression tests (Completed)**
    - Added regression tests (`tests/routes/test_security_regressions.py`) for unauthenticated curation calls and cross-user data discovery access.
    - Schemathesis smoke tests (`tests/security/test_schemathesis_contracts.py`) now run with Hypothesis to fuzz the OpenAPI contract and ensure protected endpoints never emit unexpected 5xx responses. Future work can layer OWASP ZAP for full DAST coverage if required.

### Phase 3 – Storage & Data Sovereignty (New)

11. **Storage Credential Isolation**
    - **Risk**: Storing API keys/service account JSONs in the `StorageConfiguration` JSON blob in the database exposes them to anyone with DB read access or `admin:storage:read` permissions.
    - **Mitigation**:
        - Storage plugins must accept references to Secret Manager secrets (e.g., `credentials_secret_name`) instead of raw values.
        - The `StorageConfigurationValidator` should reject configs containing apparent secrets (regex checks).
        - Infrastructure layer must implement a `SecretProvider` interface to fetch actual credentials at runtime.

12. **Preset Sharing Authorization**
    - **Risk**: Presets shared to a space (`scope="space"`) might be accessible to non-members if the API only checks `scope` and not membership.
    - **Mitigation**:
        - `DiscoveryConfigurationService.list_pubmed_presets` must join against `user_research_spaces` when filtering by `research_space_id`.
        - Integration tests must verify that a user cannot list presets for a space they do not belong to.

## Ownership & Tracking

| Workstream | Owner | Target |
|------------|-------|--------|
| Access control fixes (Phase 0) | Backend team (FastAPI) | ≤ 5 business days |
| Credential/secret rotations | DevOps + Security | In parallel with Phase 0 |
| Token hardening & CSP/HSTS | Web team (Next.js) | Following sprint |
| CI expansion | DevOps | Following sprint |
| Rate limiting/audit centralization | Platform team | Phase 2 |
| Storage & Preset Security | Backend team | Phase 3 |

Security should review each fix before release and ensure `make all` plus `make security-audit` remain green. Document residual risks after each phase in this file.
