"""Reproducible offline custody gate for the one-call development experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from artana_evidence_api.document_extraction_support.scientific_events import (
    ScientificEventDocument,
)

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ScientificEventExtraction,
    assemble_scientific_event_document,
    build_provider_input,
)
from scripts.validation.public_gold.lossless_event_provider_format import (
    build_scientific_event_provider_format,
)
from scripts.validation.public_gold.source_selection import (
    development_tree_sha256,
    load_development_sources,
    select_lowest_sha256,
    source_inventory_sha256,
)

DEVELOPMENT_DIRECTORY = Path(
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/original-data/devel"
)
ARCHIVE_PATH = Path("validation/public_gold/bionlp_cg/raw/openbiocorpora-master.zip")
PROMPT_PATH = Path(
    "docs/validation/prompts/2026-07-21-lossless-scientific-event-development-prompt.md"
)
EXPECTED_DOCUMENTS = 100
MINIMUM_STOP_RULES = 5
MODEL_IDENTITY = "openai:gpt-5.6-sol"
PROVIDER_MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "high"
ACKNOWLEDGEMENT_TIMEOUT_SECONDS = 30.0
POLLING_INTERVAL_SECONDS = 5.0
MAX_POLLING_SECONDS = 900.0
EXPERIMENT_CODE_FILES = (
    "services/artana_evidence_api/document_extraction_support/scientific_events/__init__.py",
    "services/artana_evidence_api/document_extraction_support/scientific_events/contracts.py",
    "services/artana_evidence_api/document_extraction_support/scientific_events/validation.py",
    "scripts/validation/public_gold/bionlp_cg_adapter.py",
    "scripts/validation/public_gold/bionlp_cg_event_projection.py",
    "scripts/validation/public_gold/source_selection.py",
    "scripts/validation/public_gold/lossless_event_experiment_contracts.py",
    "scripts/validation/public_gold/lossless_event_scoring.py",
    "scripts/validation/public_gold/lossless_event_preflight.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
    "scripts/validation/public_gold/lossless_event_provider_format.py",
    "scripts/validation/public_gold/lossless_event_live_execution.py",
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/background/__init__.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/background/execution.py",
    "scripts/validation/provider_receipt_boundary/background/polling.py",
    "scripts/validation/provider_receipt_boundary/background/states.py",
)
DEPENDENCY_FILES = ("pyproject.toml",)
DEPENDENCY_PACKAGES = ("openai", "litellm", "pydantic")


class ExperimentPreflightError(ValueError):
    """The experiment differs from its frozen preregistration."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return sha256_bytes(encoded)


