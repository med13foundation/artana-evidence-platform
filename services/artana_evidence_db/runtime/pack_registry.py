"""Process-local graph domain pack registry."""

from __future__ import annotations

import os

from artana_evidence_db.relation_autopromotion_policy import (
    RelationAutopromotionDefaults,
)
from artana_evidence_db.runtime.biomedical_pack import BIOMEDICAL_GRAPH_DOMAIN_PACK
from artana_evidence_db.runtime.contracts import (
    GraphDomainContextPolicy,
    GraphDomainPack,
)
from artana_evidence_db.runtime.sports_pack import SPORTS_GRAPH_DOMAIN_PACK

_DEFAULT_PACK_NAME = "biomedical"
_PACKS: dict[str, GraphDomainPack] = {}


def _normalize_pack_name(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        msg = "Graph domain pack name cannot be empty"
        raise ValueError(msg)
    return normalized


def clear_graph_domain_pack_registry() -> None:
    """Clear registered packs. Intended for focused unit tests."""
    _PACKS.clear()


def register_graph_domain_pack(pack: GraphDomainPack) -> None:
    """Register one graph domain pack by normalized name."""
    normalized_name = _normalize_pack_name(pack.name)
    existing = _PACKS.get(normalized_name)
    if existing is not None and existing is not pack:
        msg = f"Graph domain pack '{normalized_name}' is already registered"
        raise ValueError(msg)
    _PACKS[normalized_name] = pack


def bootstrap_default_graph_domain_packs() -> None:
    """Register built-in graph domain packs."""
    register_graph_domain_pack(BIOMEDICAL_GRAPH_DOMAIN_PACK)
    register_graph_domain_pack(SPORTS_GRAPH_DOMAIN_PACK)


def list_graph_domain_packs() -> tuple[GraphDomainPack, ...]:
    """Return registered graph domain packs ordered by name."""
    bootstrap_default_graph_domain_packs()
    return tuple(_PACKS[name] for name in sorted(_PACKS))


def resolve_graph_domain_pack(name: str | None = None) -> GraphDomainPack:
    """Resolve one graph domain pack from explicit name or GRAPH_DOMAIN_PACK."""
    bootstrap_default_graph_domain_packs()
    selected_name = name
    if selected_name is None:
        selected_name = os.getenv("GRAPH_DOMAIN_PACK", _DEFAULT_PACK_NAME)
    normalized_name = _normalize_pack_name(selected_name)
    pack = _PACKS.get(normalized_name)
    if pack is None:
        supported = ", ".join(sorted(_PACKS))
        msg = (
            f"Unsupported GRAPH_DOMAIN_PACK '{selected_name}'. "
            f"Supported packs: {supported}"
        )
        raise RuntimeError(msg)
    return pack


def create_graph_domain_pack() -> GraphDomainPack:
    """Return the active graph domain pack for service composition."""
    return resolve_graph_domain_pack()


def create_graph_domain_context_policy() -> GraphDomainContextPolicy:
    """Return source-type domain defaults from the active graph domain pack."""
    return create_graph_domain_pack().domain_context_policy


def create_relation_autopromotion_defaults() -> RelationAutopromotionDefaults:
    """Return relation auto-promotion defaults from the active graph domain pack."""
    return create_graph_domain_pack().relation_autopromotion_defaults


__all__ = [
    "bootstrap_default_graph_domain_packs",
    "clear_graph_domain_pack_registry",
    "create_graph_domain_context_policy",
    "create_graph_domain_pack",
    "create_relation_autopromotion_defaults",
    "list_graph_domain_packs",
    "register_graph_domain_pack",
    "resolve_graph_domain_pack",
]
