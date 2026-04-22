"""Artana-based adapter for extraction relation-policy operations."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.domain.agents.contracts import EvidenceItem
from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_policy_agent_port import (
    ExtractionPolicyAgentPort,
)
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.extraction.policy import (
    EXTRACTION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.extraction_policy_context import (
        ExtractionPolicyContext,
    )

logger = logging.getLogger(__name__)

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

OpenAIJSONSchemaModelPort = ArtanaLiteLLMModelPort


class ArtanaExtractionPolicyAdapter(ExtractionPolicyAgentPort):
    """Adapter that executes extraction policy workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for extraction policy execution. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

    async def propose(
        self,
        context: ExtractionPolicyContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionPolicyContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                reason="missing_openai_api_key",
            )

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            external_id=context.document_id,
            extraction_config_version=self._runtime_policy.extraction_config_version,
        )
        self._last_run_id = run_id

        try:
            usage_limits = self._governance.usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id or "extraction_policy",
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            kernel, client, model_port = self._create_runtime()
            result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(context),
                output_schema=ExtractionPolicyContract,
                step_key=f"extraction.policy.{context.source_type.lower()}.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, ExtractionPolicyContract)
                else ExtractionPolicyContract.model_validate(output)
            )
            if contract.agent_run_id is None:
                contract = contract.model_copy(update={"agent_run_id": run_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Extraction policy Artana step failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return self._fallback_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )
        else:
            return contract
        finally:
            if "kernel" in locals() and "model_port" in locals():
                try:
                    await kernel.close()
                finally:
                    await model_port.aclose()

    async def close(self) -> None:
        return

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _create_runtime(
        self,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, ArtanaLiteLLMModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(self._default_model)
        model_port = ArtanaLiteLLMModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="extraction_policy_contract",
        )
        kernel = ArtanaKernel(
            store=self._artana_store or self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        return kernel, client, model_port

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
    def _create_run_id(  # noqa: PLR0913
        *,
        source_type: str,
        research_space_id: str | None = None,
        external_id: str | None = None,
        extraction_config_version: str = "v1",
        model_id: str | None = None,
        document_id: str | None = None,
    ) -> str:
        _ = model_id  # retained for backward-compatible call sites/tests
        resolved_external_id = (external_id or document_id or "").strip() or "unknown"
        return build_deterministic_run_id(
            prefix="extraction_policy",
            research_space_id=research_space_id,
            source_type=source_type,
            external_id=resolved_external_id,
            extraction_config_version=extraction_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _build_input_text(context: ExtractionPolicyContext) -> str:
        serialized_patterns = json.dumps(
            [
                pattern.model_dump(mode="json")
                for pattern in context.unknown_relation_patterns
            ],
            default=str,
        )
        serialized_constraints = json.dumps(context.current_constraints, default=str)
        serialized_relation_types = json.dumps(
            context.existing_relation_types,
            default=str,
        )
        return (
            f"DOCUMENT ID: {context.document_id}\n"
            f"SOURCE TYPE: {context.source_type}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            "UNKNOWN RELATION PATTERNS:\n"
            f"{serialized_patterns}\n\n"
            "CURRENT CONSTRAINTS SNAPSHOT:\n"
            f"{serialized_constraints}\n\n"
            "EXISTING RELATION TYPES:\n"
            f"{serialized_relation_types}\n"
        )

    def _build_prompt(self, context: ExtractionPolicyContext) -> str:
        return (
            f"{EXTRACTION_POLICY_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    def _fallback_contract(
        self,
        context: ExtractionPolicyContext,
        *,
        reason: str,
    ) -> ExtractionPolicyContract:
        return ExtractionPolicyContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=(
                "Policy agent unavailable; deterministic fail-open path should "
                f"continue ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"source_document:{context.document_id}",
                    excerpt=f"Policy proposal unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            source_type=context.source_type,
            document_id=context.document_id,
            unknown_patterns=context.unknown_relation_patterns,
            relation_constraint_proposals=[],
            relation_type_mapping_proposals=[],
            agent_run_id=self._last_run_id,
        )


__all__ = ["ArtanaExtractionPolicyAdapter"]
