"""Unit tests for graph-harness runtime skill registry validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from artana_evidence_api.harness_registry import HarnessTemplate
from artana_evidence_api.runtime_skill_registry import (
    GraphHarnessSkillRegistry,
    RuntimeSkillDefinition,
    _load_skill_definition,
    load_graph_harness_skill_registry,
    reset_graph_harness_skill_registry_cache,
    validate_graph_harness_skill_configuration,
)


def _skill_definition(
    *,
    name: str,
    tool_names: tuple[str, ...] = (),
) -> RuntimeSkillDefinition:
    return RuntimeSkillDefinition(
        name=name,
        version="1.0.0",
        summary=f"Summary for {name}",
        instructions=f"Instructions for {name}",
        tool_names=tool_names,
        required_capabilities=(),
        source_path=Path(f"/tmp/{name}/SKILL.md"),
    )


def test_load_graph_harness_skill_registry_loads_packaged_tree() -> None:
    reset_graph_harness_skill_registry_cache()
    registry = load_graph_harness_skill_registry()

    assert registry.root_path.name == "runtime_skills"
    assert registry.get("graph_harness.graph_grounding") is not None
    assert registry.get("graph_harness.ai_full_mode") is not None
    assert registry.get("graph_harness.supervisor_coordination") is not None


def test_load_skill_definition_rejects_invalid_frontmatter(tmp_path: Path) -> None:
    skill_file = tmp_path / "invalid" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "name: invalid\nversion: 1.0.0\nsummary: missing frontmatter delimiters",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="YAML frontmatter"):
        _load_skill_definition(skill_file)


def test_validate_graph_harness_skill_configuration_rejects_duplicate_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = GraphHarnessSkillRegistry(
        root_path=Path("/tmp/runtime_skills"),
        skill_definitions=(
            _skill_definition(name="graph_harness.duplicate"),
            _skill_definition(name="graph_harness.duplicate"),
        ),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "artana_evidence_api.harness_registry.list_harness_templates",
        lambda: (),
    )

    with pytest.raises(ValueError, match="Duplicate graph-harness runtime skill name"):
        validate_graph_harness_skill_configuration()


def test_validate_graph_harness_skill_configuration_rejects_unknown_bundled_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = GraphHarnessSkillRegistry(
        root_path=Path("/tmp/runtime_skills"),
        skill_definitions=(
            _skill_definition(
                name="graph_harness.bad_tool",
                tool_names=("missing_tool",),
            ),
        ),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "artana_evidence_api.harness_registry.list_harness_templates",
        lambda: (),
    )

    with pytest.raises(ValueError, match="unknown bundled tools"):
        validate_graph_harness_skill_configuration()


def test_validate_graph_harness_skill_configuration_rejects_unknown_harness_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = GraphHarnessSkillRegistry(
        root_path=Path("/tmp/runtime_skills"),
        skill_definitions=(_skill_definition(name="graph_harness.graph_grounding"),),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "artana_evidence_api.harness_registry.list_harness_templates",
        lambda: (
            HarnessTemplate(
                id="graph-search",
                display_name="Graph Search",
                summary="Synthetic test harness",
                tool_groups=("graph-read",),
                outputs=("graph-search-result",),
                preloaded_skill_names=("graph_harness.graph_grounding",),
                allowed_skill_names=(
                    "graph_harness.graph_grounding",
                    "graph_harness.unknown",
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="declares unknown allowed skills"):
        validate_graph_harness_skill_configuration()


def test_validate_graph_harness_skill_configuration_rejects_preloaded_skill_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = GraphHarnessSkillRegistry(
        root_path=Path("/tmp/runtime_skills"),
        skill_definitions=(_skill_definition(name="graph_harness.graph_grounding"),),
    )
    monkeypatch.setattr(
        "artana_evidence_api.runtime_skill_registry.load_graph_harness_skill_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "artana_evidence_api.harness_registry.list_harness_templates",
        lambda: (
            HarnessTemplate(
                id="graph-search",
                display_name="Graph Search",
                summary="Synthetic test harness",
                tool_groups=("graph-read",),
                outputs=("graph-search-result",),
                preloaded_skill_names=("graph_harness.graph_grounding",),
                allowed_skill_names=(),
            ),
        ),
    )

    with pytest.raises(ValueError, match="preloads skills missing from its allowlist"):
        validate_graph_harness_skill_configuration()
