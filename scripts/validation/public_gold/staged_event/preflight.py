"""Frozen custody and policy gate for the staged exposed comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from scripts.validation.public_gold.lossless_event_preflight import (
    ARCHIVE_PATH,
    DEVELOPMENT_DIRECTORY,
    EXPECTED_DOCUMENTS,
)
from scripts.validation.public_gold.source_selection import (
    development_tree_sha256,
    load_development_sources,
    select_lowest_sha256,
    source_inventory_sha256,
)
from scripts.validation.public_gold.staged_event.paths import repository_root
from scripts.validation.public_gold.staged_event.prompting import (
    build_provider_format,
    build_stage_input,
    load_prompt,
)
from scripts.validation.public_gold.staged_event.registry import (
    ALL_STAGES,
    DISCOVERY,
    REQUIRED_STAGES,
)

MODEL_IDENTITY = "openai:gpt-5.6-sol"
PROVIDER_MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "high"
EXPERIMENT_CODE_FILES = (
    "services/artana_evidence_api/document_extraction_support/scientific_events/contracts.py",
    "services/artana_evidence_api/document_extraction_support/scientific_events/validation.py",
    "scripts/validation/public_gold/bionlp_cg_adapter.py",
    "scripts/validation/public_gold/bionlp_cg_event_projection.py",
    "scripts/validation/public_gold/source_selection.py",
    "scripts/validation/public_gold/lossless_event_experiment_contracts.py",
    "scripts/validation/public_gold/lossless_event_offset_resolution.py",
    "scripts/validation/public_gold/lossless_event_scoring.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
    "scripts/validation/public_gold/staged_event/contracts.py",
    "scripts/validation/public_gold/staged_event/assembly.py",
    "scripts/validation/public_gold/staged_event/prompting.py",
    "scripts/validation/public_gold/staged_event/registry.py",
    "scripts/validation/public_gold/staged_event/preflight.py",
    "scripts/validation/public_gold/staged_event/live_execution.py",
    "scripts/validation/public_gold/staged_event/paths.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/background/execution.py",
    "scripts/validation/provider_receipt_boundary/background/polling.py",
    "scripts/validation/provider_receipt_boundary/background/states.py",
)
DEPENDENCY_PACKAGES = ("openai", "pydantic")


class StagedExperimentPreflightError(ValueError):
    """The staged comparison differs from its immutable preregistration."""


def compute_frozen_state(repository_root: Path) -> dict[str, object]:
    sources = load_development_sources(
        repository_root / DEVELOPMENT_DIRECTORY,
        expected_documents=EXPECTED_DOCUMENTS,
    )
    selected = select_lowest_sha256(sources)
    prompts = {
        stage.name: {
            "path": stage.prompt_path,
            "sha256": _file_sha256(repository_root / stage.prompt_path),
        }
        for stage in ALL_STAGES
    }
    formats = {
        stage.name: build_provider_format(
            stage.output_model,
            description=stage.description,
        )
        for stage in ALL_STAGES
    }
    schemas = {
        stage.name: canonical_sha256(stage.output_model.model_json_schema())
        for stage in ALL_STAGES
    }
    discovery_input = build_stage_input(
        prompt=load_prompt(repository_root, DISCOVERY.prompt_path),
        document_id=selected.document_id,
        source_sha256=selected.source_sha256,
        payload={"source_text": selected.source_text},
    )
    code_files = {
        path: _file_sha256(repository_root / path) for path in EXPERIMENT_CODE_FILES
    }
    dependencies = {
        "python": platform.python_version(),
        "packages": {name: version(name) for name in DEPENDENCY_PACKAGES},
        "pyproject_sha256": _file_sha256(repository_root / "pyproject.toml"),
    }
    return {
        "source": {
            "selected_document_id": selected.document_id,
            "selected_source_sha256": selected.source_sha256,
            "development_documents": len(sources),
            "selection_rule": "minimum (source_sha256, document_id)",
            "source_inventory_sha256": source_inventory_sha256(sources),
            "development_tree_sha256": development_tree_sha256(
                repository_root / DEVELOPMENT_DIRECTORY,
                repository_root=repository_root,
            ),
            "archive_sha256": _file_sha256(repository_root / ARCHIVE_PATH),
            "test_access": "SEALED_NOT_READ",
        },
        "implementation": {
            "code_files": code_files,
            "code_bundle_sha256": canonical_sha256(code_files),
        },
        "dependencies": {
            **dependencies,
            "bundle_sha256": canonical_sha256(dependencies),
        },
        "prompts": prompts,
        "schemas": schemas,
        "provider_formats": {
            name: canonical_sha256(provider_format)
            for name, provider_format in formats.items()
        },
        "stage_order": [stage.name for stage in REQUIRED_STAGES],
        "optional_stage": "completion",
        "discovery_input_sha256": hashlib.sha256(discovery_input.encode()).hexdigest(),
        "model": {
            "identity": MODEL_IDENTITY,
            "provider_model_id": PROVIDER_MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": "provider_default_not_set",
        },
        "gold_isolation": {
            "annotations_in_agent_input": False,
            "event_counts_in_agent_input": False,
            "event_ids_in_agent_input": False,
            "triggers_in_agent_input": False,
            "roles_in_agent_input": False,
            "gold_phrases_in_agent_input": False,
        },
    }


def build_preregistration(repository_root: Path) -> dict[str, object]:
    return {
        **_experiment_policy(authorized=False),
        "frozen_state": compute_frozen_state(repository_root),
    }


def verify_preregistration(
    repository_root: Path,
    preregistration_path: Path,
    *,
    require_authorized: bool = True,
) -> dict[str, object]:
    payload = json.loads(preregistration_path.read_text(encoding="utf-8"))
    if payload.get("frozen_state") != compute_frozen_state(repository_root):
        raise StagedExperimentPreflightError("frozen state changed")
    expected_policy = _experiment_policy(authorized=require_authorized)
    for field, expected in expected_policy.items():
        if payload.get(field) != expected:
            raise StagedExperimentPreflightError(f"experiment policy changed: {field}")
    return {
        "status": "PREFLIGHT_PASSED",
        "preregistration_sha256": _file_sha256(preregistration_path),
        "frozen_state_sha256": canonical_sha256(payload["frozen_state"]),
    }


def _experiment_policy(*, authorized: bool) -> dict[str, object]:
    return {
        "schema_version": "artana.public_gold.staged_event_comparison.v1",
        "status": (
            "FROZEN_AUTHORIZED_FOR_ONE_EXECUTION"
            if authorized
            else "FROZEN_UNAUTHORIZED_AWAITING_EXPLICIT_AUTHORIZATION"
        ),
        "execution_authorized": authorized,
        "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
        "baseline": {
            "classification": "PRESERVED_V6_DIAGNOSTIC",
            "complete_events": {"matched": 2, "gold": 30},
            "triggers": {"matched": 21, "gold": 30},
            "typed_arguments": {"matched": 1, "gold": 37},
            "nested_arguments": {"matched": 1, "gold": 12},
            "modifiers": {"matched": 0, "gold": 2},
            "unsupported_or_invented_events": 31,
            "unauthorized_semantic_mappings": 19,
        },
        "budgets": {
            "max_agent_calls": 6,
            "max_total_tokens": 400000,
            "max_total_cost_usd": 12.0,
            "max_total_latency_seconds": 1800.0,
            "max_output_tokens_per_call": 20000,
            "acknowledgement_timeout_seconds": 30.0,
            "polling_interval_seconds": 5.0,
            "max_polling_seconds_per_call": 600.0,
            "provider_retries": 0,
            "fallbacks": 0,
            "alternate_models": 0,
            "pricing_usd_per_token": {
                "input": 0.000005,
                "cached_input": 0.0000005,
                "output": 0.00003,
            },
        },
        "acceptance": {
            "complete_events_minimum": 10,
            "triggers_minimum": 24,
            "typed_arguments_minimum": 15,
            "nested_arguments_minimum": 5,
            "unsupported_or_invented_events_maximum": 15,
            "completion_unsupported_increase_maximum": 0,
            "valid_receipts_required": True,
        },
        "rules": {
            "one_execution_per_required_stage": True,
            "maximum_completion_passes": 1,
            "provider_retry_allowed": False,
            "fallback_allowed": False,
            "alternate_model_allowed": False,
            "prompt_or_schema_change_after_freeze_allowed": False,
            "deterministic_semantic_inference_allowed": False,
            "graph_write_allowed": False,
            "promotion_allowed": False,
            "sealed_test_access_allowed": False,
            "one_shot_baseline_rerun_allowed": False,
        },
        "stop_rules": [
            "stop before calls on custody or hash mismatch",
            "stop at the first provider receipt or schema failure",
            "stop on a missing required stage",
            "stop on ambiguous offsets, unresolved references, or cycles",
            "stop when aggregate calls, tokens, latency, or cost exceed budget",
            "never retry, fallback, change model, or patch during execution",
            "stop after one optional completion pass",
            "never access sealed sources, write to graph, or promote",
        ],
    }


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise StagedExperimentPreflightError(f"frozen file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write")
    write.add_argument("path", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("path", type=Path)
    verify.add_argument("--allow-unauthorized", action="store_true")
    args = parser.parse_args()
    root = repository_root()
    if args.command == "write":
        payload = build_preregistration(root)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(_file_sha256(args.path))
    else:
        print(
            json.dumps(
                verify_preregistration(
                    root,
                    args.path,
                    require_authorized=not args.allow_unauthorized,
                ),
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
