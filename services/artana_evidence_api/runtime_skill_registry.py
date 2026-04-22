"""Filesystem-backed runtime skill registry for graph-harness agents."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from artana_evidence_api.tool_catalog import list_graph_harness_tool_specs

if TYPE_CHECKING:
    from collections.abc import Iterable

_SKILL_FILE_NAME = "SKILL.md"
_FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True, slots=True)
class RuntimeSkillDefinition:
    """One filesystem-backed runtime skill."""

    name: str
    version: str
    summary: str
    instructions: str
    tool_names: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    source_path: Path


@dataclass(frozen=True, slots=True)
class GraphHarnessSkillRegistry:
    """Loaded graph-harness runtime skills."""

    root_path: Path
    skill_definitions: tuple[RuntimeSkillDefinition, ...]

    def get(self, skill_name: str) -> RuntimeSkillDefinition | None:
        """Return one skill definition by name."""
        normalized = skill_name.strip()
        if normalized == "":
            return None
        for skill in self.skill_definitions:
            if skill.name == normalized:
                return skill
        return None

    def require(self, skill_name: str) -> RuntimeSkillDefinition:
        """Return one skill definition or raise for unknown names."""
        skill = self.get(skill_name)
        if skill is None:
            msg = f"Unknown graph-harness runtime skill {skill_name!r}."
            raise KeyError(msg)
        return skill

    def summaries_for(
        self,
        *,
        allowed_skill_names: Iterable[str],
        active_skill_names: Iterable[str] = (),
        tenant_capabilities: frozenset[str] = frozenset(),
    ) -> dict[str, str]:
        """Return loadable skill summaries for the current turn."""
        active_names = {
            skill_name.strip()
            for skill_name in active_skill_names
            if skill_name.strip() != ""
        }
        summaries: dict[str, str] = {}
        for raw_name in allowed_skill_names:
            normalized = raw_name.strip()
            if normalized == "" or normalized in active_names:
                continue
            skill = self.get(normalized)
            if skill is None:
                continue
            if not self._capabilities_allow(
                skill=skill,
                tenant_capabilities=tenant_capabilities,
            ):
                continue
            summaries[skill.name] = skill.summary
        return summaries

    def tool_names_for(
        self,
        *,
        active_skill_names: Iterable[str],
        tenant_capabilities: frozenset[str] = frozenset(),
    ) -> set[str]:
        """Return the union of bundled tool names for the active skills."""
        tool_names: set[str] = set()
        for raw_name in active_skill_names:
            skill = self.get(raw_name)
            if skill is None:
                continue
            if not self._capabilities_allow(
                skill=skill,
                tenant_capabilities=tenant_capabilities,
            ):
                continue
            tool_names.update(skill.tool_names)
        return tool_names

    def instruction_panel(self, *, active_skill_names: Iterable[str]) -> str | None:
        """Return the merged instructions for the active skills."""
        blocks: list[str] = []
        for raw_name in active_skill_names:
            skill = self.get(raw_name)
            if skill is None:
                continue
            tool_block = ", ".join(skill.tool_names) if skill.tool_names else "(none)"
            blocks.append(
                "\n".join(
                    (
                        f"[SKILL: {skill.name}]",
                        f"Summary: {skill.summary}",
                        f"Bundled tools: {tool_block}",
                        skill.instructions,
                    ),
                ),
            )
        if not blocks:
            return None
        return "\n\n".join(blocks)

    @staticmethod
    def _capabilities_allow(
        *,
        skill: RuntimeSkillDefinition,
        tenant_capabilities: frozenset[str],
    ) -> bool:
        if not skill.required_capabilities:
            return True
        return all(
            capability in tenant_capabilities
            for capability in skill.required_capabilities
        )


def graph_harness_runtime_skill_root() -> Path:
    """Return the packaged runtime skill root for graph-harness."""
    return Path(__file__).resolve().parent / "runtime_skills"


@lru_cache(maxsize=1)
def load_graph_harness_skill_registry() -> GraphHarnessSkillRegistry:
    """Load the packaged runtime skill tree."""
    root_path = graph_harness_runtime_skill_root()
    skill_files = sorted(root_path.rglob(_SKILL_FILE_NAME))
    definitions = tuple(_load_skill_definition(path) for path in skill_files)
    return GraphHarnessSkillRegistry(
        root_path=root_path,
        skill_definitions=definitions,
    )


def reset_graph_harness_skill_registry_cache() -> None:
    """Clear the cached packaged runtime skill registry."""
    load_graph_harness_skill_registry.cache_clear()


def validate_graph_harness_skill_configuration() -> GraphHarnessSkillRegistry:
    """Fail fast when runtime skill assets or harness declarations are invalid."""
    registry = load_graph_harness_skill_registry()
    names_seen: set[str] = set()
    catalog_names = {spec.name for spec in list_graph_harness_tool_specs()}
    for skill in registry.skill_definitions:
        if skill.name in names_seen:
            msg = f"Duplicate graph-harness runtime skill name {skill.name!r}."
            raise ValueError(msg)
        names_seen.add(skill.name)
        missing_tool_names = [
            tool_name
            for tool_name in skill.tool_names
            if tool_name not in catalog_names
        ]
        if missing_tool_names:
            joined = ", ".join(sorted(missing_tool_names))
            msg = f"Runtime skill {skill.name!r} declares unknown bundled tools: {joined}."
            raise ValueError(msg)

    from artana_evidence_api.harness_registry import list_harness_templates

    registry_names = {skill.name for skill in registry.skill_definitions}
    for harness in list_harness_templates():
        allowed_names = set(harness.allowed_skill_names)
        preloaded_names = set(harness.preloaded_skill_names)
        unknown_allowed = sorted(allowed_names - registry_names)
        if unknown_allowed:
            msg = (
                f"Harness {harness.id!r} declares unknown allowed skills: "
                f"{', '.join(unknown_allowed)}."
            )
            raise ValueError(msg)
        if not preloaded_names.issubset(allowed_names):
            missing = sorted(preloaded_names - allowed_names)
            msg = (
                f"Harness {harness.id!r} preloads skills missing from its allowlist: "
                f"{', '.join(missing)}."
            )
            raise ValueError(msg)
    return registry


def _load_skill_definition(path: Path) -> RuntimeSkillDefinition:
    content = path.read_text(encoding="utf-8")
    frontmatter, instructions = _split_frontmatter(path=path, content=content)
    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict):
        msg = f"Runtime skill file {path} frontmatter must be a YAML object."
        raise TypeError(msg)
    name = _required_string(metadata, key="name", path=path)
    version = _required_string(metadata, key="version", path=path)
    summary = _required_string(metadata, key="summary", path=path)
    tool_names = _string_sequence(metadata.get("tools"), key="tools", path=path)
    required_capabilities = _string_sequence(
        metadata.get("requires_capabilities"),
        key="requires_capabilities",
        path=path,
    )
    normalized_instructions = instructions.strip()
    if normalized_instructions == "":
        msg = f"Runtime skill file {path} must include non-empty instructions."
        raise ValueError(msg)
    return RuntimeSkillDefinition(
        name=name,
        version=version,
        summary=summary,
        instructions=normalized_instructions,
        tool_names=tool_names,
        required_capabilities=required_capabilities,
        source_path=path,
    )


def _split_frontmatter(*, path: Path, content: str) -> tuple[str, str]:
    if not content.startswith(f"{_FRONTMATTER_DELIMITER}\n"):
        msg = f"Runtime skill file {path} must start with YAML frontmatter."
        raise ValueError(msg)
    _, _, remainder = content.partition(f"{_FRONTMATTER_DELIMITER}\n")
    marker = f"\n{_FRONTMATTER_DELIMITER}\n"
    if marker not in remainder:
        msg = (
            f"Runtime skill file {path} must terminate YAML frontmatter with "
            f"{_FRONTMATTER_DELIMITER!r}."
        )
        raise ValueError(msg)
    frontmatter, _, instructions = remainder.partition(marker)
    return frontmatter, instructions


def _required_string(metadata: dict[str, object], *, key: str, path: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or value.strip() == "":
        msg = f"Runtime skill file {path} must define non-empty {key!r}."
        raise ValueError(msg)
    return value.strip()


def _string_sequence(
    value: object,
    *,
    key: str,
    path: Path,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"Runtime skill file {path} must define {key!r} as a list."
        raise TypeError(msg)
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str) or entry.strip() == "":
            msg = f"Runtime skill file {path} contains an invalid {key!r} entry."
            raise ValueError(msg)
        item = entry.strip()
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


__all__ = [
    "GraphHarnessSkillRegistry",
    "RuntimeSkillDefinition",
    "graph_harness_runtime_skill_root",
    "load_graph_harness_skill_registry",
    "reset_graph_harness_skill_registry_cache",
    "validate_graph_harness_skill_configuration",
]
