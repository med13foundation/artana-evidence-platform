"""Dictionary search helpers owned by the standalone graph service."""

from __future__ import annotations

import math
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from artana_evidence_db.dictionary_support import DomainContextResolver
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from artana_evidence_db.kernel_domain_models import DictionarySearchResult
from sqlalchemy import and_, select

_SEARCH_METHOD_PRIORITY: dict[str, int] = {
    "exact": 0,
    "synonym": 1,
    "fuzzy": 2,
    "vector": 3,
}
_FUZZY_MATCH_THRESHOLD = 0.4
_VECTOR_MATCH_THRESHOLD = 0.7
_ALLOWED_SEARCH_DIMENSIONS: frozenset[str] = frozenset(
    {"variables", "entity_types", "relation_types", "constraints"},
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _embedding_from_db(value: object) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        if not stripped:
            return []
        try:
            return [float(token) for token in stripped.split(",") if token.strip()]
        except ValueError:
            return None
    return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for index, left_value in enumerate(left):
        right_value = right[index]
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    # Floating-point error can push a mathematically valid cosine slightly outside
    # the closed interval enforced by the public result schema.
    similarity = dot / math.sqrt(left_norm * right_norm)
    return max(0.0, min(similarity, 1.0))


def _fuzzy_similarity(term: str, candidate: str) -> float:
    return SequenceMatcher(None, term, candidate).ratio()


def _is_better_match(
    *,
    current_method: str,
    current_score: float,
    new_method: str,
    new_score: float,
) -> bool:
    current_priority = _SEARCH_METHOD_PRIORITY.get(current_method, 99)
    new_priority = _SEARCH_METHOD_PRIORITY.get(new_method, 99)
    if new_priority < current_priority:
        return True
    if new_priority > current_priority:
        return False
    return new_score > current_score


def _normalize_search_dimensions(dimensions: list[str] | None) -> list[str]:
    if not dimensions:
        return ["variables", "entity_types", "relation_types", "constraints"]

    normalized: list[str] = []
    for dimension in dimensions:
        value = dimension.strip().lower()
        if value not in _ALLOWED_SEARCH_DIMENSIONS:
            continue
        if value in normalized:
            continue
        normalized.append(value)
    return normalized


def _normalize_search_terms(terms: list[str]) -> list[str]:
    normalized: list[str] = []
    for term in terms:
        value = term.strip().casefold()
        if not value:
            continue
        if value in normalized:
            continue
        normalized.append(value)
    return normalized


def _domain_context_scope(
    domain_context: str | None,
) -> set[str] | None:
    normalized = DomainContextResolver.normalize(domain_context)
    if normalized is None:
        return None
    if normalized == DomainContextResolver.GENERAL_DEFAULT_DOMAIN:
        return {normalized}
    return {normalized, DomainContextResolver.GENERAL_DEFAULT_DOMAIN}


def _ranked_search_results(
    result_map: dict[tuple[str, str], DictionarySearchResult],
    *,
    limit: int,
) -> list[DictionarySearchResult]:
    ranked = sorted(
        result_map.values(),
        key=lambda result: (
            _SEARCH_METHOD_PRIORITY.get(result.match_method, 99),
            -result.similarity_score,
            result.dimension,
            result.entry_id,
        ),
    )
    return ranked[:limit]


def _upsert_search_result(
    result_map: dict[tuple[str, str], DictionarySearchResult],
    candidate: DictionarySearchResult,
) -> None:
    key = (candidate.dimension, candidate.entry_id)
    existing = result_map.get(key)
    if existing is None:
        result_map[key] = candidate
        return

    if _is_better_match(
        current_method=existing.match_method,
        current_score=existing.similarity_score,
        new_method=candidate.match_method,
        new_score=candidate.similarity_score,
    ):
        result_map[key] = candidate


def _search_variables(  # noqa: C901,PLR0912,PLR0913
    session: Session,
    *,
    terms: list[str],
    domain_context: str | None,
    query_embeddings: dict[str, list[float]] | None,
    include_inactive: bool,
    result_map: dict[tuple[str, str], DictionarySearchResult],
) -> None:
    stmt = select(VariableDefinitionModel)
    if not include_inactive:
        stmt = stmt.where(
            and_(
                VariableDefinitionModel.review_status == "ACTIVE",
                VariableDefinitionModel.is_active.is_(True),
            ),
        )
    domain_context_scope = _domain_context_scope(domain_context)
    if domain_context_scope is not None:
        stmt = stmt.where(
            VariableDefinitionModel.domain_context.in_(domain_context_scope),
        )
    variables = session.scalars(stmt).all()

    synonym_stmt = select(VariableSynonymModel)
    if not include_inactive:
        synonym_stmt = synonym_stmt.where(
            and_(
                VariableSynonymModel.review_status == "ACTIVE",
                VariableSynonymModel.is_active.is_(True),
            ),
        )
    synonym_rows = session.scalars(synonym_stmt).all()
    synonyms_by_variable: dict[str, list[str]] = {}
    for synonym_row in synonym_rows:
        synonyms_by_variable.setdefault(synonym_row.variable_id, []).append(
            synonym_row.synonym,
        )

    for variable in variables:
        variable_synonyms = synonyms_by_variable.get(variable.id, [])
        candidate: DictionarySearchResult | None = None
        for term in terms:
            exact_fields = [
                variable.id.casefold(),
                variable.canonical_name.casefold(),
                variable.display_name.casefold(),
            ]
            if term in exact_fields:
                candidate = DictionarySearchResult(
                    dimension="variables",
                    entry_id=str(variable.id),
                    display_name=str(variable.display_name),
                    description=(
                        str(variable.description) if variable.description else None
                    ),
                    domain_context=str(variable.domain_context),
                    match_method="exact",
                    similarity_score=1.0,
                    metadata={
                        "canonical_name": variable.canonical_name,
                        "data_type": variable.data_type,
                        "preferred_unit": variable.preferred_unit,
                        "sensitivity": variable.sensitivity,
                    },
                )
            elif term in [synonym.casefold() for synonym in variable_synonyms]:
                candidate = DictionarySearchResult(
                    dimension="variables",
                    entry_id=str(variable.id),
                    display_name=str(variable.display_name),
                    description=(
                        str(variable.description) if variable.description else None
                    ),
                    domain_context=str(variable.domain_context),
                    match_method="synonym",
                    similarity_score=1.0,
                    metadata={
                        "canonical_name": variable.canonical_name,
                        "data_type": variable.data_type,
                        "preferred_unit": variable.preferred_unit,
                        "sensitivity": variable.sensitivity,
                    },
                )
            else:
                fuzzy_candidates = [
                    variable.canonical_name.casefold(),
                    variable.display_name.casefold(),
                    *[synonym.casefold() for synonym in variable_synonyms],
                ]
                fuzzy_score = max(
                    (_fuzzy_similarity(term, text) for text in fuzzy_candidates),
                    default=0.0,
                )
                if fuzzy_score >= _FUZZY_MATCH_THRESHOLD:
                    candidate = DictionarySearchResult(
                        dimension="variables",
                        entry_id=str(variable.id),
                        display_name=str(variable.display_name),
                        description=(
                            str(variable.description) if variable.description else None
                        ),
                        domain_context=str(variable.domain_context),
                        match_method="fuzzy",
                        similarity_score=float(fuzzy_score),
                        metadata={
                            "canonical_name": variable.canonical_name,
                            "data_type": variable.data_type,
                            "preferred_unit": variable.preferred_unit,
                            "sensitivity": variable.sensitivity,
                        },
                    )
                elif query_embeddings is not None:
                    term_embedding = query_embeddings.get(term)
                    variable_embedding = _embedding_from_db(
                        variable.description_embedding,
                    )
                    if term_embedding is not None and variable_embedding is not None:
                        similarity = _cosine_similarity(
                            term_embedding,
                            variable_embedding,
                        )
                        if similarity >= _VECTOR_MATCH_THRESHOLD:
                            candidate = DictionarySearchResult(
                                dimension="variables",
                                entry_id=str(variable.id),
                                display_name=str(variable.display_name),
                                description=(
                                    str(variable.description)
                                    if variable.description
                                    else None
                                ),
                                domain_context=str(variable.domain_context),
                                match_method="vector",
                                similarity_score=float(similarity),
                                metadata={
                                    "canonical_name": variable.canonical_name,
                                    "data_type": variable.data_type,
                                    "preferred_unit": variable.preferred_unit,
                                    "sensitivity": variable.sensitivity,
                                },
                            )

            if candidate is not None:
                _upsert_search_result(result_map, candidate)
                candidate = None


def _search_entity_types(  # noqa: PLR0913
    session: Session,
    *,
    terms: list[str],
    domain_context: str | None,
    query_embeddings: dict[str, list[float]] | None,
    include_inactive: bool,
    result_map: dict[tuple[str, str], DictionarySearchResult],
) -> None:
    stmt = select(DictionaryEntityTypeModel)
    if not include_inactive:
        stmt = stmt.where(
            and_(
                DictionaryEntityTypeModel.review_status == "ACTIVE",
                DictionaryEntityTypeModel.is_active.is_(True),
            ),
        )
    domain_context_scope = _domain_context_scope(domain_context)
    if domain_context_scope is not None:
        stmt = stmt.where(
            DictionaryEntityTypeModel.domain_context.in_(domain_context_scope),
        )
    rows = session.scalars(stmt).all()

    for row in rows:
        for term in terms:
            exact_fields = [row.id.casefold(), row.display_name.casefold()]
            if term in exact_fields:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="entity_types",
                        entry_id=str(row.id),
                        display_name=str(row.display_name),
                        description=str(row.description),
                        domain_context=str(row.domain_context),
                        match_method="exact",
                        similarity_score=1.0,
                        metadata={
                            "external_ontology_ref": row.external_ontology_ref,
                            "expected_properties": row.expected_properties,
                        },
                    ),
                )
                continue

            fuzzy_score = max(
                _fuzzy_similarity(term, row.display_name.casefold()),
                _fuzzy_similarity(term, row.description.casefold()),
            )
            if fuzzy_score >= _FUZZY_MATCH_THRESHOLD:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="entity_types",
                        entry_id=str(row.id),
                        display_name=str(row.display_name),
                        description=str(row.description),
                        domain_context=str(row.domain_context),
                        match_method="fuzzy",
                        similarity_score=float(fuzzy_score),
                        metadata={
                            "external_ontology_ref": row.external_ontology_ref,
                            "expected_properties": row.expected_properties,
                        },
                    ),
                )
                continue

            if query_embeddings is None:
                continue
            term_embedding = query_embeddings.get(term)
            row_embedding = _embedding_from_db(row.description_embedding)
            if term_embedding is None or row_embedding is None:
                continue
            similarity = _cosine_similarity(term_embedding, row_embedding)
            if similarity < _VECTOR_MATCH_THRESHOLD:
                continue
            _upsert_search_result(
                result_map,
                DictionarySearchResult(
                    dimension="entity_types",
                    entry_id=str(row.id),
                    display_name=str(row.display_name),
                    description=str(row.description),
                    domain_context=str(row.domain_context),
                    match_method="vector",
                    similarity_score=float(similarity),
                    metadata={
                        "external_ontology_ref": row.external_ontology_ref,
                        "expected_properties": row.expected_properties,
                    },
                ),
            )


