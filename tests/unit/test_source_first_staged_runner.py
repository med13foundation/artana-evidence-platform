from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    AnchorResolutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyPaths,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
    EventInventoryOutput,
    InventoryEvent,
    compare_exposed_inventory,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking import (
    EventArgumentDecision,
    EventLinkingOutput,
    EventLinks,
    ParticipantNode,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.staged_runner import (
    ProcessingContext,
    StagedRuntime,
    execute,
    process_inventory_execution,
    process_linking_execution,
)
from scripts.validation.public_gold.staged_event.contracts import SourceEntityType

SENTENCE = "Decrease in c-Myc activity enhances cancer cell sensitivity to vinblastine."
SOURCE = SENTENCE + " " * (222 - len(SENTENCE))


def _paths(root: Path, stage: str) -> StageCustodyPaths:
    return StageCustodyPaths(
        bundle=root / f"{stage}-bundle.json",
        receipt=root / f"{stage}-receipt.json",
        raw_output=root / f"{stage}-raw.json",
    )


def _receipt(response_id: str) -> dict[str, object]:
    return {
        "status": "VERIFIED_LIVE",
        "identity": {"response_id": response_id},
        "budgets": {
            "requested_max_output_tokens": 16000,
            "requested_max_total_tokens": 24000,
            "requested_max_latency_seconds": 900.0,
            "requested_max_cost_usd": 0.25,
            "observed_output_tokens": 100,
            "observed_total_tokens": 200,
            "observed_latency_seconds": 1.0,
            "observed_cost_usd": 0.01,
            "output_tokens": "PASS",
            "total_tokens": "PASS",
            "latency": "PASS",
            "cost": "PASS",
        },
    }


def _execution(output, response_id: str):
    envelope = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt=_receipt(response_id),
    )


def _inventory(*, include_sensitivity: bool = True) -> EventInventoryOutput:
    events = [
        InventoryEvent(
            temporary_event_id="event-decrease",
            event_type=SourceEventType.NEGATIVE_REGULATION,
            exact_trigger="Decrease",
            exact_evidence=SENTENCE,
            structural_position="NESTED_EVENT",
            explanation="Decrease event.",
        ),
        InventoryEvent(
            temporary_event_id="event-enhances",
            event_type=SourceEventType.POSITIVE_REGULATION,
            exact_trigger="enhances",
            exact_evidence=SENTENCE,
            structural_position="ROOT_CANDIDATE",
            explanation="Enhancement event.",
        ),
    ]
    if include_sensitivity:
        events.append(
            InventoryEvent(
                temporary_event_id="event-sensitivity",
                event_type=SourceEventType.REGULATION,
                exact_trigger="sensitivity",
                exact_evidence=SENTENCE,
                structural_position="NESTED_EVENT",
                explanation="Sensitivity event-state.",
            )
        )
    return EventInventoryOutput(packet_id="staged-primary-nested-v3", events=tuple(events))


def _linking() -> EventLinkingOutput:
    return EventLinkingOutput(
        packet_id="staged-primary-nested-v3",
        frozen_event_ids=(
            "event-decrease",
            "event-enhances",
            "event-sensitivity",
        ),
        participants=(
            ParticipantNode(
                participant_id="myc",
                entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
                exact_text="c-Myc",
                exact_evidence=SENTENCE,
                explanation="Decreased protein activity.",
            ),
            ParticipantNode(
                participant_id="cell",
                entity_type=SourceEntityType.CELL,
                exact_text="cancer cell",
                exact_evidence=SENTENCE,
                explanation="Sensitive cell.",
            ),
            ParticipantNode(
                participant_id="drug",
                entity_type=SourceEntityType.SIMPLE_CHEMICAL,
                exact_text="vinblastine",
                exact_evidence=SENTENCE,
                explanation="Drug sensitivity cause.",
            ),
        ),
        event_links=(
            EventLinks(
                event_id="event-decrease",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="myc",
                        explanation="c-Myc activity decreases.",
                    ),
                ),
            ),
            EventLinks(
                event_id="event-enhances",
                arguments=(
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="EVENT",
                        target_id="event-decrease",
                        explanation="Decrease causes enhancement.",
                    ),
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="EVENT",
                        target_id="event-sensitivity",
                        explanation="Sensitivity is enhanced.",
                    ),
                ),
            ),
            EventLinks(
                event_id="event-sensitivity",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="cell",
                        explanation="Cell is sensitive.",
                    ),
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="PARTICIPANT",
                        target_id="drug",
                        explanation="Sensitivity is to drug.",
                    ),
                ),
            ),
        ),
        root_event_id="event-enhances",
        structure_assessment="COMPLETE",
        structure_explanation="Complete nested graph.",
    )


