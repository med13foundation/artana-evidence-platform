"""Service-local port for optional evidence-sentence generation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from artana_evidence_db.kernel_domain_models import (
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
)


class EvidenceSentenceHarnessPort(ABC):
    """Generate contextual, non-verbatim evidence sentences for optional relations."""

    @abstractmethod
    def generate(
        self,
        request: EvidenceSentenceGenerationRequest,
        *,
        model_id: str | None = None,
    ) -> EvidenceSentenceGenerationResult: ...


__all__ = ["EvidenceSentenceHarnessPort"]
