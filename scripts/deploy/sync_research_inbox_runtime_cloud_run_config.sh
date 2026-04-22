#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-research-inbox-runtime] $*"
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

create_job_if_missing() {
  local job_name="$1"
  local image_ref="$2"
  shift 2

  if gcloud run jobs describe "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" >/dev/null 2>&1; then
    return 0
  fi

  if [[ -z "${image_ref}" ]]; then
    echo "Configured runtime migration job does not exist and no bootstrap image was provided: ${job_name}" >&2
    return 1
  fi

  log "Creating missing job ${job_name}"
  gcloud run jobs create "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${image_ref}" \
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
require_var "RESEARCH_INBOX_RUNTIME_SERVICE"
require_var "DATABASE_URL_SECRET_NAME"

log "Syncing Research Inbox Runtime service for project=${PROJECT_ID} region=${REGION}"

declare -a runtime_update_args=()
if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  runtime_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_MIN_INSTANCES:-}" ]]; then
  runtime_update_args+=(
    --min-instances
    "${RESEARCH_INBOX_RUNTIME_MIN_INSTANCES}"
  )
fi

declare -a runtime_secret_pairs=(
  "RESEARCH_INBOX_RUNTIME_DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest"
)
if [[ -n "${AUTH_JWT_SECRET_NAME:-}" ]]; then
  runtime_secret_pairs+=("AUTH_JWT_SECRET=${AUTH_JWT_SECRET_NAME}:latest")
fi
if ((${#runtime_secret_pairs[@]} > 0)); then
  runtime_update_secrets="$(IFS=,; echo "${runtime_secret_pairs[*]}")"
  runtime_update_args+=(--update-secrets "${runtime_update_secrets}")
fi

declare -a runtime_env_pairs=(
  "RESEARCH_INBOX_RUNTIME_SERVICE_HOST=0.0.0.0"
  "RESEARCH_INBOX_RUNTIME_SERVICE_PORT=8080"
  "RESEARCH_INBOX_RUNTIME_SERVICE_RELOAD=0"
)
if [[ -n "${ARTANA_ENV:-}" ]]; then
  runtime_env_pairs+=("ARTANA_ENV=${ARTANA_ENV}")
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_APP_NAME:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_APP_NAME=${RESEARCH_INBOX_RUNTIME_APP_NAME}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_DB_SCHEMA:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_DB_SCHEMA=${RESEARCH_INBOX_RUNTIME_DB_SCHEMA}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_URL:-}" ]]; then
  runtime_env_pairs+=("ARTANA_EVIDENCE_API_URL=${ARTANA_EVIDENCE_API_URL}")
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_TIMEOUT_SECONDS:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_TIMEOUT_SECONDS=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_ID:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_ID=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_ID}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_EMAIL:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_EMAIL=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USER_EMAIL}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USERNAME:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USERNAME=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_USERNAME}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_FULL_NAME:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_FULL_NAME=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_FULL_NAME}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_ROLE:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_ROLE=${RESEARCH_INBOX_RUNTIME_ARTANA_EVIDENCE_API_SERVICE_ROLE}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_WORKER_POLL_INTERVAL_SECONDS:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_WORKER_POLL_INTERVAL_SECONDS=${RESEARCH_INBOX_RUNTIME_WORKER_POLL_INTERVAL_SECONDS}"
  )
fi
if [[ -n "${RESEARCH_INBOX_RUNTIME_ENABLE_INLINE_WORKER:-}" ]]; then
  runtime_env_pairs+=(
    "RESEARCH_INBOX_RUNTIME_ENABLE_INLINE_WORKER=${RESEARCH_INBOX_RUNTIME_ENABLE_INLINE_WORKER}"
  )
fi
if ((${#runtime_env_pairs[@]} > 0)); then
  runtime_update_envs="$(IFS=@; echo "${runtime_env_pairs[*]}")"
  runtime_update_args+=(--update-env-vars "^@^${runtime_update_envs}")
fi

update_service_if_needed \
  "${RESEARCH_INBOX_RUNTIME_SERVICE}" \
  "${runtime_update_args[@]}"
set_public_access \
  "${RESEARCH_INBOX_RUNTIME_SERVICE}" \
  "${RESEARCH_INBOX_RUNTIME_PUBLIC:-}"

if [[ -n "${RESEARCH_INBOX_RUNTIME_MIGRATION_JOB_NAME:-}" ]]; then
  if ! create_job_if_missing \
    "${RESEARCH_INBOX_RUNTIME_MIGRATION_JOB_NAME}" \
    "${RESEARCH_INBOX_RUNTIME_MIGRATION_JOB_IMAGE:-}" \
    --command python \
    --args=-m,research_inbox_runtime.manage,migrate; then
    exit 1
  fi

  declare -a migration_job_update_args=()
  if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
  fi
  migration_job_update_args+=(
    --update-secrets
    "RESEARCH_INBOX_RUNTIME_DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest"
  )

  update_job_if_needed \
    "${RESEARCH_INBOX_RUNTIME_MIGRATION_JOB_NAME}" \
    "${migration_job_update_args[@]}"
fi

log "Research Inbox Runtime sync completed"
