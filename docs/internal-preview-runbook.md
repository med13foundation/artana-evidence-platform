# Internal Preview Runbook

This runbook is for a small, named group of research testers using the staging
Evidence API. It deliberately does not add a public signup page or self-service
key issuance.

## Preview Product Boundary

Offer the preview as an API-accessible, review-gated evidence workspace:

- create research spaces;
- ingest text or PDFs and search supported public scientific sources;
- inspect extracted candidates and provenance;
- review, accept, or reject proposed evidence-map updates;
- query the resulting evidence map and inspect task history.

This is a research workflow preview. Do not describe it as a clinically
validated decision system, do not use it for patient care, and do not submit
PHI or other sensitive patient data. Current scientific qualification and
benchmark work remains separate from this operational preview gate.

## Public Boundary

The Evidence API is the tester-facing ingress. For staging, these routes must
be reachable from outside Google Cloud:

- `GET /health`
- `GET /docs`
- `GET /openapi.json`
- authenticated `/v2/*` workflow routes

Workflow routes must reject missing or invalid credentials. The deployment
workflow runs `scripts/verify_internal_preview.py` after each staging deploy to
check public reachability, required auth/key-management contracts, and
fail-closed authentication.

The graph Cloud Run service is currently internet-invokable because the
Evidence API-to-graph transport uses an application JWT but does not yet attach
a Google service identity token. Graph data routes still require that JWT, and
the staging graph deployment verifies that anonymous graph-data access returns
`401`. Making Cloud Run itself private requires service-to-service IAM token
support first; changing the IAM flag alone would break Evidence API workflows.

## 1. Verify The Public Boundary

Set the staging addresses without putting any credential in shell history:

```bash
export ARTANA_PREVIEW_BASE_URL="https://artana-evidence-api-staging-zkumr6renq-uc.a.run.app"
export ARTANA_PREVIEW_GRAPH_BASE_URL="https://artana-evidence-db-staging-zkumr6renq-uc.a.run.app"
make internal-preview-public-check
```

This check is read-only. The expected result is eight passes, one skipped
tester-key check, and zero failures.

## 2. Create One Tester

Use one distinct user and key per person. Never share the admin key with a
tester. Read it silently into the environment:

```bash
read -r -s -p "Admin API key: " ARTANA_API_KEY
export ARTANA_API_KEY
echo
```

Create a low-privilege tester and default space:

```bash
venv/bin/python scripts/issue_artana_evidence_api_key.py \
  --base-url "$ARTANA_PREVIEW_BASE_URL" \
  --mode tester \
  --email "researcher@example.com" \
  --username "researcher" \
  --full-name "Researcher Example" \
  --role researcher \
  --api-key-name "Internal preview - Researcher Example" \
  --api-key-description "Named internal preview tester" \
  --output json
```

The response exposes the full tester key exactly once. Record the returned
`user_id` and `key_id` in the private tester roster. Put the full key directly
into an approved password manager or secret-sharing tool, then deliver it to
that tester. Do not put keys in repository files, tickets, email, or ordinary
chat messages.

For least privilege, use:

- `viewer` for read-only exploration;
- `researcher` for normal preview workflows;
- `curator` only when the tester must perform curation actions.

Tester creation never accepts `admin` or `owner`.

## 3. Verify The Tester Key

On the tester's machine, read the delivered key silently and run the
authenticated, non-mutating gate:

```bash
read -r -s -p "Tester API key: " ARTANA_PREVIEW_API_KEY
export ARTANA_PREVIEW_API_KEY
echo
make internal-preview-authenticated-check
```

This additionally verifies `GET /v2/auth/me` and `GET /v2/spaces` with the
tester key. It never prints the key.

## 4. Rotate Or Revoke Tester Access

Admins can manage a tester's keys without knowing the full secret. Use the
`user_id` and `key_id` from the private roster.

List key metadata:

```bash
curl -s "$ARTANA_PREVIEW_BASE_URL/v2/auth/testers/$TESTER_USER_ID/api-keys" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Rotate a compromised key and deliver the returned replacement once:

```bash
curl -s -X POST \
  "$ARTANA_PREVIEW_BASE_URL/v2/auth/testers/$TESTER_USER_ID/api-keys/$TESTER_KEY_ID/rotate" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Revoke access at the end of testing:

```bash
curl -s -X DELETE \
  "$ARTANA_PREVIEW_BASE_URL/v2/auth/testers/$TESTER_USER_ID/api-keys/$TESTER_KEY_ID" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

After rotation, update the roster with the replacement `key_id`. After
revocation, confirm the old key fails the authenticated preview check.

## 5. Operator Go/No-Go Checklist

Proceed with a named tester only when all of these are true:

- staging Evidence API and graph deployment jobs are green;
- `make internal-preview-public-check` has zero failures;
- a unique tester identity and key have been created;
- `make internal-preview-authenticated-check` has zero failures;
- the tester received the no-PHI and research-use-only boundary;
- the private roster has owner, user id, key id, issue date, and planned revoke date;
- the operator can rotate and revoke the key.

Stop onboarding if any required route is missing, anonymous data access does
not return `401`, a key cannot be centrally revoked, or the intended use
requires clinical reliability claims.

## Current Limitations

- API keys do not yet receive an automatic expiry date. Every preview key needs
  a planned manual revoke date in the operator roster.
- Rate limiting is process-local, so it is a guardrail rather than a billing or
  abuse-control system.
- The graph service is application-authenticated but not yet private at the
  Cloud Run IAM layer.
- This gate proves operational preview readiness, not scientific accuracy or
  clinical qualification.

These limits are acceptable only for a small, controlled internal preview.
They are blockers for public self-service access.
