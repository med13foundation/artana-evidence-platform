"""Dictionary helper utilities for extraction relation validation."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import ResearchSpaceSettings

_FULL_AUTO_CREATED_BY = "agent:extraction_validate_triple"
_FULL_AUTO_SOURCE_REF = "extraction:full_auto_validate_triple"
_DEFAULT_RELATION_DOMAIN_CONTEXT = "general"
_RELATION_SEARCH_LIMIT = 8
_FULL_AUTO_ENTITY_TYPE_DESCRIPTION = (
    "Auto-created by extraction validator in FULL_AUTO mode."
)


def _relation_match_priority(match_method: str) -> int:
    normalized = match_method.strip().lower()
    if normalized == "exact":
        return 0
    if normalized == "synonym":
        return 1
    if normalized == "fuzzy":
        return 2
    if normalized == "vector":
        return 3
    return 4


def _normalize_semantic_label(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _to_display_name(identifier: str) -> str:
    return (
        " ".join(
            token.capitalize()
            for token in identifier.replace("_", " ").split()
            if token
        )
        or identifier
    )


def _append_candidate_relation_type(
    *,
    candidate_relation_types: list[str],
    seen_relation_types: set[str],
    candidate_id: str,
) -> None:
    if not candidate_id or candidate_id in seen_relation_types:
        return
    candidate_relation_types.append(candidate_id)
    seen_relation_types.add(candidate_id)


def _search_relation_candidates(
    *,
    dictionary_service: DictionaryPort,
    relation_type: str,
    normalized_relation_type: str,
) -> list[str]:
    search_terms = [relation_type.strip(), normalized_relation_type]
    normalized_terms = [term for term in search_terms if term]
    if not normalized_terms:
        return []
    try:
        search_results = dictionary_service.dictionary_search(
            terms=normalized_terms,
            dimensions=["relation_types"],
            limit=_RELATION_SEARCH_LIMIT,
            include_inactive=False,
        )
    except (LookupError, ValueError):
        return []

    ranked_results = sorted(
        search_results,
        key=lambda item: (
            _relation_match_priority(item.match_method),
            -item.similarity_score,
        ),
    )
    return [
        normalize_relation_type(result.entry_id)
        for result in ranked_results
        if result.dimension == "relation_types"
        and normalize_relation_type(result.entry_id)
    ]


def _labels_match_semantic_key(labels: list[str], relation_label_key: str) -> bool:
    return any(
        _normalize_semantic_label(label) == relation_label_key
        for label in labels
        if label.strip()
    )


def _semantic_relation_candidates(
    *,
    dictionary_service: DictionaryPort,
    relation_type: str,
) -> list[str]:
    relation_label_key = _normalize_semantic_label(relation_type)
    if not relation_label_key:
        return []
    try:
        relation_types = dictionary_service.list_relation_types(
            include_inactive=False,
        )
    except (LookupError, ValueError):
        return []

    candidates: list[str] = []
    for relation in relation_types:
        if not relation.is_active or relation.review_status != "ACTIVE":
            continue
        relation_id = normalize_relation_type(relation.id)
        if not relation_id:
            continue
        labels = [relation.id, relation.display_name, relation.inverse_label or ""]
        if _labels_match_semantic_key(labels, relation_label_key):
            candidates.append(relation_id)
    return candidates


def _first_allowed_relation_type(
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    target_type: str,
    candidate_relation_types: list[str],
) -> str | None:
    for candidate_relation_type in candidate_relation_types:
        if dictionary_service.is_relation_allowed(
            source_type=source_type,
            relation_type=candidate_relation_type,
            target_type=target_type,
        ):
            return candidate_relation_type
    return None


def resolve_relation_mapping_candidate(
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    relation_type: str,
    target_type: str,
) -> str | None:
    normalized_relation_type = normalize_relation_type(relation_type)
    if not normalized_relation_type:
        return None

    candidate_relation_types: list[str] = []
    seen_relation_types: set[str] = set()

    direct_match = dictionary_service.get_relation_type(normalized_relation_type)
    if direct_match is not None:
        _append_candidate_relation_type(
            candidate_relation_types=candidate_relation_types,
            seen_relation_types=seen_relation_types,
            candidate_id=normalized_relation_type,
        )

    search_candidates = _search_relation_candidates(
        dictionary_service=dictionary_service,
        relation_type=relation_type,
        normalized_relation_type=normalized_relation_type,
    )
    semantic_candidates = _semantic_relation_candidates(
        dictionary_service=dictionary_service,
        relation_type=relation_type,
    )
    for candidate_id in [*search_candidates, *semantic_candidates]:
        _append_candidate_relation_type(
            candidate_relation_types=candidate_relation_types,
            seen_relation_types=seen_relation_types,
            candidate_id=candidate_id,
        )

    return _first_allowed_relation_type(
        dictionary_service=dictionary_service,
        source_type=source_type,
        target_type=target_type,
        candidate_relation_types=candidate_relation_types,
    )


def _build_full_auto_creation_settings() -> ResearchSpaceSettings:
    return {"dictionary_agent_creation_policy": "ACTIVE"}


def _ensure_full_auto_entity_type(
    *,
    dictionary_service: DictionaryPort,
    entity_type: str,
) -> tuple[bool, str]:
    normalized_entity_type = entity_type.strip().upper()
    if not normalized_entity_type:
        return False, "invalid_entity_type"

    outcome = "entity_type_already_active"
    existing_active = dictionary_service.get_entity_type(normalized_entity_type)
    if existing_active is None:
        existing_any = dictionary_service.get_entity_type(
            normalized_entity_type,
            include_inactive=True,
        )
        if existing_any is not None:
            outcome = "entity_type_activated"
            with contextlib.suppress(ValueError):
                dictionary_service.set_entity_type_review_status(
                    normalized_entity_type,
                    review_status="ACTIVE",
                    reviewed_by=_FULL_AUTO_CREATED_BY,
                )
        else:
            outcome = "entity_type_created"
            with contextlib.suppress(ValueError):
                dictionary_service.create_entity_type(
                    entity_type=normalized_entity_type,
                    display_name=_to_display_name(normalized_entity_type),
                    description=_FULL_AUTO_ENTITY_TYPE_DESCRIPTION,
                    domain_context=_DEFAULT_RELATION_DOMAIN_CONTEXT,
                    created_by=_FULL_AUTO_CREATED_BY,
                    source_ref=_FULL_AUTO_SOURCE_REF,
                    research_space_settings=_build_full_auto_creation_settings(),
                )
    refreshed_active = dictionary_service.get_entity_type(normalized_entity_type)
    if refreshed_active is None:
        failure_reason = {
            "entity_type_activated": "entity_type_activation_failed",
            "entity_type_created": "entity_type_creation_failed",
        }.get(outcome, "entity_type_lookup_failed")
        return False, failure_reason
    return True, outcome


def _ensure_full_auto_relation_type(
    *,
    dictionary_service: DictionaryPort,
    relation_type: str,
) -> tuple[bool, str]:
    normalized_relation_type = normalize_relation_type(relation_type)
    if not normalized_relation_type:
        return False, "invalid_relation_type"

    outcome = "relation_type_already_active"
    existing_active = dictionary_service.get_relation_type(normalized_relation_type)
    if existing_active is None:
        existing_any = dictionary_service.get_relation_type(
            normalized_relation_type,
            include_inactive=True,
        )
        if existing_any is not None:
            outcome = "relation_type_activated"
            with contextlib.suppress(ValueError):
                dictionary_service.set_relation_type_review_status(
                    normalized_relation_type,
                    review_status="ACTIVE",
                    reviewed_by=_FULL_AUTO_CREATED_BY,
                )
        else:
            outcome = "relation_type_created"
            with contextlib.suppress(ValueError):
                dictionary_service.create_relation_type(
                    relation_type=normalized_relation_type,
                    display_name=_to_display_name(normalized_relation_type),
                    description=(
                        "Auto-created by extraction validator in FULL_AUTO mode "
                        "after no equivalent canonical relation type was found."
                    ),
                    domain_context=_DEFAULT_RELATION_DOMAIN_CONTEXT,
                    created_by=_FULL_AUTO_CREATED_BY,
                    source_ref=_FULL_AUTO_SOURCE_REF,
                    research_space_settings=_build_full_auto_creation_settings(),
                )
    refreshed_active = dictionary_service.get_relation_type(normalized_relation_type)
    if refreshed_active is None:
        failure_reason = {
            "relation_type_activated": "relation_type_activation_failed",
            "relation_type_created": "relation_type_creation_failed",
        }.get(outcome, "relation_type_lookup_failed")
        return False, failure_reason
    return True, outcome


def ensure_full_auto_relation_dictionary_entry(
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    relation_type: str,
    target_type: str,
) -> tuple[bool, str]:
    source_ok, source_reason = _ensure_full_auto_entity_type(
        dictionary_service=dictionary_service,
        entity_type=source_type,
    )
    if not source_ok:
        return False, f"source_{source_reason}"

    target_ok, target_reason = _ensure_full_auto_entity_type(
        dictionary_service=dictionary_service,
        entity_type=target_type,
    )
    if not target_ok:
        return False, f"target_{target_reason}"

    normalized_relation_type = normalize_relation_type(relation_type)
    if not normalized_relation_type:
        return False, "invalid_relation_type"

    relation_ok, relation_reason = _ensure_full_auto_relation_type(
        dictionary_service=dictionary_service,
        relation_type=normalized_relation_type,
    )
    if not relation_ok:
        return False, relation_reason

    constraints = dictionary_service.get_constraints(
        source_type=source_type,
        relation_type=normalized_relation_type,
        include_inactive=True,
    )
    has_active_forbidden = any(
        constraint.target_type == target_type
        and constraint.is_active
        and constraint.review_status == "ACTIVE"
        and not constraint.is_allowed
        for constraint in constraints
    )
    if has_active_forbidden:
        return False, "active_forbidden_constraint_exists"

    if not dictionary_service.is_relation_allowed(
        source_type=source_type,
        relation_type=normalized_relation_type,
        target_type=target_type,
    ):
        with contextlib.suppress(ValueError):
            dictionary_service.create_relation_constraint(
                source_type=source_type,
                relation_type=normalized_relation_type,
                target_type=target_type,
                is_allowed=True,
                requires_evidence=True,
                created_by=_FULL_AUTO_CREATED_BY,
                source_ref=_FULL_AUTO_SOURCE_REF,
                research_space_settings=_build_full_auto_creation_settings(),
            )

    allowed_after = dictionary_service.is_relation_allowed(
        source_type=source_type,
        relation_type=normalized_relation_type,
        target_type=target_type,
    )
    return (
        (True, "dictionary_updated_for_relation")
        if allowed_after
        else (False, "relation_constraint_activation_failed")
    )
