"""Service-local graph API port interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from artana_evidence_db.common_types import ResearchSpaceSettings
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.space_registry import KernelSpaceRegistryEntry


class SpaceAccessPort(ABC):
    """Resolve one caller's effective role within one graph space."""

    @abstractmethod
    def get_effective_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        """Return the effective role for one user in one space."""


class SpaceRegistryPort(ABC):
    """Resolve graph-local space registry metadata."""

    @abstractmethod
    def get_by_id(
        self,
        space_id: UUID,
    ) -> KernelSpaceRegistryEntry | None:
        """Fetch one graph space registry entry."""

    @abstractmethod
    def get_by_slug(
        self,
        slug: str,
    ) -> KernelSpaceRegistryEntry | None:
        """Fetch one graph space registry entry by slug."""

    @abstractmethod
    def list_space_ids(self) -> list[UUID]:
        """List all graph space ids known to the registry."""

    @abstractmethod
    def list_entries(self) -> list[KernelSpaceRegistryEntry]:
        """List all graph space registry entries."""

    @abstractmethod
    def save(
        self,
        entry: KernelSpaceRegistryEntry,
    ) -> KernelSpaceRegistryEntry:
        """Create or update one graph space registry entry."""


class SpaceSettingsPort(ABC):
    """Resolve graph-space settings without platform coupling."""

    @abstractmethod
    def get_settings(
        self,
        space_id: UUID,
    ) -> ResearchSpaceSettings | None:
        """Return one graph-space settings payload."""


__all__ = ["SpaceAccessPort", "SpaceRegistryPort", "SpaceSettingsPort"]
