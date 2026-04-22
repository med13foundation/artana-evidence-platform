# Migration 026 Deployment Notes

**Migration:** `026_p0_p2_schema_columns`
**Path:** `services/artana_evidence_db/alembic/versions/026_p0_p2_schema_columns.py`

## What it adds

| Table | Column | Type | Default |
|-------|--------|------|---------|
| `relation_claims` | `assertion_class` | VARCHAR(32) NOT NULL | `'SOURCE_BACKED'` |
| `relations` | `canonicalization_fingerprint` | VARCHAR(128) NOT NULL | `''` |
| `relations` | `support_confidence` | FLOAT NOT NULL | `0.0` |
| `relations` | `refute_confidence` | FLOAT NOT NULL | `0.0` |
| `relations` | `distinct_source_family_count` | INTEGER NOT NULL | `0` |
| `relation_constraints` | `profile` | VARCHAR(32) NOT NULL | `'ALLOWED'` |

## Backfill — already automatic

All new columns are declared `NOT NULL` with a `server_default`. PostgreSQL fills existing rows with the default value during the `ALTER TABLE ... ADD COLUMN` operation, so **no separate backfill script is required**.

The migration is also idempotent — it uses `_add_if_missing()` to skip columns that already exist, so re-running on a partially-applied schema is safe.

## Deployment steps

### Staging

1. Snapshot the staging database (standard precaution).
2. Run alembic upgrade:
   ```bash
   cd services/artana_evidence_db
   alembic upgrade head
   ```
3. Verify the columns exist:
   ```sql
   SELECT column_name, data_type, column_default, is_nullable
   FROM information_schema.columns
   WHERE table_name = 'relation_claims' AND column_name = 'assertion_class';
   ```
4. Verify no NULL values (sanity check that the server default applied):
   ```sql
   SELECT COUNT(*) FROM relation_claims WHERE assertion_class IS NULL;
   -- expected: 0
   ```
5. Smoke-test the API: create a research space, run init, verify a relation gets created with `assertion_class='SOURCE_BACKED'`.

### Production

Same procedure. Migration is fast (DDL only — no data rewrite beyond default fill).

## Required environment variables

- `DRUGBANK_API_KEY` — required for DrugBank ingestion. Without it, DrugBank enrichment will skip with a logged warning. Set in production secrets before enabling DrugBank in any space.

### Provisioning `DRUGBANK_API_KEY` in Cloud Run

Mirrors the existing `OPENAI_API_KEY` flow. One-time setup:

1. Create the secret in GCP Secret Manager (academic DrugBank access is free):
   ```bash
   printf '%s' "$YOUR_DRUGBANK_KEY" | gcloud secrets create drugbank-api-key \
     --project "$PROJECT_ID" \
     --data-file=- \
     --replication-policy=automatic
   ```
   (If you need to rotate later, use `gcloud secrets versions add drugbank-api-key --data-file=-`.)

2. Export the secret name alongside the other `*_SECRET_NAME` vars when running
   `scripts/deploy/sync_artana_evidence_api_cloud_run_runtime_config.sh`:
   ```bash
   export DRUGBANK_API_KEY_SECRET_NAME=drugbank-api-key
   ./scripts/deploy/sync_artana_evidence_api_cloud_run_runtime_config.sh
   ```
   The sync script will add `DRUGBANK_API_KEY=drugbank-api-key:latest` to the
   Cloud Run service's `--update-secrets` and grant the runtime service account
   `roles/secretmanager.secretAccessor` on the secret automatically.

3. If `DRUGBANK_API_KEY_SECRET_NAME` is unset, the script skips the block
   silently — DrugBank enrichment stays disabled and logs a warning at ingest time.

## Rollback

`downgrade()` drops the columns. SQLite path is a no-op (skipped because SQLite doesn't support DROP COLUMN). For PostgreSQL:

```bash
cd services/artana_evidence_db
alembic downgrade 025_entity_embedding_status
```

## Known good revision

After applying:
```bash
alembic current
# expected: 026_p0_p2_schema_columns (head)
```
