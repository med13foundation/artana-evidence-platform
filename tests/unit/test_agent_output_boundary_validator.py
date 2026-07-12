"""Tests for the static registered-agent boundary gate."""

from __future__ import annotations

from pathlib import Path

from scripts.ci.validate_agent_output_boundaries import (
    find_agent_output_boundary_violations,
)


def test_repository_model_boundaries_use_registered_wrappers() -> None:
    assert find_agent_output_boundary_violations() == ()


def test_direct_model_call_is_rejected(tmp_path: Path) -> None:
    source_path = tmp_path / "direct_agent.py"
    source_path.write_text(
        """
async def run(agent, schema):
    return await agent.run(
        output_schema=schema,
        prompt="unsafe",
    )
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "bypasses the registered agent-output wrapper" in violations[0].message


def test_registered_wrapper_requires_schema_id(tmp_path: Path) -> None:
    source_path = tmp_path / "missing_schema_id.py"
    source_path.write_text(
        """
async def run(client, schema):
    return await run_single_step_with_policy(
        client,
        output_schema=schema,
        step_key="unsafe",
    )
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "missing required schema_id" in violations[0].message
