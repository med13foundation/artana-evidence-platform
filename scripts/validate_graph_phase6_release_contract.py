"""Validate graph-service product-boundary release contract wiring."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
for path in (PROJECT_ROOT, PROJECT_ROOT / "services"):
    resolved = str(path)
    if resolved not in sys.path:
        sys.path.append(resolved)
os.environ.setdefault(
    "GRAPH_DATABASE_URL",
    "postgresql://graph-release-contract:graph-release-contract@localhost:5432/graph_release_contract",
)

import artana_evidence_db.app as graph_app_module
from artana_evidence_db.product_contract import GRAPH_PRODUCT_CONTRACT
from artana_evidence_db.routers.health import health_check


def _skip_dictionary_seed(*_args: object, **_kwargs: object) -> None:
    """Disable runtime dictionary seeding while validating the release contract."""


graph_app_module.seed_builtin_dictionary_entries = _skip_dictionary_seed
graph_app_module.seed_biomedical_starter_concepts_for_existing_spaces = (
    _skip_dictionary_seed
)
create_app = graph_app_module.create_app


def _resolve(path: Path) -> Path:
    return PROJECT_ROOT / path


def _validate_runtime_contract() -> list[str]:
    errors: list[str] = []
    app = create_app()
    if app.version != GRAPH_PRODUCT_CONTRACT.service_version:
        errors.append(
            "FastAPI app version does not match graph product contract "
            f"({app.version!r} != {GRAPH_PRODUCT_CONTRACT.service_version!r})",
        )
    if app.openapi_url != GRAPH_PRODUCT_CONTRACT.openapi_url:
        errors.append(
            "FastAPI OpenAPI URL does not match graph product contract "
            f"({app.openapi_url!r} != {GRAPH_PRODUCT_CONTRACT.openapi_url!r})",
        )

    health = health_check()
    if health.version != GRAPH_PRODUCT_CONTRACT.service_version:
        errors.append(
            "Health endpoint version does not match graph product contract "
            f"({health.version!r} != {GRAPH_PRODUCT_CONTRACT.service_version!r})",
        )
    return errors


def _validate_openapi_artifact() -> list[str]:
    errors: list[str] = []
    openapi_path = _resolve(GRAPH_PRODUCT_CONTRACT.openapi_artifact)
    if not openapi_path.exists():
        errors.append(f"Missing OpenAPI artifact: {openapi_path}")
        return errors

    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    info = document.get("info")
    if not isinstance(info, dict):
        errors.append("OpenAPI artifact is missing the top-level info object")
        return errors

    if info.get("version") != GRAPH_PRODUCT_CONTRACT.service_version:
        errors.append(
            "OpenAPI info.version does not match graph product contract "
            f"({info.get('version')!r} != {GRAPH_PRODUCT_CONTRACT.service_version!r})",
        )

    paths = document.get("paths")
    if not isinstance(paths, dict):
        errors.append("OpenAPI artifact is missing the top-level paths object")
        return errors

    for path in paths:
        if path == GRAPH_PRODUCT_CONTRACT.health_path:
            continue
        if path.startswith(("/docs", "/openapi")):
            continue
        if not path.startswith(GRAPH_PRODUCT_CONTRACT.api_prefix):
            errors.append(
                f"OpenAPI path does not respect API prefix {GRAPH_PRODUCT_CONTRACT.api_prefix!r}: {path}",
            )
    return errors


def _validate_release_docs() -> list[str]:
    errors: list[str] = []
    required_docs = {
        GRAPH_PRODUCT_CONTRACT.release_policy_doc: (
            "## Versioning Policy",
            "## Deprecation Policy",
            "## Generated Client Ownership",
            "## Compatibility Expectations",
        ),
        GRAPH_PRODUCT_CONTRACT.release_checklist_doc: (
            "# Graph Service Release Checklist",
            "OpenAPI",
            "generated TypeScript client",
        ),
        GRAPH_PRODUCT_CONTRACT.upgrade_guide_doc: (
            "# Graph Service Upgrade Guide",
            "alembic",
            "graph-service-checks",
        ),
    }
    for relative_path, required_markers in required_docs.items():
        full_path = _resolve(relative_path)
        if not full_path.exists():
            errors.append(f"Missing release-boundary document: {full_path}")
            continue
        contents = full_path.read_text(encoding="utf-8")
        errors.extend(
            f"Document {full_path} is missing required marker {marker!r}"
            for marker in required_markers
            if marker not in contents
        )
    return errors


def _validate_generated_client_artifact() -> list[str]:
    errors: list[str] = []
    client_path = _resolve(GRAPH_PRODUCT_CONTRACT.generated_ts_client_artifact)
    if not client_path.exists():
        errors.append(f"Missing generated TypeScript client artifact: {client_path}")
        return errors
    contents = client_path.read_text(encoding="utf-8")
    if "Auto-generated by scripts/generate_ts_types.py" not in contents:
        errors.append(
            f"Generated TypeScript client artifact does not contain generator marker: {client_path}",
        )
    return errors


def _validate_make_targets() -> list[str]:
    errors: list[str] = []
    contents = MAKEFILE_PATH.read_text(encoding="utf-8")
    required_targets = (
        "graph-service-contract-check",
        "graph-service-sync-contracts",
        "graph-phase6-release-check",
    )
    errors.extend(
        f"Missing Make target for release boundary: {target}"
        for target in required_targets
        if f"{target}:" not in contents
    )
    return errors


def main() -> int:
    errors = [
        *_validate_runtime_contract(),
        *_validate_openapi_artifact(),
        *_validate_release_docs(),
        *_validate_generated_client_artifact(),
        *_validate_make_targets(),
    ]
    if errors:
        print("graph_phase6_release_contract: error")
        for error in errors:
            print(f" - {error}")
        return 1

    print("graph_phase6_release_contract: ok")
    print(
        "graph_phase6_release_contract: runtime, OpenAPI, generated client, and release docs are aligned",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