def compute_frozen_state(repository_root: Path) -> dict[str, object]:
    """Recompute every deterministic value without reading gold annotations."""

    development = repository_root / DEVELOPMENT_DIRECTORY
    sources = load_development_sources(
        development, expected_documents=EXPECTED_DOCUMENTS
    )
    selected = select_lowest_sha256(sources)
    prompt_path = repository_root / PROMPT_PATH
    prompt = prompt_path.read_text(encoding="utf-8")
    provider_input = build_provider_input(
        prompt=prompt,
        document_id=selected.document_id,
        source_sha256=selected.source_sha256,
        source_text=selected.source_text,
    )
    code_files = {
        path: _file_sha256(repository_root / path) for path in EXPERIMENT_CODE_FILES
    }
    dependency_files = {
        path: _file_sha256(repository_root / path) for path in DEPENDENCY_FILES
    }
    dependency_versions = {package: version(package) for package in DEPENDENCY_PACKAGES}
    scientific_schema = ScientificEventDocument.model_json_schema()
    extraction_schema = ScientificEventExtraction.model_json_schema()
    provider_format = build_scientific_event_provider_format()
    _prove_ir_accepts_output_contract(selected.document_id, selected.source_text)
    return {
        "source": {
            "development_directory": DEVELOPMENT_DIRECTORY.as_posix(),
            "development_documents": len(sources),
            "selection_rule": "minimum (source_sha256, document_id)",
            "selected_document_id": selected.document_id,
            "selected_source_sha256": selected.source_sha256,
            "source_inventory_sha256": source_inventory_sha256(sources),
            "development_tree_sha256": development_tree_sha256(
                development, repository_root=repository_root
            ),
            "archive_sha256": _file_sha256(repository_root / ARCHIVE_PATH),
            "test_access": "SEALED_NOT_READ",
        },
        "implementation": {
            "code_files": code_files,
            "code_bundle_sha256": canonical_sha256(code_files),
        },
        "dependencies": {
            "python": platform.python_version(),
            "packages": dependency_versions,
            "files": dependency_files,
            "dependency_bundle_sha256": canonical_sha256(
                {
                    "python": platform.python_version(),
                    "packages": dependency_versions,
                    "files": dependency_files,
                }
            ),
        },
        "schemas": {
            "scientific_event_ir_sha256": canonical_sha256(scientific_schema),
            "provider_output_contract_sha256": canonical_sha256(extraction_schema),
            "provider_response_format_sha256": canonical_sha256(provider_format),
            "provider_response_format_strict": provider_format.get("strict") is True,
            "output_contract_accepted_by_ir": True,
        },
        "prompt": {
            "path": PROMPT_PATH.as_posix(),
            "sha256": _file_sha256(prompt_path),
        },
        "model_input": {
            "sha256": sha256_bytes(provider_input.encode()),
            "components": [
                "frozen_generic_prompt",
                "document_id",
                "source_sha256",
                "source_text",
            ],
            "gold_annotations_included": False,
            "gold_counts_included": False,
            "gold_event_ids_included": False,
            "gold_arguments_included": False,
        },
        "model": {
            "identity": MODEL_IDENTITY,
            "provider_model_id": PROVIDER_MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": "provider_default_not_set",
        },
        "transport": {
            "mode": "OPENAI_RESPONSES_BACKGROUND_POLLING",
            "background": True,
            "acknowledgement_timeout_seconds": ACKNOWLEDGEMENT_TIMEOUT_SECONDS,
            "polling_interval_seconds": POLLING_INTERVAL_SECONDS,
            "max_polling_seconds": MAX_POLLING_SECONDS,
            "provider_creation_calls": 1,
            "duplicate_creation_calls": 0,
            "provider_retries": 0,
            "creation_idempotency_claimed": False,
        },
    }


def verify_preregistration(
    repository_root: Path,
    preregistration_path: Path,
    *,
    require_authorized: bool = True,
) -> dict[str, object]:
    """Fail closed unless a clean recomputation equals the frozen experiment."""

    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    expected_state = preregistration.get("frozen_state")
    actual_state = compute_frozen_state(repository_root)
    if expected_state != actual_state:
        raise ExperimentPreflightError(
            "frozen state differs from clean deterministic recomputation"
        )
    _verify_safety_contract(preregistration, require_authorized=require_authorized)
    return {
        "status": "PREFLIGHT_PASSED",
        "preregistration_sha256": _file_sha256(preregistration_path),
        "frozen_state_sha256": canonical_sha256(actual_state),
    }


def build_preregistration(repository_root: Path) -> dict[str, object]:
    """Create a new candidate; callers freeze it as a new immutable file."""

    return {
        "schema_version": "artana.public_gold.lossless_event_experiment.v5",
        "status": "FROZEN_UNAUTHORIZED_AWAITING_EXPLICIT_AUTHORIZATION",
        "execution_authorized": False,
        "qualification_status": "DEVELOPMENT_ONLY_NON_QUALIFYING",
        "invalid_predecessor": (
            "docs/validation/preregistrations/"
            "2026-07-21-lossless-event-ir-development-experiment-v4.json"
        ),
        "frozen_state": compute_frozen_state(repository_root),
        "budgets": {
            "provider_calls": 1,
            "duplicate_creation_calls": 0,
            "provider_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
            "max_output_tokens": 20000,
            "max_total_tokens": 40000,
            "max_cost_usd": 5.0,
            "max_latency_seconds": 900.0,
            "acknowledgement_timeout_seconds": ACKNOWLEDGEMENT_TIMEOUT_SECONDS,
            "polling_interval_seconds": POLLING_INTERVAL_SECONDS,
            "max_polling_seconds": MAX_POLLING_SECONDS,
            "pricing_usd_per_token": {
                "input": 0.000005,
                "cached_input": 0.0000005,
                "output": 0.00003,
            },
        },
        "deterministic_metrics": [
            "complete_event_exact_recovery",
            "exact_trigger_recovery",
            "typed_argument_and_participant_role_fidelity",
            "nested_event_recovery",
            "negation_and_speculation_fidelity",
            "unsupported_or_invented_events",
            "invalid_offsets_unresolved_references_and_cycles",
        ],
        "acceptance": {
            "complete_event_exact_recovery": "ALL",
            "trigger_recovery": "ALL",
            "typed_argument_role_fidelity": "ALL",
            "nested_event_recovery": "ALL",
            "modifier_fidelity": "ALL",
            "unsupported_or_invented_events_allowed": 0,
            "invalid_offsets_allowed": 0,
            "unresolved_references_allowed": 0,
            "cycles_allowed": 0,
            "unauthorized_semantic_mappings_allowed": 0,
        },
        "rules": {
            "retry_allowed": False,
            "fallback_allowed": False,
            "repair_allowed": False,
            "prompt_or_schema_change_after_freeze_allowed": False,
            "graph_write_allowed": False,
            "promotion_allowed": False,
            "agent_numeric_metrics_allowed": False,
            "sealed_test_access_allowed": False,
            "creation_idempotency_claimed": False,
        },
        "stop_rules": [
            "stop before the call on any deterministic preflight failure",
            "stop on provider response or receipt verification failure",
            "never repeat creation after an acknowledgement timeout",
            "poll only the acknowledged response ID",
            "stop on schema, offset, reference, cycle, provenance, custody, or budget failure",
            "stop after exactly one provider call regardless of scientific result",
            "never retry, repair, patch, reinterpret, or select another source",
        ],
    }


