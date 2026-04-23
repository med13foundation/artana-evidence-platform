"""Service-local ClinicalTrials.gov structured-source gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

_DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_PAGE_SIZE = 100
_USER_AGENT = "artana-evidence-platform/clinicaltrials-gateway"


@dataclass(frozen=True)
class ClinicalTrialsGatewayFetchResult:
    """Result of a ClinicalTrials.gov fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    next_page_token: str | None = None
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class ClinicalTrialsGatewayError(RuntimeError):
    """Raised when ClinicalTrials.gov returns an unusable response."""


class ClinicalTrialsSourceGateway:
    """Fetch and normalize public ClinicalTrials.gov v2 study records."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch_records(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        """Fetch clinical trial records matching a free-text query."""
        return asyncio.run(
            self.fetch_records_async(query=query, max_results=max_results),
        )

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        """Fetch clinical trial records from async callers."""
        if not query.strip():
            return ClinicalTrialsGatewayFetchResult()
        async with self._build_client() as client:
            payload = await self._get_json(
                client=client,
                endpoint="studies",
                params={
                    "query.term": query.strip(),
                    "pageSize": max(1, min(max_results, _MAX_PAGE_SIZE)),
                    "format": "json",
                },
            )
        records, total_count, next_page_token = _normalize_studies_payload(payload)
        return ClinicalTrialsGatewayFetchResult(
            records=records,
            fetched_records=min(total_count, len(records)),
            next_page_token=next_page_token,
        )

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    @staticmethod
    async def _get_json(
        *,
        client: httpx.AsyncClient,
        endpoint: str,
        params: Mapping[str, str | int],
    ) -> object:
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"ClinicalTrials.gov API request failed for {endpoint}: {exc}"
            raise ClinicalTrialsGatewayError(msg) from exc
        return response.json()


def _normalize_studies_payload(
    payload: object,
) -> tuple[list[dict[str, object]], int, str | None]:
    if not isinstance(payload, dict):
        return [], 0, None
    studies = payload.get("studies")
    if not isinstance(studies, list):
        return [], 0, None
    records: list[dict[str, object]] = []
    for study in studies:
        record = _normalize_study(study)
        if record is not None:
            records.append(record)
    raw_total_count = payload.get("totalCount")
    total_count = raw_total_count if isinstance(raw_total_count, int) else len(records)
    token = payload.get("nextPageToken")
    next_page_token = token.strip() if isinstance(token, str) and token.strip() else None
    return records, total_count, next_page_token


def _normalize_study(study: object) -> dict[str, object] | None:
    study_payload = _dict_value(study)
    if study_payload is None:
        return None
    protocol = _dict_value(study_payload.get("protocolSection"))
    if protocol is None:
        return None

    identification = _dict_value(protocol.get("identificationModule")) or {}
    status = _dict_value(protocol.get("statusModule")) or {}
    sponsors = _dict_value(protocol.get("sponsorCollaboratorsModule")) or {}
    conditions = _dict_value(protocol.get("conditionsModule")) or {}
    interventions = _dict_value(protocol.get("armsInterventionsModule")) or {}
    design = _dict_value(protocol.get("designModule")) or {}
    description = _dict_value(protocol.get("descriptionModule")) or {}

    nct_id = _first_string(identification, ("nctId",))
    if not nct_id:
        return None
    return {
        "nct_id": nct_id,
        "brief_title": _first_string(identification, ("briefTitle",)) or "",
        "official_title": _first_string(identification, ("officialTitle",)) or "",
        "overall_status": _first_string(status, ("overallStatus",)) or "",
        "start_date": _date_struct(status.get("startDateStruct")),
        "completion_date": _date_struct(status.get("completionDateStruct")),
        "lead_sponsor": _first_string(
            _dict_value(sponsors.get("leadSponsor")) or {},
            ("name",),
        )
        or "",
        "conditions": _string_list(conditions.get("conditions")),
        "interventions": _extract_interventions(interventions),
        "phases": _string_list(design.get("phases")),
        "study_type": _first_string(design, ("studyType",)) or "",
        "brief_summary": _first_string(description, ("briefSummary",)) or "",
        "source": "clinical_trials",
    }


def _extract_interventions(module: Mapping[str, object]) -> list[dict[str, object]]:
    interventions = module.get("interventions")
    if not isinstance(interventions, list):
        return []
    records: list[dict[str, object]] = []
    for intervention in interventions:
        payload = _dict_value(intervention)
        if payload is None:
            continue
        name = _first_string(payload, ("name",))
        if not name:
            continue
        records.append({"name": name, "type": _first_string(payload, ("type",)) or ""})
    return records


def _date_struct(value: object) -> str:
    payload = _dict_value(value)
    if payload is None:
        return ""
    return _first_string(payload, ("date",)) or ""


def _dict_value(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _first_string(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            if cleaned:
                return cleaned
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [" ".join(item.split()) for item in value if isinstance(item, str) and item.strip()]


__all__ = [
    "ClinicalTrialsGatewayError",
    "ClinicalTrialsGatewayFetchResult",
    "ClinicalTrialsSourceGateway",
]
