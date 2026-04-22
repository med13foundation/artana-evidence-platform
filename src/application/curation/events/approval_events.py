from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemsApproved:
    ids: tuple[int, ...]


@dataclass(frozen=True)
class ItemsRejected:
    ids: tuple[int, ...]


@dataclass(frozen=True)
class ItemsQuarantined:
    ids: tuple[int, ...]


__all__ = ["ItemsApproved", "ItemsQuarantined", "ItemsRejected"]