def _search_relation_types(  # noqa: C901, PLR0912, PLR0913
    session: Session,
    *,
    terms: list[str],
    domain_context: str | None,
    query_embeddings: dict[str, list[float]] | None,
    include_inactive: bool,
    result_map: dict[tuple[str, str], DictionarySearchResult],
) -> None:
    stmt = select(DictionaryRelationTypeModel)
    if not include_inactive:
        stmt = stmt.where(
            and_(
                DictionaryRelationTypeModel.review_status == "ACTIVE",
                DictionaryRelationTypeModel.is_active.is_(True),
            ),
        )
    domain_context_scope = _domain_context_scope(domain_context)
    if domain_context_scope is not None:
        stmt = stmt.where(
            DictionaryRelationTypeModel.domain_context.in_(domain_context_scope),
        )
    rows = session.scalars(stmt).all()
    if not rows:
        return
    relation_type_ids = [row.id for row in rows]
    synonym_stmt = select(DictionaryRelationSynonymModel)
    if relation_type_ids:
        synonym_stmt = synonym_stmt.where(
            DictionaryRelationSynonymModel.relation_type.in_(relation_type_ids),
        )
    if not include_inactive:
        synonym_stmt = synonym_stmt.where(
            and_(
                DictionaryRelationSynonymModel.review_status == "ACTIVE",
                DictionaryRelationSynonymModel.is_active.is_(True),
            ),
        )
    synonym_rows = session.scalars(synonym_stmt).all()
    synonyms_by_relation_type: dict[str, list[str]] = {}
    for synonym_row in synonym_rows:
        synonyms_by_relation_type.setdefault(synonym_row.relation_type, []).append(
            synonym_row.synonym,
        )

    for row in rows:
        relation_synonyms = synonyms_by_relation_type.get(row.id, [])
        relation_synonym_keys = [synonym.casefold() for synonym in relation_synonyms]
        for term in terms:
            exact_fields = [row.id.casefold(), row.display_name.casefold()]
            if term in exact_fields:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="relation_types",
                        entry_id=str(row.id),
                        display_name=str(row.display_name),
                        description=str(row.description),
                        domain_context=str(row.domain_context),
                        match_method="exact",
                        similarity_score=1.0,
                        metadata={
                            "is_directional": row.is_directional,
                            "inverse_label": row.inverse_label,
                        },
                    ),
                )
                continue

            if term in relation_synonym_keys:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="relation_types",
                        entry_id=str(row.id),
                        display_name=str(row.display_name),
                        description=str(row.description),
                        domain_context=str(row.domain_context),
                        match_method="synonym",
                        similarity_score=1.0,
                        metadata={
                            "is_directional": row.is_directional,
                            "inverse_label": row.inverse_label,
                            "synonyms": relation_synonyms,
                        },
                    ),
                )
                continue

            fuzzy_score = max(
                _fuzzy_similarity(term, row.display_name.casefold()),
                _fuzzy_similarity(term, row.description.casefold()),
            )
            if fuzzy_score >= _FUZZY_MATCH_THRESHOLD:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="relation_types",
                        entry_id=str(row.id),
                        display_name=str(row.display_name),
                        description=str(row.description),
                        domain_context=str(row.domain_context),
                        match_method="fuzzy",
                        similarity_score=float(fuzzy_score),
                        metadata={
                            "is_directional": row.is_directional,
                            "inverse_label": row.inverse_label,
                        },
                    ),
                )
                continue

            if query_embeddings is None:
                continue
            term_embedding = query_embeddings.get(term)
            row_embedding = _embedding_from_db(row.description_embedding)
            if term_embedding is None or row_embedding is None:
                continue
            similarity = _cosine_similarity(term_embedding, row_embedding)
            if similarity < _VECTOR_MATCH_THRESHOLD:
                continue
            _upsert_search_result(
                result_map,
                DictionarySearchResult(
                    dimension="relation_types",
                    entry_id=str(row.id),
                    display_name=str(row.display_name),
                    description=str(row.description),
                    domain_context=str(row.domain_context),
                    match_method="vector",
                    similarity_score=float(similarity),
                    metadata={
                        "is_directional": row.is_directional,
                        "inverse_label": row.inverse_label,
                    },
                ),
            )


