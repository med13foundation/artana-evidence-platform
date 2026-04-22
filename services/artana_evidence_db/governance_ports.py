"""Service-local governance harness port interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

from artana_evidence_db.kernel_domain_models import (
    ConceptDecisionProposal,  # noqa: TC001
    ConceptHarnessVerdict,  # noqa: TC001
    DictionarySearchResult,
)


class DictionarySearchHarnessPort(ABC):
    """Port for staged dictionary search orchestration."""

    @abstractmethod
    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        """Run staged dictionary search and return ranked matches."""


class ConceptDecisionHarnessPort(ABC):
    """Evaluate concept decisions before application."""

    @abstractmethod
    def evaluate(
        self,
        proposal: ConceptDecisionProposal,
    ) -> ConceptHarnessVerdict:
        """Run harness checks and return normalized verdict."""


__all__ = ["ConceptDecisionHarnessPort", "DictionarySearchHarnessPort"]