def test_inventory_uses_typed_tuple_and_persists_before_processing(tmp_path: Path) -> None:
    paths = _paths(tmp_path, "inventory")

    output, inventory, record = process_inventory_execution(
        _execution(_inventory(), "resp-inventory"),
        provider_input_value="inventory input",
        source=SOURCE,
        custody_paths=paths,
    )

    assert isinstance(output.events, tuple)
    assert compare_exposed_inventory(inventory).passed is True
    assert record.response_id == "resp-inventory"
    assert paths.bundle.exists()
    assert paths.receipt.exists()
    assert paths.raw_output.exists()


def test_crash_after_inventory_persistence_preserves_all_artifacts(tmp_path: Path) -> None:
    paths = _paths(tmp_path, "inventory")

    with pytest.raises(RuntimeError, match="simulated crash"):
        process_inventory_execution(
            _execution(_inventory(), "resp-inventory"),
            provider_input_value="inventory input",
            source=SOURCE,
            custody_paths=paths,
            after_persist=lambda: (_ for _ in ()).throw(RuntimeError("simulated crash")),
        )

    assert paths.bundle.exists()
    assert paths.receipt.exists()
    assert paths.raw_output.exists()


def test_anchor_and_scientific_failures_preserve_inventory_custody(tmp_path: Path) -> None:
    missing = _inventory().model_copy(
        update={
            "events": (
                _inventory().events[0].model_copy(update={"exact_trigger": "absent"}),
            )
        }
    )
    anchor_paths = _paths(tmp_path, "anchor")
    with pytest.raises(AnchorResolutionError):
        process_inventory_execution(
            _execution(missing, "resp-anchor"),
            provider_input_value="inventory input",
            source=SOURCE,
            custody_paths=anchor_paths,
        )
    assert anchor_paths.bundle.exists()

    scientific_paths = _paths(tmp_path, "scientific")
    _, inventory, _ = process_inventory_execution(
        _execution(_inventory(include_sensitivity=False), "resp-scientific"),
        provider_input_value="inventory input",
        source=SOURCE,
        custody_paths=scientific_paths,
    )
    assert compare_exposed_inventory(inventory).passed is False
    assert scientific_paths.bundle.exists()


def test_linking_uses_typed_output_and_crash_preserves_both_stages(tmp_path: Path) -> None:
    inventory_paths = _paths(tmp_path, "inventory")
    _, inventory, _ = process_inventory_execution(
        _execution(_inventory(), "resp-inventory"),
        provider_input_value="inventory input",
        source=SOURCE,
        custody_paths=inventory_paths,
    )
    linking_paths = _paths(tmp_path, "linking")
    with pytest.raises(RuntimeError, match="linking crash"):
        process_linking_execution(
            _execution(_linking(), "resp-linking"),
            provider_input_value="linking input",
            inventory=inventory,
            context=ProcessingContext(
                source=SOURCE,
                custody_paths=linking_paths,
                after_persist=lambda: (_ for _ in ()).throw(
                    RuntimeError("linking crash")
                ),
            ),
        )
    assert inventory_paths.bundle.exists()
    assert linking_paths.bundle.exists()