def _search_constraints(
    session: Session,
    *,
    terms: list[str],
    domain_context: str | None,
    include_inactive: bool,
    result_map: dict[tuple[str, str], DictionarySearchResult],
) -> None:
    stmt = select(RelationConstraintModel)
    if not include_inactive:
        stmt = stmt.where(
            and_(
                RelationConstraintModel.review_status == "ACTIVE",
                RelationConstraintModel.is_active.is_(True),
            ),
        )
    rows = session.scalars(stmt).all()

    relation_type_stmt = select(DictionaryRelationTypeModel)
    if not include_inactive:
        relation_type_stmt = relation_type_stmt.where(
            and_(
                DictionaryRelationTypeModel.review_status == "ACTIVE",
                DictionaryRelationTypeModel.is_active.is_(True),
            ),
        )
    relation_context_map: dict[str, str] = {
        relation_type.id: relation_type.domain_context
        for relation_type in session.scalars(relation_type_stmt).all()
    }
    domain_context_scope = _domain_context_scope(domain_context)

    for row in rows:
        row_domain_context = relation_context_map.get(row.relation_type)
        if (
            domain_context_scope is not None
            and row_domain_context not in domain_context_scope
        ):
            continue

        display_name = f"{row.source_type} -[{row.relation_type}]-> {row.target_type}"
        tokens = [
            row.source_type.casefold(),
            row.relation_type.casefold(),
            row.target_type.casefold(),
            display_name.casefold(),
        ]
        for term in terms:
            if term in tokens:
                _upsert_search_result(
                    result_map,
                    DictionarySearchResult(
                        dimension="constraints",
                        entry_id=str(row.id),
                        display_name=display_name,
                        description="Allowed relation constraint",
                        domain_context=row_domain_context,
                        match_method="exact",
                        similarity_score=1.0,
                        metadata={
                            "source_type": row.source_type,
                            "relation_type": row.relation_type,
                            "target_type": row.target_type,
                            "is_allowed": row.is_allowed,
                            "requires_evidence": row.requires_evidence,
                        },
                    ),
                )
                continue

            fuzzy_score = max(_fuzzy_similarity(term, token) for token in tokens)
            if fuzzy_score < _FUZZY_MATCH_THRESHOLD:
                continue
            _upsert_search_result(
                result_map,
                DictionarySearchResult(
                    dimension="constraints",
                    entry_id=str(row.id),
                    display_name=display_name,
                    description="Allowed relation constraint",
                    domain_context=row_domain_context,
                    match_method="fuzzy",
                    similarity_score=float(fuzzy_score),
                    metadata={
                        "source_type": row.source_type,
                        "relation_type": row.relation_type,
                        "target_type": row.target_type,
                        "is_allowed": row.is_allowed,
                        "requires_evidence": row.requires_evidence,
                    },
                ),
            )


