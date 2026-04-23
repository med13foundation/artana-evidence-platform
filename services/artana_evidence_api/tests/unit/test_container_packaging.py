from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".dockerignore").exists() and (
            candidate / "services" / "artana_evidence_api" / "Dockerfile"
        ).exists():
            return candidate
    message = "Unable to locate repository root from artana-evidence-api packaging test"
    raise RuntimeError(message)


REPO_ROOT = _repo_root()
DOCKERFILE_PATH = REPO_ROOT / "services" / "artana_evidence_api" / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"
REQUIREMENTS_PATH = REPO_ROOT / "services" / "artana_evidence_api" / "requirements.txt"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_artana_evidence_api_container_keeps_separate_test_and_runtime_stages() -> None:
    """Regression: the Dockerfile must keep a dedicated pytest target."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    assert "FROM python:3.13.12-slim AS base" in dockerfile
    assert "FROM base AS test" in dockerfile
    assert "FROM base AS runtime" in dockerfile
    assert dockerfile.index("FROM base AS test") < dockerfile.index(
        "FROM base AS runtime",
    )
    assert (
        'CMD ["pytest", "artana_evidence_api/tests/unit", '
        '"artana_evidence_api/tests/integration", "-q"]' in dockerfile
    )
    assert 'CMD ["python", "-m", "artana_evidence_api"]' in dockerfile


def test_artana_evidence_api_test_stage_copies_subprocess_and_validator_inputs() -> (
    None
):
    """Regression: subprocess-driven tests need repo assets inside the image."""
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
    assert "COPY services/artana_evidence_api ./artana_evidence_api" in dockerfile
    assert (
        "COPY services/artana_evidence_api ./services/artana_evidence_api"
        not in dockerfile
    )
    assert "COPY src ./src" not in dockerfile
    assert "COPY src/web/types ./src/web/types" not in dockerfile
    assert "COPY services/__init__.py ./services/__init__.py" not in dockerfile
    assert "COPY services ./services" not in dockerfile
    assert "pip install -r /tmp/artana_evidence_api_requirements_dev.txt" in dockerfile
    assert 'pip install ".[dev]"' not in dockerfile
    assert "ln -sf /usr/local/bin/alembic /app/venv/bin/alembic" in dockerfile


def test_artana_evidence_api_container_installs_git_for_git_based_runtime_dependencies() -> (
    None
):
    """Regression: git-backed requirements need git available in the image."""
    dockerfile = _read_text(DOCKERFILE_PATH)
    requirements = _read_text(REQUIREMENTS_PATH)

    assert "git+" in requirements
    assert "apt-get install --yes --no-install-recommends git" in dockerfile


def test_artana_evidence_api_runtime_requirements_include_multipart_parser() -> None:
    """Regression: FastAPI file/form routes need python-multipart in runtime deps."""
    requirements = _read_text(REQUIREMENTS_PATH)

    assert "python-multipart" in requirements


def test_artana_evidence_api_runtime_stage_prunes_service_local_tests() -> None:
    """Regression: production images must not ship the service test tree."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    assert "FROM base AS runtime" in dockerfile
    assert "RUN rm -rf /app/artana_evidence_api/tests" in dockerfile


def test_dockerignore_reincludes_artana_evidence_api_shared_assets() -> None:
    """Regression: the build context must expose shared docs assets to Docker."""
    dockerignore = _read_text(DOCKERIGNORE_PATH)

    assert "docs" in dockerignore

    expected_reincludes = (
        "!docs/",
        "!docs/**",
    )

    for pattern in expected_reincludes:
        assert pattern in dockerignore