def test_stage_two_cannot_run_after_failed_inventory_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first import (
        staged_runner,
    )

    source_path = tmp_path / "source.txt"
    source_path.write_text(SOURCE)
    preregistration = tmp_path / "prereg.json"
    preregistration.write_text("{}")
    result = tmp_path / "result.json"
    inventory_paths = _paths(tmp_path, "inventory")
    linking_paths = _paths(tmp_path, "linking")
    monkeypatch.setattr(staged_runner, "SOURCE", source_path)
    monkeypatch.setattr(staged_runner, "REPO", tmp_path)
    monkeypatch.setattr(staged_runner, "PREREGISTRATION", preregistration)
    monkeypatch.setattr(staged_runner, "RESULT", result)
    monkeypatch.setattr(staged_runner, "INVENTORY_CUSTODY", inventory_paths)
    monkeypatch.setattr(staged_runner, "LINKING_CUSTODY", linking_paths)
    monkeypatch.setattr(staged_runner, "INVENTORY_ATTEMPT", tmp_path / "inventory-attempt.json")
    monkeypatch.setattr(staged_runner, "LINKING_ATTEMPT", tmp_path / "linking-attempt.json")
    monkeypatch.setattr(staged_runner, "_load_and_verify_preregistration", dict)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    linking_calls = 0

    def inventory_call(_key: str, _input: str, _hash: str):
        return _execution(_inventory(include_sensitivity=False), "resp-inventory")

    def linking_call(_key: str, _input: str, _hash: str):
        nonlocal linking_calls
        linking_calls += 1
        return _execution(_linking(), "resp-linking")

    decision = execute(
        StagedRuntime(inventory_call, linking_call, lambda: None, lambda: None)
    )

    assert decision == "STOP_EVENT_INVENTORY_SCIENTIFIC_FAILURE"
    assert linking_calls == 0
    assert inventory_paths.bundle.exists()
    assert not linking_paths.bundle.exists()


def test_crash_after_provider_return_reservation_blocks_duplicate_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first import (
        staged_runner,
    )

    source_path = tmp_path / "source.txt"
    source_path.write_text(SOURCE)
    preregistration = tmp_path / "prereg.json"
    preregistration.write_text("{}")
    monkeypatch.setattr(staged_runner, "REPO", tmp_path)
    monkeypatch.setattr(staged_runner, "SOURCE", source_path)
    monkeypatch.setattr(staged_runner, "PREREGISTRATION", preregistration)
    monkeypatch.setattr(staged_runner, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(staged_runner, "INVENTORY_CUSTODY", _paths(tmp_path, "inventory"))
    monkeypatch.setattr(staged_runner, "LINKING_CUSTODY", _paths(tmp_path, "linking"))
    monkeypatch.setattr(staged_runner, "INVENTORY_ATTEMPT", tmp_path / "inventory-attempt.json")
    monkeypatch.setattr(staged_runner, "LINKING_ATTEMPT", tmp_path / "linking-attempt.json")
    monkeypatch.setattr(staged_runner, "_load_and_verify_preregistration", dict)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    inventory_calls = 0

    def inventory_call(_key: str, _input: str, _hash: str):
        nonlocal inventory_calls
        inventory_calls += 1
        return _execution(_inventory(), "resp-inventory")

    runtime = StagedRuntime(
        inventory_call,
        lambda _key, _input, _hash: _execution(_linking(), "resp-linking"),
        lambda: (_ for _ in ()).throw(RuntimeError("post-persistence crash")),
        lambda: None,
    )
    with pytest.raises(RuntimeError, match="post-persistence crash"):
        execute(runtime)
    with pytest.raises(staged_runner.StagedExperimentStateError):
        execute(runtime)

    assert inventory_calls == 1
    assert staged_runner.INVENTORY_ATTEMPT.exists()
    assert staged_runner.INVENTORY_CUSTODY.bundle.exists()