def _verify_safety_contract(
    preregistration: dict[str, object], *, require_authorized: bool
) -> None:
    if require_authorized and preregistration.get("execution_authorized") is not True:
        raise ExperimentPreflightError(
            "the new experiment is not explicitly authorized"
        )
    if (
        not require_authorized
        and preregistration.get("execution_authorized") is not False
    ):
        raise ExperimentPreflightError(
            "unauthorized preregistration unexpectedly permits execution"
        )
    budgets = preregistration.get("budgets")
    rules = preregistration.get("rules")
    stop_rules = preregistration.get("stop_rules")
    if not isinstance(budgets, dict) or not isinstance(rules, dict):
        raise ExperimentPreflightError("budgets and safety rules must be explicit")
    expected_budgets = {
        "provider_calls": 1,
        "duplicate_creation_calls": 0,
        "provider_retries": 0,
        "fallbacks": 0,
        "repairs": 0,
    }
    if any(budgets.get(key) != value for key, value in expected_budgets.items()):
        raise ExperimentPreflightError("one-call budget or zero-recovery rules changed")
    prohibited = (
        "retry_allowed",
        "fallback_allowed",
        "repair_allowed",
        "prompt_or_schema_change_after_freeze_allowed",
        "graph_write_allowed",
        "promotion_allowed",
        "agent_numeric_metrics_allowed",
        "sealed_test_access_allowed",
        "creation_idempotency_claimed",
    )
    if any(rules.get(rule) is not False for rule in prohibited):
        raise ExperimentPreflightError("a prohibited experiment capability is enabled")
    if not isinstance(stop_rules, list) or len(stop_rules) < MINIMUM_STOP_RULES:
        raise ExperimentPreflightError("experiment stop rules are incomplete")


def _prove_ir_accepts_output_contract(document_id: str, source_text: str) -> None:
    source_sha256 = sha256_bytes(source_text.encode())
    extraction = ScientificEventExtraction(
        status="ABSTAIN",
        mentions=(),
        events=(),
        abstention_reason="offline schema compatibility proof",
    )
    assemble_scientific_event_document(
        extraction,
        document_id=document_id,
        source_text=source_text,
        source_sha256=source_sha256,
        producer_identity=MODEL_IDENTITY,
    )


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise ExperimentPreflightError(f"frozen file is missing: {path}")
    return sha256_bytes(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write")
    write.add_argument("path", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("path", type=Path)
    verify.add_argument("--allow-unauthorized", action="store_true")
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[3]
    if args.command == "write":
        payload = build_preregistration(repository_root)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(_file_sha256(args.path))
    else:
        print(
            json.dumps(
                verify_preregistration(
                    repository_root,
                    args.path,
                    require_authorized=not args.allow_unauthorized,
                ),
                sort_keys=True,
            )
        )
    return 0


__all__ = [
    "ExperimentPreflightError",
    "build_preregistration",
    "canonical_sha256",
    "compute_frozen_state",
    "sha256_bytes",
    "verify_preregistration",
]


if __name__ == "__main__":
    raise SystemExit(main())
