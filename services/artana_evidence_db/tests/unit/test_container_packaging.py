from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".dockerignore").exists() and (
            candidate / "services" / "artana_evidence_db" / "Dockerfile"
        ).exists():
            return candidate
    message = "Unable to locate repository root from artana_evidence_db packaging test"
    raise RuntimeError(message)


REPO_ROOT = _repo_root()
DOCKERFILE_PATH = REPO_ROOT / "services" / "artana_evidence_db" / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_artana_evidence_db_container_keeps_separate_test_and_runtime_stages() -> None:
    """Regression: the Dockerfile must keep a dedicated pytest target."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    assert "FROM python:3.13.12-slim AS base" in dockerfile
    assert "FROM base AS test" in dockerfile
    assert "FROM base AS runtime" in dockerfile
    assert dockerfile.index("FROM base AS test") < dockerfile.index(
        "FROM base AS runtime",
    )
    assert 'CMD ["pytest", "artana_evidence_db/tests/unit", "-q"]' in dockerfile
    assert 'CMD ["python", "-m", "artana_evidence_db"]' in dockerfile


def test_artana_evidence_db_test_stage_copies_required_repo_test_assets() -> None:
    """Regression: graph-service test images need repo fixtures and tooling."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    required_copy_lines = (
        "COPY architecture_overrides.json ./architecture_overrides.json",
        "COPY pytest.ini ./pytest.ini",
        "COPY docs ./docs",
        "COPY scripts ./scripts",
    )

    for copy_line in required_copy_lines:
        assert copy_line in dockerfile

    assert "PYTHONPATH=/app" in dockerfile
    assert "COPY services/artana_evidence_db/requirements-dev.txt" in dockerfile
    assert "COPY services/artana_evidence_db ./artana_evidence_db" in dockerfile
    assert (
        "COPY services/artana_evidence_db ./services/artana_evidence_db"
        not in dockerfile
    )
    assert "COPY src ./src" in dockerfile
    assert "COPY src/web/types ./src/web/types" not in dockerfile
    assert "COPY services/__init__.py ./services/__init__.py" not in dockerfile
    assert "COPY services ./services" not in dockerfile
    assert "pip install -r /tmp/artana_evidence_db_requirements_dev.txt" in dockerfile
    assert "aiosqlite>=0.20.0" in _read_text(
        REPO_ROOT / "services" / "artana_evidence_db" / "requirements-dev.txt",
    )
    assert 'pip install ".[dev]"' not in dockerfile
    assert "ln -sf /usr/local/bin/alembic /app/venv/bin/alembic" in dockerfile


def test_artana_evidence_db_runtime_stage_prunes_service_local_tests() -> None:
    """Regression: production images must not ship the service test tree."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    assert "FROM base AS runtime" in dockerfile
    assert "RUN rm -rf /app/artana_evidence_db/tests" in dockerfile


def test_dockerignore_reincludes_artana_evidence_db_shared_assets() -> None:
    """Regression: the Docker build context must expose shared docs assets."""
    dockerignore = _read_text(DOCKERIGNORE_PATH)

    assert "docs" in dockerignore

    expected_reincludes = (
        "!docs/",
        "!docs/**",
    )

    for pattern in expected_reincludes:
        assert pattern in dockerignore
