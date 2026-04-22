"""ClinicalTrials.gov v2 REST API client.

Fetches clinical trial records from the public ClinicalTrials.gov API
(https://clinicaltrials.gov/api/v2/) which requires no authentication
and is used for the Phase 3 translational source connector.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.infrastructure.ingest.base_ingestor import BaseIngestor

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, JSONValue, RawRecord

logger = logging.getLogger(__name__)

_CLINICALTRIALS_BASE_URL = "https://clinicaltrials.gov/api/v2"
_CLINICALTRIALS_RATE_LIMIT = 30  # requests per minute (conservative)
_CLINICALTRIALS_TIMEOUT = 30
_CLINICALTRIALS_MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class ClinicalTrialsFetchPage:
    """Result of a ClinicalTrials.gov fetch."""

    records: list[RawRecord] = field(default_factory=list)
    total_count: int = 0
    next_page_token: str | None = None

    @property
    def has_more(self) -> bool:
        return self.next_page_token is not None


class ClinicalTrialsIngestor(BaseIngestor):
    """Async HTTP client for the ClinicalTrials.gov v2 REST API."""

    def __init__(self) -> None:
        super().__init__(
            source_name="clinical_trials",
            base_url=_CLINICALTRIALS_BASE_URL,
            requests_per_minute=_CLINICALTRIALS_RATE_LIMIT,
            timeout_seconds=_CLINICALTRIALS_TIMEOUT,
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """Fetch clinical trial records (BaseIngestor abstract method).

        Accepts ``query`` (free-text search term, required) and ``max_results``
        (int, default 20) as kwargs.
        """
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return []
        max_results_raw = kwargs.get("max_results", 20)
        try:
            max_results = int(max_results_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            max_results = 20
        page = await self.fetch_studies(query=query, max_results=max_results)
        return page.records

    async def fetch_studies(
        self,
        *,
        query: str,
        max_results: int = 20,
        page_token: str | None = None,
    ) -> ClinicalTrialsFetchPage:
        """Fetch studies matching the given free-text query.

        Uses the ``GET /studies`` endpoint with ``query.term`` for keyword
        search.  ``max_results`` is capped at the API page-size limit.
        """
        if not query.strip():
            return ClinicalTrialsFetchPage()
        page_size = max(1, min(max_results, _CLINICALTRIALS_MAX_PAGE_SIZE))
        params: dict[str, str] = {
            "query.term": query.strip(),
            "pageSize": str(page_size),
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            response = await self._make_request(
                "GET",
                "studies",
                params=params,
            )
            data = response.json()
        except Exception:  # noqa: BLE001
            logger.warning(
                "ClinicalTrials.gov request failed for query=%r",
                query,
                exc_info=True,
            )
            return ClinicalTrialsFetchPage()

        return self._parse_studies_payload(data)

    def _parse_studies_payload(self, data: object) -> ClinicalTrialsFetchPage:
        """Parse the v2 ``/studies`` response shape into RawRecord rows."""
        if not isinstance(data, dict):
            return ClinicalTrialsFetchPage()
        studies_raw = data.get("studies")
        if not isinstance(studies_raw, list):
            return ClinicalTrialsFetchPage()
        records: list[RawRecord] = []
        for study in studies_raw:
            if not isinstance(study, dict):
                continue
            normalized = self._normalize_study(study)
            if normalized:
                records.append(normalized)
        total_count_raw = data.get("totalCount")
        total_count = (
            int(total_count_raw) if isinstance(total_count_raw, int) else len(records)
        )
        next_page_token_raw = data.get("nextPageToken")
        next_page_token = (
            str(next_page_token_raw)
            if isinstance(next_page_token_raw, str) and next_page_token_raw.strip()
            else None
        )
        return ClinicalTrialsFetchPage(
            records=records,
            total_count=total_count,
            next_page_token=next_page_token,
        )

    def _normalize_study(self, study: JSONObject) -> RawRecord | None:
        """Project a v2 study payload into a flat RawRecord.

        The v2 API returns deeply nested ``protocolSection`` blocks; flatten
        the fields the downstream pipeline cares about (NCT ID, title,
        conditions, interventions, phase, status, sponsor) into a stable
        record shape.
        """
        protocol = study.get("protocolSection")
        if not isinstance(protocol, dict):
            return None
        identification = protocol.get("identificationModule") or {}
        status_module = protocol.get("statusModule") or {}
        sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
        conditions_module = protocol.get("conditionsModule") or {}
        interventions_module = protocol.get("armsInterventionsModule") or {}
        design_module = protocol.get("designModule") or {}
        description_module = protocol.get("descriptionModule") or {}

        nct_id = self._scalar_string(identification, "nctId")
        if not nct_id:
            return None
        brief_title = self._scalar_string(identification, "briefTitle")
        official_title = self._scalar_string(identification, "officialTitle")
        overall_status = self._scalar_string(status_module, "overallStatus")
        start_date = self._scalar_string(
            status_module.get("startDateStruct"),
            "date",
        )
        completion_date = self._scalar_string(
            status_module.get("completionDateStruct"),
            "date",
        )
        lead_sponsor = self._scalar_string(
            sponsor_module.get("leadSponsor"),
            "name",
        )
        conditions = self._scalar_list(conditions_module, "conditions")
        interventions = self._extract_interventions(interventions_module)
        phases = self._scalar_list(design_module, "phases")
        study_type = self._scalar_string(design_module, "studyType")
        brief_summary = self._scalar_string(description_module, "briefSummary")

        return {
            "nct_id": nct_id,
            "brief_title": brief_title,
            "official_title": official_title,
            "overall_status": overall_status,
            "start_date": start_date,
            "completion_date": completion_date,
            "lead_sponsor": lead_sponsor,
            "conditions": conditions,
            "interventions": interventions,
            "phases": phases,
            "study_type": study_type,
            "brief_summary": brief_summary,
        }

    @staticmethod
    def _scalar_string(payload: object, key: str) -> str:
        if not isinstance(payload, dict):
            return ""
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _scalar_list(payload: object, key: str) -> list[str]:
        if not isinstance(payload, dict):
            return []
        value = payload.get(key)
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if isinstance(item, str) and item]

    @staticmethod
    def _extract_interventions(module: object) -> list[JSONObject]:
        """Pull intervention name + type out of the v2 arms/interventions block."""
        if not isinstance(module, dict):
            return []
        interventions_raw = module.get("interventions")
        if not isinstance(interventions_raw, list):
            return []
        results: list[JSONObject] = []
        for entry in interventions_raw:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            intervention_type = entry.get("type")
            if not isinstance(name, str) or not name.strip():
                continue
            results.append(
                {
                    "name": name.strip(),
                    "type": (
                        intervention_type.strip()
                        if isinstance(intervention_type, str)
                        else ""
                    ),
                },
            )
        return results


__all__ = ["ClinicalTrialsFetchPage", "ClinicalTrialsIngestor"]
