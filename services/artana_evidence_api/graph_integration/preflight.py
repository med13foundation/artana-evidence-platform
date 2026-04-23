"""DB-first graph preflight for entity, relation, and workflow preparation."""

from __future__ import annotations

import difflib
import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.graph_client import (
    GraphDictionaryTransport,
    GraphServiceClientError,
    GraphTransportBundle,
    GraphTransportConfig,
)
from artana_evidence_api.graph_integration.context import GraphCallContext
from artana_evidence_api.graph_integration.contracts import (
    GovernedGraphCommand,
    RawGraphIntent,
    ResolvedGraphIntent,
)
from artana_evidence_api.relation_type_resolver import (
    RelationTypeAction,
    RelationTypeDecision,
)
from artana_evidence_api.relation_type_resolver import (
    resolve_entity_with_ai as resolve_entity_with_kernel,
)
from artana_evidence_api.relation_type_resolver import (
    resolve_relation_type as resolve_relation_with_kernel,
)
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    DictionaryEntityTypeListResponse,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationTypeListResponse,
    DictionarySearchListResponse,
    KernelGraphValidationResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
    KernelRelationSuggestionRequest,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_STATUS = 404
_BAD_REQUEST_STATUS = 400
_RELATION_CACHE_MAX_SIZE = 2000
_ENTITY_CACHE_MAX_SIZE = 5000

class GraphResolutionCache(Protocol):
    """Cache contract for space-scoped entity and relation resolution decisions."""

    def get_entity(
        self,
        *,
        space_id: UUID | str,
        label: str,
    ) -> tuple[bool, JSONObject | None]: ...

    def set_entity(
        self,
        *,
        space_id: UUID | str,
        label: str,
        value: JSONObject | None,
    ) -> None: ...

    def get_relation(
        self,
        *,
        space_id: UUID | str,
        relation_type: str,
    ) -> RelationTypeDecision | None: ...

    def set_relation(
        self,
        *,
        space_id: UUID | str,
        relation_type: str,
        value: RelationTypeDecision,
    ) -> None: ...


class InMemoryGraphResolutionCache:
    """Simple bounded in-memory cache for graph preflight decisions."""

    def __init__(self) -> None:
        self._entity_data: OrderedDict[str, JSONObject | None] = OrderedDict()
        self._relation_data: OrderedDict[str, RelationTypeDecision] = OrderedDict()

    def get_entity(
        self,
        *,
        space_id: UUID | str,
        label: str,
    ) -> tuple[bool, JSONObject | None]:
        key = _entity_cache_key(space_id, label)
        if key not in self._entity_data:
            return False, None
        return True, self._entity_data[key]

    def set_entity(
        self,
        *,
        space_id: UUID | str,
        label: str,
        value: JSONObject | None,
    ) -> None:
        key = _entity_cache_key(space_id, label)
        if key in self._entity_data:
            self._entity_data.move_to_end(key)
        self._entity_data[key] = value
        if len(self._entity_data) > _ENTITY_CACHE_MAX_SIZE:
            self._entity_data.popitem(last=False)

    def get_relation(
        self,
        *,
        space_id: UUID | str,
        relation_type: str,
    ) -> RelationTypeDecision | None:
        return self._relation_data.get(_relation_cache_key(space_id, relation_type))

    def set_relation(
        self,
        *,
        space_id: UUID | str,
        relation_type: str,
        value: RelationTypeDecision,
    ) -> None:
        key = _relation_cache_key(space_id, relation_type)
        if key in self._relation_data:
            self._relation_data.move_to_end(key)
        self._relation_data[key] = value
        if len(self._relation_data) > _RELATION_CACHE_MAX_SIZE:
            self._relation_data.popitem(last=False)


GraphDictionaryTransportFactory = Callable[[], GraphDictionaryTransport]


def _default_admin_dictionary_transport_factory() -> GraphDictionaryTransportFactory:
    def _factory() -> GraphDictionaryTransport:
        bundle = GraphTransportBundle(
            call_context=GraphCallContext.service(graph_admin=True),
        )
        return bundle.dictionary

    return _factory


def _normalize_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip().upper()
    return normalized.replace("-", "_").replace("/", "_").replace(" ", "_")


