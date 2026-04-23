#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-artana-evidence-api-runtime] $*"
}

get_project_number() {
  gcloud projects describe "${PROJECT_ID}" \
    --format='value(projectNumber)'
}

get_service_account_for_service() {
  local service_name="$1"
  local service_account

  service_account="$(gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(spec.template.spec.serviceAccountName)' \
    2>/dev/null || true)"

  if [[ -n "${service_account}" ]]; then
    printf '%s\n' "${service_account}"
    return 0
  fi

  local project_number
  project_number="$(get_project_number)"
  printf '%s-compute@developer.gserviceaccount.com\n' "${project_number}"
}

grant_secret_accessor_if_needed() {
  local secret_name="$1"
  local service_account="$2"
  local grant_output

  if [[ -z "${secret_name}" || -z "${service_account}" ]]; then
    return 0
  fi

  log "Ensuring ${service_account} can access secret ${secret_name}"
  if ! grant_output="$(gcloud secrets add-iam-policy-binding "${secret_name}" \
    --project "${PROJECT_ID}" \
    --member "serviceAccount:${service_account}" \
    --role "roles/secretmanager.secretAccessor" \
    --quiet 2>&1 >/dev/null)"; then
    log "Unable to grant secret access for ${secret_name}; continuing. gcloud said: ${grant_output}"
  fi
}

