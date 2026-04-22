"""Service-local Artana adapter for PubMed semantic relevance classification."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from artana_evidence_api.agent_contracts import BaseAgentContract
from artana_evidence_api.runtime_support import (
    GovernanceConfig,
    ModelCapability,
    create_artana_postgres_store,
    get_model_registry,
    has_configured_openai_api_key,
    load_runtime_policy,
    normalize_litellm_model_id,
    stable_sha256_digest,
)
from artana_evidence_api.step_helpers import run_single_step_with_policy
from pydantic import BaseModel, ConfigDict, Field

PUBMED_RELEVANCE_SYSTEM_PROMPT = """
You are the Artana PubMed Relevance Agent.

Mission:
- Read the provided title and abstract.
- Judge semantic relevance to the provided research query/topic.
- Return a valid PubMedRelevanceContract.

Critical constraints:
- Classify only from the supplied title and abstract.
- Do not rely on exact string matching as the main criterion.
- Do not invent external facts or citations.
- Output one label only: relevance="relevant" or relevance="non_relevant".

Decision policy:
- relevant: the paper meaningfully contributes evidence, mechanism, association,
  or context directly aligned with the query/topic.
- non_relevant: the paper is tangential, off-topic, or too weakly related.
- If uncertain, choose non_relevant with lower confidence.

Output quality:
- confidence_score must reflect decision certainty (0.0-1.0).
- rationale must be concise and specific.
- evidence should reference title and/or abstract spans.
""".strip()


class PubMedRelevanceContext(BaseModel):
    """Execution context for one PubMed relevance decision."""

    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=8000)
    abstract: str | None = Field(default=None, max_length=32000)
    domain_context: str | None = Field(default=None, max_length=64)
    pubmed_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PubMedRelevanceContract(BaseAgentContract):
    """Structured output for title/abstract semantic relevance classification."""

    relevance: Literal["relevant", "non_relevant"] = Field(
        ...,
        description="Semantic relevance label for the research topic/query.",
    )
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=4000)
    agent_run_id: str | None = Field(default=None, max_length=128)

    model_config = ConfigDict(use_enum_values=True)


def _build_deterministic_run_id(
    *,
    prefix: str,
    source_type: str,
    external_id: str,
    extraction_config_version: str,
) -> str:
    normalized_prefix = prefix.strip().lower() or "run"
    normalized_source_type = source_type.strip().lower() or "unknown"
    normalized_external_id = external_id.strip() or "unknown"
    normalized_config_version = extraction_config_version.strip() or "v1"
    payload = f"global|{normalized_source_type}|{normalized_external_id}|{normalized_config_version}"
    digest = stable_sha256_digest(payload, length=24)
    return f"{normalized_prefix}:{normalized_source_type}:{digest}"


class ArtanaPubMedRelevanceAdapter:
    """Classify PubMed record relevance by semantic meaning."""

    def __init__(self, model: str | None = None) -> None:
        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def classify(
        self,
        context: PubMedRelevanceContext,
        *,
        model_id: str | None = None,
    ) -> PubMedRelevanceContract:
        if not has_configured_openai_api_key():
            msg = "OPENAI_API_KEY is required for semantic PubMed relevance classification."
            raise RuntimeError(msg)

        from artana.agent import SingleStepModelClient
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter

        resolved_model_id = self._resolve_model_id(model_id)
        execution_model_id = normalize_litellm_model_id(resolved_model_id)
        timeout_seconds = float(
            self._registry.get_model(resolved_model_id).timeout_seconds,
        )
        run_id = self._create_run_id(context=context)
        budget_limit = self._governance.usage_limits.total_cost_usd or 1.0

        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=timeout_seconds),
        )
        try:
            client = SingleStepModelClient(kernel=kernel)
            tenant = TenantContext(
                tenant_id="pubmed_relevance",
                capabilities=frozenset(),
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            step_result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=execution_model_id,
                prompt=self._build_prompt(context),
                output_schema=PubMedRelevanceContract,
                step_key="pubmed.relevance.title_abstract.v1",
                replay_policy=self._runtime_policy.replay_policy,
            )
            output = step_result.output
            contract = (
                output
                if isinstance(output, PubMedRelevanceContract)
                else PubMedRelevanceContract.model_validate(output)
            )
            if contract.agent_run_id is None:
                return contract.model_copy(update={"agent_run_id": run_id})
            return contract
        finally:
            try:
                await kernel.close()
            finally:
                await store.close()

    async def close(self) -> None:
        return None

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            model_id is not None
            and self._registry.allow_runtime_model_overrides()
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.JUDGE,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(ModelCapability.JUDGE).model_id

    def _create_run_id(self, *, context: PubMedRelevanceContext) -> str:
        fingerprint = stable_sha256_digest(
            "|".join(
                [
                    context.query.strip(),
                    (context.title or "").strip(),
                    (context.abstract or "").strip(),
                    (context.domain_context or "").strip(),
                ],
            ),
            length=32,
        )
        return _build_deterministic_run_id(
            prefix="pubmed_relevance",
            source_type=context.source_type,
            external_id=fingerprint,
            extraction_config_version=self._runtime_policy.extraction_config_version,
        )

    @staticmethod
    def _build_prompt(context: PubMedRelevanceContext) -> str:
        input_text = (
            f"SOURCE TYPE: {context.source_type}\n"
            f"QUERY/TOPIC: {context.query}\n"
            f"DOMAIN CONTEXT: {context.domain_context or 'unknown'}\n"
            f"PUBMED ID: {context.pubmed_id or 'unknown'}\n\n"
            "TITLE:\n"
            f"{context.title or ''}\n\n"
            "ABSTRACT:\n"
            f"{context.abstract or ''}\n"
        )
        return (
            f"{PUBMED_RELEVANCE_SYSTEM_PROMPT}\n\n"
            "---\nREQUEST CONTEXT\n---\n"
            f"{input_text}"
        )


__all__ = [
    "ArtanaPubMedRelevanceAdapter",
    "PubMedRelevanceContext",
    "PubMedRelevanceContract",
]
