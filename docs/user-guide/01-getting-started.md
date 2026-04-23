# Getting Started

This page gets you from a local service to your first authenticated API call.

## 1. Start The Services

From the repo root:

```bash
make install-dev
make run-all
```

`make run-all` starts:

- graph service: `http://localhost:8090`
- evidence API: `http://localhost:8091`

Most user-facing examples talk to the evidence API on port `8091`.

Set the base URL:

```bash
export ARTANA_API_BASE_URL="http://localhost:8091"
```

## 2. Get An API Key

Normal requests use either a bearer token or an Artana API key. For local
developer use, an API key is usually easiest.

If this is the first user on a fresh self-hosted deployment, create an admin
user with the bootstrap key configured for the service:

```bash
export ARTANA_EVIDENCE_API_BOOTSTRAP_KEY="artana-evidence-api-bootstrap-key-for-development-2026-03"
```

Then create the first user and API key:

```bash
eval "$(
  venv/bin/python scripts/issue_artana_evidence_api_key.py \
    --base-url "$ARTANA_API_BASE_URL" \
    --bootstrap-key "$ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" \
    --email admin@example.com \
    --username admin \
    --full-name "Admin Example" \
    --role admin
)"
```

That helper prints shell exports for values such as:

- `ARTANA_API_BASE_URL`
- `ARTANA_API_KEY`
- `ARTANA_KEY_ID`
- `ARTANA_USER_EMAIL`
- sometimes `ARTANA_DEFAULT_SPACE_ID`

If you already have a key, just set:

```bash
export ARTANA_API_KEY="art_sk_your_key"
```

Admins can create additional tester accounts without adding an external
identity service:

```bash
curl -s -X POST "$ARTANA_API_BASE_URL/v1/auth/testers" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "researcher@example.com",
    "username": "researcher",
    "full_name": "Researcher Example",
    "role": "researcher",
    "api_key_name": "Researcher test key",
    "create_default_space": true
  }'
```

The response includes the tester's API key once. Save it for that tester.

## 3. Verify Your Identity

Check that the API key works:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/auth/me" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

If this returns your user identity, you are ready.

## 4. Create Or Get A Default Space

A space is your research workspace. Create or retrieve your default space:

```bash
curl -s -X PUT "$ARTANA_API_BASE_URL/v1/spaces/default" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Save the returned space id:

```bash
export SPACE_ID="your-space-id"
```

## 5. Your First Health Check

You can also verify the service is alive:

```bash
curl -s "$ARTANA_API_BASE_URL/health"
```

## What To Read Next

Next, read [Core Concepts](./02-core-concepts.md). It explains the words you
will see in the API: space, document, run, proposal, review queue, graph, and
artifact.
