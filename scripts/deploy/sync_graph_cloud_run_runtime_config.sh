#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-graph-runtime] $*"
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
    --format='value(spec.template.spec.serviceAccountName)')"

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
  if grant_output="$(gcloud secrets add-iam-policy-binding "${secret_name}" \
    --project "${PROJECT_ID}" \
    --member "serviceAccount:${service_account}" \
    --role "roles/secretmanager.secretAccessor" \
    --quiet 2>&1 >/dev/null)"; then
    return 0
  fi

  if [[ "${grant_output}" == *"secretmanager.secrets.getIamPolicy"* ]]; then
    log "Unable to grant secret access for ${secret_name}; continuing. gcloud said: ${grant_output}"
    return 0
  fi

  echo "${grant_output}" >&2
  return 1
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
    echo "Configured graph migration job does not exist and no bootstrap image was provided: ${job_name}" >&2
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

require_distinct_if_present() {
  local left_name="$1"
  local right_name="$2"
  local message="$3"
  local left_value="${!left_name:-}"
  local right_value="${!right_name:-}"

  if [[ -z "${left_value}" || -z "${right_value}" ]]; then
    return
  fi

  if [[ "${left_value}" == "${right_value}" ]]; then
    echo "${message}" >&2
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
require_var "GRAPH_SERVICE"
require_var "GRAPH_DATABASE_URL_SECRET_NAME"
require_var "GRAPH_JWT_SECRET_NAME"
require_distinct_if_present \
  "GRAPH_DATABASE_URL_SECRET_NAME" \
  "DATABASE_URL_SECRET_NAME" \
  "GRAPH_DATABASE_URL_SECRET_NAME must differ from DATABASE_URL_SECRET_NAME in deployed environments"

log "Syncing graph runtime config for project=${PROJECT_ID} region=${REGION}"

declare -a graph_update_args=()
if [[ -n "${GRAPH_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  graph_update_args+=(--set-cloudsql-instances "${GRAPH_CLOUDSQL_CONNECTION_NAME}")
fi
if [[ -n "${GRAPH_MIN_INSTANCES:-}" ]]; then
  graph_update_args+=(--min-instances "${GRAPH_MIN_INSTANCES}")
fi

declare -a graph_secret_pairs=()
declare -a graph_secret_names=()
if [[ -n "${GRAPH_DATABASE_URL_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("GRAPH_DATABASE_URL=${GRAPH_DATABASE_URL_SECRET_NAME}:latest")
  graph_secret_names+=("${GRAPH_DATABASE_URL_SECRET_NAME}")
fi
if [[ -n "${GRAPH_JWT_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("GRAPH_JWT_SECRET=${GRAPH_JWT_SECRET_NAME}:latest")
  graph_secret_names+=("${GRAPH_JWT_SECRET_NAME}")
fi
if [[ -n "${OPENAI_API_KEY_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("OPENAI_API_KEY=${OPENAI_API_KEY_SECRET_NAME}:latest")
  graph_secret_names+=("${OPENAI_API_KEY_SECRET_NAME}")
fi

if ((${#graph_secret_pairs[@]} > 0)); then
  graph_update_secrets="$(IFS=,; echo "${graph_secret_pairs[*]}")"
  graph_update_args+=(--update-secrets "${graph_update_secrets}")
fi

declare -a graph_env_pairs=(
  "GRAPH_SERVICE_HOST=0.0.0.0"
  "GRAPH_SERVICE_PORT=8080"
  "GRAPH_SERVICE_RELOAD=0"
)
if [[ -n "${ARTANA_ENV:-}" ]]; then
  graph_env_pairs+=("ARTANA_ENV=${ARTANA_ENV}")
fi
if [[ -n "${GRAPH_SERVICE_NAME:-}" ]]; then
  graph_env_pairs+=("GRAPH_SERVICE_NAME=${GRAPH_SERVICE_NAME}")
fi
if [[ -n "${GRAPH_DB_POOL_SIZE:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_POOL_SIZE=${GRAPH_DB_POOL_SIZE}")
fi
if [[ -n "${GRAPH_DB_MAX_OVERFLOW:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_MAX_OVERFLOW=${GRAPH_DB_MAX_OVERFLOW}")
fi
if [[ -n "${GRAPH_DB_POOL_TIMEOUT_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_DB_POOL_TIMEOUT_SECONDS=${GRAPH_DB_POOL_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${GRAPH_DB_POOL_RECYCLE_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_DB_POOL_RECYCLE_SECONDS=${GRAPH_DB_POOL_RECYCLE_SECONDS}"
  )
fi
if [[ -n "${GRAPH_DB_POOL_USE_LIFO:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_POOL_USE_LIFO=${GRAPH_DB_POOL_USE_LIFO}")
fi
if [[ -n "${GRAPH_ENABLE_ENTITY_EMBEDDINGS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_ENTITY_EMBEDDINGS=${GRAPH_ENABLE_ENTITY_EMBEDDINGS}"
  )
fi
if [[ -n "${GRAPH_ENABLE_SEARCH_AGENT:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_SEARCH_AGENT=${GRAPH_ENABLE_SEARCH_AGENT}"
  )
fi
if [[ -n "${GRAPH_ENABLE_RELATION_SUGGESTIONS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_RELATION_SUGGESTIONS=${GRAPH_ENABLE_RELATION_SUGGESTIONS}"
  )
fi
if [[ -n "${GRAPH_ENABLE_HYPOTHESIS_GENERATION:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_HYPOTHESIS_GENERATION=${GRAPH_ENABLE_HYPOTHESIS_GENERATION}"
  )
fi
if [[ -n "${ARTANA_POOL_MIN_SIZE:-}" ]]; then
  graph_env_pairs+=(
    "ARTANA_POOL_MIN_SIZE=${ARTANA_POOL_MIN_SIZE}"
  )
fi
if [[ -n "${ARTANA_POOL_MAX_SIZE:-}" ]]; then
  graph_env_pairs+=(
    "ARTANA_POOL_MAX_SIZE=${ARTANA_POOL_MAX_SIZE}"
  )
fi
if [[ -n "${ARTANA_COMMAND_TIMEOUT_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "ARTANA_COMMAND_TIMEOUT_SECONDS=${ARTANA_COMMAND_TIMEOUT_SECONDS}"
  )
fi

if ((${#graph_env_pairs[@]} > 0)); then
  graph_update_envs="$(IFS=@; echo "${graph_env_pairs[*]}")"
  graph_update_args+=(--update-env-vars "^@^${graph_update_envs}")
fi

grant_secret_access_for_service \
  "${GRAPH_SERVICE}" \
  "${graph_secret_names[@]}"

update_service_if_needed "${GRAPH_SERVICE}" "${graph_update_args[@]}"
set_public_access "${GRAPH_SERVICE}" "${GRAPH_PUBLIC:-}"

if [[ -n "${GRAPH_MIGRATION_JOB_NAME:-}" ]]; then
  if ! create_job_if_missing \
    "${GRAPH_MIGRATION_JOB_NAME}" \
    "${GRAPH_MIGRATION_JOB_IMAGE:-}" \
    --command python \
    --args=-m,artana_evidence_db.manage,migrate; then
    exit 1
  fi

  declare -a migration_job_update_args=()
  if [[ -n "${GRAPH_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(
      --set-cloudsql-instances
      "${GRAPH_CLOUDSQL_CONNECTION_NAME}"
    )
  fi

  if [[ -n "${GRAPH_DATABASE_URL_SECRET_NAME:-}" ]]; then
    migration_job_update_args+=(
      --update-secrets
      "GRAPH_DATABASE_URL=${GRAPH_DATABASE_URL_SECRET_NAME}:latest"
    )
  fi

  update_job_if_needed "${GRAPH_MIGRATION_JOB_NAME}" "${migration_job_update_args[@]}"
fi

log "Graph runtime sync completed"
