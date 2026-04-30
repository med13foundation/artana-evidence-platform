"""Governed dictionary proposal service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.dictionary_models import DictionaryProposal
from artana_evidence_db.dictionary_proposal_merge_targets import (
    DictionaryProposalMergeTargetResolver,
)
from artana_evidence_db.dictionary_proposal_support import (
    REVIEWABLE_PROPOSAL_STATUSES,
    AppliedDictionaryObject,
    ProposalStatus,
    ProposalType,
    normalize_actor,
    normalize_dictionary_id,
    normalize_domain_context,
    normalize_optional_text,
    normalize_profile,
    normalize_required_text,
    normalize_source_ref,
    snapshot_proposal_model,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryChangelogModel,
    DictionaryProposalModel,
)
from artana_evidence_db.kernel_domain_models import (
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    RelationConstraint,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from sqlalchemy import select
from sqlalchemy.orm import Session


class DictionaryProposalService:
    """DB-owned governance workflow for dictionary change proposals."""

    def __init__(
        self,
        *,
        session: Session,
        dictionary_service: DictionaryPort,
    ) -> None:
        self._session = session
        self._dictionary = dictionary_service
        self._merge_targets = DictionaryProposalMergeTargetResolver(dictionary_service)

    def _get_model(self, proposal_id: str) -> DictionaryProposalModel:
        model = self._session.get(DictionaryProposalModel, proposal_id)
        if model is None:
            msg = f"Dictionary proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _require_reviewable_status(self, model: DictionaryProposalModel) -> None:
        if model.status not in REVIEWABLE_PROPOSAL_STATUSES:
            msg = f"Dictionary proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)

    def _set_review_decision(
        self,
        model: DictionaryProposalModel,
        *,
        status: ProposalStatus,
        reviewed_by: str,
        decision_reason: str | None = None,
        merge_target_type: str | None = None,
        merge_target_id: str | None = None,
    ) -> None:
        model.status = status
        model.reviewed_by = normalize_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = normalize_optional_text(decision_reason)
        model.merge_target_type = merge_target_type
        model.merge_target_id = merge_target_id

    def _record_proposal_change(
        self,
        *,
        model: DictionaryProposalModel,
        action: str,
        before_snapshot: JSONObject | None,
        changed_by: str | None,
    ) -> None:
        self._session.add(
            DictionaryChangelogModel(
                table_name=DictionaryProposalModel.__tablename__,
                record_id=model.id,
                action=action,
                before_snapshot=before_snapshot,
                after_snapshot=snapshot_proposal_model(model),
                changed_by=changed_by,
                source_ref=model.source_ref,
            ),
        )

    def _finalize_created_proposal(
        self,
        model: DictionaryProposalModel,
    ) -> DictionaryProposal:
        self._session.add(model)
        self._session.flush()
        self._record_proposal_change(
            model=model,
            action="CREATE",
            before_snapshot=None,
            changed_by=model.proposed_by,
        )
        return DictionaryProposal.model_validate(model, from_attributes=True)

    def _ensure_domain_context_exists(self, domain_context: str) -> None:
        contexts = self._dictionary.list_domain_contexts(include_inactive=False)
        if not any(context.id == domain_context for context in contexts):
            msg = f"Domain context '{domain_context}' not found"
            raise ValueError(msg)

    def _get_existing_idempotent_proposal(
        self,
        *,
        proposal_type: ProposalType,
        source_ref: str | None,
        identity_fields: dict[str, str | None],
    ) -> DictionaryProposal | None:
        normalized_source_ref = normalize_source_ref(source_ref)
        if normalized_source_ref is None:
            return None
        model = self._session.scalar(
            select(DictionaryProposalModel).where(
                DictionaryProposalModel.source_ref == normalized_source_ref,
            ),
        )
        if model is None:
            return None
        if model.proposal_type != proposal_type:
            msg = (
                "source_ref is already linked to a different dictionary proposal type"
            )
            raise ValueError(msg)
        for field_name, expected_value in identity_fields.items():
            if getattr(model, field_name) != expected_value:
                msg = (
                    "source_ref is already linked to a different dictionary proposal"
                )
                raise ValueError(msg)
        return DictionaryProposal.model_validate(model, from_attributes=True)

    def create_domain_context_proposal(
        self,
        *,
        domain_context_id: str,
        display_name: str,
        description: str | None = None,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a domain context."""
        normalized_domain_context = normalize_domain_context(domain_context_id)
        existing = self._get_existing_idempotent_proposal(
            proposal_type="DOMAIN_CONTEXT",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={"domain_context": normalized_domain_context},
        )
        if existing is not None:
            return existing
        if any(
            context.id == normalized_domain_context
            for context in self._dictionary.list_domain_contexts(include_inactive=True)
        ):
            msg = f"Domain context '{normalized_domain_context}' already exists"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="DOMAIN_CONTEXT",
            status="SUBMITTED",
            domain_context=normalized_domain_context,
            display_name=normalize_required_text(
                display_name,
                field_name="display_name",
            ),
            description=description,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_entity_type_proposal(  # noqa: PLR0913
        self,
        *,
        entity_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        external_ontology_ref: str | None = None,
        expected_properties: JSONObject | None = None,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for an entity type."""
        normalized_entity_type = normalize_dictionary_id(
            entity_type,
            field_name="entity_type",
        )
        normalized_domain_context = normalize_domain_context(domain_context)
        existing = self._get_existing_idempotent_proposal(
            proposal_type="ENTITY_TYPE",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={"entity_type": normalized_entity_type},
        )
        if existing is not None:
            return existing
        self._ensure_domain_context_exists(normalized_domain_context)
        if self._dictionary.get_entity_type(normalized_entity_type) is not None:
            msg = f"Entity type '{normalized_entity_type}' already exists"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="ENTITY_TYPE",
            status="SUBMITTED",
            entity_type=normalized_entity_type,
            display_name=normalize_required_text(
                display_name,
                field_name="display_name",
            ),
            description=normalize_required_text(
                description,
                field_name="description",
            ),
            domain_context=normalized_domain_context,
            external_ontology_ref=(
                external_ontology_ref.strip() if external_ontology_ref else None
            ),
            expected_properties=expected_properties or {},
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_relation_type_proposal(  # noqa: PLR0913
        self,
        *,
        relation_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        is_directional: bool = True,
        inverse_label: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a relation type."""
        normalized_relation_type = normalize_dictionary_id(
            relation_type,
            field_name="relation_type",
        )
        normalized_domain_context = normalize_domain_context(domain_context)
        existing = self._get_existing_idempotent_proposal(
            proposal_type="RELATION_TYPE",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={"relation_type": normalized_relation_type},
        )
        if existing is not None:
            return existing
        self._ensure_domain_context_exists(normalized_domain_context)
        if self._dictionary.get_relation_type(normalized_relation_type) is not None:
            msg = f"Relation type '{normalized_relation_type}' already exists"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="RELATION_TYPE",
            status="SUBMITTED",
            relation_type=normalized_relation_type,
            display_name=normalize_required_text(
                display_name,
                field_name="display_name",
            ),
            description=normalize_required_text(
                description,
                field_name="description",
            ),
            domain_context=normalized_domain_context,
            is_directional=is_directional,
            inverse_label=inverse_label.strip() if inverse_label else None,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_variable_proposal(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str,
        sensitivity: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a variable definition."""
        normalized_variable_id = normalize_dictionary_id(
            variable_id,
            field_name="variable_id",
        )
        normalized_domain_context = normalize_domain_context(domain_context)
        existing = self._get_existing_idempotent_proposal(
            proposal_type="VARIABLE",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={"variable_id": normalized_variable_id},
        )
        if existing is not None:
            return existing
        self._ensure_domain_context_exists(normalized_domain_context)
        if self._dictionary.get_variable(normalized_variable_id) is not None:
            msg = f"Variable '{normalized_variable_id}' already exists"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="VARIABLE",
            status="SUBMITTED",
            variable_id=normalized_variable_id,
            canonical_name=normalize_required_text(
                canonical_name,
                field_name="canonical_name",
            ),
            display_name=normalize_required_text(
                display_name,
                field_name="display_name",
            ),
            data_type=normalize_required_text(data_type, field_name="data_type").upper(),
            preferred_unit=preferred_unit.strip() if preferred_unit else None,
            constraints=constraints or {},
            domain_context=normalized_domain_context,
            sensitivity=normalize_required_text(
                sensitivity,
                field_name="sensitivity",
            ).upper(),
            description=description,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_relation_synonym_proposal(  # noqa: PLR0913
        self,
        *,
        relation_type_id: str,
        synonym: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        source: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a relation synonym."""
        normalized_relation_type = normalize_dictionary_id(
            relation_type_id,
            field_name="relation_type_id",
        )
        normalized_synonym = normalize_required_text(synonym, field_name="synonym")
        existing = self._get_existing_idempotent_proposal(
            proposal_type="RELATION_SYNONYM",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={
                "relation_type": normalized_relation_type,
                "synonym": normalized_synonym,
            },
        )
        if existing is not None:
            return existing
        if self._dictionary.get_relation_type(normalized_relation_type) is None:
            msg = f"Relation type '{normalized_relation_type}' not found"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="RELATION_SYNONYM",
            status="SUBMITTED",
            relation_type=normalized_relation_type,
            synonym=normalized_synonym,
            source=source.strip() if source else None,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_value_set_proposal(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        variable_id: str,
        name: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        description: str | None = None,
        external_ref: str | None = None,
        is_extensible: bool = False,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a value set."""
        normalized_value_set_id = normalize_required_text(
            value_set_id,
            field_name="value_set_id",
        )
        normalized_variable_id = normalize_required_text(
            variable_id,
            field_name="variable_id",
        )
        existing = self._get_existing_idempotent_proposal(
            proposal_type="VALUE_SET",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={"value_set_id": normalized_value_set_id},
        )
        if existing is not None:
            return existing
        variable = self._dictionary.get_variable(normalized_variable_id)
        if variable is None:
            msg = f"Variable '{normalized_variable_id}' not found"
            raise ValueError(msg)
        if variable.data_type != "CODED":
            msg = (
                f"Variable '{normalized_variable_id}' has data_type "
                f"'{variable.data_type}' and cannot have a value set"
            )
            raise ValueError(msg)
        if self._dictionary.get_value_set(normalized_value_set_id) is not None:
            msg = f"Value set '{normalized_value_set_id}' already exists"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="VALUE_SET",
            status="SUBMITTED",
            value_set_id=normalized_value_set_id,
            variable_id=normalized_variable_id,
            name=normalize_required_text(name, field_name="name"),
            description=description,
            external_ref=external_ref,
            is_extensible=is_extensible,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def create_value_set_item_proposal(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        code: str,
        display_label: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        synonyms: list[str] | None = None,
        external_ref: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a value-set item."""
        normalized_value_set_id = normalize_required_text(
            value_set_id,
            field_name="value_set_id",
        )
        normalized_code = normalize_required_text(code, field_name="code")
        existing = self._get_existing_idempotent_proposal(
            proposal_type="VALUE_SET_ITEM",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={
                "value_set_id": normalized_value_set_id,
                "code": normalized_code,
            },
        )
        if existing is not None:
            return existing
        if self._dictionary.get_value_set(normalized_value_set_id) is None:
            msg = f"Value set '{normalized_value_set_id}' not found"
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="VALUE_SET_ITEM",
            status="SUBMITTED",
            value_set_id=normalized_value_set_id,
            code=normalized_code,
            display_label=normalize_required_text(
                display_label,
                field_name="display_label",
            ),
            synonyms=list(synonyms or []),
            external_ref=external_ref,
            sort_order=sort_order,
            is_active_value=is_active,
            rationale=normalize_required_text(rationale, field_name="rationale"),
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def _ensure_relation_constraint_references(  # noqa: PLR0913
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> None:
        if self._dictionary.get_entity_type(source_type) is None:
            msg = f"Entity type '{source_type}' not found"
            raise ValueError(msg)
        if self._dictionary.get_relation_type(relation_type) is None:
            msg = f"Relation type '{relation_type}' not found"
            raise ValueError(msg)
        if self._dictionary.get_entity_type(target_type) is None:
            msg = f"Entity type '{target_type}' not found"
            raise ValueError(msg)

    def create_relation_constraint_proposal(  # noqa: PLR0913
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        rationale: str,
        proposed_by: str,
        evidence_payload: JSONObject | None = None,
        is_allowed: bool = True,
        requires_evidence: bool = True,
        profile: str = "ALLOWED",
        source_ref: str | None = None,
    ) -> DictionaryProposal:
        """Create a submitted proposal for a relation constraint."""
        normalized_source = normalize_dictionary_id(
            source_type,
            field_name="source_type",
        )
        normalized_relation = normalize_dictionary_id(
            relation_type,
            field_name="relation_type",
        )
        normalized_target = normalize_dictionary_id(
            target_type,
            field_name="target_type",
        )
        existing = self._get_existing_idempotent_proposal(
            proposal_type="RELATION_CONSTRAINT",
            source_ref=normalize_source_ref(source_ref),
            identity_fields={
                "source_type": normalized_source,
                "relation_type": normalized_relation,
                "target_type": normalized_target,
            },
        )
        if existing is not None:
            return existing
        normalized_profile = normalize_profile(profile)
        normalized_rationale = rationale.strip()
        if not normalized_rationale:
            msg = "rationale is required"
            raise ValueError(msg)

        self._ensure_relation_constraint_references(
            source_type=normalized_source,
            relation_type=normalized_relation,
            target_type=normalized_target,
        )
        existing_constraints = self._dictionary.get_constraints(
            source_type=normalized_source,
            relation_type=normalized_relation,
            include_inactive=False,
        )
        if any(
            constraint.target_type == normalized_target
            and constraint.review_status == "ACTIVE"
            for constraint in existing_constraints
        ):
            msg = (
                "Relation constraint already exists for "
                f"{normalized_source} -> {normalized_relation} -> {normalized_target}"
            )
            raise ValueError(msg)

        model = DictionaryProposalModel(
            id=str(uuid4()),
            proposal_type="RELATION_CONSTRAINT",
            status="SUBMITTED",
            source_type=normalized_source,
            relation_type=normalized_relation,
            target_type=normalized_target,
            is_allowed=is_allowed,
            requires_evidence=requires_evidence,
            profile=normalized_profile,
            rationale=normalized_rationale,
            evidence_payload=evidence_payload or {},
            proposed_by=normalize_actor(proposed_by),
            source_ref=normalize_source_ref(source_ref),
        )
        return self._finalize_created_proposal(model)

    def list_proposals(
        self,
        *,
        status: ProposalStatus | None = None,
        proposal_type: ProposalType | None = None,
        limit: int = 100,
    ) -> list[DictionaryProposal]:
        """List dictionary proposals ordered newest first."""
        stmt = select(DictionaryProposalModel)
        if status is not None:
            stmt = stmt.where(DictionaryProposalModel.status == status)
        if proposal_type is not None:
            stmt = stmt.where(DictionaryProposalModel.proposal_type == proposal_type)
        stmt = stmt.order_by(DictionaryProposalModel.created_at.desc()).limit(limit)
        return [
            DictionaryProposal.model_validate(model, from_attributes=True)
            for model in self._session.scalars(stmt).all()
        ]

    def get_proposal(self, proposal_id: str) -> DictionaryProposal:
        """Return one dictionary proposal."""
        return DictionaryProposal.model_validate(
            self._get_model(proposal_id),
            from_attributes=True,
        )

    def _approve_domain_context(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> DictionaryDomainContext:
        if model.domain_context is None or model.display_name is None:
            msg = "Domain context proposal is missing required fields"
            raise ValueError(msg)
        return self._dictionary.create_domain_context(
            domain_context_id=model.domain_context,
            display_name=model.display_name,
            description=model.description,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_entity_type(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> DictionaryEntityType:
        if (
            model.entity_type is None
            or model.display_name is None
            or model.description is None
            or model.domain_context is None
        ):
            msg = "Entity type proposal is missing required fields"
            raise ValueError(msg)
        self._ensure_domain_context_exists(model.domain_context)
        return self._dictionary.create_entity_type(
            entity_type=model.entity_type,
            display_name=model.display_name,
            description=model.description,
            domain_context=model.domain_context,
            external_ontology_ref=model.external_ontology_ref,
            expected_properties=model.expected_properties,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_variable(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> VariableDefinition:
        if (
            model.variable_id is None
            or model.canonical_name is None
            or model.display_name is None
            or model.data_type is None
            or model.domain_context is None
            or model.sensitivity is None
        ):
            msg = "Variable proposal is missing required fields"
            raise ValueError(msg)
        self._ensure_domain_context_exists(model.domain_context)
        return self._dictionary.create_variable(
            variable_id=model.variable_id,
            canonical_name=model.canonical_name,
            display_name=model.display_name,
            data_type=model.data_type,
            domain_context=model.domain_context,
            sensitivity=model.sensitivity,
            preferred_unit=model.preferred_unit,
            constraints=model.constraints,
            description=model.description,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_relation_type(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> DictionaryRelationType:
        if (
            model.relation_type is None
            or model.display_name is None
            or model.description is None
            or model.domain_context is None
            or model.is_directional is None
        ):
            msg = "Relation type proposal is missing required fields"
            raise ValueError(msg)
        self._ensure_domain_context_exists(model.domain_context)
        return self._dictionary.create_relation_type(
            relation_type=model.relation_type,
            display_name=model.display_name,
            description=model.description,
            domain_context=model.domain_context,
            is_directional=model.is_directional,
            inverse_label=model.inverse_label,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_relation_constraint(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> RelationConstraint:
        if (
            model.source_type is None
            or model.relation_type is None
            or model.target_type is None
            or model.is_allowed is None
            or model.requires_evidence is None
            or model.profile is None
        ):
            msg = "Relation constraint proposal is missing required fields"
            raise ValueError(msg)

        self._ensure_relation_constraint_references(
            source_type=model.source_type,
            relation_type=model.relation_type,
            target_type=model.target_type,
        )
        return self._dictionary.create_relation_constraint(
            source_type=model.source_type,
            relation_type=model.relation_type,
            target_type=model.target_type,
            is_allowed=model.is_allowed,
            requires_evidence=model.requires_evidence,
            profile=model.profile,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_relation_synonym(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> DictionaryRelationSynonym:
        if model.relation_type is None or model.synonym is None:
            msg = "Relation synonym proposal is missing required fields"
            raise ValueError(msg)
        return self._dictionary.create_relation_synonym(
            relation_type_id=model.relation_type,
            synonym=model.synonym,
            source=model.source,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_value_set(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> ValueSet:
        if (
            model.value_set_id is None
            or model.variable_id is None
            or model.name is None
            or model.is_extensible is None
        ):
            msg = "Value set proposal is missing required fields"
            raise ValueError(msg)
        return self._dictionary.create_value_set(
            value_set_id=model.value_set_id,
            variable_id=model.variable_id,
            name=model.name,
            description=model.description,
            external_ref=model.external_ref,
            is_extensible=model.is_extensible,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def _approve_value_set_item(
        self,
        model: DictionaryProposalModel,
        *,
        reviewed_by: str,
    ) -> ValueSetItem:
        if (
            model.value_set_id is None
            or model.code is None
            or model.display_label is None
            or model.is_active_value is None
        ):
            msg = "Value-set item proposal is missing required fields"
            raise ValueError(msg)
        return self._dictionary.create_value_set_item(
            value_set_id=model.value_set_id,
            code=model.code,
            display_label=model.display_label,
            synonyms=model.synonyms,
            external_ref=model.external_ref,
            sort_order=model.sort_order or 0,
            is_active=model.is_active_value,
            created_by=normalize_actor(reviewed_by),
            source_ref=model.source_ref,
        )

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> tuple[DictionaryProposal, AppliedDictionaryObject]:
        """Approve a submitted proposal and apply it to official dictionary state."""
        model = self._get_model(proposal_id)
        self._require_reviewable_status(model)
        before_snapshot = snapshot_proposal_model(model)
        applied: AppliedDictionaryObject

        if model.proposal_type == "DOMAIN_CONTEXT":
            applied = self._approve_domain_context(model, reviewed_by=reviewed_by)
            model.applied_domain_context_id = applied.id
        elif model.proposal_type == "ENTITY_TYPE":
            applied = self._approve_entity_type(model, reviewed_by=reviewed_by)
            model.applied_entity_type_id = applied.id
        elif model.proposal_type == "VARIABLE":
            applied = self._approve_variable(model, reviewed_by=reviewed_by)
            model.applied_variable_id = applied.id
        elif model.proposal_type == "RELATION_TYPE":
            applied = self._approve_relation_type(model, reviewed_by=reviewed_by)
            model.applied_relation_type_id = applied.id
        elif model.proposal_type == "RELATION_CONSTRAINT":
            applied = self._approve_relation_constraint(model, reviewed_by=reviewed_by)
            model.applied_constraint_id = applied.id
        elif model.proposal_type == "RELATION_SYNONYM":
            applied = self._approve_relation_synonym(model, reviewed_by=reviewed_by)
            model.applied_relation_synonym_id = applied.id
        elif model.proposal_type == "VALUE_SET":
            applied = self._approve_value_set(model, reviewed_by=reviewed_by)
            model.applied_value_set_id = applied.id
        elif model.proposal_type == "VALUE_SET_ITEM":
            applied = self._approve_value_set_item(model, reviewed_by=reviewed_by)
            model.applied_value_set_item_id = applied.id
        else:
            msg = f"Unsupported proposal type '{model.proposal_type}'"
            raise ValueError(msg)

        self._set_review_decision(
            model,
            status="APPROVED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
        )
        self._session.flush()
        self._record_proposal_change(
            model=model,
            action="APPROVE",
            before_snapshot=before_snapshot,
            changed_by=reviewed_by,
        )
        return (
            DictionaryProposal.model_validate(model, from_attributes=True),
            applied,
        )

    def reject_proposal(
        self,
        proposal_id: str,
        *,
        reviewed_by: str,
        decision_reason: str,
    ) -> DictionaryProposal:
        """Reject a submitted dictionary proposal."""
        model = self._get_model(proposal_id)
        self._require_reviewable_status(model)
        before_snapshot = snapshot_proposal_model(model)
        normalized_reason = decision_reason.strip()
        if not normalized_reason:
            msg = "decision_reason is required when rejecting a proposal"
            raise ValueError(msg)
        self._set_review_decision(
            model,
            status="REJECTED",
            reviewed_by=reviewed_by,
            decision_reason=normalized_reason,
        )
        self._session.flush()
        self._record_proposal_change(
            model=model,
            action="REJECT",
            before_snapshot=before_snapshot,
            changed_by=reviewed_by,
        )
        return DictionaryProposal.model_validate(model, from_attributes=True)

    def request_changes(
        self,
        proposal_id: str,
        *,
        reviewed_by: str,
        decision_reason: str,
    ) -> DictionaryProposal:
        """Move a proposal into changes-requested state with reviewer guidance."""
        model = self._get_model(proposal_id)
        self._require_reviewable_status(model)
        before_snapshot = snapshot_proposal_model(model)
        normalized_reason = decision_reason.strip()
        if not normalized_reason:
            msg = "decision_reason is required when requesting changes"
            raise ValueError(msg)
        self._set_review_decision(
            model,
            status="CHANGES_REQUESTED",
            reviewed_by=reviewed_by,
            decision_reason=normalized_reason,
        )
        self._session.flush()
        self._record_proposal_change(
            model=model,
            action="REQUEST_CHANGES",
            before_snapshot=before_snapshot,
            changed_by=reviewed_by,
        )
        return DictionaryProposal.model_validate(model, from_attributes=True)

    def merge_proposal(
        self,
        proposal_id: str,
        *,
        reviewed_by: str,
        target_id: str,
        decision_reason: str,
    ) -> DictionaryProposal:
        """Merge a proposal into an existing approved dictionary entry."""
        model = self._get_model(proposal_id)
        self._require_reviewable_status(model)
        before_snapshot = snapshot_proposal_model(model)
        normalized_reason = decision_reason.strip()
        if not normalized_reason:
            msg = "decision_reason is required when merging a proposal"
            raise ValueError(msg)
        merge_target_type, merge_target_id = self._merge_targets.resolve(
            model,
            target_id=target_id,
        )
        self._set_review_decision(
            model,
            status="MERGED",
            reviewed_by=reviewed_by,
            decision_reason=normalized_reason,
            merge_target_type=merge_target_type,
            merge_target_id=merge_target_id,
        )
        self._session.flush()
        self._record_proposal_change(
            model=model,
            action="MERGE",
            before_snapshot=before_snapshot,
            changed_by=reviewed_by,
        )
        return DictionaryProposal.model_validate(model, from_attributes=True)


__all__ = ["DictionaryProposalService"]
