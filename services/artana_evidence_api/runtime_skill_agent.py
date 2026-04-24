"""Service-local Artana runtime bridge for filesystem-backed graph-harness skills."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypeVar

from artana.agent.autonomous import AutonomousAgent
from artana.agent.context import ContextBuilder
from artana.agent.runtime_tools import RuntimeToolManager
from artana.canonicalization import canonical_json_dumps
from artana.events import ChatMessage
from artana.json_utils import sha256_hex
from artana.models import TenantContext
from artana.ports.tool import ToolExecutionContext
from artana.safety import IntentPlanRecord

if TYPE_CHECKING:
    from collections.abc import Mapping

    from artana.agent.experience import ExperienceStore
    from artana.agent.memory import MemoryStore
    from artana.kernel import ArtanaKernel
    from artana_evidence_api.runtime_skill_registry import (
        GraphHarnessSkillRegistry,
    )
    from artana_evidence_api.runtime_support import ReplayPolicy

OutputT = TypeVar("OutputT")


class GraphHarnessSkillContextBuilder(ContextBuilder):
    """Context builder that exposes filesystem-backed skill instructions."""

    VERSION = "graph_harness.skill_context_builder.v1"

    def __init__(  # noqa: PLR0913
        self,
        *,
        skill_registry: GraphHarnessSkillRegistry,
        preloaded_skill_names: tuple[str, ...],
        identity: str = "You are a helpful autonomous agent.",
        memory_store: MemoryStore | None = None,
        experience_store: ExperienceStore | None = None,
        task_category: str | None = None,
        progressive_skills: bool = True,
        workspace_context_path: str | None = None,
    ) -> None:
        super().__init__(
            identity=identity,
            memory_store=memory_store,
            experience_store=experience_store,
            task_category=task_category,
            progressive_skills=progressive_skills,
            workspace_context_path=workspace_context_path,
        )
        self._skill_registry = skill_registry
        self._preloaded_skill_names = preloaded_skill_names

    async def build_messages(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant: TenantContext,
        short_term_messages: tuple[ChatMessage, ...],
        system_prompt: str,
        active_skills: frozenset[str],
        available_skill_summaries: Mapping[str, str] | None,
        memory_text: str | None,
    ) -> tuple[ChatMessage, ...]:
        merged_active_skills = frozenset(
            {
                *self._preloaded_skill_names,
                *active_skills,
            },
        )
        base_messages = await super().build_messages(
            run_id=run_id,
            tenant=tenant,
            short_term_messages=short_term_messages,
            system_prompt=system_prompt,
            active_skills=merged_active_skills,
            available_skill_summaries=available_skill_summaries,
            memory_text=memory_text,
        )
        if not base_messages:
            return base_messages
        system_message = base_messages[0]
        skill_panel = self._skill_registry.instruction_panel(
            active_skill_names=merged_active_skills,
        )
        if skill_panel is None:
            return base_messages
        system_content = system_message.content or ""
        merged_content = (
            f"{system_content}\n\nRuntime Skill Instructions:\n{skill_panel}"
            if system_content
            else f"Runtime Skill Instructions:\n{skill_panel}"
        )
        return (
            ChatMessage(role="system", content=merged_content),
            *base_messages[1:],
        )


class GraphHarnessSkillRuntimeToolManager(RuntimeToolManager):
    """Runtime tool manager that loads named filesystem skills instead of raw tools."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        kernel: ArtanaKernel,
        memory_store: MemoryStore,
        progressive_skills: bool,
        load_skill_name: str,
        core_memory_append: str,
        core_memory_replace: str,
        core_memory_search: str,
        query_event_history: str,
        record_intent_plan: str,
        skill_registry: GraphHarnessSkillRegistry,
        preloaded_skill_names: tuple[str, ...],
        allowed_skill_names: tuple[str, ...],
    ) -> None:
        super().__init__(
            kernel=kernel,
            memory_store=memory_store,
            progressive_skills=progressive_skills,
            load_skill_name=load_skill_name,
            core_memory_append=core_memory_append,
            core_memory_replace=core_memory_replace,
            core_memory_search=core_memory_search,
            query_event_history=query_event_history,
            record_intent_plan=record_intent_plan,
        )
        self._graph_harness_skill_registry = skill_registry
        self._preloaded_skill_names = preloaded_skill_names
        self._graph_harness_allowed_skill_names = allowed_skill_names
        self._loaded_skill_names_by_run: dict[str, set[str]] = {}

    def ensure_registered(self) -> None:  # noqa: C901
        if self._registered:
            return

        async def load_skill(
            skill_name: str,
            artana_context: ToolExecutionContext,
        ) -> str:
            return self._skill_load_payload(
                run_id=artana_context.run_id,
                skill_name=skill_name,
                tenant_capabilities=artana_context.tenant_capabilities,
            )

        self._register_runtime_tool(
            name=self._load_skill_name,
            function=load_skill,
        )

        async def core_memory_append(
            content: str,
            artana_context: ToolExecutionContext,
        ) -> str:
            await self._memory_store.append(run_id=artana_context.run_id, text=content)
            return json.dumps(
                {"status": "appended", "run_id": artana_context.run_id},
                ensure_ascii=False,
            )

        self._register_runtime_tool(
            name=self._core_memory_append,
            function=core_memory_append,
        )

        async def core_memory_replace(
            content: str,
            artana_context: ToolExecutionContext,
        ) -> str:
            await self._memory_store.replace(
                run_id=artana_context.run_id,
                content=content,
            )
            return json.dumps(
                {"status": "replaced", "run_id": artana_context.run_id},
                ensure_ascii=False,
            )

        self._register_runtime_tool(
            name=self._core_memory_replace,
            function=core_memory_replace,
        )

        async def core_memory_search(
            query: str,
            artana_context: ToolExecutionContext,
        ) -> str:
            return await self._memory_store.search(
                run_id=artana_context.run_id,
                query=query,
            )

        self._register_runtime_tool(
            name=self._core_memory_search,
            function=core_memory_search,
        )

        async def query_event_history(
            limit: int,
            event_type: str,
            artana_context: ToolExecutionContext,
        ) -> str:
            if limit <= 0:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "invalid_limit",
                        "detail": "limit must be >= 1",
                    },
                    ensure_ascii=False,
                )
            tenant_budget = artana_context.tenant_budget_usd_limit
            if tenant_budget is None:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "missing_tenant_budget",
                        "detail": "tenant_budget_usd_limit missing in ToolExecutionContext",
                    },
                    ensure_ascii=False,
                )
            events = await self._kernel.get_events(
                run_id=artana_context.run_id,
                tenant=TenantContext(
                    tenant_id=artana_context.tenant_id,
                    capabilities=artana_context.tenant_capabilities,
                    budget_usd_limit=tenant_budget,
                ),
            )
            normalized_event_type = event_type.strip().lower()
            if normalized_event_type in {"", "*", "all"}:
                filtered_events = list(events)
            else:
                filtered_events = [
                    event
                    for event in events
                    if event.event_type.value == normalized_event_type
                ]
            selected = filtered_events[-limit:]
            return json.dumps(
                {
                    "ok": True,
                    "run_id": artana_context.run_id,
                    "event_type": normalized_event_type or "all",
                    "returned": len(selected),
                    "events": [
                        {
                            "seq": event.seq,
                            "event_id": event.event_id,
                            "event_type": event.event_type.value,
                            "timestamp": event.timestamp.isoformat(),
                            "payload": event.payload.model_dump(mode="json"),
                        }
                        for event in selected
                    ],
                },
                ensure_ascii=False,
            )

        self._register_runtime_tool(
            name=self._query_event_history,
            function=query_event_history,
            requires_capability="self_reflection",
        )

        async def record_intent_plan(  # noqa: PLR0913
            goal: str,
            why: str,
            success_criteria: str,
            assumed_state: str,
            applies_to_tools: list[str] | None,
            intent_id: str | None,
            artana_context: ToolExecutionContext,
        ) -> str:
            payload = {
                "goal": goal,
                "why": why,
                "success_criteria": success_criteria,
                "assumed_state": assumed_state,
                "applies_to_tools": applies_to_tools or [],
            }
            resolved_intent_id = intent_id
            if resolved_intent_id is None:
                resolved_intent_id = sha256_hex(canonical_json_dumps(payload))
            tenant_budget = artana_context.tenant_budget_usd_limit
            if tenant_budget is None:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "missing_tenant_budget",
                        "detail": "tenant_budget_usd_limit missing in ToolExecutionContext",
                    },
                    ensure_ascii=False,
                )
            await self._kernel.record_intent_plan(
                run_id=artana_context.run_id,
                tenant=TenantContext(
                    tenant_id=artana_context.tenant_id,
                    capabilities=artana_context.tenant_capabilities,
                    budget_usd_limit=tenant_budget,
                ),
                intent=IntentPlanRecord(
                    intent_id=resolved_intent_id,
                    goal=goal,
                    why=why,
                    success_criteria=success_criteria,
                    assumed_state=assumed_state,
                    applies_to_tools=tuple(applies_to_tools or []),
                ),
            )
            return json.dumps(
                {"ok": True, "intent_id": resolved_intent_id},
                ensure_ascii=False,
            )

        self._register_runtime_tool(
            name=self._record_intent_plan,
            function=record_intent_plan,
        )

        self._registered = True

    def visible_tool_names(
        self,
        *,
        loaded_skills: set[str],
        tenant_capabilities: frozenset[str],
        active_registry_skills: set[str] | None = None,
    ) -> set[str] | None:
        if not self._progressive_skills:
            return None
        runtime_tools = self._runtime_tool_names()
        active_skill_names = {
            *self._preloaded_skill_names,
            *loaded_skills,
            *(active_registry_skills or set()),
        }
        runtime_tools.update(
            self._graph_harness_skill_registry.tool_names_for(
                active_skill_names=active_skill_names,
                tenant_capabilities=tenant_capabilities,
            ),
        )
        return {
            tool.name
            for tool in self._kernel.list_registered_tools()
            if tool.name in runtime_tools
        }

    def available_skill_summaries(
        self,
        *,
        tenant_capabilities: frozenset[str],
    ) -> dict[str, str]:
        return self._graph_harness_skill_registry.summaries_for(
            allowed_skill_names=self._graph_harness_allowed_skill_names,
            active_skill_names=self._preloaded_skill_names,
            tenant_capabilities=tenant_capabilities,
        )

    def active_skill_names(self, *, run_id: str) -> tuple[str, ...]:
        """Return the skills active for one run."""
        loaded = self._loaded_skill_names_by_run.get(run_id, set())
        return tuple(sorted({*self._preloaded_skill_names, *loaded}))

    def active_skill_records(self, *, run_id: str) -> tuple[tuple[str, str], ...]:
        """Return ordered active skill records as ``(skill_name, source)`` pairs."""
        records: list[tuple[str, str]] = [
            (skill_name, "preloaded") for skill_name in self._preloaded_skill_names
        ]
        loaded = self._loaded_skill_names_by_run.get(run_id, set())
        for skill_name in sorted(loaded):
            if skill_name in self._preloaded_skill_names:
                continue
            records.append((skill_name, "loaded"))
        return tuple(records)

    def _skill_load_payload(
        self,
        *,
        run_id: str,
        skill_name: str,
        tenant_capabilities: frozenset[str],
    ) -> str:
        normalized_name = skill_name.strip()
        available = sorted(
            self._graph_harness_skill_registry.summaries_for(
                allowed_skill_names=self._graph_harness_allowed_skill_names,
                active_skill_names=self.active_skill_names(run_id=run_id),
                tenant_capabilities=tenant_capabilities,
            ).keys(),
        )
        if normalized_name == "":
            return json.dumps(
                {
                    "name": normalized_name,
                    "loaded": False,
                    "error": "unknown_skill",
                    "available": available,
                },
                ensure_ascii=False,
            )
        if normalized_name not in self._graph_harness_allowed_skill_names:
            return json.dumps(
                {
                    "name": normalized_name,
                    "loaded": False,
                    "error": "forbidden_skill",
                    "available": available,
                },
                ensure_ascii=False,
            )
        skill = self._graph_harness_skill_registry.get(normalized_name)
        if skill is None:
            return json.dumps(
                {
                    "name": normalized_name,
                    "loaded": False,
                    "error": "unknown_skill",
                    "available": available,
                },
                ensure_ascii=False,
            )
        if skill.required_capabilities and not all(
            capability in tenant_capabilities
            for capability in skill.required_capabilities
        ):
            return json.dumps(
                {
                    "name": normalized_name,
                    "loaded": False,
                    "error": "forbidden_skill",
                    "available": available,
                },
                ensure_ascii=False,
            )
        if normalized_name not in self._preloaded_skill_names:
            self._loaded_skill_names_by_run.setdefault(run_id, set()).add(
                normalized_name,
            )
        return json.dumps(
            {
                "name": skill.name,
                "loaded": True,
                "summary": skill.summary,
                "tool_names": list(skill.tool_names),
                "required_capabilities": list(skill.required_capabilities),
                "usage_examples": [f'load_skill(skill_name="{skill.name}")'],
            },
            ensure_ascii=False,
        )


