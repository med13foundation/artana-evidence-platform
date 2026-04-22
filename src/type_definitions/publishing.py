"""
Publishing-related typed contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.type_definitions.external_apis import ZenodoPublishResponse


class DOIMintResult(TypedDict):
    deposit_id: int
    doi: str
    url: str
    deposit: ZenodoPublishResponse


__all__ = ["DOIMintResult"]
