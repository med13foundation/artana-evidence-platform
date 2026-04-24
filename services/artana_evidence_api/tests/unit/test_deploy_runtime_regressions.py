from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github" / "workflows").exists() and (
            candidate
            / "scripts"
            / "deploy"
            / "sync_artana_evidence_api_cloud_run_runtime_config.sh"
        ).exists():
            return candidate
    message = "Unable to locate repository root from deploy regression test"
    raise RuntimeError(message)


REPO_ROOT = _repo_root()
API_SYNC_SCRIPT = (
    REPO_ROOT / "scripts" / "deploy" / "sync_artana_evidence_api_cloud_run_runtime_config.sh"
)
API_DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "artana-evidence-api-deploy.yml"
DB_DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "artana-evidence-db-deploy.yml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_job_block(workflow: str, job_name: str) -> str:
    marker = f"  {job_name}:"
    start = workflow.index(marker)
    next_job = re.search(r"\n  [A-Za-z0-9_-]+:", workflow[start + len(marker) :])
    if next_job is None:
        return workflow[start:]
    return workflow[start : start + len(marker) + next_job.start()]


def _workflow_step_block(workflow: str, step_name: str) -> str:
    marker = f"      - name: {step_name}"
    start = workflow.index(marker)
    next_step = re.search(r"\n      - name:", workflow[start + len(marker) :])
    if next_step is None:
        return workflow[start:]
    return workflow[start : start + len(marker) + next_step.start()]


def test_artana_evidence_api_runtime_sync_wires_graph_jwt_secret() -> None:
    """Regression: deployed API must not silently use the dev graph JWT secret."""
    script = _read_text(API_SYNC_SCRIPT)

    assert 'require_var "GRAPH_JWT_SECRET_NAME"' in script
    assert '"${ARTANA_ENV:-}" == "staging"' in script
    assert '"${ARTANA_ENV:-}" == "production"' in script
    assert "GRAPH_JWT_SECRET=${GRAPH_JWT_SECRET_NAME}:latest" in script
    assert script.count("GRAPH_JWT_SECRET=${GRAPH_JWT_SECRET_NAME}:latest") >= 2
    assert 'harness_secret_names+=("${GRAPH_JWT_SECRET_NAME}")' in script
    assert 'migration_job_secret_names+=("${GRAPH_JWT_SECRET_NAME}")' in script
    assert "grant_secret_access_for_job" in script


def test_artana_evidence_api_runtime_sync_propagates_env_and_acl_defaults() -> None:
    """Regression: staging/prod sync must set env-aware runtime defaults."""
    script = _read_text(API_SYNC_SCRIPT)

    assert 'harness_env_pairs+=("ARTANA_ENV=${ARTANA_ENV}")' in script
    assert 'if [[ -n "${SPACE_ACL_MODE:-}" ]]; then' in script
    assert 'elif [[ "${ARTANA_ENV:-}" == "production" || "${ARTANA_ENV:-}" == "staging" ]]; then' in script
    assert 'harness_env_pairs+=("SPACE_ACL_MODE=enforce")' in script


def test_artana_evidence_api_deploy_workflow_provisions_graph_jwt_secret() -> None:
    """Regression: every API deploy target must pass the graph JWT secret name."""
    workflow = _read_text(API_DEPLOY_WORKFLOW)

    expected_secret_bindings = (
        "GRAPH_JWT_SECRET_NAME: ${{ vars.GRAPH_JWT_SECRET_NAME_DEV }}",
        "GRAPH_JWT_SECRET_NAME: ${{ vars.GRAPH_JWT_SECRET_NAME_STAGING }}",
        "GRAPH_JWT_SECRET_NAME: ${{ vars.GRAPH_JWT_SECRET_NAME_PROD }}",
    )
    for binding in expected_secret_bindings:
        assert workflow.count(binding) == 2

    staging_grant_block = workflow[
        workflow.index("Grant Artana Evidence API secret access (Staging)") :
        workflow.index("Deploy Artana Evidence API to Cloud Run (Staging)")
    ]
    production_grant_block = workflow[
        workflow.index("Grant Artana Evidence API secret access (Production)") :
        workflow.index("Deploy Artana Evidence API to Cloud Run (Production)")
    ]
    assert "ARTANA_ENV: staging" in staging_grant_block
    assert "ARTANA_ENV: production" in production_grant_block


def test_artana_evidence_api_deploy_workflow_sets_expected_runtime_env_by_stage() -> (
    None
):
    """Regression: each deploy stage must pass the intended ARTANA_ENV value."""
    workflow = _read_text(API_DEPLOY_WORKFLOW)

    dev_grant_block = _workflow_step_block(
        workflow,
        "Grant Artana Evidence API secret access (Dev)",
    )
    dev_sync_block = _workflow_step_block(
        workflow,
        "Sync Artana Evidence API runtime config (Dev)",
    )
    staging_sync_block = _workflow_step_block(
        workflow,
        "Sync Artana Evidence API runtime config (Staging)",
    )
    production_sync_block = _workflow_step_block(
        workflow,
        "Sync Artana Evidence API runtime config (Production)",
    )

    assert "ARTANA_ENV:" not in dev_grant_block
    assert "ARTANA_ENV: development" in dev_sync_block
    assert "ARTANA_ENV: staging" in staging_sync_block
    assert "ARTANA_ENV: production" in production_sync_block


def test_artana_evidence_api_deploy_jobs_depend_on_service_checks() -> None:
    """Regression: API deploy jobs must not build or deploy before checks pass."""
    workflow = _read_text(API_DEPLOY_WORKFLOW)

    checks_block = _workflow_job_block(workflow, "evidence-api-service-checks")
    assert "run: make artana-evidence-api-service-checks" in checks_block

    for job_name in ("deploy-dev", "deploy-staging", "deploy-production"):
        deploy_block = _workflow_job_block(workflow, job_name)
        assert "needs: evidence-api-service-checks" in deploy_block
        assert deploy_block.index("needs: evidence-api-service-checks") < deploy_block.index(
            "runs-on: ubuntu-latest",
        )
        assert deploy_block.index("needs: evidence-api-service-checks") < deploy_block.index(
            "docker/build-push-action@v5",
        )


def test_artana_evidence_db_deploy_jobs_depend_on_service_checks() -> None:
    """Regression: graph deploy jobs must not build or deploy before checks pass."""
    workflow = _read_text(DB_DEPLOY_WORKFLOW)

    checks_block = _workflow_job_block(workflow, "graph-service-checks")
    assert "run: make graph-service-checks" in checks_block

    for job_name in ("deploy-dev", "deploy-staging", "deploy-production"):
        deploy_block = _workflow_job_block(workflow, job_name)
        assert "needs: graph-service-checks" in deploy_block
        assert deploy_block.index("needs: graph-service-checks") < deploy_block.index(
            "runs-on: ubuntu-latest",
        )
        assert deploy_block.index("needs: graph-service-checks") < deploy_block.index(
            "docker/build-push-action@v5",
        )