def _relation_cache_key(space_id: UUID | str, relation_type: str) -> str:
    return f"{str(space_id).strip()}:{relation_type.strip().upper().replace(' ', '_')}"


def _entity_cache_key(space_id: UUID | str, label: str) -> str:
    return f"{str(space_id).strip()}:{label.strip().casefold()}"


def _query_client(graph_transport: object) -> object:
    return getattr(graph_transport, "query", graph_transport)


def _validation_client(graph_transport: object) -> object:
    return getattr(graph_transport, "validation", graph_transport)


def _legacy_allowed_validation(
    *,
    relation_type: str | None = None,
) -> KernelGraphValidationResponse:
    normalized_relation_type = (
        relation_type.strip().upper().replace(" ", "_")
        if isinstance(relation_type, str) and relation_type.strip()
        else None
    )
    return KernelGraphValidationResponse(
        valid=True,
        code="allowed",
        message="Legacy flat graph gateway does not expose explicit validation; assuming allowed.",
        severity="info",
        next_actions=[],
        normalized_relation_type=normalized_relation_type,
        validation_state="ALLOWED",
        validation_reason="legacy_flat_gateway_without_validation",
        persistability="PERSISTABLE",
    )


def _preserved_runtime_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.casefold() not in {"authorization", "x-request-id"}
    }


def _extract_entity_type_ids(
    payload: DictionaryEntityTypeListResponse,
) -> list[str]:
    return [_normalize_entity_type(item.id) for item in payload.entity_types if item.id]


def _extract_relation_type_ids(
    payload: DictionaryRelationTypeListResponse,
) -> list[str]:
    return [item.id.strip().upper() for item in payload.relation_types if item.id]


def _extract_relation_synonyms(
    payload: DictionaryRelationSynonymListResponse,
) -> list[str]:
    return [
        item.synonym.strip().upper()
        for item in payload.relation_synonyms
        if item.synonym
    ]


def _extract_relation_search_match(
    *,
    payload: DictionarySearchListResponse,
    relation_type: str,
) -> str | None:
    normalized = relation_type.strip().upper()
    for item in payload.results:
        if str(item.dimension).strip().lower() not in {"relation_type", "relationtype"}:
            continue
        if item.entry_id.strip().upper() == normalized:
            return item.entry_id.strip().upper()
        if (
            item.display_name.strip().upper().replace(" ", "_") == normalized
            and item.entry_id.strip()
        ):
            return item.entry_id.strip().upper()
    return None


