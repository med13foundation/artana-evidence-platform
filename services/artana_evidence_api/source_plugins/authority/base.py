"""Shared support for authority and ontology source plugins."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins._helpers import (
    compact_json_object,
    metadata_from_definition,
    string_field,
)
from artana_evidence_api.source_plugins.contracts import (
    SourceAuthorityReference,
    SourceGroundingContext,
    SourceGroundingInput,
    SourcePluginMetadata,
)
from artana_evidence_api.source_registry import SourceDefinition
from artana_evidence_api.types.common import JSONObject, json_array_or_empty


@dataclass(frozen=True, slots=True)
class AuthoritySourceConfig:
    """Source-specific configuration for authority plugins."""

    definition: SourceDefinition
    entity_kind: str
    id_fields: tuple[str, ...]
    alias_fields: tuple[str, ...]
    label_fields: tuple[str, ...]
    unresolved_limitation: str
    ambiguous_limitation: str
    resolved_limitation: str


@dataclass(frozen=True, slots=True)
class StaticAuthoritySourcePlugin:
    """Source-owned grounding behavior for ontology/nomenclature sources."""

    config: AuthoritySourceConfig

    @property
    def source_key(self) -> str:
        return self.config.definition.source_key

    @property
    def source_family(self) -> str:
        return self.config.definition.source_family

    @property
    def display_name(self) -> str:
        return self.config.definition.display_name

    @property
    def direct_search_supported(self) -> bool:
        return self.config.definition.direct_search_enabled

    @property
    def handoff_target_kind(self) -> str:
        return "authority_reference"

    @property
    def request_schema_ref(self) -> str | None:
        return self.config.definition.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        return self.config.definition.result_schema_ref

    @property
    def metadata(self) -> SourcePluginMetadata:
        return metadata_from_definition(self.config.definition)

    def source_definition(self) -> SourceDefinition:
        """Return this plugin's public source definition."""

        return self.config.definition

    def normalize_identifier(self, identifier: str) -> str:
        """Return a normalized authority identifier."""

        return " ".join(identifier.strip().split())

    def authority_reference(self, record: JSONObject) -> SourceAuthorityReference:
        """Build an authority reference from one resolved record."""

        normalized_id = _required_identifier(record=record, config=self.config)
        label = string_field(record, *self.config.label_fields)
        aliases = _aliases(record=record, config=self.config)
        return SourceAuthorityReference(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            entity_kind=self.config.entity_kind,
            normalized_id=self.normalize_identifier(normalized_id),
            label=label,
            aliases=aliases,
            provenance=_provenance(record=record, source_key=self.source_key),
        )

    async def resolve_entity(
        self,
        grounding: SourceGroundingInput,
    ) -> SourceGroundingContext:
        """Resolve one grounding request into resolved, ambiguous, or not-found context."""

        _assert_grounding_source_key(grounding, source_key=self.source_key)
        candidates = _candidate_references(
            plugin=self,
            context=grounding.context,
        )
        if len(candidates) > 1:
            return self._ambiguous_context(
                query=grounding.query,
                entity_kind=grounding.entity_kind,
                candidates=candidates,
            )
        if len(candidates) == 1:
            return self._resolved_context(
                query=grounding.query,
                entity_kind=grounding.entity_kind,
                reference=candidates[0],
                confidence=_confidence(grounding.context),
            )

        identifier = _identifier_from_payload(
            identifiers=grounding.identifiers,
            config=self.config,
        )
        if identifier is not None:
            reference = self.authority_reference(
                {
                    **grounding.context,
                    self.config.id_fields[0]: identifier,
                    "label": grounding.context.get("label") or grounding.query,
                },
            )
            return self._resolved_context(
                query=grounding.query,
                entity_kind=grounding.entity_kind,
                reference=reference,
                confidence=_confidence(grounding.context),
            )

        return self._not_found_context(
            query=grounding.query,
            entity_kind=grounding.entity_kind,
        )

    def build_grounding_context(self, record: JSONObject) -> SourceGroundingContext:
        """Build grounding context from an already shaped authority record."""

        reference = self.authority_reference(record)
        status = string_field(record, "status")
        if status == "ambiguous":
            candidates = _candidate_references(plugin=self, context=record)
            return self._ambiguous_context(
                query=string_field(record, "query") or reference.label or "",
                entity_kind=string_field(record, "entity_kind")
                or self.config.entity_kind,
                candidates=candidates or (reference,),
            )
        return self._resolved_context(
            query=string_field(record, "query") or reference.label or reference.normalized_id,
            entity_kind=string_field(record, "entity_kind") or self.config.entity_kind,
            reference=reference,
            confidence=_confidence(record),
        )

    def _resolved_context(
        self,
        *,
        query: str,
        entity_kind: str,
        reference: SourceAuthorityReference,
        confidence: float | None,
    ) -> SourceGroundingContext:
        return SourceGroundingContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            entity_kind=entity_kind or self.config.entity_kind,
            query=query,
            status="resolved",
            authority_reference=reference,
            candidate_references=(reference,),
            confidence=confidence,
            limitations=(self.config.resolved_limitation,),
        )

    def _ambiguous_context(
        self,
        *,
        query: str,
        entity_kind: str,
        candidates: tuple[SourceAuthorityReference, ...],
    ) -> SourceGroundingContext:
        return SourceGroundingContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            entity_kind=entity_kind or self.config.entity_kind,
            query=query,
            status="ambiguous",
            authority_reference=None,
            candidate_references=candidates,
            confidence=None,
            limitations=(self.config.ambiguous_limitation,),
        )

    def _not_found_context(
        self,
        *,
        query: str,
        entity_kind: str,
    ) -> SourceGroundingContext:
        return SourceGroundingContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            entity_kind=entity_kind or self.config.entity_kind,
            query=query,
            status="not_found",
            authority_reference=None,
            candidate_references=(),
            confidence=None,
            limitations=(self.config.unresolved_limitation,),
        )


