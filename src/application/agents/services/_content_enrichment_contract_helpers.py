"""Contract and validation helpers for content enrichment service."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.application.agents.services._content_enrichment_helpers import (
    extract_structured_payload,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject


class _ContentEnrichmentContractHelpers:
    _FULL_TEXT_REQUIRED_SOURCE_TYPES = frozenset({"pubmed"})
    _FULL_TEXT_ACQUISITION_METHODS = frozenset(
        {"pmc_oa", "europe_pmc", "publisher_pdf"},
    )

    @staticmethod
    def _build_extraction_input_patch(
        *,
        metadata: JSONObject,
        contract: ContentEnrichmentContract,
    ) -> JSONObject:
        full_text_methods = frozenset({"pmc_oa", "europe_pmc", "publisher_pdf"})
        full_text_fetched = contract.acquisition_method in full_text_methods
        fallback_reason = (
            None
            if full_text_fetched
            else (
                contract.warning
                if contract.warning and contract.warning.strip()
                else "open_access_full_text_not_available"
            )
        )

        content_text = contract.content_text
        if content_text is None:
            return {}
        normalized_text = content_text.strip()
        if not normalized_text:
            return {}

        raw_record_value = metadata.get("raw_record")
        raw_record: JSONObject
        if isinstance(raw_record_value, dict):
            raw_record = {
                str(key): to_json_value(value)
                for key, value in raw_record_value.items()
            }
        else:
            raw_record = {}

        raw_record["full_text"] = normalized_text
        raw_record["full_text_source"] = contract.acquisition_method
        raw_record["full_text_length_chars"] = len(normalized_text)
        raw_record["full_text_fetch_attempted"] = full_text_fetched or bool(
            contract.warning,
        )
        raw_record["full_text_fetch_acquired"] = full_text_fetched
        raw_record["full_text_fallback_reason"] = fallback_reason

        return {"raw_record": raw_record}

    @classmethod
    def _validate_required_full_text_contract(
        cls,
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
    ) -> str | None:
        if (
            document.source_type.value.strip().lower()
            not in cls._FULL_TEXT_REQUIRED_SOURCE_TYPES
        ):
            return None
        if contract.decision != "enriched":
            return "full_text_required_agent_not_enriched"
        if contract.acquisition_method not in cls._FULL_TEXT_ACQUISITION_METHODS:
            return "full_text_required_non_full_text_acquisition"

        has_text_content = bool(
            isinstance(contract.content_text, str) and contract.content_text.strip(),
        )
        has_storage_key = bool(
            isinstance(contract.content_storage_key, str)
            and contract.content_storage_key.strip(),
        )
        if not has_text_content and not has_storage_key:
            return "full_text_required_missing_content_payload"
        return None

    @staticmethod
    def _should_treat_full_text_validation_as_skip(
        *,
        failure_reason: str,
        contract: ContentEnrichmentContract,
    ) -> bool:
        if failure_reason not in {
            "full_text_required_agent_not_enriched",
            "full_text_required_non_full_text_acquisition",
        }:
            return False

        decision = contract.decision.strip().lower()
        if decision == "skipped":
            return True

        warning = contract.warning.strip().casefold() if contract.warning else ""
        if not warning:
            return False

        if (
            "pipeline_execution_failed" in warning
            or "missing_openai_api_key" in warning
        ):
            return False

        non_blocking_markers = (
            "no open-access full text",
            "open-access full text",
            "full text was not retrieved",
            "full-text not available",
            "enrichment skipped",
            "respect access controls",
            "paywall",
            "paywalled",
            "no pmc oa id",
            "cannot retrieve paywalled",
        )
        return any(marker in warning for marker in non_blocking_markers)

    @staticmethod
    def _build_pass_through_contract(
        *,
        document: SourceDocument,
    ) -> ContentEnrichmentContract:
        payload = extract_structured_payload(document.metadata)
        serialized = json.dumps(payload, default=str)
        return ContentEnrichmentContract(
            decision="enriched",
            confidence_score=0.98,
            rationale="Structured source type uses deterministic pass-through enrichment.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"document:{document.id}",
                    excerpt="Structured payload copied to enriched document content.",
                    relevance=0.98,
                ),
            ],
            document_id=str(document.id),
            source_type=document.source_type.value,
            acquisition_method="pass_through",
            content_format="structured_json",
            content_storage_key=document.raw_storage_key,
            content_length_chars=len(serialized),
            content_payload=payload,
            agent_run_id=None,
        )
