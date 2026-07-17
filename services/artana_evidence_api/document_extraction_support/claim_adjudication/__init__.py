"""Source-bound categorical claim adjudication."""

from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDiagnostics,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.service import (
    adjudicate_document_claims,
)

__all__ = ["ClaimAdjudicationDiagnostics", "adjudicate_document_claims"]