def _assert_grounding_source_key(
    grounding: SourceGroundingInput,
    *,
    source_key: str,
) -> None:
    if grounding.source_key == source_key:
        return
    msg = f"{source_key} plugin cannot ground '{grounding.source_key}'."
    raise ValueError(msg)


def _required_identifier(
    *,
    record: JSONObject,
    config: AuthoritySourceConfig,
) -> str:
    identifier = string_field(record, *config.id_fields)
    if identifier is not None:
        return identifier
    msg = f"{config.definition.display_name} authority record requires an identifier."
    raise ValueError(msg)


def _identifier_from_payload(
    *,
    identifiers: JSONObject,
    config: AuthoritySourceConfig,
) -> str | None:
    return string_field(identifiers, *config.id_fields)


def _aliases(
    *,
    record: JSONObject,
    config: AuthoritySourceConfig,
) -> tuple[str, ...]:
    aliases: list[str] = []
    for field_name in config.alias_fields:
        value = record.get(field_name)
        if isinstance(value, str) and value.strip() and value.strip() not in aliases:
            aliases.append(value.strip())
        elif isinstance(value, list):
            aliases.extend(
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip() and item.strip() not in aliases
            )
    return tuple(aliases)


def _candidate_references(
    *,
    plugin: StaticAuthoritySourcePlugin,
    context: JSONObject,
) -> tuple[SourceAuthorityReference, ...]:
    candidates = json_array_or_empty(context.get("candidates"))
    return tuple(
        plugin.authority_reference(candidate)
        for candidate in candidates
        if isinstance(candidate, dict)
    )


def _confidence(payload: JSONObject) -> float | None:
    value = payload.get("confidence")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _provenance(*, record: JSONObject, source_key: str) -> JSONObject:
    raw_provenance = record.get("provenance")
    provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
    return compact_json_object(
        {
            "source_key": source_key,
            **provenance,
            "source_url": string_field(record, "source_url", "url"),
            "version": string_field(record, "version", "release"),
        },
    )
