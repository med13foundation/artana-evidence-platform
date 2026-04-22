#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Missing required env var: PROJECT_ID" >&2
  exit 1
fi

if [[ -z "${REGION:-}" ]]; then
  echo "Missing required env var: REGION" >&2
  exit 1
fi

repository_name="${ARTIFACT_REGISTRY_REPOSITORY:-cloud-run-source-deploy}"

if gcloud artifacts repositories describe "${repository_name}" \
  --project "${PROJECT_ID}" \
  --location "${REGION}" >/dev/null 2>&1; then
  echo "[ensure-artifact-registry] Repository ${repository_name} already exists"
  exit 0
fi

echo "[ensure-artifact-registry] Creating repository ${repository_name} in ${REGION}"
gcloud artifacts repositories create "${repository_name}" \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --repository-format=docker \
  --description="Cloud Run deployment images" \
  --quiet
