from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first import (
    linking_diagnostic_runner as runner,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyPaths,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking import (
    EventArgumentDecision,
    EventLinkingOutput,
    EventLinks,
    ParticipantNode,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking_review import (
    SourceOnlyLinkingReview,
)
from scripts.validation.public_gold.staged_event.contracts import SourceEntityType

SENTENCE = "Decrease in c-Myc activity enhances cancer cell sensitivity to vinblastine."


def _execution(output, response_id: str):
    envelope = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id},
            "usage": {"cost_usd": 0.01},
            "budgets": {
                "output_tokens": "PASS",
                "total_tokens": "PASS",
                "latency": "PASS",
                "cost": "PASS",
            },
        },
    )


def _linking() -> EventLinkingOutput:
    return EventLinkingOutput(
        packet_id="staged-linking-diagnostic-v1",
        frozen_event_ids=(
            "evt_decrease_c_myc_activity",
            "evt_cancer_cell_sensitivity",
            "evt_enhances_sensitivity",
        ),
        participants=(
            ParticipantNode(
                participant_id="p-myc",
                entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
                exact_text="c-Myc",
                exact_evidence=SENTENCE,
                explanation="The activity belongs to c-Myc.",
            ),
            ParticipantNode(
                participant_id="p-cell",
                entity_type=SourceEntityType.CELL,
                exact_text="cancer cell",
                exact_evidence=SENTENCE,
                explanation="The cancer cell bears the sensitivity state.",
            ),
            ParticipantNode(
                participant_id="p-drug",
                entity_type=SourceEntityType.SIMPLE_CHEMICAL,
                exact_text="vinblastine",
                exact_evidence=SENTENCE,
                explanation="The sensitivity is to vinblastine.",
            ),
        ),
        event_links=(
            EventLinks(
                event_id="evt_decrease_c_myc_activity",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="p-myc",
                        explanation="c-Myc activity decreases.",
                    ),
                ),
            ),
            EventLinks(
                event_id="evt_cancer_cell_sensitivity",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="p-cell",
                        explanation="The cell has the sensitivity.",
                    ),
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="PARTICIPANT",
                        target_id="p-drug",
                        explanation="The sensitivity is to the drug.",
                    ),
                ),
            ),
            EventLinks(
                event_id="evt_enhances_sensitivity",
                arguments=(
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="EVENT",
                        target_id="evt_decrease_c_myc_activity",
                        explanation="The decrease causes the enhancement.",
                    ),
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="EVENT",
                        target_id="evt_cancer_cell_sensitivity",
                        explanation="The sensitivity state is enhanced.",
                    ),
                ),
            ),
        ),
        root_event_id="evt_enhances_sensitivity",
        structure_assessment="COMPLETE",
        structure_explanation="The outer event links the two nested events.",
    )


def _paths(root: Path, name: str) -> StageCustodyPaths:
    return StageCustodyPaths(
        bundle=root / f"{name}-custody.json",
        receipt=root / f"{name}-receipt.json",
        raw_output=root / f"{name}-raw.json",
    )


def test_fake_provider_runs_only_linking_and_review_without_gold_leakage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = tmp_path / "source.txt"
    source_path.write_text(SENTENCE + " " * (222 - len(SENTENCE)))
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}")
    result_path = tmp_path / "result.json"
    linking_paths = _paths(tmp_path, "linking")
    review_paths = _paths(tmp_path, "review")
    monkeypatch.setattr(runner, "SOURCE", source_path)
    monkeypatch.setattr(runner, "PREREGISTRATION", preregistration)
    monkeypatch.setattr(runner, "RESULT", result_path)
    monkeypatch.setattr(runner, "LINKING_ATTEMPT", tmp_path / "linking-attempt.json")
    monkeypatch.setattr(runner, "REVIEW_ATTEMPT", tmp_path / "review-attempt.json")
    monkeypatch.setattr(runner, "LINKING_CUSTODY", linking_paths)
    monkeypatch.setattr(runner, "REVIEW_CUSTODY", review_paths)
    monkeypatch.setattr(
        runner,
        "_load_and_verify_preregistration",
        lambda _replay: {
            "review_prompt_sha256": hashlib.sha256(
                runner.REVIEW_PROMPT.read_bytes()
            ).hexdigest()
        },
    )
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    calls: list[str] = []

    def linking_call(_key: str, provider_input: str, _hash: str):
        calls.append("linking")
        assert "public gold" not in provider_input.lower()
        assert "expected participant" not in provider_input.lower()
        assert "evt_cancer_cell_sensitivity" in provider_input
        return _execution(_linking(), "resp-linking")

    def review_call(_key: str, provider_input: str, _hash: str):
        calls.append("review")
        assert "public gold" not in provider_input.lower()
        return _execution(
            SourceOnlyLinkingReview(
                verdict="SUPPORTED",
                exact_evidence=SENTENCE,
                explanation="The complete nested structure is source-supported.",
            ),
            "resp-review",
        )

    decision = runner.execute(
        runner.DiagnosticRuntime(linking_call, review_call, lambda: None, lambda: None)
    )

    assert decision == "ADVANCE_STAGED_LINKING_DIAGNOSTIC"
    assert calls == ["linking", "review"]
    assert linking_paths.bundle.exists()
    assert review_paths.bundle.exists()
    result = json.loads(result_path.read_text())
    assert result["graph_comparison"]["exact"] is True
    assert result["graph_writes"] == 0
    assert result["trusted_promotion"] is False


def test_linking_input_contains_no_exposed_graph_answer() -> None:
    source = runner.SOURCE.read_text(encoding="utf-8")
    packet = runner.linking_input(source, runner.load_diagnostic_inventory())

    forbidden = (
        '"role": "THEME"',
        '"role": "CAUSE"',
        '"target_kind"',
        '"participant_id"',
        '"root_event_id"',
    )
    assert all(item not in packet for item in forbidden)
