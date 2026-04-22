"""Simplified cross-reference mapper returning typed network structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CrossReferenceNode:
    identifier: str
    references: list[str] = field(default_factory=list)


class CrossReferenceMapper:
    def __init__(self) -> None:
        self._networks: dict[str, CrossReferenceNode] = {}

    def add_reference(self, source_id: str, reference_id: str) -> None:
        node = self._networks.setdefault(
            source_id,
            CrossReferenceNode(identifier=source_id),
        )
        if reference_id not in node.references:
            node.references.append(reference_id)

    def build_cross_reference_network(self, root_id: str) -> dict[str, list[str]]:
        node = self._networks.get(root_id)
        if node is None:
            return {root_id: []}
        return {root_id: list(node.references)}


__all__ = ["CrossReferenceMapper"]