@dataclass
class GraphAIPreflightService:
    """Central DB-first graph resolution and validation service."""

    admin_dictionary_transport_factory: GraphDictionaryTransportFactory | None = None
    resolution_cache: GraphResolutionCache | None = None

    def __post_init__(self) -> None:
        self._admin_dictionary_transport_factory = (
            self.admin_dictionary_transport_factory
            or _default_admin_dictionary_transport_factory()
        )
        self._resolution_cache = self.resolution_cache or InMemoryGraphResolutionCache()

    def _admin_dictionary_transport_for_graph_transport(
        self,
        graph_transport: GraphTransportBundle,
    ) -> GraphDictionaryTransport:
        runtime = graph_transport._runtime  # noqa: SLF001 - intentional shared transport runtime
        scoped_bundle = GraphTransportBundle(
            config=GraphTransportConfig(
                base_url=runtime.config.base_url,
                timeout_seconds=runtime.config.timeout_seconds,
                default_headers=_preserved_runtime_headers(runtime.config.default_headers),
            ),
            client=runtime.client,
            call_context=GraphCallContext.service(graph_admin=True),
        )
        return scoped_bundle.dictionary

    def resolve_entity_label(
        self,
        *,
        space_id: UUID,
        label: str,
        graph_transport: GraphTransportBundle,
    ) -> JSONObject | None:
        """Resolve one entity label deterministically against current graph state."""
        cached_hit, cached = self._resolution_cache.get_entity(
            space_id=space_id,
            label=label,
        )
        if cached_hit:
            return cached
        try:
            response = _query_client(graph_transport).list_entities(
                space_id=space_id,
                q=label,
                limit=5,
            )
        except GraphServiceClientError:
            return None
        normalized_label = label.strip().casefold()
        for entity in response.entities:
            display_label = entity.display_label or ""
            exact_aliases = {alias.casefold() for alias in entity.aliases}
            if (
                display_label.casefold() == normalized_label
                or normalized_label in exact_aliases
            ):
                resolved = {
                    "id": str(entity.id),
                    "display_label": display_label or str(entity.id),
                }
                self._resolution_cache.set_entity(
                    space_id=space_id,
                    label=label,
                    value=resolved,
                )
                return resolved
        for entity in response.entities:
            display_label = entity.display_label or ""
            if normalized_label in display_label.casefold() or any(
                normalized_label in alias.casefold() for alias in entity.aliases
            ):
                resolved = {
                    "id": str(entity.id),
                    "display_label": display_label or str(entity.id),
                }
                self._resolution_cache.set_entity(
                    space_id=space_id,
                    label=label,
                    value=resolved,
                )
                return resolved
        if not response.entities:
            self._resolution_cache.set_entity(
                space_id=space_id,
                label=label,
                value=None,
            )
            return None
        first_entity = response.entities[0]
        resolved = {
            "id": str(first_entity.id),
            "display_label": first_entity.display_label or str(first_entity.id),
        }
        self._resolution_cache.set_entity(
            space_id=space_id,
            label=label,
            value=resolved,
        )
        return resolved

    async def resolve_entity_label_with_ai(
        self,
        *,
        space_id: UUID,
        label: str,
        graph_transport: GraphTransportBundle,
        space_context: str = "",
    ) -> JSONObject | None:
        """Resolve one entity label, using Artana Kernel only after DB-first checks."""
        deterministic = self.resolve_entity_label(
            space_id=space_id,
            label=label,
            graph_transport=graph_transport,
        )
        if deterministic is not None:
            return deterministic
        resolved = await resolve_entity_with_kernel(
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_transport,
            space_context=space_context,
        )
        self._resolution_cache.set_entity(
            space_id=space_id,
            label=label,
            value=cast("JSONObject | None", resolved),
        )
        return cast("JSONObject | None", resolved)

    async def resolve_relation_type(  # noqa: PLR0911
        self,
        *,
        space_id: UUID,
        relation_type: str,
        known_types: list[str],
        graph_transport: GraphTransportBundle | None = None,
        domain_context: str = "general",
        space_context: str = "",
        allowed_relation_suggestions: list[str] | None = None,
    ) -> RelationTypeDecision:
        """Resolve one relation label via DB-first checks and AI fallback."""
        cached = self._resolution_cache.get_relation(
            space_id=space_id,
            relation_type=relation_type,
        )
        if cached is not None:
            return cached
        normalized = relation_type.strip().upper().replace(" ", "_")
        known_upper = {item.strip().upper() for item in known_types if item.strip()}
        if normalized in known_upper:
            decision = RelationTypeDecision(
                action=RelationTypeAction.MAP_TO_EXISTING,
                canonical_type=normalized,
                reasoning="Already a known canonical relation type.",
            )
            self._resolution_cache.set_relation(
                space_id=space_id,
                relation_type=relation_type,
                value=decision,
            )
            return decision

        admin_dictionary_transport = (
            self._admin_dictionary_transport_for_graph_transport(graph_transport)
            if graph_transport is not None
            else self._admin_dictionary_transport_factory()
        )
        with admin_dictionary_transport as admin_dictionary:
            live_relation_types: list[str] = []
            live_relation_synonyms: list[str] = []
            search_match: str | None = None
            try:
                resolved_payload = admin_dictionary.resolve_dictionary_relation_synonym(
                    synonym=normalized,
                )
                relation_type_id = resolved_payload.id
                if relation_type_id.strip():
                    decision = RelationTypeDecision(
                        action=RelationTypeAction.MAP_TO_EXISTING,
                        canonical_type=relation_type_id.strip().upper(),
                        reasoning="Resolved against an active graph dictionary synonym.",
                    )
                    self._resolution_cache.set_relation(
                        space_id=space_id,
                        relation_type=relation_type,
                        value=decision,
                    )
                    return decision
            except GraphServiceClientError:
                pass

            try:
                live_relation_types = _extract_relation_type_ids(
                    admin_dictionary.list_dictionary_relation_types(
                        domain_context=domain_context,
                    ),
                )
            except GraphServiceClientError:
                logger.debug("Graph relation-type listing failed during preflight", exc_info=True)
            try:
                live_relation_synonyms = _extract_relation_synonyms(
                    admin_dictionary.list_dictionary_relation_synonyms(),
                )
            except GraphServiceClientError:
                logger.debug("Graph relation-synonym listing failed during preflight", exc_info=True)
            try:
                search_match = _extract_relation_search_match(
                    payload=admin_dictionary.search_dictionary_entries_by_domain(
                        domain_context=domain_context,
                    ),
                    relation_type=normalized,
                )
            except GraphServiceClientError:
                logger.debug("Graph dictionary search failed during preflight", exc_info=True)

        merged_known_types = sorted(set(live_relation_types) | known_upper)
        if normalized in set(merged_known_types):
            decision = RelationTypeDecision(
                action=RelationTypeAction.MAP_TO_EXISTING,
                canonical_type=normalized,
                reasoning="Matched an active graph dictionary relation type.",
            )
            self._resolution_cache.set_relation(
                space_id=space_id,
                relation_type=relation_type,
                value=decision,
            )
            return decision
        if search_match is not None:
            decision = RelationTypeDecision(
                action=RelationTypeAction.MAP_TO_EXISTING,
                canonical_type=search_match,
                reasoning="Matched an active graph dictionary search candidate.",
            )
            self._resolution_cache.set_relation(
                space_id=space_id,
                relation_type=relation_type,
                value=decision,
            )
            return decision
        fuzzy_matches = difflib.get_close_matches(
            normalized,
            merged_known_types,
            n=1,
            cutoff=0.82,
        )
        if fuzzy_matches:
            decision = RelationTypeDecision(
                action=RelationTypeAction.TYPO_CORRECTION,
                canonical_type=fuzzy_matches[0],
                reasoning="Deterministic fuzzy match against active relation types.",
            )
            self._resolution_cache.set_relation(
                space_id=space_id,
                relation_type=relation_type,
                value=decision,
            )
            return decision

        decision = await resolve_relation_with_kernel(
            normalized,
            known_types=merged_known_types or sorted(known_upper),
            space_context=space_context,
            space_id=str(space_id),
            live_candidate_types=merged_known_types,
            live_relation_synonyms=live_relation_synonyms,
            allowed_relation_suggestions=allowed_relation_suggestions or [],
        )
        self._resolution_cache.set_relation(
            space_id=space_id,
            relation_type=relation_type,
            value=decision,
        )
        return decision

    def prepare_entity_create(
        self,
        *,
        space_id: UUID,
        entity_type: str,
        display_label: str,
        aliases: list[str] | None,
        metadata: JSONObject | None = None,
        identifiers: dict[str, str] | None = None,
        graph_transport: GraphTransportBundle,
    ) -> ResolvedGraphIntent:
        """Prepare one governed entity-create command."""
        payload: JSONObject = {
            "entity_type": entity_type,
            "display_label": display_label,
            "aliases": aliases or [],
            "metadata": metadata or {},
            "identifiers": identifiers or {},
        }
        raw_intent = RawGraphIntent(kind="entity_create", space_id=space_id, payload=payload)
        validation_client = _validation_client(graph_transport)
        if hasattr(validation_client, "validate_entity_create"):
            validation = validation_client.validate_entity_create(
                space_id=space_id,
                payload=payload,
            )
        else:
            validation = _legacy_allowed_validation()
        normalized_entity_type = _normalize_entity_type(entity_type)
        if validation.valid:
            normalized_payload = {**payload, "entity_type": normalized_entity_type}
            return ResolvedGraphIntent(
                raw_intent=raw_intent,
                normalized_payload=normalized_payload,
                validation=validation,
                commands=(
                    GovernedGraphCommand(
                        kind="create_entity",
                        payload=normalized_payload,
                    ),
                ),
            )

        if validation.code == "unknown_entity_type":
            known_ids: list[str] = []
            with self._admin_dictionary_transport_for_graph_transport(
                graph_transport,
            ) as admin_dictionary:
                try:
                    known_ids = _extract_entity_type_ids(
                        admin_dictionary.list_dictionary_entity_types(),
                    )
                except GraphServiceClientError:
                    logger.debug("Graph entity-type listing failed during preflight", exc_info=True)
            fuzzy_matches = difflib.get_close_matches(
                normalized_entity_type,
                known_ids,
                n=1,
                cutoff=0.82,
            )
            if fuzzy_matches:
                retry_payload = {**payload, "entity_type": fuzzy_matches[0]}
                if hasattr(validation_client, "validate_entity_create"):
                    retry_validation = validation_client.validate_entity_create(
                        space_id=space_id,
                        payload=retry_payload,
                    )
                else:
                    retry_validation = _legacy_allowed_validation()
                if retry_validation.valid:
                    return ResolvedGraphIntent(
                        raw_intent=raw_intent,
                        normalized_payload=retry_payload,
                        validation=retry_validation,
                        commands=(
                            GovernedGraphCommand(
                                kind="create_entity",
                                payload=retry_payload,
                            ),
                        ),
                    )
            return ResolvedGraphIntent(
                raw_intent=raw_intent,
                normalized_payload=payload,
                validation=validation,
                commands=(
                    GovernedGraphCommand(
                        kind="propose_entity_type",
                        payload=_entity_type_proposal_payload(
                            entity_type=normalized_entity_type,
                            display_label=display_label,
                        ),
                        detail=validation.message,
                    ),
                ),
                requires_review=True,
                blocked_detail=validation.message,
            )

        return ResolvedGraphIntent(
            raw_intent=raw_intent,
            normalized_payload=payload,
            validation=validation,
            blocked_detail=validation.message,
        )

    async def prepare_claim_create(
        self,
        *,
        space_id: UUID,
        request: KernelRelationClaimCreateRequest,
        graph_transport: GraphTransportBundle,
        space_context: str = "",
        domain_context: str = "general",
    ) -> ResolvedGraphIntent:
        """Prepare one governed claim-create command."""
        return await self._prepare_relation_like_create(
            space_id=space_id,
            request=request,
            graph_transport=graph_transport,
            relation_payload=_claim_validation_payload(request),
            create_command_kind="create_claim",
            space_context=space_context,
            domain_context=domain_context,
        )

    async def prepare_relation_create(
        self,
        *,
        space_id: UUID,
        request: KernelRelationCreateRequest,
        graph_transport: GraphTransportBundle,
        space_context: str = "",
        domain_context: str = "general",
    ) -> ResolvedGraphIntent:
        """Prepare one governed canonical relation create command."""
        return await self._prepare_relation_like_create(
            space_id=space_id,
            request=request,
            graph_transport=graph_transport,
            relation_payload=_relation_validation_payload(request),
            create_command_kind="create_relation",
            space_context=space_context,
            domain_context=domain_context,
        )

    def _relation_request_intent_kind(
        self,
        request: KernelRelationClaimCreateRequest | KernelRelationCreateRequest,
    ) -> str:
        return (
            "claim_create"
            if isinstance(request, KernelRelationClaimCreateRequest)
            else "relation_create"
        )

    def _validate_relation_like_request(
        self,
        *,
        space_id: UUID,
        request: KernelRelationClaimCreateRequest | KernelRelationCreateRequest,
        graph_transport: GraphTransportBundle,
    ) -> KernelGraphValidationResponse:
        validation_client = _validation_client(graph_transport)
        if isinstance(request, KernelRelationClaimCreateRequest):
            if hasattr(validation_client, "validate_claim_create"):
                return validation_client.validate_claim_create(
                    space_id=space_id,
                    request=request,
                )
            return _legacy_allowed_validation(
                relation_type=request.relation_type,
            )
        if hasattr(validation_client, "validate_relation_materialization"):
            return validation_client.validate_relation_materialization(
                space_id=space_id,
                payload=_relation_validation_payload(request),
            )
        return _legacy_allowed_validation(
            relation_type=request.relation_type,
        )

    async def _prepare_relation_like_create(
        self,
        *,
        space_id: UUID,
        request: KernelRelationClaimCreateRequest | KernelRelationCreateRequest,
        graph_transport: GraphTransportBundle,
        relation_payload: JSONObject,
        create_command_kind: str,
        space_context: str,
        domain_context: str,
    ) -> ResolvedGraphIntent:
        raw_intent_kind = self._relation_request_intent_kind(request)
        validation = self._validate_relation_like_request(
            space_id=space_id,
            request=request,
            graph_transport=graph_transport,
        )
        normalized_request = request
        if validation.normalized_relation_type is not None:
            normalized_request = request.model_copy(
                update={"relation_type": validation.normalized_relation_type},
            )
        if not validation.valid and validation.code == "unknown_entity":
            return ResolvedGraphIntent(
                raw_intent=RawGraphIntent(
                    kind=raw_intent_kind,
                    space_id=space_id,
                    payload=cast("JSONObject", request.model_dump(mode="json")),
                ),
                normalized_payload=cast("JSONObject", normalized_request.model_dump(mode="json")),
                validation=validation,
                blocked_detail=validation.message,
            )
        if not validation.valid and validation.code == "invalid_relation_type":
            return ResolvedGraphIntent(
                raw_intent=RawGraphIntent(
                    kind=raw_intent_kind,
                    space_id=space_id,
                    payload=cast("JSONObject", request.model_dump(mode="json")),
                ),
                normalized_payload=cast("JSONObject", normalized_request.model_dump(mode="json")),
                validation=validation,
                blocked_detail=validation.message,
            )

        if validation.code == "unknown_relation_type":
            allowed_suggestions = self._allowed_relation_suggestions(
                space_id=space_id,
                graph_transport=graph_transport,
                relation_payload=relation_payload,
            )
            decision = await self.resolve_relation_type(
                space_id=space_id,
                relation_type=normalized_request.relation_type,
                known_types=[],
                graph_transport=graph_transport,
                domain_context=domain_context,
                space_context=space_context,
                allowed_relation_suggestions=allowed_suggestions,
            )
            if decision.action in {
                RelationTypeAction.MAP_TO_EXISTING,
                RelationTypeAction.TYPO_CORRECTION,
            }:
                normalized_request = normalized_request.model_copy(
                    update={"relation_type": decision.canonical_type},
                )
                validation = self._validate_relation_like_request(
                    space_id=space_id,
                    request=normalized_request,
                    graph_transport=graph_transport,
                )
            else:
                validation = validation.model_copy(
                    update={"message": decision.reasoning},
                )

        commands: list[GovernedGraphCommand] = []
        if validation.code == "unknown_relation_type":
            commands.append(
                GovernedGraphCommand(
                    kind="propose_relation_type",
                    payload=_relation_type_proposal_payload(
                        request=normalized_request,
                        validation=validation,
                    ),
                    detail=validation.message,
                ),
            )
        if validation.code == "relation_constraint_not_allowed":
            proposal_payload = _relation_constraint_proposal_payload(validation=validation)
            if proposal_payload is not None:
                commands.append(
                    GovernedGraphCommand(
                        kind="propose_relation_constraint",
                        payload=proposal_payload,
                        detail=validation.message,
                    ),
                )
        if (
            validation.valid
            and validation.persistability == "PERSISTABLE"
            and validation.code == "allowed"
            and not commands
        ):
            commands.append(
                GovernedGraphCommand(
                    kind=create_command_kind,
                    payload=cast("JSONObject", normalized_request.model_dump(mode="json")),
                ),
            )
        return ResolvedGraphIntent(
            raw_intent=RawGraphIntent(
                kind=raw_intent_kind,
                space_id=space_id,
                payload=cast("JSONObject", request.model_dump(mode="json")),
            ),
            normalized_payload=cast("JSONObject", normalized_request.model_dump(mode="json")),
            validation=validation,
            commands=tuple(commands),
            requires_review=any(command.kind.startswith("propose_") for command in commands),
            blocked_detail=(
                None
                if commands or (
                    validation.valid
                    and validation.persistability == "PERSISTABLE"
                    and validation.code == "allowed"
                )
                else validation.message
            ),
        )

    def _allowed_relation_suggestions(
        self,
        *,
        space_id: UUID,
        graph_transport: GraphTransportBundle,
        relation_payload: JSONObject,
    ) -> list[str]:
        source_entity_id = relation_payload.get("source_entity_id")
        target_entity_id = relation_payload.get("target_entity_id")
        if not isinstance(source_entity_id, str) or not isinstance(target_entity_id, str):
            return []
        query_client = _query_client(graph_transport)
        try:
            entity_list = query_client.list_entities(
                space_id=space_id,
                ids=[source_entity_id, target_entity_id],
                limit=2,
            )
        except GraphServiceClientError:
            return []
        target_type = None
        for entity in entity_list.entities:
            if str(entity.id) == target_entity_id:
                target_type = entity.entity_type
                break
        if target_type is None:
            return []
        try:
            suggestions = query_client.suggest_relations(
                space_id=space_id,
                request=KernelRelationSuggestionRequest(
                    source_entity_ids=[UUID(source_entity_id)],
                    target_entity_types=[target_type],
                    limit_per_source=25,
                ),
            )
        except GraphServiceClientError:
            return []
        return sorted({item.relation_type for item in suggestions.suggestions})