def search_dictionary_entries(  # noqa: PLR0913
    session: Session,
    *,
    terms: list[str],
    dimensions: list[str] | None = None,
    domain_context: str | None = None,
    limit: int = 50,
    query_embeddings: dict[str, list[float]] | None = None,
    include_inactive: bool = False,
) -> list[DictionarySearchResult]:
    normalized_terms = _normalize_search_terms(terms)
    if not normalized_terms:
        return []
    normalized_domain_context = DomainContextResolver.normalize(domain_context)
    normalized_dimensions = _normalize_search_dimensions(dimensions)
    if not normalized_dimensions:
        return []

    normalized_limit = max(1, min(limit, 500))
    result_map: dict[tuple[str, str], DictionarySearchResult] = {}

    if "variables" in normalized_dimensions:
        _search_variables(
            session,
            terms=normalized_terms,
            domain_context=normalized_domain_context,
            query_embeddings=query_embeddings,
            include_inactive=include_inactive,
            result_map=result_map,
        )
    if "entity_types" in normalized_dimensions:
        _search_entity_types(
            session,
            terms=normalized_terms,
            domain_context=normalized_domain_context,
            query_embeddings=query_embeddings,
            include_inactive=include_inactive,
            result_map=result_map,
        )
    if "relation_types" in normalized_dimensions:
        _search_relation_types(
            session,
            terms=normalized_terms,
            domain_context=normalized_domain_context,
            query_embeddings=query_embeddings,
            include_inactive=include_inactive,
            result_map=result_map,
        )
    if "constraints" in normalized_dimensions:
        _search_constraints(
            session,
            terms=normalized_terms,
            domain_context=normalized_domain_context,
            include_inactive=include_inactive,
            result_map=result_map,
        )

    return _ranked_search_results(result_map, limit=normalized_limit)


