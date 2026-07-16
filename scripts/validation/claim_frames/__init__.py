"""TG-03 ClaimFrame benchmark and deterministic report helpers."""

from scripts.validation.claim_frames.fixture import (
    DEFAULT_FIXTURE_PATH,
    BenchmarkCase,
    BenchmarkFixture,
    ExpectedFrame,
    ExpectedSourceMeasurement,
    load_fixture,
)
from scripts.validation.claim_frames.metrics import (
    build_run_report,
    compare_three_reports,
    evaluate_case,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkFixture",
    "DEFAULT_FIXTURE_PATH",
    "ExpectedFrame",
    "ExpectedSourceMeasurement",
    "build_run_report",
    "compare_three_reports",
    "evaluate_case",
    "load_fixture",
]