def _entity_type_proposal_payload(
    *,
    entity_type: str,
    display_label: str,
) -> JSONObject:
    return {
        "id": entity_type,
        "display_name": entity_type.replace("_", " ").title(),
        "description": "Proposed entity type discovered during graph entity validation.",
        "domain_context": "general",
        "rationale": f"Entity preflight found no approved entity type for {entity_type}.",
        "evidence_payload": {
            "source": "graph_preflight",
            "display_label": display_label,
        },
        "expected_properties": {},
        "source_ref": f"graph-preflight:proposal:entity-type:{entity_type.lower()}",
    }


def _relation_type_proposal_payload(
    *,
    request: KernelRelationClaimCreateRequest | KernelRelationCreateRequest,
    validation: KernelGraphValidationResponse,
) -> JSONObject:
    relation_type = validation.normalized_relation_type or request.relation_type.strip().upper()
    claim_text = getattr(request, "claim_text", None)
    evidence_payload: JSONObject = {
        "source": "graph_preflight",
        "source_document_ref": request.source_document_ref,
    }
    if isinstance(claim_text, str):
        evidence_payload["claim_text"] = claim_text
    elif request.evidence_sentence is not None:
        evidence_payload["claim_text"] = request.evidence_sentence
    elif request.evidence_summary is not None:
        evidence_payload["claim_text"] = request.evidence_summary
    return {
        "id": relation_type,
        "display_name": relation_type.replace("_", " ").title(),
        "description": "Proposed relation type discovered during graph relation validation.",
        "domain_context": "general",
        "rationale": f"Relation preflight found no approved relation type for {relation_type}.",
        "evidence_payload": evidence_payload,
        "is_directional": True,
        "source_ref": f"graph-preflight:proposal:relation-type:{relation_type.lower()}",
    }


