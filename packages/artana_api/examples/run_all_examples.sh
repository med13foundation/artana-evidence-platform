#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="${PYTHON_BIN}"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON="${VIRTUAL_ENV}/bin/python"
elif [[ -x "${REPO_ROOT}/venv/bin/python" ]]; then
  PYTHON="${REPO_ROOT}/venv/bin/python"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${REPO_ROOT}/.venv/bin/python"
else
  PYTHON="python3"
fi

BASE_URL="${ARTANA_API_BASE_URL:-${ARTANA_BASE_URL:-}}"
BOOTSTRAP_KEY="${ARTANA_BOOTSTRAP_KEY:-${ARTANA_EVIDENCE_API_BOOTSTRAP_KEY:-}}"
EMAIL="${ARTANA_EXAMPLE_EMAIL:-developer@example.com}"
USERNAME="${ARTANA_EXAMPLE_USERNAME:-developer}"
FULL_NAME="${ARTANA_EXAMPLE_FULL_NAME:-Developer Example}"

if [[ -z "${BASE_URL}" ]]; then
  echo "Missing ARTANA_API_BASE_URL." >&2
  exit 1
fi

if [[ -z "${BOOTSTRAP_KEY}" ]]; then
  echo "Missing ARTANA_BOOTSTRAP_KEY." >&2
  exit 1
fi

run_example() {
  local example_name="$1"
  shift
  echo
  echo ">>> ${example_name}"
  "${PYTHON}" "$@"
}

bootstrap_output="$(
  "${PYTHON}" "${SCRIPT_DIR}/01_bootstrap_api_key.py" \
    --base-url "${BASE_URL}" \
    --bootstrap-key "${BOOTSTRAP_KEY}" \
    --email "${EMAIL}" \
    --username "${USERNAME}" \
    --full-name "${FULL_NAME}"
)"

echo "${bootstrap_output}"

api_key="$(
  printf '%s\n' "${bootstrap_output}" \
    | awk -F': ' '/^api_key: / {print $2; exit}'
)"

if [[ -z "${api_key}" ]]; then
  echo "Could not extract api_key from bootstrap output." >&2
  exit 1
fi

export ARTANA_API_BASE_URL="${BASE_URL}"
export ARTANA_API_KEY="${api_key}"

run_example "02_health_and_identity.py" "${SCRIPT_DIR}/02_health_and_identity.py"
run_example "03_graph_search_default_space.py" "${SCRIPT_DIR}/03_graph_search_default_space.py"
run_example "04_project_space_workflow.py" "${SCRIPT_DIR}/04_project_space_workflow.py"
run_example "05_onboarding_round_trip.py" "${SCRIPT_DIR}/05_onboarding_round_trip.py"
run_example "06_runs_and_artifacts.py" "${SCRIPT_DIR}/06_runs_and_artifacts.py"
run_example "07_graph_connection_workflow.py" "${SCRIPT_DIR}/07_graph_connection_workflow.py"
run_example "08_document_ingestion_and_extraction.py" "${SCRIPT_DIR}/08_document_ingestion_and_extraction.py"
run_example "09_review_queue_actions.py" "${SCRIPT_DIR}/09_review_queue_actions.py"
run_example "10_chat_with_documents.py" "${SCRIPT_DIR}/10_chat_with_documents.py"
run_example "11_pubmed_search.py" "${SCRIPT_DIR}/11_pubmed_search.py"
run_example "12_chat_with_pdf.py" "${SCRIPT_DIR}/12_chat_with_pdf.py"
