"""Artana-backed optional evidence sentence generation harness."""

from __future__ import annotations

import asyncio
import logging
from threading import Thread
from typing import TYPE_CHECKING, Literal

from artana_evidence_db.evidence_sentence_harness_port import (
    EvidenceSentenceHarnessPort,
)
from artana_evidence_db.kernel_domain_models import (
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
)
from pydantic import BaseModel, Field

from src.domain.agents.models import ModelCapability
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
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from artana.store import PostgresStore

_ARTANA_IMPORT_ERROR: Exception | None = None
_THREAD_BRIDGE_TIMEOUT_SECONDS = 90.0
_MIN_SENTENCE_LENGTH = 24
_MAX_SENTENCE_LENGTH = 2000
_MAX_INPUT_TEXT_LENGTH = 6000
_NOISE_MARKERS: tuple[str, ...] = (
    "```",
    "validation:",
    "governance_override:",
)

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

OpenAIJSONSchemaModelPort = ArtanaLiteLLMModelPort


class _EvidenceSentenceContract(BaseModel):
    sentence: str = Field(..., min_length=1, max_length=_MAX_SENTENCE_LENGTH)
    confidence: Literal["low", "medium", "high"] = "low"
    rationale: str = Field(..., min_length=1, max_length=2000)


class ArtanaEvidenceSentenceHarnessAdapter(EvidenceSentenceHarnessPort):
    """Generate non-verbatim review aid sentences for optional relations."""

    def __init__(
        self,
        model: str | None = None,
        *,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for evidence sentence generation. Install "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR
        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._artana_store = artana_store

    def generate(
        self,
        request: EvidenceSentenceGenerationRequest,
        *,
        model_id: str | None = None,
    ) -> EvidenceSentenceGenerationResult:
        if not has_configured_openai_api_key():
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason="openai_api_key_missing",
            )

        run_id = self._create_run_id(request=request, model_id=model_id)
        effective_model = self._resolve_model_id(model_id)
        logger.info(
            "Evidence sentence harness started",
            extra={
                "run_id": run_id,
                "document_id": request.document_id,
                "source_type": request.source_type,
                "relation_type": request.relation_type,
                "model_id": effective_model,
            },
        )

        async def execute() -> _EvidenceSentenceContract:
            kernel, client, model_port = self._create_runtime(model_id=effective_model)
            try:
                return await self._generate_async(
                    request=request,
                    model_id=effective_model,
                    run_id=run_id,
                    client=client,
                )
            finally:
                await model_port.aclose()

        try:
            contract = self._run_contract_coroutine(execute())
        except Exception as exc:  # noqa: BLE001 - fail-open by contract
            logger.warning(
                "Evidence sentence harness failed",
                extra={
                    "run_id": run_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason=f"artana_generation_error:{type(exc).__name__}",
                metadata={"run_id": run_id, "error": str(exc)},
            )

        normalized_sentence = _normalize_sentence(contract.sentence)
        if normalized_sentence is None:
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason="generated_sentence_invalid",
                metadata={"run_id": run_id},
            )
        rationale = contract.rationale.strip()[:2000]
        if not rationale:
            rationale = "Generated from relation extraction context."
        logger.info(
            "Evidence sentence harness finished",
            extra={
                "run_id": run_id,
                "confidence": contract.confidence,
                "sentence_length": len(normalized_sentence),
            },
        )
        return EvidenceSentenceGenerationResult(
            outcome="generated",
            sentence=normalized_sentence,
            source="artana_generated",
            confidence=contract.confidence,
            rationale=rationale,
            metadata={"run_id": run_id, "model_id": effective_model},
        )

    def _create_runtime(
        self,
        *,
        model_id: str,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, ArtanaLiteLLMModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(model_id=model_id)
        model_port = ArtanaLiteLLMModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="evidence_sentence_contract",
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

    def _resolve_timeout_seconds(self, *, model_id: str) -> float:
        try:
            model_spec = self._registry.get_model(model_id)
            return float(model_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        return create_artana_postgres_store()

    @staticmethod
    def _create_tenant(
        *,
        research_space_id: str,
        budget_usd_limit: float,
    ) -> TenantContext:
        return TenantContext(
            tenant_id=f"evidence_sentence:{research_space_id}",
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    async def _generate_async(
        self,
        *,
        request: EvidenceSentenceGenerationRequest,
        model_id: str,
        run_id: str,
        client: SingleStepModelClient,
    ) -> _EvidenceSentenceContract:
        usage_limits = self._governance.usage_limits
        budget_limit = (
            usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
        )
        tenant = self._create_tenant(
            research_space_id=request.research_space_id,
            budget_usd_limit=max(float(budget_limit), 0.01),
        )

        result = await run_single_step_with_policy(
            client,
            run_id=run_id,
            tenant=tenant,
            model=model_id,
            prompt=self._build_input_text(request),
            output_schema=_EvidenceSentenceContract,
            step_key="evidence_sentence.generate.v1",
            replay_policy=self._runtime_policy.replay_policy,
            context_version=self._runtime_policy.to_context_version(),
        )
        output = result.output
        return (
            output
            if isinstance(output, _EvidenceSentenceContract)
            else _EvidenceSentenceContract.model_validate(output)
        )

    @staticmethod
    def _build_input_text(request: EvidenceSentenceGenerationRequest) -> str:
        excerpt = (request.evidence_excerpt or "").strip()
        locator = (request.evidence_locator or "").strip()
        document_text = (request.document_text or "").strip()
        if len(document_text) > _MAX_INPUT_TEXT_LENGTH:
            document_text = document_text[:_MAX_INPUT_TEXT_LENGTH]
        return (
            "You generate ONE concise contextual evidence sentence for relation review.\n"
            "Rules:\n"
            "1) Do not quote verbatim unless explicitly provided by EVIDENCE_EXCERPT.\n"
            "2) Do not fabricate document citations, PMIDs, or section claims.\n"
            "3) Keep sentence plain, no markdown, no JSON, no prefixes.\n"
            "4) Mention both source and target labels when possible.\n"
            "5) Keep output sentence factual and conservative.\n\n"
            "Context:\n"
            f"- source_type: {request.source_type}\n"
            f"- relation_type: {request.relation_type}\n"
            f"- source_label: {request.source_label or 'unknown'}\n"
            f"- target_label: {request.target_label or 'unknown'}\n"
            f"- evidence_summary: {request.evidence_summary}\n"
            f"- evidence_excerpt: {excerpt or 'none'}\n"
            f"- evidence_locator: {locator or 'none'}\n"
            f"- document_text_window: {document_text or 'none'}\n"
        )

    def _create_run_id(
        self,
        *,
        request: EvidenceSentenceGenerationRequest,
        model_id: str | None,
    ) -> str:
        payload = "|".join(
            [
                request.research_space_id.strip(),
                request.source_type.strip().lower(),
                request.relation_type.strip().upper(),
                (request.source_label or "").strip().lower(),
                (request.target_label or "").strip().lower(),
                (request.document_id or "").strip(),
                (request.run_id or "").strip(),
                (model_id or self._default_model or "").strip(),
                request.evidence_summary.strip()[:256],
            ],
        )
        digest = stable_sha256_digest(payload)
        return f"evidence_sentence:{digest}"

    @staticmethod
    def _run_contract_coroutine(
        coroutine: Coroutine[object, object, _EvidenceSentenceContract],
    ) -> _EvidenceSentenceContract:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        if not running_loop.is_running():
            return running_loop.run_until_complete(coroutine)

        result_holder: dict[str, _EvidenceSentenceContract] = {}
        error_holder: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result_holder["result"] = asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=_THREAD_BRIDGE_TIMEOUT_SECONDS)
        if thread.is_alive():
            msg = "Evidence sentence generation timed out while bridging event loop."
            raise TimeoutError(msg)
        if "error" in error_holder:
            raise error_holder["error"]
        if "result" not in result_holder:
            msg = "Evidence sentence generation did not return a contract."
            raise RuntimeError(msg)
        return result_holder["result"]


def _normalize_sentence(raw_sentence: str) -> str | None:
    normalized = " ".join(raw_sentence.strip().split())
    if len(normalized) < _MIN_SENTENCE_LENGTH:
        return None
    lowered = normalized.lower()
    if any(marker in lowered for marker in _NOISE_MARKERS):
        return None
    if not any(char.isalnum() for char in normalized):
        return None
    return normalized[:_MAX_SENTENCE_LENGTH]


__all__ = ["ArtanaEvidenceSentenceHarnessAdapter"]
