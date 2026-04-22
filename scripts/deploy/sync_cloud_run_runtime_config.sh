#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-inbox-runtime] $*"
}

update_service_if_needed() {
  local service_name="$1"
  shift

  if (($# == 0)); then
    log "No runtime changes requested for ${service_name}"
    return
  fi

  log "Applying runtime updates for ${service_name} in a single revision"
  gcloud run services update "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    "$@" \
    --quiet >/dev/null
}

update_job_if_needed() {
  local job_name="$1"
  shift

  if (($# == 0)); then
    log "No runtime changes requested for job ${job_name}"
    return
  fi

  log "Applying runtime updates for job ${job_name}"
  gcloud run jobs update "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    "$@" \
    --quiet >/dev/null
}

is_true() {
  local value="${1:-}"
  local normalized
  normalized="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
  case "${normalized}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

get_service_status_url() {
  local service_name="$1"
  gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)'
}

get_service_primary_url() {
  local service_name="$1"
  local urls_json=""

  urls_json="$(gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(metadata.annotations."run.googleapis.com/urls")' 2>/dev/null || true)"

  if [[ "${urls_json}" =~ ^\[[[:space:]]*\"([^\"]+)\" ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi

  get_service_status_url "${service_name}"
}

set_public_access() {
  local service_name="$1"
  local public_flag="$2"

  if [[ -z "${public_flag}" ]]; then
    return
  fi

  if is_true "${public_flag}"; then
    log "Ensuring public access for ${service_name}"
    gcloud run services add-iam-policy-binding "${service_name}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --member="allUsers" \
      --role="roles/run.invoker" \
      --quiet >/dev/null
    return
  fi

  log "Ensuring private access for ${service_name}"
  gcloud run services remove-iam-policy-binding "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet >/dev/null || true
}

require_var "PROJECT_ID"
require_var "REGION"
require_var "INBOX_SERVICE"

log "Syncing Research Inbox runtime config for project=${PROJECT_ID} region=${REGION}"

if [[ -z "${INBOX_PUBLIC_URL:-}" ]]; then
  INBOX_PUBLIC_URL="$(get_service_primary_url "${INBOX_SERVICE}")"
fi

declare -a inbox_update_args=()
if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  inbox_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
fi
if [[ -n "${INBOX_MIN_INSTANCES:-}" ]]; then
  inbox_update_args+=(--min-instances "${INBOX_MIN_INSTANCES}")
fi

declare -a inbox_env_pairs=()
if [[ -n "${ARTANA_ENV:-}" ]]; then
  inbox_env_pairs+=("ARTANA_ENV=${ARTANA_ENV}")
fi
if is_true "${SYNC_INBOX_URLS:-}"; then
  inbox_env_pairs+=("NEXTAUTH_URL=${INBOX_PUBLIC_URL}")
  inbox_env_pairs+=("RESEARCH_INBOX_APP_URL=${INBOX_PUBLIC_URL}")
fi
if is_true "${SYNC_INBOX_HARNESS_URLS:-}" && [[ -n "${ARTANA_EVIDENCE_API_PUBLIC_URL:-}" ]]; then
  inbox_env_pairs+=("ARTANA_EVIDENCE_API_URL=${ARTANA_EVIDENCE_API_PUBLIC_URL}")
fi
if is_true "${SYNC_INBOX_RUNTIME_URLS:-}" && [[ -n "${RESEARCH_INBOX_RUNTIME_PUBLIC_URL:-}" ]]; then
  inbox_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_API_URL=${RESEARCH_INBOX_RUNTIME_PUBLIC_URL}"
  )
fi
if [[ -n "${RESEARCH_INBOX_DB_SCHEMA:-}" ]]; then
  inbox_env_pairs+=("RESEARCH_INBOX_DB_SCHEMA=${RESEARCH_INBOX_DB_SCHEMA}")
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_DB_SCHEMA:-}" ]]; then
  inbox_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_DB_SCHEMA=${RESEARCH_INBOX_RUNTIME_DB_SCHEMA}"
  )
fi
if [[ -n "${NEXT_PUBLIC_WORKFLOW_SSE_ENABLED:-}" ]]; then
  inbox_env_pairs+=(
    "NEXT_PUBLIC_WORKFLOW_SSE_ENABLED=${NEXT_PUBLIC_WORKFLOW_SSE_ENABLED}"
  )
fi
if ((${#inbox_env_pairs[@]} > 0)); then
  inbox_update_envs="$(IFS=@; echo "${inbox_env_pairs[*]}")"
  inbox_update_args+=(--update-env-vars "^@^${inbox_update_envs}")
fi

declare -a inbox_secret_pairs=()
if [[ -n "${DATABASE_URL_SECRET_NAME:-}" ]]; then
  inbox_secret_pairs+=(
    "RESEARCH_INBOX_DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest"
  )
fi
if [[ -n "${NEXTAUTH_SECRET_SECRET_NAME:-}" ]]; then
  inbox_secret_pairs+=("NEXTAUTH_SECRET=${NEXTAUTH_SECRET_SECRET_NAME}:latest")
fi
if [[ -n "${AUTH_JWT_SECRET_NAME:-}" ]]; then
  inbox_secret_pairs+=("AUTH_JWT_SECRET=${AUTH_JWT_SECRET_NAME}:latest")
fi
if ((${#inbox_secret_pairs[@]} > 0)); then
  inbox_update_secrets="$(IFS=,; echo "${inbox_secret_pairs[*]}")"
  inbox_update_args+=(--update-secrets "${inbox_update_secrets}")
fi

update_service_if_needed "${INBOX_SERVICE}" "${inbox_update_args[@]}"
set_public_access "${INBOX_SERVICE}" "${INBOX_PUBLIC:-}"

if [[ -n "${MIGRATION_JOB_NAME:-}" ]] && gcloud run jobs describe "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" >/dev/null 2>&1; then
  declare -a migration_job_update_args=()
  if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
  fi

  if [[ -n "${DATABASE_URL_SECRET_NAME:-}" ]]; then
    migration_job_update_args+=(
      --update-secrets
      "DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest"
    )
  fi

  update_job_if_needed "${MIGRATION_JOB_NAME}" "${migration_job_update_args[@]}"
fi

log "Research Inbox runtime sync completed"