def _relation_constraint_proposal_payload(
    *,
    validation: KernelGraphValidationResponse,
) -> JSONObject | None:
    source_type = validation.source_type
    relation_type = validation.normalized_relation_type
    target_type = validation.target_type
    if source_type is None or relation_type is None or target_type is None:
        return None
    return {
        "source_type": source_type,
        "relation_type": relation_type,
        "target_type": target_type,
        "rationale": "Claim preflight found no approved relation constraint for this triple.",
        "evidence_payload": {"source": "graph_preflight"},
        "is_allowed": True,
        "requires_evidence": bool(validation.requires_evidence),
        "profile": "REVIEW_ONLY",
        "source_ref": (
            "graph-preflight:proposal:relation-constraint:"
            f"{source_type.lower()}:{relation_type.lower()}:{target_type.lower()}"
        ),
    }


def _claim_validation_payload(request: KernelRelationClaimCreateRequest) -> JSONObject:
    return {
        "source_entity_id": str(request.source_entity_id),
        "target_entity_id": str(request.target_entity_id),
        "relation_type": request.relation_type,
        "claim_text": request.claim_text,
        "evidence_summary": request.evidence_summary,
        "evidence_sentence": request.evidence_sentence,
        "source_document_ref": request.source_document_ref,
    }


def _relation_validation_payload(request: KernelRelationCreateRequest) -> JSONObject:
    return {
        "source_entity_id": str(request.source_id),
        "target_entity_id": str(request.target_id),
        "relation_type": request.relation_type,
        "evidence_summary": request.evidence_summary,
        "evidence_sentence": request.evidence_sentence,
        "source_document_ref": request.source_document_ref,
    }


__all__ = ["GraphAIPreflightService"]
