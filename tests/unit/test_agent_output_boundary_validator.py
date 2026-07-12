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


def test_registered_wrapper_requires_output_schema(tmp_path: Path) -> None:
    source_path = tmp_path / "missing_output_schema.py"
    source_path.write_text(
        """
async def run(client):
    return await run_single_step_with_policy(
        client,
        schema_id="model_health.probe.v1",
        step_key="unsafe",
    )
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "missing required output_schema" in violations[0].message


def test_registered_wrapper_requires_literal_schema_id(tmp_path: Path) -> None:
    source_path = tmp_path / "dynamic_schema_id.py"
    source_path.write_text(
        """
async def run(client, schema, schema_id):
    return await run_single_step_with_policy(
        client,
        output_schema=schema,
        schema_id=schema_id,
        step_key="unsafe",
    )
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "must use a literal schema_id" in violations[0].message


def test_registered_wrapper_rejects_unknown_schema_id(tmp_path: Path) -> None:
    source_path = tmp_path / "unknown_schema_id.py"
    source_path.write_text(
        """
async def run(client, schema):
    return await run_single_step_with_policy(
        client,
        output_schema=schema,
        schema_id="unknown.agent.v1",
        step_key="unsafe",
    )
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "uses unknown schema_id" in violations[0].message


def test_unstructured_direct_agent_step_is_rejected(tmp_path: Path) -> None:
    source_path = tmp_path / "unstructured_agent.py"
    source_path.write_text(
        """
async def run(client):
    return await client.step(prompt="return prose")
""",
        encoding="utf-8",
    )

    violations = find_agent_output_boundary_violations((source_path,))

    assert len(violations) == 1
    assert "bypasses the registered agent-output wrapper" in violations[0].message
