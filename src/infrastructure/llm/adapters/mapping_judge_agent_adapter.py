"""Artana-based adapter for mapping-judge operations."""

from __future__ import annotations

import asyncio
import logging
import time
from contextvars import copy_context
from threading import Thread
from typing import TYPE_CHECKING

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.contracts.mapping_judge_assessment import (
    mapping_judge_assessment_confidence,
)
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
    stable_sha256_digest,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.mapping_judge import MAPPING_JUDGE_SYSTEM_PROMPT
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext

logger = logging.getLogger(__name__)

_ARTANA_IMPORT_ERROR: Exception | None = None
_THREAD_BRIDGE_TIMEOUT_SECONDS = 90.0

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = ArtanaLiteLLMModelPort


class ArtanaMappingJudgeAdapter(MappingJudgePort):
    """Adapter that executes mapping-judge workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for mapping judge execution. Install "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._artana_store = artana_store

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        if not self._has_openai_key():
            msg = "Mapping-judge requires OPENAI_API_KEY for Artana execution."
            raise RuntimeError(msg)

        if not context.candidates:
            msg = "Mapping-judge received no candidates."
            raise ValueError(msg)

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            model_id=effective_model,
            source_id=context.source_id,
            field_key=context.field_key,
            field_value_preview=context.field_value_preview,
            candidate_ids=[candidate.variable_id for candidate in context.candidates],
        )
        logger.info(
            "Mapping judge started",
            extra={
                "run_id": run_id,
                "source_id": context.source_id,
                "field_key": context.field_key,
                "candidate_count": len(context.candidates),
                "model_id": effective_model,
            },
        )

        async def execute() -> MappingJudgeContract:
            kernel, client, model_port = self._create_runtime()
            try:
                return await self._judge_async(
                    context=context,
                    model_id=effective_model,
                    run_id=run_id,
                    client=client,
                )
            finally:
                try:
                    await kernel.close()
                finally:
                    await model_port.aclose()

        contract = self._run_contract_coroutine(execute())
        logger.info(
            "Mapping judge finished",
            extra={
                "run_id": run_id,
                "decision": contract.decision,
                "selected_variable_id": contract.selected_variable_id,
                "candidate_count": contract.candidate_count,
            },
        )
        return contract

    def close(self) -> None:
        return

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _resolve_timeout_seconds(self, model: str | None) -> float:
        if model:
            try:
                model_spec = self._registry.get_model(model)
                return float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                pass
        try:
            default_spec = self._registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        return create_artana_postgres_store()

    def _create_runtime(
        self,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, _OpenAIChatModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(self._default_model)
        model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="mapping_judge_contract",
        )
        kernel = ArtanaKernel(
            store=self._artana_store or self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        return kernel, client, model_port

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and model_id is not None
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.EVIDENCE_EXTRACTION,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        ).model_id

    @staticmethod
    def _create_run_id(
        *,
        model_id: str,
        source_id: str,
        field_key: str,
        field_value_preview: str,
        candidate_ids: list[str],
    ) -> str:
        payload = "|".join(
            [
                model_id,
                source_id,
                field_key.strip(),
                field_value_preview.strip(),
                ",".join(sorted(candidate_ids)),
            ],
        )
        digest = stable_sha256_digest(payload)
        return f"mapping_judge:{digest}"

    @staticmethod
    def _build_input_text(context: MappingJudgeContext) -> str:
        candidate_lines = [
            (
                f"- variable_id={candidate.variable_id}; "
                f"display_name={candidate.display_name}; "
                f"method={candidate.match_method}; "
                f"similarity={candidate.similarity_score:.3f}"
            )
            for candidate in context.candidates
        ]
        candidates_blob = "\n".join(candidate_lines)
        return (
            f"{MAPPING_JUDGE_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"FIELD KEY: {context.field_key}\n"
            f"FIELD VALUE: {context.field_value_preview}\n"
            f"SOURCE ID: {context.source_id}\n"
            f"SOURCE TYPE: {context.source_type or 'unknown'}\n"
            f"DOMAIN CONTEXT: {context.domain_context or 'none'}\n"
            "CANDIDATES:\n"
            f"{candidates_blob}\n"
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    async def _judge_async(
        self,
        *,
        context: MappingJudgeContext,
        model_id: str,
        run_id: str,
        client: SingleStepModelClient,
    ) -> MappingJudgeContract:
        input_text = self._build_input_text(context)
        usage_limits = self._governance.usage_limits
        budget_limit = (
            usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
        )
        tenant = self._create_tenant(
            tenant_id=f"mapping_judge:{context.source_id}",
            budget_usd_limit=max(float(budget_limit), 0.01),
        )

        result = await run_single_step_with_policy(
            client,
            run_id=run_id,
            tenant=tenant,
            model=model_id,
            prompt=input_text,
            output_schema=MappingJudgeContract,
            step_key="mapping.judge.v1",
            replay_policy=self._runtime_policy.replay_policy,
            context_version=self._runtime_policy.to_context_version(),
        )
        output = result.output
        contract = (
            output
            if isinstance(output, MappingJudgeContract)
            else MappingJudgeContract.model_validate(output)
        )
        normalized = self._normalize_contract(contract=contract, context=context)
        if normalized.agent_run_id is None:
            normalized = normalized.model_copy(update={"agent_run_id": run_id})
        return normalized

    def _normalize_contract(
        self,
        *,
        contract: MappingJudgeContract,
        context: MappingJudgeContext,
    ) -> MappingJudgeContract:
        candidate_map = {
            candidate.variable_id: candidate for candidate in context.candidates
        }
        candidate_count = len(context.candidates)

        if contract.decision == "matched":
            selected_id = contract.selected_variable_id
            if selected_id is None or selected_id not in candidate_map:
                msg = (
                    "Mapping-judge selected a variable_id outside provided candidates."
                )
                raise ValueError(msg)
            selected_candidate = candidate_map[selected_id]
            normalized = contract.model_copy(
                update={
                    "candidate_count": candidate_count,
                    "selected_candidate": selected_candidate,
                    "selected_variable_id": selected_id,
                },
            )
            if normalized.assessment is not None:
                normalized = normalized.model_copy(
                    update={
                        "confidence_score": mapping_judge_assessment_confidence(
                            normalized.assessment,
                        ),
                    },
                )
            if normalized.evidence:
                return normalized
            return normalized.model_copy(
                update={
                    "evidence": [
                        EvidenceItem(
                            source_type="note",
                            locator=f"mapping-judge:{context.source_id}:{context.field_key}",
                            excerpt="LLM selected a provided mapping candidate.",
                            relevance=0.5,
                        ),
                    ],
                },
            )

        return contract.model_copy(
            update={
                "candidate_count": candidate_count,
                "selected_variable_id": None,
                "selected_candidate": None,
            },
        )

    @staticmethod
    def _run_contract_coroutine(coroutine: object) -> MappingJudgeContract:
        if not asyncio.iscoroutine(coroutine):
            msg = "Expected coroutine for mapping judge execution."
            raise TypeError(msg)

        async def _typed_coroutine() -> MappingJudgeContract:
            result = await coroutine
            if not isinstance(result, MappingJudgeContract):
                msg = "Mapping judge coroutine returned unexpected result type."
                raise TypeError(msg)
            return result

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("Mapping judge coroutine executing on direct event loop")
            return asyncio.run(_typed_coroutine())

        result_holder: dict[str, MappingJudgeContract | None] = {"result": None}
        error_holder: dict[str, BaseException | None] = {"error": None}
        bridge_started_at = time.monotonic()
        execution_context = copy_context()

        def _target() -> None:
            try:
                result_holder["result"] = execution_context.run(
                    asyncio.run,
                    _typed_coroutine(),
                )
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        logger.debug(
            "Mapping judge coroutine executing via thread bridge",
            extra={"timeout_seconds": _THREAD_BRIDGE_TIMEOUT_SECONDS},
        )
        thread = Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=_THREAD_BRIDGE_TIMEOUT_SECONDS)
        if thread.is_alive():
            msg = (
                "Mapping-judge coroutine bridge timed out while awaiting async "
                "workflow completion."
            )
            logger.error(
                "Mapping judge coroutine bridge timed out",
                extra={"timeout_seconds": _THREAD_BRIDGE_TIMEOUT_SECONDS},
            )
            raise TimeoutError(msg)

        if error_holder["error"] is not None:
            logger.error(
                "Mapping judge coroutine bridge raised exception",
                extra={"error_class": error_holder["error"].__class__.__name__},
            )
            raise error_holder["error"]
        if result_holder["result"] is None:
            msg = "Mapping judge coroutine returned no contract."
            raise RuntimeError(msg)
        logger.debug(
            "Mapping judge coroutine bridge completed",
            extra={
                "duration_ms": int((time.monotonic() - bridge_started_at) * 1000),
            },
        )
        return result_holder["result"]


__all__ = ["ArtanaMappingJudgeAdapter"]
