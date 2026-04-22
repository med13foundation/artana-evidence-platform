"""Helpers for rebuilding Phase 2 shadow-planner fixtures from real compare runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from artana_evidence_api.phase1_compare import (
    Phase1CompareRequest,
    build_phase1_source_preferences,
)
from artana_evidence_api.phase2_shadow_compare import (
    DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
)
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class Phase2ShadowFixtureRunSpec:
    run_id: str
    checkpoint_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase2ShadowFixtureSpec:
    fixture_name: str
    objective: str
    seed_terms: tuple[str, ...]
    title: str
    enabled_sources: tuple[str, ...]
    max_depth: int
    max_hypotheses: int
    runs: tuple[Phase2ShadowFixtureRunSpec, ...]

    @property
    def fixture_filename(self) -> str:
        return f"{self.fixture_name.casefold()}.json"


Phase2ShadowFixtureSet = Literal["objective", "supplemental", "all"]


DEFAULT_PHASE2_SHADOW_OBJECTIVE_FIXTURE_SPECS: tuple[Phase2ShadowFixtureSpec, ...] = (
    Phase2ShadowFixtureSpec(
        fixture_name="BRCA1",
        objective="Investigate BRCA1 and PARP inhibitor response.",
        seed_terms=("BRCA1", "PARP inhibitor"),
        title="BRCA1 PARP inhibitor shadow fixture",
        enabled_sources=("pubmed", "clinvar", "alphafold", "drugbank"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="brca1-run-1",
                checkpoint_keys=("before_first_action", "before_terminal_stop"),
            ),
            Phase2ShadowFixtureRunSpec(
                run_id="brca1-run-2",
                checkpoint_keys=("after_pubmed_discovery",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="CFTR",
        objective="Investigate CFTR and cystic fibrosis.",
        seed_terms=("CFTR", "cystic fibrosis"),
        title="CFTR cystic fibrosis shadow fixture",
        enabled_sources=("pubmed", "clinvar", "drugbank"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="cftr-run-1",
                checkpoint_keys=("after_pubmed_ingest_extract",),
            ),
            Phase2ShadowFixtureRunSpec(
                run_id="cftr-run-2",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="MED13",
        objective="Investigate MED13 and congenital heart disease.",
        seed_terms=("MED13", "congenital heart disease"),
        title="MED13 congenital heart disease shadow fixture",
        enabled_sources=("pubmed", "clinvar", "marrvel", "mgi", "zfin"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="med13-run-1",
                checkpoint_keys=("before_first_action", "before_brief_generation"),
            ),
            Phase2ShadowFixtureRunSpec(
                run_id="med13-run-2",
                checkpoint_keys=("before_terminal_stop",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="PCSK9",
        objective="Investigate PCSK9 drug repurposing and lipid metabolism.",
        seed_terms=("PCSK9", "lipid metabolism"),
        title="PCSK9 lipid metabolism shadow fixture",
        enabled_sources=("pubmed", "drugbank", "clinical_trials"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="pcsk9-run-1",
                checkpoint_keys=("after_driven_terms_ready",),
            ),
            Phase2ShadowFixtureRunSpec(
                run_id="pcsk9-run-2",
                checkpoint_keys=("before_terminal_stop",),
            ),
        ),
    ),
)

SUPPLEMENTAL_PHASE2_SHADOW_FIXTURE_SPECS: tuple[Phase2ShadowFixtureSpec, ...] = (
    Phase2ShadowFixtureSpec(
        fixture_name="SUPPLEMENTAL_CHASE_SELECTION",
        objective="Investigate CFTR and cystic fibrosis.",
        seed_terms=("CFTR", "cystic fibrosis"),
        title="Supplemental guarded chase-selection fixture",
        enabled_sources=("pubmed", "clinvar", "drugbank"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="supplemental-chase-run-1",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="SUPPLEMENTAL_CHASE_STOP",
        objective="Investigate MED13 and congenital heart disease.",
        seed_terms=("MED13", "congenital heart disease"),
        title="Supplemental guarded chase-stop fixture",
        enabled_sources=("pubmed", "clinvar", "marrvel", "mgi", "zfin"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="supplemental-chase-stop-run-1",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="SUPPLEMENTAL_BOUNDED_CHASE_CONTINUE",
        objective="Investigate BRCA1 and PARP inhibitor response.",
        seed_terms=("BRCA1", "PARP inhibitor"),
        title="Supplemental guarded bounded-chase continuation fixture",
        enabled_sources=("pubmed", "clinvar", "drugbank", "alphafold"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="supplemental-bounded-chase-run-1",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    ),
    Phase2ShadowFixtureSpec(
        fixture_name="SUPPLEMENTAL_LABEL_FILTERING",
        objective="Investigate BRCA1 and PARP inhibitor response.",
        seed_terms=("BRCA1", "PARP inhibitor"),
        title="Supplemental guarded label-filtering fixture",
        enabled_sources=("pubmed", "clinvar", "drugbank", "alphafold"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="supplemental-label-filtering-run-1",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    ),
)

DEFAULT_PHASE2_SHADOW_FIXTURE_SPECS = DEFAULT_PHASE2_SHADOW_OBJECTIVE_FIXTURE_SPECS


def default_phase2_shadow_fixture_specs() -> tuple[Phase2ShadowFixtureSpec, ...]:
    return DEFAULT_PHASE2_SHADOW_FIXTURE_SPECS


def supplemental_phase2_shadow_fixture_specs() -> tuple[Phase2ShadowFixtureSpec, ...]:
    return SUPPLEMENTAL_PHASE2_SHADOW_FIXTURE_SPECS


def phase2_shadow_fixture_specs_for_set(
    fixture_set: Phase2ShadowFixtureSet = "objective",
) -> tuple[Phase2ShadowFixtureSpec, ...]:
    if fixture_set == "objective":
        return DEFAULT_PHASE2_SHADOW_OBJECTIVE_FIXTURE_SPECS
    if fixture_set == "supplemental":
        return SUPPLEMENTAL_PHASE2_SHADOW_FIXTURE_SPECS
    if fixture_set == "all":
        return (
            *DEFAULT_PHASE2_SHADOW_OBJECTIVE_FIXTURE_SPECS,
            *SUPPLEMENTAL_PHASE2_SHADOW_FIXTURE_SPECS,
        )
    msg = f"Unknown Phase 2 shadow fixture set: {fixture_set}"
    raise ValueError(msg)


def fixture_request_from_spec(spec: Phase2ShadowFixtureSpec) -> Phase1CompareRequest:
    return Phase1CompareRequest(
        objective=spec.objective,
        seed_terms=spec.seed_terms,
        title=spec.title,
        sources=build_phase1_source_preferences(list(spec.enabled_sources)),
        max_depth=spec.max_depth,
        max_hypotheses=spec.max_hypotheses,
    )


def build_fixture_bundle(
    *,
    spec: Phase2ShadowFixtureSpec,
    compare_payloads_by_run_id: dict[str, JSONObject],
) -> JSONObject:
    runs: list[JSONObject] = []
    for run_spec in spec.runs:
        compare_payload = compare_payloads_by_run_id.get(run_spec.run_id)
        if compare_payload is None:
            msg = (
                f"Missing compare payload for fixture {spec.fixture_name} run "
                f"{run_spec.run_id}"
            )
            raise KeyError(msg)
        runs.append(
            _build_fixture_run(
                spec=spec,
                run_spec=run_spec,
                compare_payload=compare_payload,
            ),
        )
    return {
        "fixture_name": spec.fixture_name,
        "runs": runs,
    }


def write_fixture_bundle(
    *,
    fixture_bundle: JSONObject,
    output_path: str | Path,
) -> Path:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(fixture_bundle, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_file


def resolve_fixture_output_path(
    *,
    spec: Phase2ShadowFixtureSpec,
    fixture_dir: str | Path = DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
) -> Path:
    fixture_dir_path = Path(fixture_dir)
    return fixture_dir_path / spec.fixture_filename


def _build_fixture_run(
    *,
    spec: Phase2ShadowFixtureSpec,
    run_spec: Phase2ShadowFixtureRunSpec,
    compare_payload: JSONObject,
) -> JSONObject:
    orchestrator_payload = _dict_value(compare_payload.get("orchestrator"))
    timeline_payload = _dict_value(orchestrator_payload.get("shadow_planner_timeline"))
    timeline_entries = _list_of_dicts(timeline_payload.get("checkpoints"))
    timeline_by_checkpoint = {
        str(entry.get("checkpoint_key")): entry
        for entry in timeline_entries
        if isinstance(entry.get("checkpoint_key"), str)
    }
    step_key_to_round_number = _decision_round_by_step_key(
        orchestrator_payload.get("decision_history"),
    )
    baseline_payload = _dict_value(compare_payload.get("baseline"))
    environment_payload = _dict_value(compare_payload.get("environment"))
    checkpoints: list[JSONObject] = []

    for checkpoint_key in run_spec.checkpoint_keys:
        checkpoint_entry = timeline_by_checkpoint.get(checkpoint_key)
        if checkpoint_entry is None:
            msg = (
                f"Missing checkpoint {checkpoint_key!r} in compare payload for "
                f"{spec.fixture_name}/{run_spec.run_id}"
            )
            raise ValueError(msg)
        comparison_payload = _dict_value(checkpoint_entry.get("comparison"))
        target_action_type = comparison_payload.get("target_action_type")
        target_step_key = _maybe_string(comparison_payload.get("target_step_key"))
        if not isinstance(target_action_type, str) or target_step_key is None:
            msg = (
                f"Checkpoint {checkpoint_key!r} does not expose a deterministic "
                f"target in compare payload for {spec.fixture_name}/{run_spec.run_id}"
            )
            raise ValueError(msg)
        deterministic_target: JSONObject = {
            "action_type": target_action_type,
            "round_number": step_key_to_round_number.get(target_step_key, 0),
            "step_key": target_step_key,
        }
        target_source_key = comparison_payload.get("target_source_key")
        if isinstance(target_source_key, str):
            deterministic_target["source_key"] = target_source_key
        checkpoints.append(
            {
                "checkpoint_key": checkpoint_key,
                "workspace_summary": _checkpoint_workspace_summary(
                    checkpoint_key=checkpoint_key,
                    checkpoint_entry=checkpoint_entry,
                    comparison_payload=comparison_payload,
                ),
                "deterministic_target": deterministic_target,
            },
        )

    deterministic_baseline: JSONObject = {
        "run_id": baseline_payload.get("run_id"),
        "status": baseline_payload.get("status"),
        "telemetry": _dict_value(baseline_payload.get("telemetry")),
        "telemetry_run_ids": _string_list(baseline_payload.get("telemetry_run_ids")),
        "cost_comparison": _dict_value(compare_payload.get("cost_comparison")),
        "environment": environment_payload,
    }

    return {
        "run_id": run_spec.run_id,
        "objective": spec.objective,
        "sources": _enabled_sources_payload(spec.enabled_sources),
        "deterministic_baseline": deterministic_baseline,
        "checkpoints": checkpoints,
    }


def _decision_round_by_step_key(decision_history_payload: object) -> dict[str, int]:
    history = _dict_value(decision_history_payload)
    decisions = history.get("decisions")
    if not isinstance(decisions, list):
        return {}
    step_key_to_round: dict[str, int] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        step_key = decision.get("step_key")
        round_number = decision.get("round_number")
        if isinstance(step_key, str) and isinstance(round_number, int):
            step_key_to_round[step_key] = round_number
    return step_key_to_round


def _enabled_sources_payload(enabled_sources: tuple[str, ...]) -> JSONObject:
    return dict.fromkeys(enabled_sources, True)


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _maybe_string(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _checkpoint_workspace_summary(
    *,
    checkpoint_key: str,
    checkpoint_entry: JSONObject,
    comparison_payload: JSONObject,
) -> JSONObject:
    workspace_summary = _dict_value(checkpoint_entry.get("workspace_summary"))
    if checkpoint_key not in {"after_bootstrap", "after_chase_round_1"}:
        return workspace_summary
    if isinstance(workspace_summary.get("deterministic_selection"), dict):
        return workspace_summary

    deterministic_selected_entity_ids = _string_list(
        comparison_payload.get("deterministic_selected_entity_ids")
    )
    deterministic_selected_labels = _string_list(
        comparison_payload.get("deterministic_selected_labels")
    )
    deterministic_stop_expected = comparison_payload.get("deterministic_stop_expected")
    if not isinstance(deterministic_stop_expected, bool):
        deterministic_stop_expected = False
    if (
        not deterministic_selected_entity_ids
        and not deterministic_selected_labels
        and deterministic_stop_expected is False
    ):
        return workspace_summary

    enriched_summary = dict(workspace_summary)
    enriched_summary["deterministic_selection"] = {
        "selected_entity_ids": deterministic_selected_entity_ids,
        "selected_labels": deterministic_selected_labels,
        "stop_instead": deterministic_stop_expected,
        "stop_reason": ("threshold_not_met" if deterministic_stop_expected else None),
        "selection_basis": (
            "Recovered deterministic chase selection from the compare payload."
        ),
    }
    enriched_summary.setdefault(
        "deterministic_candidate_count",
        len(deterministic_selected_entity_ids),
    )
    enriched_summary.setdefault(
        "deterministic_threshold_met",
        not deterministic_stop_expected,
    )
    return enriched_summary


__all__ = [
    "DEFAULT_PHASE2_SHADOW_OBJECTIVE_FIXTURE_SPECS",
    "DEFAULT_PHASE2_SHADOW_FIXTURE_SPECS",
    "Phase2ShadowFixtureSet",
    "Phase2ShadowFixtureRunSpec",
    "Phase2ShadowFixtureSpec",
    "SUPPLEMENTAL_PHASE2_SHADOW_FIXTURE_SPECS",
    "build_fixture_bundle",
    "default_phase2_shadow_fixture_specs",
    "fixture_request_from_spec",
    "phase2_shadow_fixture_specs_for_set",
    "resolve_fixture_output_path",
    "supplemental_phase2_shadow_fixture_specs",
    "write_fixture_bundle",
]
