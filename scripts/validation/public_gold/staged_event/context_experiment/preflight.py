"""Freeze and verify the bounded Luna semantic-context experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import openai
import pydantic
from pydantic import BaseModel

from scripts.validation.public_gold.staged_event.context_experiment.compact_input import (
    INPUT_TOKEN_ESTIMATION_METHOD,
    V1_PARTICIPANT_INPUT_BYTES,
    build_compact_payload,
    measure_provider_input,
)
from scripts.validation.public_gold.staged_event.context_experiment.contracts import (
    SourceBoundParticipantOutput,
)
from scripts.validation.public_gold.staged_event.context_experiment.panel import (
    CONTROL_IDS,
    NON_CREDITABLE_IDS,
    PANEL_IDS,
    REPAIR_TARGET_IDS,
    build_context_panel,
)
from scripts.validation.public_gold.staged_event.contracts import (
    ModifierOutput,
    RoleAssignmentOutput,
    VerificationOutput,
)
from scripts.validation.public_gold.staged_event.paths import repository_root
from scripts.validation.public_gold.staged_event.prompting import (
    GUIDELINE_PATH,
    build_provider_format,
    build_stage_input,
    load_prompt,
)

RESULT_PATH = Path(
    "docs/validation/reports/2026-07-22-staged-event-comparison-v2-result.json"
)
CONSENSUS_PATH = Path(
    "docs/validation/adjudications/2026-07-22-staged-event-v2-consensus.json"
)
SOURCE_PATH = Path(
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
PROMPTS = {
    "participants": "docs/validation/prompts/2026-07-22-luna-context-participants.md",
    "roles": "docs/validation/prompts/2026-07-22-luna-context-roles.md",
    "modifiers": "docs/validation/prompts/2026-07-22-luna-context-modifiers.md",
    "verification": "docs/validation/prompts/2026-07-22-luna-context-verification.md",
}
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "participants": SourceBoundParticipantOutput,
    "roles": RoleAssignmentOutput,
    "modifiers": ModifierOutput,
    "verification": VerificationOutput,
}
CODE_FILES = (
    "scripts/validation/public_gold/staged_event/context_experiment/panel.py",
    "scripts/validation/public_gold/staged_event/context_experiment/preflight.py",
    "scripts/validation/public_gold/staged_event/context_experiment/live_execution.py",
    "scripts/validation/public_gold/staged_event/context_experiment/compact_input.py",
    "scripts/validation/public_gold/staged_event/context_experiment/contracts.py",
    "scripts/validation/public_gold/staged_event/context_experiment/participant_grounding.py",
)
MODEL_IDENTITY = "openai:gpt-5.6-luna"
PROVIDER_MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "high"


class ContextExperimentPreflightError(ValueError):
    """The frozen context experiment differs from current offline state."""


def build_preregistration(root: Path, *, authorized: bool) -> dict[str, object]:
    panel = build_context_panel(
        result_path=root / RESULT_PATH,
        source_path=root / SOURCE_PATH,
    )
    prompts = {
        stage: {
            "path": path,
            "sha256": _sha256(root / path),
            "effective_sha256": _text_sha256(
                (root / path).read_text(encoding="utf-8")
                + "\n"
                + (root / GUIDELINE_PATH).read_text(encoding="utf-8")
            ),
        }
        for stage, path in PROMPTS.items()
    }
    schemas = {
        stage: _canonical_sha256(model.model_json_schema())
        for stage, model in OUTPUT_MODELS.items()
    }
    formats = {
        stage: _canonical_sha256(
            build_provider_format(
                model,
                description=f"Focused Luna {stage} output for fixed V2 events.",
            )
        )
        for stage, model in OUTPUT_MODELS.items()
    }
    participant_input = build_stage_input(
        prompt=load_prompt(root, PROMPTS["participants"]),
        document_id="PMID-16428936",
        source_sha256=panel.source_sha256,
        payload=build_compact_payload(panel=panel, prior_stage_outputs={}),
    )
    participant_measurement = measure_provider_input(participant_input)
    input_byte_ceiling = 200_000
    if participant_measurement.serialized_bytes >= input_byte_ceiling:
        raise ContextExperimentPreflightError(
            "compact participant input exceeds byte ceiling"
        )
    if participant_measurement.serialized_bytes >= V1_PARTICIPANT_INPUT_BYTES // 2:
        raise ContextExperimentPreflightError(
            "compact participant input is not materially smaller"
        )
    frozen = {
        "source": {
            "document_id": "PMID-16428936",
            "path": SOURCE_PATH.as_posix(),
            "sha256": _sha256(root / SOURCE_PATH),
            "classification": "EXPOSED_DEVELOPMENT",
            "sealed_test_access": "DISABLED",
        },
        "inputs": {
            "v2_result_path": RESULT_PATH.as_posix(),
            "v2_result_sha256": _sha256(root / RESULT_PATH),
            "v2_consensus_path": CONSENSUS_PATH.as_posix(),
            "v2_consensus_sha256": _sha256(root / CONSENSUS_PATH),
            "shared_context_sha256": _canonical_sha256(panel.shared_context),
            "target_packets_sha256": _canonical_sha256(list(panel.packets)),
            "participant_provider_input_sha256": _text_sha256(participant_input),
            "participant_provider_input_bytes": participant_measurement.serialized_bytes,
            "participant_estimated_input_tokens": participant_measurement.estimated_input_tokens,
            "input_token_estimation_method": INPUT_TOKEN_ESTIMATION_METHOD,
            "provider_input_byte_ceiling_per_stage": input_byte_ceiling,
            "v1_participant_provider_input_bytes": V1_PARTICIPANT_INPUT_BYTES,
        },
        "panel": {
            "event_ids": sorted(PANEL_IDS),
            "repair_target_ids": sorted(REPAIR_TARGET_IDS),
            "control_ids": sorted(CONTROL_IDS),
            "non_creditable_ids": sorted(NON_CREDITABLE_IDS),
        },
        "model": {
            "identity": MODEL_IDENTITY,
            "provider_model_id": PROVIDER_MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "verifier_independence": "SAME_MODEL_FRESH_INDEPENDENT_CALL",
        },
        "prompts": prompts,
        "guidelines": {
            "path": GUIDELINE_PATH,
            "sha256": _sha256(root / GUIDELINE_PATH),
        },
        "schemas": schemas,
        "provider_formats": formats,
        "code": {
            "files": {path: _sha256(root / path) for path in CODE_FILES},
        },
        "dependencies": {
            "python": platform.python_version(),
            "openai": openai.__version__,
            "pydantic": pydantic.__version__,
        },
    }
    return {
        "schema_version": "artana.public_gold.luna_context_experiment.v2",
        "status": (
            "FROZEN_AUTHORIZED_FOR_ONE_EXECUTION"
            if authorized
            else "FROZEN_UNAUTHORIZED"
        ),
        "execution_authorized": authorized,
        "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
        "stage_order": ["participants", "roles", "modifiers", "verification"],
        "budgets": {
            "max_agent_calls": 4,
            "max_output_tokens_per_call": 50000,
            "max_total_tokens": 300000,
            "max_total_cost_usd": 3.0,
            "max_total_latency_seconds": 3600.0,
            "acknowledgement_timeout_seconds": 30.0,
            "polling_interval_seconds": 5.0,
            "max_polling_seconds_per_call": 900.0,
            "provider_retries": 0,
            "fallbacks": 0,
            "pricing_usd_per_token": {
                "input": 0.000001,
                "cached_input": 0.0000001,
                "output": 0.000006,
            },
        },
        "acceptance": {
            "wrong_to_correct_minimum": 2,
            "control_regressions_maximum": 0,
            "modifier_scope_event_id": "E-2773996d557442a07d58",
            "modifier_scope_must_be_correct": True,
            "typed_role_matches_must_increase": True,
            "nested_matches_must_increase": True,
            "verifier_false_acceptances_must_decrease": True,
            "unsupported_claims_maximum": 0,
            "receipts_must_verify": True,
        },
        "terminal_rules": {
            "discovery_calls": 0,
            "completion_calls": 0,
            "sol_calls": 0,
            "retries": 0,
            "fallbacks": 0,
            "untouched_sources": 0,
            "graph_writes": 0,
            "promotion": 0,
        },
        "frozen_state": frozen,
    }


def verify_preregistration(root: Path, path: Path) -> dict[str, object]:
    actual = json.loads(path.read_text(encoding="utf-8"))
    expected = build_preregistration(root, authorized=True)
    if actual != expected:
        raise ContextExperimentPreflightError("frozen context experiment changed")
    serialized = json.dumps(actual["frozen_state"]["inputs"], sort_keys=True).lower()
    if "gold_event" in serialized or "expected_event" in serialized:
        raise ContextExperimentPreflightError("gold answers entered model inputs")
    return {
        "status": "PREFLIGHT_PASSED",
        "preregistration_sha256": _sha256(path),
        "frozen_state_sha256": _canonical_sha256(actual["frozen_state"]),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _text_sha256(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write")
    write.add_argument("path", type=Path)
    write.add_argument("--authorized", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("path", type=Path)
    args = parser.parse_args()
    root = repository_root()
    if args.command == "write":
        payload = build_preregistration(root, authorized=args.authorized)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(_sha256(args.path))
        return 0
    print(json.dumps(verify_preregistration(root, args.path), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_preregistration", "verify_preregistration"]