class GraphHarnessSkillAutonomousAgent(AutonomousAgent):
    """Autonomous agent wrapper with service-local filesystem-backed skills."""

    def __init__(  # noqa: PLR0913
        self,
        kernel: ArtanaKernel,
        *,
        skill_registry: GraphHarnessSkillRegistry,
        preloaded_skill_names: tuple[str, ...],
        allowed_skill_names: tuple[str, ...],
        context_builder: GraphHarnessSkillContextBuilder,
        memory_store: MemoryStore | None = None,
        replay_policy: ReplayPolicy = "strict",
    ) -> None:
        super().__init__(
            kernel,
            context_builder=context_builder,
            memory_store=memory_store,
            replay_policy=replay_policy,
        )
        runtime_tools = GraphHarnessSkillRuntimeToolManager(
            kernel=kernel,
            memory_store=self._memory_store,
            progressive_skills=context_builder.progressive_skills,
            load_skill_name=self.LOAD_SKILL_NAME,
            core_memory_append=self.CORE_MEMORY_APPEND,
            core_memory_replace=self.CORE_MEMORY_REPLACE,
            core_memory_search=self.CORE_MEMORY_SEARCH,
            query_event_history=self.QUERY_EVENT_HISTORY,
            record_intent_plan=self.RECORD_INTENT_PLAN,
            skill_registry=skill_registry,
            preloaded_skill_names=preloaded_skill_names,
            allowed_skill_names=allowed_skill_names,
        )
        runtime_tools.ensure_registered()
        self._runtime_tools = runtime_tools
        self._graph_harness_runtime_tools = runtime_tools

    def active_skill_names(self, *, run_id: str) -> tuple[str, ...]:
        """Return active skill names for one completed run."""
        return self._graph_harness_runtime_tools.active_skill_names(run_id=run_id)

    def active_skill_records(self, *, run_id: str) -> tuple[tuple[str, str], ...]:
        """Return active skill records for one completed run."""
        return self._graph_harness_runtime_tools.active_skill_records(run_id=run_id)

    async def emit_active_skill_summary(
        self,
        *,
        run_id: str,
        tenant: TenantContext,
        step_key: str,
    ) -> tuple[str, ...]:
        """Append the active-skill run summary and return the active skill names."""
        active_skill_names = self.active_skill_names(run_id=run_id)
        await self._emit_run_summary(
            run_id=run_id,
            tenant=tenant,
            summary_type="agent_active_skills",
            step_key=step_key,
            payload={"active_skill_names": list(active_skill_names)},
        )
        return active_skill_names


__all__ = [
    "GraphHarnessSkillAutonomousAgent",
    "GraphHarnessSkillContextBuilder",
]