grant_secret_access_for_service() {
  local service_name="$1"
  shift

  if (($# == 0)); then
    return 0
  fi

  local service_account
  service_account="$(get_service_account_for_service "${service_name}")"

  local secret_name
  for secret_name in "$@"; do
    grant_secret_accessor_if_needed "${secret_name}" "${service_account}"
  done
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
    echo "Configured Artana Evidence API migration job does not exist and no bootstrap image was provided: ${job_name}" >&2
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
require_var "ARTANA_EVIDENCE_API_SERVICE"
require_var "ARTANA_EVIDENCE_API_DATABASE_URL_SECRET_NAME"

log "Syncing Artana Evidence API runtime config for project=${PROJECT_ID} region=${REGION}"

declare -a harness_update_args=()
if [[ -n "${ARTANA_EVIDENCE_API_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  harness_update_args+=(
    --set-cloudsql-instances
    "${ARTANA_EVIDENCE_API_CLOUDSQL_CONNECTION_NAME}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_MIN_INSTANCES:-}" ]]; then
  harness_update_args+=(--min-instances "${ARTANA_EVIDENCE_API_MIN_INSTANCES}")
fi

declare -a harness_secret_pairs=(
  "ARTANA_EVIDENCE_API_DATABASE_URL=${ARTANA_EVIDENCE_API_DATABASE_URL_SECRET_NAME}:latest"
)
declare -a harness_secret_names=("${ARTANA_EVIDENCE_API_DATABASE_URL_SECRET_NAME}")
if [[ -n "${AUTH_JWT_SECRET_NAME:-}" ]]; then
  harness_secret_pairs+=("AUTH_JWT_SECRET=${AUTH_JWT_SECRET_NAME}:latest")
  harness_secret_names+=("${AUTH_JWT_SECRET_NAME}")
fi
if [[ -n "${OPENAI_API_KEY_SECRET_NAME:-}" ]]; then
  harness_secret_pairs+=("OPENAI_API_KEY=${OPENAI_API_KEY_SECRET_NAME}:latest")
  harness_secret_names+=("${OPENAI_API_KEY_SECRET_NAME}")
fi
if [[ -n "${DRUGBANK_API_KEY_SECRET_NAME:-}" ]]; then
  harness_secret_pairs+=("DRUGBANK_API_KEY=${DRUGBANK_API_KEY_SECRET_NAME}:latest")
  harness_secret_names+=("${DRUGBANK_API_KEY_SECRET_NAME}")
fi
if [[ -n "${ARTANA_EVIDENCE_API_BOOTSTRAP_KEY_SECRET_NAME:-}" ]]; then
  harness_secret_pairs+=(
    "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY=${ARTANA_EVIDENCE_API_BOOTSTRAP_KEY_SECRET_NAME}:latest"
  )
  harness_secret_names+=("${ARTANA_EVIDENCE_API_BOOTSTRAP_KEY_SECRET_NAME}")
elif is_true "${ARTANA_EVIDENCE_API_REMOVE_BOOTSTRAP_KEY:-}"; then
  harness_update_args+=(
    --remove-secrets
    "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"
  )
fi
if ((${#harness_secret_pairs[@]} > 0)); then
  harness_update_secrets="$(IFS=,; echo "${harness_secret_pairs[*]}")"
  harness_update_args+=(--update-secrets "${harness_update_secrets}")
fi

declare -a harness_env_pairs=(
  "ARTANA_EVIDENCE_API_SERVICE_HOST=0.0.0.0"
  "ARTANA_EVIDENCE_API_SERVICE_PORT=8080"
  "ARTANA_EVIDENCE_API_SERVICE_RELOAD=0"
)
if [[ -n "${ARTANA_ENV:-}" ]]; then
  harness_env_pairs+=("ARTANA_ENV=${ARTANA_ENV}")
fi
if [[ -n "${SPACE_ACL_MODE:-}" ]]; then
  harness_env_pairs+=("SPACE_ACL_MODE=${SPACE_ACL_MODE}")
elif [[ "${ARTANA_ENV:-}" == "production" || "${ARTANA_ENV:-}" == "staging" ]]; then
  harness_env_pairs+=("SPACE_ACL_MODE=enforce")
fi
if [[ -n "${ARTANA_EVIDENCE_API_SERVICE_NAME:-}" ]]; then
  harness_env_pairs+=("ARTANA_EVIDENCE_API_APP_NAME=${ARTANA_EVIDENCE_API_SERVICE_NAME}")
fi
if [[ -n "${GRAPH_API_URL:-}" ]]; then
  harness_env_pairs+=("GRAPH_API_URL=${GRAPH_API_URL}")
fi
if [[ -n "${ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS=${ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_DB_POOL_SIZE:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_DB_POOL_SIZE=${ARTANA_EVIDENCE_API_DB_POOL_SIZE}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_DB_MAX_OVERFLOW:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_DB_MAX_OVERFLOW=${ARTANA_EVIDENCE_API_DB_MAX_OVERFLOW}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_DB_POOL_TIMEOUT_SECONDS:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_DB_POOL_TIMEOUT_SECONDS=${ARTANA_EVIDENCE_API_DB_POOL_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_DB_POOL_RECYCLE_SECONDS:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_DB_POOL_RECYCLE_SECONDS=${ARTANA_EVIDENCE_API_DB_POOL_RECYCLE_SECONDS}"
  )
fi
if [[ -n "${ARTANA_EVIDENCE_API_DB_POOL_USE_LIFO:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_EVIDENCE_API_DB_POOL_USE_LIFO=${ARTANA_EVIDENCE_API_DB_POOL_USE_LIFO}"
  )
fi
if [[ -n "${ARTANA_POOL_MIN_SIZE:-}" ]]; then
  harness_env_pairs+=("ARTANA_POOL_MIN_SIZE=${ARTANA_POOL_MIN_SIZE}")
fi
if [[ -n "${ARTANA_POOL_MAX_SIZE:-}" ]]; then
  harness_env_pairs+=("ARTANA_POOL_MAX_SIZE=${ARTANA_POOL_MAX_SIZE}")
fi
if [[ -n "${ARTANA_COMMAND_TIMEOUT_SECONDS:-}" ]]; then
  harness_env_pairs+=(
    "ARTANA_COMMAND_TIMEOUT_SECONDS=${ARTANA_COMMAND_TIMEOUT_SECONDS}"
  )
fi
if ((${#harness_env_pairs[@]} > 0)); then
  harness_update_envs="$(IFS=@; echo "${harness_env_pairs[*]}")"
  harness_update_args+=(--update-env-vars "^@^${harness_update_envs}")
fi

grant_secret_access_for_service \
  "${ARTANA_EVIDENCE_API_SERVICE}" \
  "${harness_secret_names[@]}"

if is_true "${ARTANA_EVIDENCE_API_GRANT_SECRET_ACCESS_ONLY:-}"; then
  log "Secret access grant completed; skipping runtime updates"
  exit 0
fi

update_service_if_needed "${ARTANA_EVIDENCE_API_SERVICE}" "${harness_update_args[@]}"
set_public_access "${ARTANA_EVIDENCE_API_SERVICE}" "${ARTANA_EVIDENCE_API_PUBLIC:-}"

if [[ -n "${ARTANA_EVIDENCE_API_MIGRATION_JOB_NAME:-}" ]]; then
  if ! create_job_if_missing \
    "${ARTANA_EVIDENCE_API_MIGRATION_JOB_NAME}" \
    "${ARTANA_EVIDENCE_API_MIGRATION_JOB_IMAGE:-}" \
    --command python \
    --args=-m,artana_evidence_api.manage,migrate; then
    exit 1
  fi

  declare -a migration_job_update_args=()
  if [[ -n "${ARTANA_EVIDENCE_API_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(
      --set-cloudsql-instances
      "${ARTANA_EVIDENCE_API_CLOUDSQL_CONNECTION_NAME}"
    )
  fi
  migration_job_update_args+=(
    --update-secrets
    "ARTANA_EVIDENCE_API_DATABASE_URL=${ARTANA_EVIDENCE_API_DATABASE_URL_SECRET_NAME}:latest"
  )

  update_job_if_needed \
    "${ARTANA_EVIDENCE_API_MIGRATION_JOB_NAME}" \
    "${migration_job_update_args[@]}"
fi

log "Artana Evidence API runtime sync completed"