def search_dictionary_entries_by_domain(
    session: Session,
    *,
    domain_context: str,
    limit: int = 50,
    include_inactive: bool = False,
) -> list[DictionarySearchResult]:
    normalized_limit = max(1, min(limit, 500))
    normalized_context = DomainContextResolver.normalize(domain_context)
    context = normalized_context or ""
    if not context:
        return []

    results: list[DictionarySearchResult] = []

    variable_stmt = select(VariableDefinitionModel).where(
        VariableDefinitionModel.domain_context == context,
    )
    if not include_inactive:
        variable_stmt = variable_stmt.where(
            and_(
                VariableDefinitionModel.review_status == "ACTIVE",
                VariableDefinitionModel.is_active.is_(True),
            ),
        )
    variables = session.scalars(variable_stmt).all()
    results.extend(
        [
            DictionarySearchResult(
                dimension="variables",
                entry_id=str(variable.id),
                display_name=str(variable.display_name),
                description=str(variable.description) if variable.description else None,
                domain_context=context,
                match_method="exact",
                similarity_score=1.0,
                metadata={
                    "canonical_name": variable.canonical_name,
                    "data_type": variable.data_type,
                    "preferred_unit": variable.preferred_unit,
                    "sensitivity": variable.sensitivity,
                },
            )
            for variable in variables
        ],
    )

    entity_type_stmt = select(DictionaryEntityTypeModel).where(
        DictionaryEntityTypeModel.domain_context == context,
    )
    if not include_inactive:
        entity_type_stmt = entity_type_stmt.where(
            and_(
                DictionaryEntityTypeModel.review_status == "ACTIVE",
                DictionaryEntityTypeModel.is_active.is_(True),
            ),
        )
    entity_types = session.scalars(entity_type_stmt).all()
    results.extend(
        [
            DictionarySearchResult(
                dimension="entity_types",
                entry_id=str(entity_type.id),
                display_name=str(entity_type.display_name),
                description=str(entity_type.description),
                domain_context=context,
                match_method="exact",
                similarity_score=1.0,
                metadata={
                    "external_ontology_ref": entity_type.external_ontology_ref,
                    "expected_properties": entity_type.expected_properties,
                },
            )
            for entity_type in entity_types
        ],
    )

    relation_type_stmt = select(DictionaryRelationTypeModel).where(
        DictionaryRelationTypeModel.domain_context == context,
    )
    if not include_inactive:
        relation_type_stmt = relation_type_stmt.where(
            and_(
                DictionaryRelationTypeModel.review_status == "ACTIVE",
                DictionaryRelationTypeModel.is_active.is_(True),
            ),
        )
    relation_types = session.scalars(relation_type_stmt).all()
    results.extend(
        [
            DictionarySearchResult(
                dimension="relation_types",
                entry_id=str(relation_type.id),
                display_name=str(relation_type.display_name),
                description=str(relation_type.description),
                domain_context=context,
                match_method="exact",
                similarity_score=1.0,
                metadata={
                    "is_directional": relation_type.is_directional,
                    "inverse_label": relation_type.inverse_label,
                },
            )
            for relation_type in relation_types
        ],
    )

    relation_type_ids = [relation_type.id for relation_type in relation_types]
    if relation_type_ids:
        constraint_stmt = select(RelationConstraintModel).where(
            RelationConstraintModel.relation_type.in_(relation_type_ids),
        )
        if not include_inactive:
            constraint_stmt = constraint_stmt.where(
                and_(
                    RelationConstraintModel.review_status == "ACTIVE",
                    RelationConstraintModel.is_active.is_(True),
                ),
            )
        constraints = session.scalars(constraint_stmt).all()
        results.extend(
            [
                DictionarySearchResult(
                    dimension="constraints",
                    entry_id=str(constraint.id),
                    display_name=(
                        f"{constraint.source_type} -[{constraint.relation_type}]-> "
                        f"{constraint.target_type}"
                    ),
                    description="Allowed relation constraint",
                    domain_context=context,
                    match_method="exact",
                    similarity_score=1.0,
                    metadata={
                        "source_type": constraint.source_type,
                        "relation_type": constraint.relation_type,
                        "target_type": constraint.target_type,
                        "is_allowed": constraint.is_allowed,
                        "requires_evidence": constraint.requires_evidence,
                    },
                )
                for constraint in constraints
            ],
        )

    results.sort(
        key=lambda item: (
            item.dimension,
            item.display_name.casefold(),
            item.entry_id,
        ),
    )
    return results[:normalized_limit]


__all__ = ["search_dictionary_entries", "search_dictionary_entries_by_domain"]
