"""Processing helpers for entity-recognition orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.domain.agents.contracts.assessment_compat import (
    assessment_payload,
    confidence_from_entity_recognition_contract,
    confidence_from_item,
)
from src.domain.entities.source_document import DocumentExtractionStatus

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionDocumentOutcome,
    )
    from src.application.agents.services.extraction_service import (
        ExtractionDocumentOutcome,
        ExtractionService,
    )
    from src.application.agents.services.governance_service import (
        GovernanceDecision,
        GovernanceService,
    )
    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionProgressUpdate,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings
    from src.type_definitions.ingestion import IngestResult, RawRecord


logger = logging.getLogger(__name__)


class _EntityRecognitionProcessingContext(Protocol):
    """Structural typing contract consumed by processing helper methods."""

    _agent: EntityRecognitionPort
    _source_documents: SourceDocumentRepository
    _ingestion_pipeline: IngestionPipelinePort
    _extraction_service: ExtractionService | None
    _governance: GovernanceService
    _pipeline_trace: PipelineRunTraceService | None
    _agent_timeout_seconds: float
    _agent_timeout_retry_attempts: int
    _agent_timeout_retry_backoff_seconds: float
    _extraction_stage_timeout_seconds: float

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject: ...

    def _prepare_agent_raw_record(self, raw_record: JSONObject) -> JSONObject: ...

    def _resolve_research_space_settings(
        self,
        document: SourceDocument,
    ) -> ResearchSpaceSettings: ...

    def _resolve_shadow_mode(
        self,
        *,
        override: bool | None,
        settings: ResearchSpaceSettings,
    ) -> bool: ...

    def _persist_failed_document(
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument: ...

    def _persist_extracted_document(
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument: ...

    @staticmethod
    def _resolve_run_id(contract: EntityRecognitionContract) -> str | None: ...

    @staticmethod
    def _resolve_governance_decision(
        contract: EntityRecognitionContract,
    ) -> str: ...

    def _build_outcome_metadata(  # noqa: PLR0913
        self,
        *,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        pipeline_run_id: str | None,
        wrote_to_kernel: bool,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        ingestion_result: IngestResult | None,
    ) -> JSONObject: ...

    @staticmethod
    def _build_extraction_metadata(
        extraction_outcome: ExtractionDocumentOutcome,
    ) -> JSONObject: ...

    def _enforce_active_dictionary_creation_policy(
        self,
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings: ...

    def _ensure_domain_bootstrap(
        self,
        *,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]: ...

    def _apply_dictionary_mutations(  # noqa: PLR0913
        self,
        *,
        contract: EntityRecognitionContract,
        raw_record: JSONObject,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int, int]: ...

    def _build_pipeline_records(
        self,
        *,
        contract: EntityRecognitionContract,
        document: SourceDocument,
        raw_record: JSONObject,
        run_id: str | None,
    ) -> list[RawRecord]: ...

    def _normalize_seed_entity_ids(
        self,
        seed_entity_ids: list[str],
    ) -> tuple[str, ...]: ...

    @staticmethod
    def _build_graph_fallback_relation_payloads(
        *,
        seed_entity_ids: tuple[str, ...],
        rejected_relation_details: tuple[JSONObject, ...],
    ) -> tuple[JSONObject, ...]: ...

    @staticmethod
    def _merge_metadata(existing: JSONObject, patch: JSONObject) -> JSONObject: ...

    def _document_outcome(  # noqa: PLR0913
        self,
        *,
        document_id: UUID,
        status: Literal["extracted", "failed", "skipped"],
        reason: str,
        review_required: bool,
        shadow_mode: bool,
        wrote_to_kernel: bool,
        run_id: str | None = None,
        dictionary_variables_created: int = 0,
        dictionary_synonyms_created: int = 0,
        dictionary_entity_types_created: int = 0,
        ingestion_entities_created: int = 0,
        ingestion_observations_created: int = 0,
        relation_claims_count: int = 0,
        pending_review_relations_count: int = 0,
        undefined_relations_count: int = 0,
        persisted_relations_count: int = 0,
        concept_members_created_count: int = 0,
        concept_aliases_created_count: int = 0,
        concept_decisions_proposed_count: int = 0,
        seed_entity_ids: tuple[str, ...] = (),
        graph_fallback_relation_payloads: tuple[JSONObject, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> EntityRecognitionDocumentOutcome: ...

    def _build_resolver_warning_progress_callback(
        self,
        *,
        document: SourceDocument,
        pipeline_run_id: str | None,
        stage: Literal["extraction"],
    ) -> IngestionProgressCallback | None: ...

    async def _process_document_with_extraction(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        document_run_id: str | None,
        model_id: str | None,
        requested_shadow_mode: bool,
        research_space_settings: ResearchSpaceSettings,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome: ...

    async def _process_document_entity(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
        shadow_mode: bool | None,
        force: bool,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome: ...


class _EntityRecognitionProcessingHelpers:
    """Mixin containing heavy document processing paths."""

    def _build_resolver_warning_progress_callback(
        self: _EntityRecognitionProcessingContext,
        *,
        document: SourceDocument,
        pipeline_run_id: str | None,
        stage: Literal["extraction"],
    ) -> IngestionProgressCallback | None:
        if (
            self._pipeline_trace is None
            or pipeline_run_id is None
            or document.research_space_id is None
        ):
            return None
        trace = self._pipeline_trace
        research_space_id = document.research_space_id

        def _callback(update: IngestionProgressUpdate) -> None:
            if update.event_type != "resolver_warning":
                return
            payload = {str(key): value for key, value in dict(update.payload).items()}
            payload.setdefault("document_id", str(document.id))
            payload.setdefault("external_record_id", document.external_record_id)
            raw_source_record_id = payload.get("source_record_id")
            source_record_id = (
                raw_source_record_id.strip()
                if isinstance(raw_source_record_id, str)
                and raw_source_record_id.strip()
                else None
            )
            trace.record_event(
                research_space_id=research_space_id,
                source_id=document.source_id,
                pipeline_run_id=pipeline_run_id,
                event_type="resolver_warning",
                stage=stage,
                scope_kind="document",
                scope_id=str(document.id),
                message=update.message,
                level="warning",
                status="warning",
                agent_kind="entity_resolver",
                error_code="resolver_policy_missing",
                occurred_at=update.occurred_at,
                payload={
                    **payload,
                    "stage": stage,
                    "source_record_id": source_record_id,
                },
            )

        return _callback

    async def _process_document_entity(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self: _EntityRecognitionProcessingContext,
        *,
        document: SourceDocument,
        model_id: str | None,
        shadow_mode: bool | None,
        force: bool,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome:
        if not force and document.extraction_status != DocumentExtractionStatus.PENDING:
            logger.info(
                "Entity recognition document skipped due to extraction status",
                extra={
                    "document_id": str(document.id),
                    "extraction_status": document.extraction_status.value,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return self._document_outcome(
                document_id=document.id,
                status="skipped",
                reason=f"document_status={document.extraction_status.value}",
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
            )

        raw_record = self._extract_raw_record(document)
        if not raw_record:
            failure_reason = "missing_raw_record_metadata"
            logger.warning(
                "Entity recognition document missing raw_record metadata",
                extra={
                    "document_id": str(document.id),
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            self._persist_failed_document(
                document=document,
                run_id=None,
                metadata_patch={"entity_recognition_error": failure_reason},
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                errors=(failure_reason,),
            )

        research_space_settings = self._resolve_research_space_settings(document)
        requested_shadow_mode = self._resolve_shadow_mode(
            override=shadow_mode,
            settings=research_space_settings,
        )
        context_raw_record = self._prepare_agent_raw_record(raw_record)
        context = EntityRecognitionContext(
            document_id=str(document.id),
            source_type=document.source_type.value,
            research_space_id=(
                str(document.research_space_id) if document.research_space_id else None
            ),
            research_space_settings=research_space_settings,
            raw_record=context_raw_record,
            shadow_mode=requested_shadow_mode,
        )

        logger.info(
            "Entity recognition marking document in_progress",
            extra={
                "document_id": str(document.id),
                "pipeline_run_id": pipeline_run_id,
                "shadow_mode": requested_shadow_mode,
                "source_type": document.source_type.value,
            },
        )
        in_progress = document.mark_extraction_in_progress(started_at=datetime.now(UTC))
        document = self._source_documents.upsert(
            in_progress.model_copy(
                update={
                    "metadata": self._merge_metadata(
                        in_progress.metadata,
                        {
                            "entity_recognition_started_at": datetime.now(
                                UTC,
                            ).isoformat(),
                            "entity_recognition_shadow_mode": requested_shadow_mode,
                            "pipeline_run_id": pipeline_run_id,
                        },
                    ),
                },
            ),
        )

        agent_started_at = datetime.now(UTC)
        logger.info(
            "Entity recognition agent call started",
            extra={
                "document_id": str(document.id),
                "pipeline_run_id": pipeline_run_id,
                "source_type": document.source_type.value,
                "model_id": model_id,
                "timeout_seconds": self._agent_timeout_seconds,
                "timeout_retry_attempts": self._agent_timeout_retry_attempts,
            },
        )
        timeout_attempts = max(self._agent_timeout_retry_attempts + 1, 1)
        timeout_backoff_seconds = self._agent_timeout_retry_backoff_seconds
        timeout_failures = 0
        contract: EntityRecognitionContract | None = None
        for attempt_index in range(timeout_attempts):
            try:
                contract = await asyncio.wait_for(
                    self._agent.recognize(context, model_id=model_id),
                    timeout=self._agent_timeout_seconds,
                )
                logger.info(
                    "Entity recognition agent call finished",
                    extra={
                        "document_id": str(document.id),
                        "pipeline_run_id": pipeline_run_id,
                        "duration_ms": int(
                            (datetime.now(UTC) - agent_started_at).total_seconds()
                            * 1000,
                        ),
                        "decision": contract.decision,
                        "confidence_score": confidence_from_entity_recognition_contract(
                            contract,
                        ),
                        "attempt": attempt_index + 1,
                        "attempts_total": timeout_attempts,
                    },
                )
                break
            except TimeoutError:
                timeout_failures += 1
                if attempt_index + 1 >= timeout_attempts:
                    logger.exception(
                        (
                            "Entity recognition agent call timed out for document=%s "
                            "after %.1fs (attempt %s/%s)"
                        ),
                        document.id,
                        self._agent_timeout_seconds,
                        attempt_index + 1,
                        timeout_attempts,
                    )
                    break
                backoff_seconds = timeout_backoff_seconds * (attempt_index + 1)
                logger.warning(
                    (
                        "Entity recognition timeout for document=%s (attempt %s/%s); "
                        "retrying in %.1fs"
                    ),
                    document.id,
                    attempt_index + 1,
                    timeout_attempts,
                    backoff_seconds,
                )
                if (
                    self._pipeline_trace is not None
                    and pipeline_run_id is not None
                    and document.research_space_id is not None
                ):
                    self._pipeline_trace.record_event(
                        research_space_id=document.research_space_id,
                        source_id=document.source_id,
                        pipeline_run_id=pipeline_run_id,
                        event_type="entity_recognition_retry_scheduled",
                        stage="extraction",
                        scope_kind="document",
                        scope_id=str(document.id),
                        message=(
                            "Entity recognition timed out and will retry for "
                            f"document {document.external_record_id}."
                        ),
                        level="warning",
                        status="retrying",
                        agent_kind="entity_recognition",
                        occurred_at=datetime.now(UTC),
                        payload={
                            "document_id": str(document.id),
                            "external_record_id": document.external_record_id,
                            "attempt": attempt_index + 1,
                            "attempts_total": timeout_attempts,
                            "timeout_seconds": self._agent_timeout_seconds,
                            "backoff_seconds": backoff_seconds,
                        },
                    )
                # Refresh the context timestamp so retry-capable Artana adapters
                # derive a fresh run-attempt identity instead of replaying the
                # terminal outcome from the timed-out attempt.
                context = context.model_copy(
                    update={"created_at": datetime.now(UTC)},
                )
                await asyncio.sleep(max(backoff_seconds, 0.0))
            except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
                logger.exception(
                    "Entity recognition failed for document=%s",
                    document.id,
                )
                failure_reason = "agent_execution_failed"
                self._persist_failed_document(
                    document=document,
                    run_id=None,
                    metadata_patch={
                        "entity_recognition_error": str(exc),
                        "entity_recognition_failure_reason": failure_reason,
                    },
                )
                return self._document_outcome(
                    document_id=document.id,
                    status="failed",
                    reason=failure_reason,
                    review_required=False,
                    shadow_mode=requested_shadow_mode,
                    wrote_to_kernel=False,
                    errors=(str(exc),),
                )

        if contract is None:
            failure_reason = "agent_execution_timeout"
            self._persist_failed_document(
                document=document,
                run_id=None,
                metadata_patch={
                    "entity_recognition_error": (
                        "entity_recognition_agent_timeout:"
                        f"{self._agent_timeout_seconds:.1f}s"
                    ),
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_timeout_seconds": self._agent_timeout_seconds,
                    "entity_recognition_timeout_attempts": timeout_failures,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=requested_shadow_mode,
                wrote_to_kernel=False,
                errors=(
                    "entity_recognition_agent_timeout:"
                    f"{self._agent_timeout_seconds:.1f}s",
                ),
            )

        run_id = self._resolve_run_id(contract)
        contract_confidence = confidence_from_entity_recognition_contract(contract)
        contract_assessment = assessment_payload(contract)
        assessment_scores = tuple(
            confidence_from_item(candidate)
            for candidate in (
                *contract.recognized_entities,
                *contract.recognized_observations,
            )
        )
        if (
            contract.decision != "generated"
            and self._pipeline_trace is not None
            and pipeline_run_id is not None
            and document.research_space_id is not None
        ):
            self._pipeline_trace.record_event(
                research_space_id=document.research_space_id,
                source_id=document.source_id,
                pipeline_run_id=pipeline_run_id,
                event_type="entity_recognition_decision_warning",
                stage="extraction",
                scope_kind="document",
                scope_id=str(document.id),
                message=(
                    "Entity recognition returned a non-generated decision for "
                    f"document {document.external_record_id}."
                ),
                level="warning",
                status=contract.decision,
                agent_kind="entity_recognition",
                agent_run_id=run_id,
                occurred_at=datetime.now(UTC),
                payload={
                    "document_id": str(document.id),
                    "external_record_id": document.external_record_id,
                    "decision": contract.decision,
                    "confidence_score": contract_confidence,
                    "rationale": contract.rationale,
                    **(
                        {"entity_recognition_assessment": contract_assessment}
                        if contract_assessment is not None
                        else {}
                    ),
                },
            )
        governance = self._governance.evaluate(
            confidence_score=contract_confidence,
            assessment_scores=assessment_scores,
            evidence_count=len(contract.evidence),
            decision=self._resolve_governance_decision(contract),
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=research_space_settings,
        )

        if governance.shadow_mode:
            self._persist_extracted_document(
                document=document,
                run_id=run_id,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=0,
                    dictionary_synonyms_created=0,
                    dictionary_entity_types_created=0,
                    ingestion_result=None,
                ),
            )
            return self._document_outcome(
                document_id=document.id,
                status="extracted",
                reason="shadow_mode_enabled",
                review_required=False,
                shadow_mode=True,
                wrote_to_kernel=False,
                run_id=run_id,
            )

        if not governance.allow_write:
            failure_reason = governance.reason
            if (
                failure_reason == "agent_requested_escalation"
                and self._extraction_service is not None
                and document.research_space_id is not None
            ):
                bootstrap_settings = self._enforce_active_dictionary_creation_policy(
                    research_space_settings,
                )
                (
                    bootstrap_variables_created,
                    bootstrap_entity_types_created,
                ) = self._ensure_domain_bootstrap(
                    source_type=document.source_type.value,
                    source_ref=f"source_document:{document.id}",
                    research_space_settings=bootstrap_settings,
                )
                return await self._process_document_with_extraction(
                    document=document,
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    document_run_id=run_id,
                    model_id=model_id,
                    requested_shadow_mode=requested_shadow_mode,
                    research_space_settings=bootstrap_settings,
                    dictionary_variables_created=bootstrap_variables_created,
                    dictionary_synonyms_created=0,
                    dictionary_entity_types_created=bootstrap_entity_types_created,
                    pipeline_run_id=pipeline_run_id,
                )
            self._persist_failed_document(
                document=document,
                run_id=run_id,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=0,
                    dictionary_synonyms_created=0,
                    dictionary_entity_types_created=0,
                    ingestion_result=None,
                ),
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=governance.requires_review,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(failure_reason,),
            )

        if document.research_space_id is None:
            failure_reason = "missing_research_space_id"
            self._persist_failed_document(
                document=document,
                run_id=run_id,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(failure_reason,),
            )

        try:
            (
                dictionary_variables_created,
                dictionary_synonyms_created,
                dictionary_entity_types_created,
            ) = self._apply_dictionary_mutations(
                contract=contract,
                raw_record=raw_record,
                source_type=document.source_type.value,
                source_ref=f"source_document:{document.id}",
                research_space_settings=research_space_settings,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
            logger.exception(
                "Dictionary mutation failed for document=%s",
                document.id,
            )
            failure_reason = "dictionary_mutation_failed"
            self._persist_failed_document(
                document=document,
                run_id=run_id,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_error": str(exc),
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(str(exc),),
            )

        if self._extraction_service is not None:
            return await self._process_document_with_extraction(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                document_run_id=run_id,
                model_id=model_id,
                requested_shadow_mode=requested_shadow_mode,
                research_space_settings=research_space_settings,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                pipeline_run_id=pipeline_run_id,
            )

        pipeline_records = self._build_pipeline_records(
            contract=contract,
            document=document,
            raw_record=raw_record,
            run_id=run_id,
        )
        if not pipeline_records:
            failure_reason = "no_pipeline_payloads"
            self._persist_failed_document(
                document=document,
                run_id=run_id,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                errors=(failure_reason,),
            )

        ingestion_result = self._ingestion_pipeline.run(
            pipeline_records,
            str(document.research_space_id),
            progress_callback=self._build_resolver_warning_progress_callback(
                document=document,
                pipeline_run_id=pipeline_run_id,
                stage="extraction",
            ),
        )
        if not ingestion_result.success:
            failure_reason = "kernel_ingestion_failed"
            self._persist_failed_document(
                document=document,
                run_id=run_id,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=dictionary_variables_created,
                    dictionary_synonyms_created=dictionary_synonyms_created,
                    dictionary_entity_types_created=dictionary_entity_types_created,
                    ingestion_result=ingestion_result,
                ),
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_entities_created=ingestion_result.entities_created,
                ingestion_observations_created=ingestion_result.observations_created,
                seed_entity_ids=self._normalize_seed_entity_ids(
                    ingestion_result.entity_ids_touched,
                ),
                errors=tuple(ingestion_result.errors),
            )

        self._persist_extracted_document(
            document=document,
            run_id=run_id,
            metadata_patch=self._build_outcome_metadata(
                contract=contract,
                governance=governance,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
                wrote_to_kernel=True,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_result=ingestion_result,
            ),
        )
        return self._document_outcome(
            document_id=document.id,
            status="extracted",
            reason="processed",
            review_required=False,
            shadow_mode=False,
            wrote_to_kernel=True,
            run_id=run_id,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=ingestion_result.entities_created,
            ingestion_observations_created=ingestion_result.observations_created,
            seed_entity_ids=self._normalize_seed_entity_ids(
                ingestion_result.entity_ids_touched,
            ),
            errors=tuple(ingestion_result.errors),
        )

    async def _process_document_with_extraction(  # noqa: PLR0913, PLR0915
        self: _EntityRecognitionProcessingContext,
        *,
        document: SourceDocument,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        document_run_id: str | None,
        model_id: str | None,
        requested_shadow_mode: bool,
        research_space_settings: ResearchSpaceSettings,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome:
        if self._extraction_service is None:
            msg = "Extraction service is not configured"
            raise RuntimeError(msg)

        extraction_started_at = datetime.now(UTC)
        logger.info(
            "Entity recognition extraction handoff started",
            extra={
                "document_id": str(document.id),
                "pipeline_run_id": pipeline_run_id,
                "entity_run_id": run_id,
                "model_id": model_id,
                "timeout_seconds": self._extraction_stage_timeout_seconds,
            },
        )
        try:
            extraction_outcome = await asyncio.wait_for(
                self._extraction_service.extract_from_entity_recognition(
                    document=document,
                    recognition_contract=contract,
                    research_space_settings=research_space_settings,
                    model_id=model_id,
                    shadow_mode=requested_shadow_mode,
                    ingestion_progress_callback=(
                        self._build_resolver_warning_progress_callback(
                            document=document,
                            pipeline_run_id=pipeline_run_id,
                            stage="extraction",
                        )
                    ),
                ),
                timeout=self._extraction_stage_timeout_seconds,
            )
            logger.info(
                "Entity recognition extraction handoff finished",
                extra={
                    "document_id": str(document.id),
                    "pipeline_run_id": pipeline_run_id,
                    "entity_run_id": run_id,
                    "duration_ms": int(
                        (datetime.now(UTC) - extraction_started_at).total_seconds()
                        * 1000,
                    ),
                    "extraction_status": extraction_outcome.status,
                    "extraction_reason": extraction_outcome.reason,
                    "extraction_run_id": extraction_outcome.run_id,
                },
            )
        except TimeoutError:
            elapsed_ms = int(
                (datetime.now(UTC) - extraction_started_at).total_seconds() * 1000,
            )
            failure_run_id = run_id or document_run_id
            error_code = "EXTRACTION_STAGE_TIMEOUT"
            error_class = "TimeoutError"
            logger.exception(
                "Extraction stage timed out for document=%s after %.1fs",
                document.id,
                self._extraction_stage_timeout_seconds,
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "entity_run_id": run_id,
                    "failure_run_id": failure_run_id,
                    "elapsed_ms": elapsed_ms,
                    "error_code": error_code,
                    "error_class": error_class,
                },
            )
            failure_reason = "extraction_stage_timeout"
            metadata_patch = self._build_outcome_metadata(
                contract=contract,
                governance=governance,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
                wrote_to_kernel=False,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_result=None,
            )
            metadata_patch["extraction_stage_error"] = (
                "extraction_stage_timeout:"
                f"{self._extraction_stage_timeout_seconds:.1f}s"
            )
            metadata_patch["extraction_stage_failure_reason"] = failure_reason
            metadata_patch["extraction_stage_timeout_seconds"] = (
                self._extraction_stage_timeout_seconds
            )
            metadata_patch["extraction_stage_failure"] = {
                "error_code": error_code,
                "error_class": error_class,
                "elapsed_ms": elapsed_ms,
                "run_id": failure_run_id,
            }
            metadata_patch["extraction_stage_error_code"] = error_code
            metadata_patch["extraction_stage_error_class"] = error_class
            metadata_patch["extraction_stage_elapsed_ms"] = elapsed_ms
            metadata_patch["extraction_stage_run_id"] = failure_run_id
            self._persist_failed_document(
                document=document,
                run_id=document_run_id,
                metadata_patch=metadata_patch,
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=governance.requires_review,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                errors=(
                    "extraction_stage_timeout:"
                    f"{self._extraction_stage_timeout_seconds:.1f}s",
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
            elapsed_ms = int(
                (datetime.now(UTC) - extraction_started_at).total_seconds() * 1000,
            )
            failure_run_id = run_id or document_run_id
            custom_error_code = getattr(exc, "error_code", None)
            error_code = (
                custom_error_code.strip()
                if isinstance(custom_error_code, str) and custom_error_code.strip()
                else "EXTRACTION_STAGE_FAILED"
            )
            error_class = type(exc).__name__
            logger.exception(
                "Extraction stage failed for document=%s",
                document.id,
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "entity_run_id": run_id,
                    "failure_run_id": failure_run_id,
                    "elapsed_ms": elapsed_ms,
                    "error_code": error_code,
                    "error_class": error_class,
                },
            )
            failure_reason = "extraction_stage_failed"
            metadata_patch = self._build_outcome_metadata(
                contract=contract,
                governance=governance,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
                wrote_to_kernel=False,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_result=None,
            )
            metadata_patch["extraction_stage_error"] = str(exc)
            metadata_patch["extraction_stage_failure_reason"] = failure_reason
            metadata_patch["extraction_stage_failure"] = {
                "error_code": error_code,
                "error_class": error_class,
                "elapsed_ms": elapsed_ms,
                "run_id": failure_run_id,
            }
            metadata_patch["extraction_stage_error_code"] = error_code
            metadata_patch["extraction_stage_error_class"] = error_class
            metadata_patch["extraction_stage_elapsed_ms"] = elapsed_ms
            metadata_patch["extraction_stage_run_id"] = failure_run_id
            self._persist_failed_document(
                document=document,
                run_id=document_run_id,
                metadata_patch=metadata_patch,
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=governance.requires_review,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                errors=(str(exc),),
            )

        extraction_run_id = (
            extraction_outcome.run_id.strip()
            if isinstance(extraction_outcome.run_id, str)
            and extraction_outcome.run_id.strip()
            else document_run_id
        )
        graph_fallback_relation_payloads = self._build_graph_fallback_relation_payloads(
            seed_entity_ids=extraction_outcome.seed_entity_ids,
            rejected_relation_details=extraction_outcome.rejected_relation_details,
        )
        metadata_patch = self._build_outcome_metadata(
            contract=contract,
            governance=governance,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
            wrote_to_kernel=extraction_outcome.wrote_to_kernel,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_result=None,
        )
        metadata_patch = self._merge_metadata(
            metadata_patch,
            self._build_extraction_metadata(extraction_outcome),
        )

        review_required = (
            governance.requires_review or extraction_outcome.review_required
        )
        if extraction_outcome.status == "failed":
            self._persist_failed_document(
                document=document,
                run_id=extraction_run_id,
                metadata_patch=metadata_patch,
            )
            return self._document_outcome(
                document_id=document.id,
                status="failed",
                reason=extraction_outcome.reason,
                review_required=review_required,
                shadow_mode=extraction_outcome.shadow_mode,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_entities_created=(
                    extraction_outcome.ingestion_entities_created
                ),
                ingestion_observations_created=(
                    extraction_outcome.ingestion_observations_created
                ),
                relation_claims_count=extraction_outcome.relation_claims_count,
                pending_review_relations_count=(
                    extraction_outcome.pending_review_relations_count
                ),
                undefined_relations_count=(
                    extraction_outcome.undefined_relations_count
                ),
                persisted_relations_count=(
                    extraction_outcome.persisted_relations_count
                ),
                concept_members_created_count=(
                    extraction_outcome.concept_members_created_count
                ),
                concept_aliases_created_count=(
                    extraction_outcome.concept_aliases_created_count
                ),
                concept_decisions_proposed_count=(
                    extraction_outcome.concept_decisions_proposed_count
                ),
                seed_entity_ids=extraction_outcome.seed_entity_ids,
                graph_fallback_relation_payloads=graph_fallback_relation_payloads,
                errors=extraction_outcome.errors,
            )

        self._persist_extracted_document(
            document=document,
            run_id=extraction_run_id,
            metadata_patch=metadata_patch,
        )
        return self._document_outcome(
            document_id=document.id,
            status="extracted",
            reason=extraction_outcome.reason,
            review_required=review_required,
            shadow_mode=extraction_outcome.shadow_mode,
            wrote_to_kernel=extraction_outcome.wrote_to_kernel,
            run_id=run_id,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=extraction_outcome.ingestion_entities_created,
            ingestion_observations_created=(
                extraction_outcome.ingestion_observations_created
            ),
            relation_claims_count=extraction_outcome.relation_claims_count,
            pending_review_relations_count=(
                extraction_outcome.pending_review_relations_count
            ),
            undefined_relations_count=(extraction_outcome.undefined_relations_count),
            persisted_relations_count=extraction_outcome.persisted_relations_count,
            concept_members_created_count=(
                extraction_outcome.concept_members_created_count
            ),
            concept_aliases_created_count=(
                extraction_outcome.concept_aliases_created_count
            ),
            concept_decisions_proposed_count=(
                extraction_outcome.concept_decisions_proposed_count
            ),
            seed_entity_ids=extraction_outcome.seed_entity_ids,
            graph_fallback_relation_payloads=graph_fallback_relation_payloads,
            errors=extraction_outcome.errors,
        )


__all__ = ["_EntityRecognitionProcessingHelpers"]
