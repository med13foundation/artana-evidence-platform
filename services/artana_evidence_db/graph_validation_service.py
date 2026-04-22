"""Side-effect-free validators for graph and dictionary writes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from artana_evidence_db._dictionary_relation_types import (
    canonicalize_dictionary_relation_type,
)
from artana_evidence_db.graph_api_schemas.kernel_entity_schemas import (
    KernelEntityCreateRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_observation_schemas import (
    KernelObservationCreateRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    DictionaryEntityTypeValidationRequest,
    DictionaryRelationConstraintValidationRequest,
    DictionaryRelationTypeValidationRequest,
    GraphValidationCode,
    GraphValidationNextAction,
    GraphValidationSeverity,
    KernelGraphValidationResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationTripleValidationRequest,
)
from artana_evidence_db.kernel_domain_models import KernelEntity, RelationConstraint
from artana_evidence_db.kernel_services import KernelEntityService
from artana_evidence_db.observation_value_support import (
    ObservationValueValidationError,
    coerce_observation_value_for_data_type,
)
from artana_evidence_db.relation_claim_models import KernelRelationClaim
from artana_evidence_db.semantic_ports import DictionaryPort

_VALIDATION_REASON_BY_CODE: dict[GraphValidationCode, str] = {
    "allowed": "created_via_claim_api",
    "relation_constraint_review_only": "relation_constraint_review_only",
    "unknown_relation_type": "relation_type_not_found_in_dictionary",
    "relation_constraint_not_allowed": "relation_not_allowed_by_active_constraints",
    "insufficient_evidence": "relation_requires_evidence",
    "unknown_entity": "source_or_target_entity_not_found",
    "invalid_relation_type": "relation_type_invalid",
    "unknown_subject": "observation_subject_not_found",
    "unknown_variable": "variable_not_found_in_dictionary",
    "invalid_value_for_variable": "observation_value_invalid",
    "missing_provenance": "observation_requires_provenance",
    "unknown_provenance": "observation_provenance_not_found",
    "cross_space_provenance": "observation_provenance_cross_space",
    "duplicate_claim": "duplicate_claim",
    "conflicting_claim": "conflicting_claim",
    "missing_ai_provenance": "ai_claim_provenance_required",
}
_MAX_VALUE_PREVIEW_LENGTH = 120
_TRUNCATED_VALUE_PREVIEW_LENGTH = _MAX_VALUE_PREVIEW_LENGTH - 3


def _normalize_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip().upper()
    return normalized.replace("-", "_").replace("/", "_").replace(" ", "_")


def _infer_variable_data_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, list | dict):
        return "JSON"
    return "STRING"


def _variable_display_name(variable_id: str) -> str:
    return variable_id.replace("_", " ").title()


def _value_preview(value: object) -> str:
    preview = str(value)
    if len(preview) <= _MAX_VALUE_PREVIEW_LENGTH:
        return preview
    return f"{preview[:_TRUNCATED_VALUE_PREVIEW_LENGTH]}..."


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True)
class _ResolvedClaimEntities:
    source: KernelEntity
    target: KernelEntity


class _ProvenanceRecordLike(Protocol):
    research_space_id: object


class ProvenanceServiceLike(Protocol):
    def get_provenance(self, provenance_id: str) -> _ProvenanceRecordLike | None:
        """Return one provenance record by ID."""


class RelationClaimServiceLike(Protocol):
    def list_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
    ) -> list[KernelRelationClaim]:
        """Return claims in a research space, optionally scoped by relation type."""


class GraphValidationService:
    """Reusable validation logic shared by routes and clients."""

    def __init__(
        self,
        *,
        entity_service: KernelEntityService,
        dictionary_service: DictionaryPort,
        provenance_service: ProvenanceServiceLike | None = None,
        relation_claim_service: RelationClaimServiceLike | None = None,
    ) -> None:
        self._entity_service = entity_service
        self._dictionary_service = dictionary_service
        self._provenance_service = provenance_service
        self._relation_claim_service = relation_claim_service

    def validate_claim_request(
        self,
        *,
        space_id: str,
        request: KernelRelationClaimCreateRequest,
        check_existing_claims: bool = True,
    ) -> KernelGraphValidationResponse:
        triple_validation = self.validate_triple(
            space_id=space_id,
            request=KernelRelationTripleValidationRequest(
                source_entity_id=request.source_entity_id,
                target_entity_id=request.target_entity_id,
                relation_type=request.relation_type,
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                source_document_ref=request.source_document_ref,
            ),
        )
        ai_provenance_error = self._claim_ai_provenance_error(request)
        if (
            ai_provenance_error is not None
            and triple_validation.normalized_relation_type is not None
        ):
            return self._response(
                valid=False,
                code="missing_ai_provenance",
                message=ai_provenance_error,
                severity="blocking",
                normalized_relation_type=triple_validation.normalized_relation_type,
                source_type=triple_validation.source_type,
                target_type=triple_validation.target_type,
                requires_evidence=triple_validation.requires_evidence,
                profile=triple_validation.profile,
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
            )
        if (
            not check_existing_claims
            or self._relation_claim_service is None
            or triple_validation.normalized_relation_type is None
        ):
            return triple_validation

        resolved_entities = self._resolve_space_entities(
            space_id=space_id,
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
        )
        if resolved_entities is None:
            return triple_validation

        duplicate_claim_ids, conflicting_claim_ids = self._find_claim_conflicts(
            research_space_id=space_id,
            source_entity_id=str(resolved_entities.source.id),
            target_entity_id=str(resolved_entities.target.id),
            relation_type=triple_validation.normalized_relation_type,
            polarity="SUPPORT",
            claim_text=_normalize_optional_text(request.claim_text),
            source_document_ref=_normalize_optional_text(request.source_document_ref),
        )
        if duplicate_claim_ids:
            return self._response(
                valid=False,
                code="duplicate_claim",
                message="An equivalent support claim already exists in this research space.",
                severity="blocking",
                claim_ids=duplicate_claim_ids,
                normalized_relation_type=triple_validation.normalized_relation_type,
                source_type=triple_validation.source_type,
                target_type=triple_validation.target_type,
                requires_evidence=triple_validation.requires_evidence,
                profile=triple_validation.profile,
                validation_state=triple_validation.validation_state,
                persistability=triple_validation.persistability,
            )
        if conflicting_claim_ids:
            return self._response(
                valid=False,
                code="conflicting_claim",
                message="An opposing claim already exists for this triple in this research space.",
                severity="blocking",
                claim_ids=conflicting_claim_ids,
                normalized_relation_type=triple_validation.normalized_relation_type,
                source_type=triple_validation.source_type,
                target_type=triple_validation.target_type,
                requires_evidence=triple_validation.requires_evidence,
                profile=triple_validation.profile,
                validation_state=triple_validation.validation_state,
                persistability=triple_validation.persistability,
            )
        return triple_validation

    def validate_triple(  # noqa: PLR0911
        self,
        *,
        space_id: str,
        request: KernelRelationTripleValidationRequest,
    ) -> KernelGraphValidationResponse:
        resolved_entities = self._resolve_space_entities(
            space_id=space_id,
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
        )
        if resolved_entities is None:
            return self._response(
                valid=False,
                code="unknown_entity",
                message="Source or target entity was not found in the research space.",
                severity="blocking",
                validation_state="ENDPOINT_UNRESOLVED",
                persistability="NON_PERSISTABLE",
            )

        normalized_relation_type = canonicalize_dictionary_relation_type(
            self._dictionary_service,
            request.relation_type,
        )
        if not normalized_relation_type:
            return self._response(
                valid=False,
                code="invalid_relation_type",
                message="relation_type is required.",
                severity="blocking",
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
            )

        source_type = resolved_entities.source.entity_type
        target_type = resolved_entities.target.entity_type
        relation_definition = self._dictionary_service.get_relation_type(
            normalized_relation_type,
            include_inactive=True,
        )
        if relation_definition is None:
            return self._response(
                valid=False,
                code="unknown_relation_type",
                message=(
                    f"Relation type {normalized_relation_type} is not approved."
                ),
                severity="blocking",
                validation_state="UNDEFINED",
                persistability="NON_PERSISTABLE",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                next_actions=[
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="RELATION_TYPE",
                        reason=(
                            "No approved relation type captures this meaning yet."
                        ),
                        endpoint="/v1/dictionary/proposals/relation-types",
                        payload={
                            "id": normalized_relation_type,
                            "display_name": (
                                normalized_relation_type.replace("_", " ").title()
                            ),
                            "description": (
                                "Proposed relation type discovered during graph validation."
                            ),
                            "domain_context": "general",
                            "rationale": (
                                "Claim validation found a relation type reference that is not yet approved in the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "source_type": source_type,
                                "target_type": target_type,
                            },
                            "source_ref": (
                                "graph-validation:relation-type:"
                                f"{normalized_relation_type.lower()}"
                            ),
                        },
                    ),
                ],
            )

        exact_constraint = self._get_exact_constraint(
            source_type=source_type,
            relation_type=normalized_relation_type,
            target_type=target_type,
        )
        profile = exact_constraint.profile if exact_constraint is not None else None

        if not self._dictionary_service.is_relation_allowed(
            source_type,
            normalized_relation_type,
            target_type,
        ):
            if exact_constraint is not None:
                next_actions = [
                    GraphValidationNextAction(
                        action="request_dictionary_review",
                        reason=(
                            "The current dictionary already has an active constraint for this triple."
                        ),
                        endpoint="/v1/dictionary/relation-constraints",
                        payload={
                            "source_type": source_type,
                            "relation_type": normalized_relation_type,
                            "target_type": target_type,
                            "current_profile": profile or "FORBIDDEN",
                        },
                    ),
                ]
            else:
                next_actions = [
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="RELATION_CONSTRAINT",
                        reason=(
                            "The current dictionary does not allow this triple."
                        ),
                        endpoint="/v1/dictionary/proposals/relation-constraints",
                        payload={
                            "source_type": source_type,
                            "relation_type": normalized_relation_type,
                            "target_type": target_type,
                            "rationale": (
                                "Claim validation found a triple that is not yet approved by the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "source_type": source_type,
                                "target_type": target_type,
                                "relation_type": normalized_relation_type,
                            },
                            "is_allowed": True,
                            "requires_evidence": True,
                            "profile": "REVIEW_ONLY",
                            "source_ref": (
                                "graph-validation:relation-constraint:"
                                f"{source_type.lower()}:{normalized_relation_type.lower()}:"
                                f"{target_type.lower()}"
                            ),
                        },
                    ),
                ]
            return self._response(
                valid=False,
                code="relation_constraint_not_allowed",
                message=(
                    "This source, relation, and target combination is not approved."
                ),
                severity="blocking",
                validation_state="FORBIDDEN",
                persistability="NON_PERSISTABLE",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                profile=profile or "FORBIDDEN",
                next_actions=next_actions,
            )

        requires_evidence = self._dictionary_service.requires_evidence(
            source_type,
            normalized_relation_type,
            target_type,
        )
        if requires_evidence and not self._has_evidence(request):
            return self._response(
                valid=False,
                code="insufficient_evidence",
                message="This relation requires supporting evidence before promotion.",
                severity="blocking",
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                requires_evidence=True,
                profile=profile,
                next_actions=[
                    GraphValidationNextAction(
                        action="attach_evidence",
                        reason=(
                            "Add evidence_summary, evidence_sentence, or a source document ref."
                        ),
                    ),
                ],
            )

        if profile == "REVIEW_ONLY":
            return self._response(
                valid=True,
                code="relation_constraint_review_only",
                message=(
                    "This triple is allowed, but it should stay in review before promotion."
                ),
                severity="warning",
                validation_state="ALLOWED",
                persistability="NON_PERSISTABLE",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                requires_evidence=requires_evidence,
                profile=profile,
                next_actions=[
                    GraphValidationNextAction(
                        action="manual_review_before_promotion",
                        reason="The matching constraint uses REVIEW_ONLY governance.",
                    ),
                ],
            )

        return self._response(
            valid=True,
            code="allowed",
            message="The triple is valid for claim creation.",
            severity="info",
            validation_state="ALLOWED",
            persistability="PERSISTABLE",
            normalized_relation_type=normalized_relation_type,
            source_type=source_type,
            target_type=target_type,
            requires_evidence=requires_evidence,
            profile=profile or "ALLOWED",
        )

    def validate_entity_type(
        self,
        *,
        request: DictionaryEntityTypeValidationRequest,
    ) -> KernelGraphValidationResponse:
        normalized_entity_type = _normalize_entity_type(request.entity_type)
        entity_type = self._dictionary_service.get_entity_type(
            normalized_entity_type,
            include_inactive=True,
        )
        if entity_type is None:
            return self._response(
                valid=False,
                code="unknown_entity_type",
                message=f"Entity type {normalized_entity_type} is not approved.",
                severity="blocking",
                next_actions=[
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="ENTITY_TYPE",
                        reason="No approved entity type matches this identifier.",
                        endpoint="/v1/dictionary/proposals/entity-types",
                        payload={
                            "id": normalized_entity_type,
                            "display_name": normalized_entity_type.replace(
                                "_",
                                " ",
                            ).title(),
                            "domain_context": "general",
                            "description": (
                                "Proposed entity type discovered during graph validation."
                            ),
                            "rationale": (
                                "Entity validation found an entity type reference that is not yet approved in the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "entity_type": normalized_entity_type,
                            },
                            "expected_properties": {},
                            "source_ref": (
                                "graph-validation:entity-type:"
                                f"{normalized_entity_type.lower()}"
                            ),
                        },
                    ),
                ],
            )
        if not entity_type.is_active or entity_type.review_status != "ACTIVE":
            return self._response(
                valid=False,
                code="inactive_entity_type",
                message=(
                    f"Entity type {normalized_entity_type} exists but is not active."
                ),
                severity="blocking",
                next_actions=[
                    GraphValidationNextAction(
                        action="request_dictionary_review",
                        reason=(
                            "The entity type exists, but it must be reactivated or approved before writes."
                        ),
                        endpoint=(
                            f"/v1/dictionary/entity-types/{normalized_entity_type}/review-status"
                        ),
                        payload={
                            "entity_type": normalized_entity_type,
                            "review_status": "ACTIVE",
                        },
                    ),
                ],
            )
        return self._response(
            valid=True,
            code="allowed",
            message="The entity type is approved.",
            severity="info",
        )

    def validate_entity_write(
        self,
        *,
        request: KernelEntityCreateRequest,
    ) -> KernelGraphValidationResponse:
        return self.validate_entity_type(
            request=DictionaryEntityTypeValidationRequest(
                entity_type=request.entity_type,
            ),
        )

    def validate_observation_write(  # noqa: PLR0911
        self,
        *,
        space_id: str,
        request: KernelObservationCreateRequest,
    ) -> KernelGraphValidationResponse:
        subject = self._entity_service.get_entity(str(request.subject_id))
        if subject is None or str(subject.research_space_id) != str(space_id):
            return self._response(
                valid=False,
                code="unknown_subject",
                message="Subject entity was not found in the research space.",
                severity="blocking",
                validation_state="ENDPOINT_UNRESOLVED",
                persistability="NON_PERSISTABLE",
                validation_reason="observation_subject_not_found",
                next_actions=[
                    GraphValidationNextAction(
                        action="resolve_subject_entity",
                        reason=(
                            "Select an existing entity in this research space before recording the observation."
                        ),
                    ),
                ],
            )

        variable = self._dictionary_service.get_variable(request.variable_id)
        if variable is None:
            inferred_data_type = _infer_variable_data_type(request.value)
            return self._response(
                valid=False,
                code="unknown_variable",
                message=f"Variable {request.variable_id} is not approved.",
                severity="blocking",
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
                validation_reason="observation_variable_not_found",
                next_actions=[
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="VARIABLE",
                        reason=(
                            "Propose and approve the variable before recording observations."
                        ),
                        endpoint="/v1/dictionary/proposals/variables",
                        payload={
                            "id": request.variable_id,
                            "canonical_name": request.variable_id.lower(),
                            "display_name": _variable_display_name(
                                request.variable_id,
                            ),
                            "data_type": inferred_data_type,
                            "domain_context": "general",
                            "sensitivity": "INTERNAL",
                            "constraints": {},
                            "description": (
                                "Proposed variable discovered during observation validation."
                            ),
                            "rationale": (
                                "Observation validation found a variable reference that is not yet approved in the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "observation_origin": request.observation_origin,
                                "value_preview": _value_preview(request.value),
                                "inferred_data_type": inferred_data_type,
                            },
                            "source_ref": (
                                f"graph-validation:variable:{request.variable_id.lower()}"
                            ),
                        },
                    ),
                ],
            )

        try:
            coerce_observation_value_for_data_type(
                variable_id=request.variable_id,
                data_type=variable.data_type,
                value=request.value,
            )
        except ObservationValueValidationError as exc:
            return self._response(
                valid=False,
                code="invalid_value_for_variable",
                message=exc.message,
                severity="blocking",
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
                validation_reason=exc.code,
            )

        if (
            request.observation_origin != "MANUAL"
            and request.provenance_id is None
        ):
            return self._response(
                valid=False,
                code="missing_provenance",
                message=(
                    "Imported or AI-authored observations require a provenance_id."
                ),
                severity="blocking",
                validation_state="INVALID_COMPONENTS",
                persistability="NON_PERSISTABLE",
                validation_reason="observation_requires_provenance",
                next_actions=[
                    GraphValidationNextAction(
                        action="attach_provenance",
                        reason=(
                            "Link the observation to an existing provenance record in this research space."
                        ),
                    ),
                ],
            )

        if request.provenance_id is not None and self._provenance_service is not None:
            provenance = self._provenance_service.get_provenance(
                str(request.provenance_id),
            )
            if provenance is None:
                return self._response(
                    valid=False,
                    code="unknown_provenance",
                    message="The supplied provenance_id was not found.",
                    severity="blocking",
                    validation_state="ENDPOINT_UNRESOLVED",
                    persistability="NON_PERSISTABLE",
                    validation_reason="observation_provenance_not_found",
                    next_actions=[
                        GraphValidationNextAction(
                            action="attach_provenance",
                            reason=(
                                "Use a provenance record that exists in this research space."
                            ),
                        ),
                    ],
                )
            if str(provenance.research_space_id) != str(space_id):
                return self._response(
                    valid=False,
                    code="cross_space_provenance",
                    message=(
                        "The supplied provenance_id belongs to a different research space."
                    ),
                    severity="blocking",
                    validation_state="INVALID_COMPONENTS",
                    persistability="NON_PERSISTABLE",
                    validation_reason="observation_provenance_cross_space",
                    next_actions=[
                        GraphValidationNextAction(
                            action="attach_provenance",
                            reason=(
                                "Choose a provenance record that belongs to this research space."
                            ),
                        ),
                    ],
                )

        return self._response(
            valid=True,
            code="allowed",
            message="The observation is valid for recording.",
            severity="info",
            validation_state="ALLOWED",
            persistability="PERSISTABLE",
            validation_reason="observation_validated",
        )

    def validate_relation_type(
        self,
        *,
        request: DictionaryRelationTypeValidationRequest,
    ) -> KernelGraphValidationResponse:
        normalized_relation_type = canonicalize_dictionary_relation_type(
            self._dictionary_service,
            request.relation_type,
        )
        if not normalized_relation_type:
            return self._response(
                valid=False,
                code="invalid_relation_type",
                message="relation_type is required.",
                severity="blocking",
            )
        relation_type = self._dictionary_service.get_relation_type(
            normalized_relation_type,
            include_inactive=True,
        )
        if relation_type is None:
            return self._response(
                valid=False,
                code="unknown_relation_type",
                message=f"Relation type {normalized_relation_type} is not approved.",
                severity="blocking",
                normalized_relation_type=normalized_relation_type,
                next_actions=[
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="RELATION_TYPE",
                        reason="No approved relation type matches this identifier.",
                        endpoint="/v1/dictionary/proposals/relation-types",
                        payload={
                            "id": normalized_relation_type,
                            "display_name": normalized_relation_type.replace(
                                "_",
                                " ",
                            ).title(),
                            "domain_context": "general",
                            "description": (
                                "Proposed relation type discovered during graph validation."
                            ),
                            "rationale": (
                                "Relation-type validation found a relation type reference that is not yet approved in the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "relation_type": normalized_relation_type,
                            },
                            "source_ref": (
                                "graph-validation:relation-type:"
                                f"{normalized_relation_type.lower()}"
                            ),
                        },
                    ),
                ],
            )
        return self._response(
            valid=True,
            code="allowed",
            message="The relation type is approved.",
            severity="info",
            normalized_relation_type=normalized_relation_type,
        )

    def validate_relation_constraint(  # noqa: PLR0911
        self,
        *,
        request: DictionaryRelationConstraintValidationRequest,
    ) -> KernelGraphValidationResponse:
        source_type = request.source_type.strip().upper()
        target_type = request.target_type.strip().upper()
        relation_validation = self.validate_relation_type(
            request=DictionaryRelationTypeValidationRequest(
                relation_type=request.relation_type,
            ),
        )
        if not relation_validation.valid:
            return relation_validation
        source_validation = self.validate_entity_type(
            request=DictionaryEntityTypeValidationRequest(entity_type=source_type),
        )
        if not source_validation.valid:
            return source_validation
        target_validation = self.validate_entity_type(
            request=DictionaryEntityTypeValidationRequest(entity_type=target_type),
        )
        if not target_validation.valid:
            return target_validation

        normalized_relation_type = relation_validation.normalized_relation_type
        if normalized_relation_type is None:
            return self._response(
                valid=False,
                code="invalid_relation_type",
                message="relation_type is required.",
                severity="blocking",
            )

        exact_constraint = self._get_exact_constraint(
            source_type=source_type,
            relation_type=normalized_relation_type,
            target_type=target_type,
        )
        profile = exact_constraint.profile if exact_constraint is not None else "ALLOWED"
        requires_evidence = self._dictionary_service.requires_evidence(
            source_type,
            normalized_relation_type,
            target_type,
        )
        if not self._dictionary_service.is_relation_allowed(
            source_type,
            normalized_relation_type,
            target_type,
        ):
            if exact_constraint is not None:
                next_actions = [
                    GraphValidationNextAction(
                        action="request_dictionary_review",
                        reason=(
                            "The current dictionary already has an active constraint for this triple."
                        ),
                        endpoint="/v1/dictionary/relation-constraints",
                        payload={
                            "source_type": source_type,
                            "relation_type": normalized_relation_type,
                            "target_type": target_type,
                            "current_profile": profile,
                        },
                    ),
                ]
            else:
                next_actions = [
                    GraphValidationNextAction(
                        action="create_dictionary_proposal",
                        proposal_type="RELATION_CONSTRAINT",
                        reason="The dictionary must explicitly approve this triple.",
                        endpoint="/v1/dictionary/proposals/relation-constraints",
                        payload={
                            "source_type": source_type,
                            "relation_type": normalized_relation_type,
                            "target_type": target_type,
                            "rationale": (
                                "Relation-constraint validation found a triple that is not yet approved by the dictionary."
                            ),
                            "evidence_payload": {
                                "source": "graph_validation",
                                "source_type": source_type,
                                "target_type": target_type,
                                "relation_type": normalized_relation_type,
                            },
                            "is_allowed": True,
                            "requires_evidence": requires_evidence,
                            "profile": "REVIEW_ONLY",
                            "source_ref": (
                                "graph-validation:relation-constraint:"
                                f"{source_type.lower()}:{normalized_relation_type.lower()}:"
                                f"{target_type.lower()}"
                            ),
                        },
                    ),
                ]
            return self._response(
                valid=False,
                code="relation_constraint_not_allowed",
                message="This triple is not approved by the current dictionary.",
                severity="blocking",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                requires_evidence=requires_evidence,
                profile=profile,
                next_actions=next_actions,
            )
        if requires_evidence and not request.has_evidence:
            return self._response(
                valid=False,
                code="insufficient_evidence",
                message="This triple requires evidence.",
                severity="blocking",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                requires_evidence=requires_evidence,
                profile=profile,
            )
        if profile == "REVIEW_ONLY":
            return self._response(
                valid=True,
                code="relation_constraint_review_only",
                message="This triple is approved for review-only usage.",
                severity="warning",
                normalized_relation_type=normalized_relation_type,
                source_type=source_type,
                target_type=target_type,
                requires_evidence=requires_evidence,
                profile=profile,
            )
        return self._response(
            valid=True,
            code="allowed",
            message="This triple is approved.",
            severity="info",
            normalized_relation_type=normalized_relation_type,
            source_type=source_type,
            target_type=target_type,
            requires_evidence=requires_evidence,
            profile=profile,
        )

    def _resolve_space_entities(
        self,
        *,
        space_id: str,
        source_entity_id: UUID,
        target_entity_id: UUID,
    ) -> _ResolvedClaimEntities | None:
        source_entity = self._entity_service.get_entity(str(source_entity_id))
        target_entity = self._entity_service.get_entity(str(target_entity_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != space_id
            or str(target_entity.research_space_id) != space_id
        ):
            return None
        return _ResolvedClaimEntities(source=source_entity, target=target_entity)

    def _get_exact_constraint(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> RelationConstraint | None:
        constraints = self._dictionary_service.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=False,
        )
        for constraint in constraints:
            if constraint.target_type == target_type and constraint.is_active:
                return constraint
        return None

    def _find_claim_conflicts(
        self,
        *,
        research_space_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        polarity: str,
        claim_text: str | None,
        source_document_ref: str | None,
    ) -> tuple[list[str], list[str]]:
        if self._relation_claim_service is None:
            return [], []
        related_claims = self._relation_claim_service.list_by_research_space(
            research_space_id,
            relation_type=relation_type,
        )
        duplicate_claim_ids: list[str] = []
        conflicting_claim_ids: list[str] = []
        for existing_claim in related_claims:
            if existing_claim.claim_status == "REJECTED":
                continue
            if not self._claim_matches_request(
                existing_claim,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
            ):
                continue
            if existing_claim.polarity == polarity and self._claim_duplicate_matches(
                existing_claim,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                polarity=polarity,
                claim_text=claim_text,
                source_document_ref=source_document_ref,
            ):
                duplicate_claim_ids.append(str(existing_claim.id))
            elif existing_claim.polarity == "REFUTE":
                conflicting_claim_ids.append(str(existing_claim.id))
        return duplicate_claim_ids, conflicting_claim_ids

    @staticmethod
    def _claim_matches_request(
        claim: KernelRelationClaim,
        *,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
    ) -> bool:
        metadata = dict(claim.metadata_payload)
        return (
            str(claim.relation_type) == relation_type
            and str(metadata.get("source_entity_id", "")) == source_entity_id
            and str(metadata.get("target_entity_id", "")) == target_entity_id
        )

    def _claim_duplicate_matches(
        self,
        claim: KernelRelationClaim,
        *,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        polarity: str,
        claim_text: str | None,
        source_document_ref: str | None,
    ) -> bool:
        return (
            self._claim_matches_request(
                claim,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
            )
            and str(claim.polarity) == polarity
            and _normalize_optional_text(claim.claim_text) == claim_text
            and _normalize_optional_text(claim.source_document_ref) == source_document_ref
        )

    def _response(  # noqa: PLR0913
        self,
        *,
        valid: bool,
        code: GraphValidationCode,
        message: str,
        severity: GraphValidationSeverity,
        next_actions: list[GraphValidationNextAction] | None = None,
        claim_ids: list[str] | None = None,
        normalized_relation_type: str | None = None,
        source_type: str | None = None,
        target_type: str | None = None,
        requires_evidence: bool | None = None,
        profile: str | None = None,
        validation_state: str | None = None,
        persistability: str | None = None,
        validation_reason: str | None = None,
    ) -> KernelGraphValidationResponse:
        return KernelGraphValidationResponse(
            valid=valid,
            code=code,
            message=message,
            severity=severity,
            next_actions=next_actions or [],
            claim_ids=claim_ids or [],
            normalized_relation_type=normalized_relation_type,
            source_type=source_type,
            target_type=target_type,
            requires_evidence=requires_evidence,
            profile=profile,
            validation_state=validation_state,
            validation_reason=validation_reason or _VALIDATION_REASON_BY_CODE.get(code),
            persistability=persistability,
        )

    @staticmethod
    def _claim_ai_provenance_error(
        request: KernelRelationClaimCreateRequest,
    ) -> str | None:
        if not GraphValidationService._is_ai_authored_claim(request):
            return None
        if _normalize_optional_text(request.agent_run_id) is None:
            return "AI-authored claims require agent_run_id."
        if request.ai_provenance is None:
            return "AI-authored claims require ai_provenance audit metadata."
        if (
            not request.ai_provenance.evidence_references
            and _normalize_optional_text(request.source_document_ref) is None
        ):
            return (
                "AI-authored claims require evidence_references or "
                "source_document_ref in the provenance envelope."
            )
        return None

    @staticmethod
    def _is_ai_authored_claim(request: KernelRelationClaimCreateRequest) -> bool:
        if request.ai_provenance is not None:
            return True
        if _normalize_optional_text(request.agent_run_id) is not None:
            return True
        evidence_source = _normalize_optional_text(request.evidence_sentence_source)
        if evidence_source is not None and evidence_source.lower() in {
            "ai_generated",
            "artana_generated",
            "llm_generated",
        }:
            return True
        for key in ("origin", "source", "author_type", "created_by"):
            marker = request.metadata.get(key)
            if isinstance(marker, str) and marker.strip().lower() in {
                "ai",
                "agent",
                "artana",
                "artana_kernel",
                "graph_harness",
                "llm",
            }:
                return True
        return "artana_idempotency_key" in request.metadata

    @staticmethod
    def _has_evidence(request: KernelRelationTripleValidationRequest) -> bool:
        return any(
            (
                request.evidence_summary,
                request.evidence_sentence,
                request.source_document_ref,
            ),
        )


__all__ = ["GraphValidationService"]
