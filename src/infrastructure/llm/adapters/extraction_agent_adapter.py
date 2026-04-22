"""Artana-based adapter for extraction agent operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
    run_confidence_from_assessments,
)
from src.domain.agents.contracts import EvidenceItem, ExtractionContract
from src.domain.agents.contracts.extraction import (
    ExtractedEntityCandidate,
    ExtractedRelation,
)
from src.domain.agents.contracts.fact_assessment import (
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    resolve_external_record_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._extraction_adapter_payloads import (
    DEFAULT_EXTRACTION_USAGE_MAX_TOKENS,
    ENV_EXTRACTION_USAGE_MAX_TOKENS,
    build_compact_raw_record,
    build_extraction_input_text,
    build_extraction_prompt,
    coerce_utc_iso_datetime,
    get_extraction_system_prompt,
    normalize_temporal_context,
    normalize_temporal_value,
    sanitize_json_value,
    sanitize_text_value,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    UsageLimits,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)
from src.type_definitions.common import JSONValue  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from artana.store import PostgresStore

    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.graph_domain_ai_contracts import (
        ExtractionPayloadConfig,
        ExtractionPromptConfig,
    )

logger = logging.getLogger(__name__)
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = ArtanaLiteLLMModelPort


@dataclass(frozen=True)
class _VariantSignalCandidate:
    """Normalized deterministic variant signal candidate used for enrichment."""

    variant_key: tuple[str, str]
    anchors: dict[str, JSONValue]
    metadata: dict[str, JSONValue]
    evidence_excerpt: str
    evidence_locator: str


class ArtanaExtractionAdapter(ExtractionAgentPort):
    """Adapter that executes extraction workflows through Artana."""

    def __init__(  # noqa: PLR0913
        self,
        model: str | None = None,
        *,
        prompt_config: ExtractionPromptConfig,
        payload_config: ExtractionPayloadConfig,
        use_governance: bool = True,
        dictionary_service: object | None = None,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for extraction execution. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._prompt_config = prompt_config
        self._payload_config = payload_config
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        self._governance = GovernanceConfig.from_environment()
        self._pipeline_usage_limits = self._resolve_pipeline_usage_limits(
            self._governance.usage_limits,
        )
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        self._last_run_id = None
        source_type = context.source_type.strip().lower()
        if source_type not in self._prompt_config.supported_source_types():
            return self._unsupported_source_contract(context)

        if not self._has_openai_key():
            return self._ai_required_contract(
                context,
                reason="missing_openai_api_key",
            )

        effective_model = self._resolve_model_id(model_id)
        external_record_id = resolve_external_record_id(
            source_type=source_type,
            raw_record=context.raw_record,
            fallback_document_id=context.document_id,
        )
        run_id = self._create_run_id(
            source_type=source_type,
            research_space_id=context.research_space_id,
            external_id=external_record_id,
            extraction_config_version=self._runtime_policy.extraction_config_version,
            run_attempt_token=context.created_at.isoformat(),
        )
        self._last_run_id = run_id
        relation_governance_mode = self._resolve_relation_governance_mode(
            context.research_space_settings,
        )

        try:
            usage_limits = self._pipeline_usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id or "extraction",
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            kernel, client, model_port = self._create_runtime()
            result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(
                    source_type=source_type,
                    context=context,
                    relation_governance_mode=relation_governance_mode,
                ),
                output_schema=ExtractionContract,
                step_key=f"extraction.{source_type}.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, ExtractionContract)
                else ExtractionContract.model_validate(output)
            )
            return self._normalize_contract(
                contract=contract,
                context=context,
                source_type=source_type,
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Extraction Artana step failed for document=%s source_type=%s model=%s: %s",
                context.document_id,
                source_type,
                effective_model,
                exc,
                exc_info=True,
            )
            return self._ai_required_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )
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
    ) -> tuple[ArtanaKernel, SingleStepModelClient, _OpenAIChatModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(self._default_model)
        model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="extraction_contract",
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
        run_attempt_token: str | None = None,
        model_id: str | None = None,
        document_id: str | None = None,
    ) -> str:
        _ = model_id  # retained for backward-compatible call sites/tests
        resolved_external_id = (external_id or document_id or "").strip() or "unknown"
        normalized_attempt = (
            run_attempt_token.strip() if isinstance(run_attempt_token, str) else ""
        )
        effective_config_version = extraction_config_version
        if normalized_attempt:
            effective_config_version = (
                f"{extraction_config_version}|attempt:{normalized_attempt}"
            )
        return build_deterministic_run_id(
            prefix="extraction",
            research_space_id=research_space_id,
            source_type=source_type,
            external_id=resolved_external_id,
            extraction_config_version=effective_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    def _get_system_prompt(self, source_type: str) -> str:
        return get_extraction_system_prompt(
            source_type,
            prompt_config=self._prompt_config,
        )

    def _build_prompt(
        self,
        *,
        source_type: str,
        context: ExtractionContext,
        relation_governance_mode: str,
    ) -> str:
        return build_extraction_prompt(
            source_type=source_type,
            context=context,
            relation_governance_mode=relation_governance_mode,
            prompt_config=self._prompt_config,
            payload_config=self._payload_config,
        )

    @classmethod
    def _resolve_pipeline_usage_limits(cls, base_limits: UsageLimits) -> UsageLimits:
        env_override = cls._read_positive_int_from_env(
            ENV_EXTRACTION_USAGE_MAX_TOKENS,
        )
        base_max_tokens = (
            base_limits.max_tokens
            if isinstance(base_limits.max_tokens, int) and base_limits.max_tokens > 0
            else None
        )
        minimum_tokens = (
            env_override
            if env_override is not None
            else DEFAULT_EXTRACTION_USAGE_MAX_TOKENS
        )
        resolved_max_tokens = minimum_tokens
        if base_max_tokens is not None and base_max_tokens > resolved_max_tokens:
            resolved_max_tokens = base_max_tokens
        return UsageLimits(
            total_cost_usd=base_limits.total_cost_usd,
            max_turns=base_limits.max_turns,
            max_tokens=resolved_max_tokens,
        )

    @staticmethod
    def _read_positive_int_from_env(name: str) -> int | None:
        import os

        raw_value = os.getenv(name)
        if raw_value is None:
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        if not normalized.isdigit():
            return None
        parsed = int(normalized)
        return parsed if parsed > 0 else None

    @staticmethod
    def _resolve_relation_governance_mode(settings: Mapping[str, object]) -> str:
        raw_mode = settings.get("relation_governance_mode")
        if isinstance(raw_mode, str) and raw_mode.strip().upper() == "FULL_AUTO":
            return "FULL_AUTO"
        return "HUMAN_IN_LOOP"

    def _build_input_text(self, context: ExtractionContext) -> str:
        return build_extraction_input_text(
            context,
            payload_config=self._payload_config,
        )

    @classmethod
    def _sanitize_json_value(cls, value: object) -> object:
        return sanitize_json_value(value)

    @staticmethod
    def _sanitize_text_value(value: str) -> str:
        return sanitize_text_value(value)

    def _build_compact_raw_record(
        self,
        context: ExtractionContext,
    ) -> dict[str, object]:
        return build_compact_raw_record(
            context,
            payload_config=self._payload_config,
        )

    @classmethod
    def _normalize_temporal_context(
        cls,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return normalize_temporal_context(payload)

    @classmethod
    def _normalize_temporal_value(cls, *, key: str, value: object) -> object:
        return normalize_temporal_value(key=key, value=value)

    @staticmethod
    def _coerce_utc_iso_datetime(raw_value: str | datetime) -> str | None:
        return coerce_utc_iso_datetime(raw_value)

    def _normalize_contract(
        self,
        *,
        contract: ExtractionContract,
        context: ExtractionContext,
        source_type: str,
        run_id: str,
    ) -> ExtractionContract:
        updates: dict[str, object] = {
            "source_type": source_type,
            "document_id": context.document_id,
            "shadow_mode": context.shadow_mode,
        }
        if contract.agent_run_id is None:
            updates["agent_run_id"] = run_id
        normalized_entities = self._normalize_entities_with_genomics_signals(
            existing_entities=contract.entities,
            context=context,
        )
        if normalized_entities != contract.entities:
            updates["entities"] = normalized_entities
        supplemented_relations = self._supplement_relation_endpoint_anchors(
            relations=contract.relations,
            entity_candidates=normalized_entities,
        )
        if supplemented_relations != contract.relations:
            updates["relations"] = supplemented_relations
        updates["confidence_score"] = run_confidence_from_assessments(
            (
                *(fact_evidence_weight(entity) for entity in normalized_entities),
                *(
                    fact_evidence_weight(observation)
                    for observation in contract.observations
                ),
                *(
                    fact_evidence_weight(relation)
                    for relation in supplemented_relations
                ),
            ),
        )
        if not contract.pipeline_payloads:
            compact_payload = self._build_compact_raw_record(context)
            if compact_payload:
                updates["pipeline_payloads"] = [compact_payload]
        return contract.model_copy(update=updates)

    @staticmethod
    def _normalize_entities_with_genomics_signals(
        *,
        existing_entities: list[ExtractedEntityCandidate],
        context: ExtractionContext,
    ) -> list[ExtractedEntityCandidate]:
        signal_candidates = ArtanaExtractionAdapter._variant_signal_candidates(context)
        if not signal_candidates:
            return existing_entities

        used_variant_keys: set[tuple[str, str]] = set()
        normalized_entities: list[ExtractedEntityCandidate] = []
        for entity in existing_entities:
            if entity.entity_type.strip().upper() != "VARIANT":
                normalized_entities.append(entity)
                continue
            signal_candidate = ArtanaExtractionAdapter._match_variant_signal_candidate(
                entity=entity,
                signal_candidates=signal_candidates,
            )
            if signal_candidate is None:
                normalized_entities.append(entity)
                continue
            used_variant_keys.add(signal_candidate.variant_key)
            merged_anchors = {
                **entity.anchors,
                **signal_candidate.anchors,
            }
            merged_metadata = {
                **entity.metadata,
                **signal_candidate.metadata,
            }
            if (
                merged_anchors == entity.anchors
                and merged_metadata == entity.metadata
            ):
                normalized_entities.append(entity)
                continue
            normalized_entities.append(
                entity.model_copy(
                    update={
                        "anchors": merged_anchors,
                        "metadata": merged_metadata,
                    },
                ),
            )

        existing_variant_keys = {
            (
                str(entity.anchors.get("gene_symbol", "")).strip(),
                str(entity.anchors.get("hgvs_notation", "")).strip(),
            )
            for entity in normalized_entities
            if entity.entity_type.strip().upper() == "VARIANT"
        }
        supplemented_entities = list(normalized_entities)
        for signal_candidate in signal_candidates:
            if (
                signal_candidate.variant_key in used_variant_keys
                or signal_candidate.variant_key in existing_variant_keys
            ):
                continue
            supplemented_entities.append(
                ExtractedEntityCandidate(
                    entity_type="VARIANT",
                    label=str(
                        signal_candidate.anchors["hgvs_notation"],
                    ).strip(),
                    anchors=signal_candidate.anchors,
                    metadata=signal_candidate.metadata,
                    evidence_excerpt=signal_candidate.evidence_excerpt,
                    evidence_locator=signal_candidate.evidence_locator,
                    assessment=build_fact_assessment_from_confidence(
                        0.9,
                        confidence_rationale=(
                            "Exact anchored variant supplemented from deterministic "
                            "genomics signal parsing."
                        ),
                        grounding_level=GroundingLevel.SPAN,
                        mapping_status=MappingStatus.RESOLVED,
                        speculation_level=SpeculationLevel.DIRECT,
                    ),
                ),
            )
        return supplemented_entities

    @staticmethod
    def _variant_signal_candidates(
        context: ExtractionContext,
    ) -> tuple[_VariantSignalCandidate, ...]:
        raw_candidates = context.genomics_signals.get("variant_candidates")
        if not isinstance(raw_candidates, list):
            return ()
        signal_candidates: list[_VariantSignalCandidate] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                continue
            anchors = raw_candidate.get("anchors")
            metadata = raw_candidate.get("metadata")
            evidence_excerpt = raw_candidate.get("evidence_excerpt")
            evidence_locator = raw_candidate.get("evidence_locator")
            if not isinstance(anchors, dict) or not isinstance(metadata, dict):
                continue
            gene_symbol = anchors.get("gene_symbol")
            hgvs_notation = anchors.get("hgvs_notation")
            if not isinstance(gene_symbol, str) or not gene_symbol.strip():
                continue
            if not isinstance(hgvs_notation, str) or not hgvs_notation.strip():
                continue
            if not isinstance(evidence_excerpt, str) or not evidence_excerpt.strip():
                continue
            if not isinstance(evidence_locator, str) or not evidence_locator.strip():
                continue
            signal_candidates.append(
                _VariantSignalCandidate(
                    variant_key=(gene_symbol.strip(), hgvs_notation.strip()),
                    anchors={
                        str(key): cast("JSONValue", sanitize_json_value(value))
                        for key, value in anchors.items()
                    },
                    metadata={
                        str(key): cast("JSONValue", sanitize_json_value(value))
                        for key, value in metadata.items()
                    },
                    evidence_excerpt=evidence_excerpt.strip(),
                    evidence_locator=evidence_locator.strip(),
                ),
            )
        return tuple(signal_candidates)

    @staticmethod
    def _match_variant_signal_candidate(
        *,
        entity: ExtractedEntityCandidate,
        signal_candidates: tuple[_VariantSignalCandidate, ...],
    ) -> _VariantSignalCandidate | None:
        existing_gene_symbol = entity.anchors.get("gene_symbol")
        existing_hgvs_notation = entity.anchors.get("hgvs_notation")
        if isinstance(existing_gene_symbol, str) and isinstance(
            existing_hgvs_notation,
            str,
        ):
            normalized_existing_key = (
                existing_gene_symbol.strip(),
                existing_hgvs_notation.strip(),
            )
            for signal_candidate in signal_candidates:
                if signal_candidate.variant_key == normalized_existing_key:
                    return signal_candidate

        normalized_label = entity.label.strip().lower()
        for signal_candidate in signal_candidates:
            candidate_labels = ArtanaExtractionAdapter._variant_signal_labels(
                signal_candidate,
            )
            if normalized_label in candidate_labels:
                return signal_candidate
            hgvs_notation = str(
                signal_candidate.anchors.get("hgvs_notation", ""),
            ).strip().lower()
            hgvs_protein = str(
                signal_candidate.metadata.get("hgvs_protein", ""),
            ).strip().lower()
            if (
                hgvs_notation
                and hgvs_notation in normalized_label
                and (not hgvs_protein or hgvs_protein in normalized_label)
            ):
                return signal_candidate
        return None

    @staticmethod
    def _variant_signal_labels(
        signal_candidate: _VariantSignalCandidate,
    ) -> set[str]:
        hgvs_notation = str(signal_candidate.anchors.get("hgvs_notation", "")).strip()
        transcript = str(signal_candidate.metadata.get("transcript", "")).strip()
        hgvs_protein = str(signal_candidate.metadata.get("hgvs_protein", "")).strip()
        labels = {
            hgvs_notation.lower(),
        }
        if hgvs_protein:
            labels.add(hgvs_protein.lower())
            if hgvs_notation:
                labels.add(f"{hgvs_notation} ({hgvs_protein})".lower())
        if transcript and hgvs_notation:
            labels.add(f"{transcript}:{hgvs_notation}".lower())
            if hgvs_protein:
                labels.add(f"{transcript}:{hgvs_notation} ({hgvs_protein})".lower())
        return {label for label in labels if label}

    @staticmethod
    def _supplement_relation_endpoint_anchors(  # noqa: C901, PLR0912
        *,
        relations: list[ExtractedRelation],
        entity_candidates: list[ExtractedEntityCandidate],
    ) -> list[ExtractedRelation]:
        index: dict[tuple[str, str], ExtractedEntityCandidate | None] = {}
        for candidate in entity_candidates:
            normalized_type = candidate.entity_type.strip().upper()
            if not normalized_type:
                continue
            labels = {
                candidate.label.strip().lower(),
            }
            for key in (
                "display_label",
                "hgvs_notation",
                "mechanism_name",
                "hpo_term",
                "name",
                "label",
                "gene_symbol",
            ):
                value = candidate.anchors.get(key)
                if isinstance(value, str) and value.strip():
                    labels.add(value.strip().lower())
            for label in labels:
                if not label:
                    continue
                lookup_key = (normalized_type, label)
                existing = index.get(lookup_key)
                if existing is None and lookup_key in index:
                    continue
                if existing is not None:
                    index[lookup_key] = None
                    continue
                index[lookup_key] = candidate

        supplemented: list[ExtractedRelation] = []
        for relation in relations:
            source_anchors = relation.source_anchors
            target_anchors = relation.target_anchors
            if not source_anchors:
                source_lookup = (
                    relation.source_type.strip().upper(),
                    relation.source_label.strip().lower(),
                ) if isinstance(relation.source_label, str) and relation.source_label.strip() else None
                if source_lookup is not None:
                    source_candidate = index.get(source_lookup)
                    if source_candidate is not None:
                        source_anchors = {
                            **source_candidate.anchors,
                            "display_label": source_candidate.label,
                        }
            if not target_anchors:
                target_lookup = (
                    relation.target_type.strip().upper(),
                    relation.target_label.strip().lower(),
                ) if isinstance(relation.target_label, str) and relation.target_label.strip() else None
                if target_lookup is not None:
                    target_candidate = index.get(target_lookup)
                    if target_candidate is not None:
                        target_anchors = {
                            **target_candidate.anchors,
                            "display_label": target_candidate.label,
                        }
            if source_anchors == relation.source_anchors and target_anchors == relation.target_anchors:
                supplemented.append(relation)
                continue
            supplemented.append(
                relation.model_copy(
                    update={
                        "source_anchors": source_anchors,
                        "target_anchors": target_anchors,
                    },
                ),
            )
        return supplemented

    def _ai_required_contract(
        self,
        context: ExtractionContext,
        *,
        reason: str,
    ) -> ExtractionContract:
        return ExtractionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=(
                "AI-only extraction is required for PubMed/ClinVar pipeline stages; "
                f"no deterministic fallback was executed ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"source_document:{context.document_id}",
                    excerpt=f"AI extraction unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            source_type=context.source_type,
            document_id=context.document_id,
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _unsupported_source_contract(context: ExtractionContext) -> ExtractionContract:
        return ExtractionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{context.source_type}' is not supported",
            evidence=[],
            source_type=context.source_type,
            document_id=context.document_id,
            shadow_mode=context.shadow_mode,
        )


__all__ = ["ArtanaExtractionAdapter"]
