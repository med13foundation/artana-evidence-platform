from __future__ import annotations

from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment import (
    run_target_deepeventmine as runner,
)


def test_runner_is_bound_to_exposed_target_and_one_shot_directory() -> None:
    assert runner.SOURCE.name == "PMID-16428936.txt"
    assert runner.SOURCE_SHA256 == (
        "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
    )
    assert runner.RUN_DIR.name == "target_deepeventmine_pmid_16428936_v1"


def test_runner_never_reads_gold_annotation_extensions() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert ".a1" not in source
    assert ".a2" not in source
    assert "expected_event" not in source
    assert "known_error" not in source


def test_runner_has_fixed_image_timeout_and_no_alternate_generator() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert runner.IMAGE.startswith("sha256:")
    assert runner.TIMEOUT_SECONDS == 900
    assert "PubTator" not in source
    assert "openai" not in source.lower()
    assert "retry" not in source.lower()
