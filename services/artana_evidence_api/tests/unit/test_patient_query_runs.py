"""Patient-context query-run route tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsGatewayFetchResult
from artana_evidence_api.dependencies import (
    get_clinicaltrials_source_gateway,
    get_proposal_store,
    get_research_space_store,
    get_study_outcome_store,
)
from artana_evidence_api.patient_queries import PatientQueryRunRequest
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.study_outcomes import (
    HarnessStudyOutcomeStore,
    StudyOutcomeDraft,
)
from fastapi.testclient import TestClient

_TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_AUTH_HEADERS = {
    "X-TEST-USER-ID": str(_TEST_USER_ID),
    "X-TEST-USER-EMAIL": "query-runs@example.com",
    "X-TEST-USER-ROLE": "researcher",
}


class _QueryRunClinicalTrialsGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
        condition: str | None = None,
        overall_statuses: tuple[str, ...] = (),
        location: str | None = None,
        geo_filter: str | None = None,
    ) -> ClinicalTrialsGatewayFetchResult:
        self.calls.append(
            {
                "query": query,
                "max_results": max_results,
                "condition": condition,
                "overall_statuses": overall_statuses,
                "location": location,
                "geo_filter": geo_filter,
            },
        )
        return ClinicalTrialsGatewayFetchResult(
            records=[
                {
                    "nct_id": "NCT00000077",
                    "brief_title": "MGMT methylated GBM trial",
                    "overall_status": "RECRUITING",
                    "conditions": ["Glioblastoma"],
                    "interventions": [{"name": "Temozolomide", "type": "DRUG"}],
                    "phases": ["PHASE2"],
                    "eligibility_criteria": "MGMT methylated glioblastoma.",
                    "minimum_age": "18 Years",
                    "maximum_age": "70 Years",
                    "locations": [
                        {
                            "facility": "Boston Cancer Center",
                            "status": "RECRUITING",
                            "city": "Boston",
                            "state": "Massachusetts",
                            "zip": "02115",
                            "country": "United States",
                            "contacts": [
                                {
                                    "name": "Boston Coordinator",
                                    "role": "CONTACT",
                                    "phone": "",
                                    "email": "boston@example.org",
                                },
                            ],
                            "geo_point": {"lat": 42.36, "lon": -71.06},
                        },
                    ],
                },
            ],
            fetched_records=1,
        )


def test_patient_query_run_filters_claims_outcomes_and_trials_by_context() -> None:
    gateway = _QueryRunClinicalTrialsGateway()
    built = _build_client(gateway=gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/query-runs",
        headers=_AUTH_HEADERS,
        json={
            "query": "treatment_landscape",
            "patient_context": {
                "age": 35,
                "performance_status": "ECOG 0",
                "diagnosis": "GBM",
                "stage_or_grade": "IV",
                "molecular_markers": {
                    "MGMT": "methylated",
                    "IDH": "wildtype",
                    "EGFR": "amplified",
                    "EGFRvIII": "negative",
                },
                "prior_treatments": ["surgery_gross_total_resection"],
                "location": {"country": "US", "city": "Boston"},
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["query"] == "treatment_landscape"
    assert payload["patient_context"]["molecular_markers"]["MGMT"] == "methylated"
    assert [claim["title"] for claim in payload["claim_matches"]] == [
        "Lomustine plus TMZ for MGMT-methylated GBM",
    ]
    assert payload["claim_matches"][0]["evidence_grade"] == "High"
    assert "MGMT methylated" in payload["claim_matches"][0]["matched_terms"]
    assert payload["study_outcomes"][0]["intervention"] == "Lomustine plus TMZ"
    assert payload["study_outcomes"][0]["population"] == "MGMT-methylated GBM"
    assert payload["trial_matches"][0]["nct_id"] == "NCT00000077"
    assert payload["trial_matches"][0]["locations"][0]["city"] == "Boston"
    assert gateway.calls == [
        {
            "query": (
                "MGMT methylated IDH wildtype EGFR amplified "
                "surgery gross total resection"
            ),
            "max_results": 20,
            "condition": "GBM",
            "overall_statuses": ("RECRUITING", "NOT_YET_RECRUITING"),
            "location": "Boston, US",
            "geo_filter": None,
        },
    ]


def test_patient_query_run_returns_503_when_trial_gateway_is_missing() -> None:
    built = _build_client(gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/query-runs",
        headers=_AUTH_HEADERS,
        json={
            "query": "treatment_landscape",
            "patient_context": {"diagnosis": "GBM"},
        },
    )

    assert response.status_code == 503
    assert "ClinicalTrials.gov gateway is not available" in response.json()["detail"]


def test_patient_context_normalizes_blank_diagnosis_without_nulling_field() -> None:
    request = PatientQueryRunRequest.model_validate(
        {
            "query": " treatment_landscape ",
            "patient_context": {
                "diagnosis": "   ",
                "molecular_markers": {"MGMT": " methylated "},
                "prior_treatments": ["tmz", "tmz", "  "],
            },
        },
    )

    assert request.query == "treatment_landscape"
    assert request.patient_context.diagnosis == ""
    assert request.patient_context.molecular_markers == {"MGMT": "methylated"}
    assert request.patient_context.prior_treatments == ["tmz"]


class _BuiltClient:
    def __init__(self, *, client: TestClient, space_id: UUID) -> None:
        self.client = client
        self.space_id = space_id


def _build_client(
    *,
    gateway: _QueryRunClinicalTrialsGateway | None,
) -> _BuiltClient:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Patient Query Runs",
        description="Owned test space for patient-context query routes.",
    )
    proposal_store = HarnessProposalStore()
    study_outcome_store = HarnessStudyOutcomeStore()
    run_id = uuid4()
    _seed_promoted_proposals(
        proposal_store=proposal_store,
        space_id=UUID(space.id),
        run_id=run_id,
    )
    study_outcome_store.create_outcomes(
        space_id=space.id,
        document_id=uuid4(),
        run_id=run_id,
        outcomes=(
            StudyOutcomeDraft(
                intervention="Lomustine plus TMZ",
                comparator="TMZ",
                outcome_metric="median_overall_survival",
                value=48.1,
                unit="months",
                confidence_interval_low=None,
                confidence_interval_high=None,
                population="MGMT-methylated GBM",
                n=129,
                source_pmid="30782343",
                source_quote="MGMT-methylated subset median OS 48.1 months",
                metadata={"marker": "MGMT methylated"},
            ),
            StudyOutcomeDraft(
                intervention="EGFRvIII vaccine",
                comparator=None,
                outcome_metric="objective_response_rate",
                value=12.0,
                unit="percent",
                confidence_interval_low=None,
                confidence_interval_high=None,
                population="EGFRvIII-positive GBM",
                n=20,
                source_pmid="00000000",
                source_quote="EGFRvIII-positive cohort ORR 12%",
                metadata={"marker": "EGFRvIII positive"},
            ),
        ),
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_study_outcome_store] = lambda: study_outcome_store
    app.dependency_overrides[get_clinicaltrials_source_gateway] = lambda: gateway
    return _BuiltClient(client=TestClient(app), space_id=UUID(space.id))


def _seed_promoted_proposals(
    *,
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: UUID,
) -> None:
    proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="pubmed",
                source_key="pubmed:mgmt",
                title="Lomustine plus TMZ for MGMT-methylated GBM",
                summary=(
                    "Lomustine plus temozolomide treats MGMT methylated "
                    "glioblastoma with improved survival."
                ),
                confidence=0.91,
                ranking_score=0.95,
                reasoning_path={},
                evidence_bundle=[
                    {"quote": "MGMT methylated GBM median OS improved with TMZ."},
                ],
                payload={
                    "subject": "Lomustine plus TMZ",
                    "relation": "TREATS",
                    "object": "MGMT-methylated GBM",
                },
                metadata={"stratification": {"MGMT": "methylated"}},
                evidence_grade="high",
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="pubmed",
                source_key="pubmed:egfrviii",
                title="EGFRvIII vaccine for EGFRvIII-positive GBM",
                summary="EGFRvIII-targeted vaccine applies to EGFRvIII-positive GBM.",
                confidence=0.8,
                ranking_score=0.7,
                reasoning_path={},
                evidence_bundle=[{"quote": "EGFRvIII-positive GBM vaccine cohort."}],
                payload={
                    "subject": "EGFRvIII vaccine",
                    "relation": "TREATS",
                    "object": "EGFRvIII-positive GBM",
                },
                metadata={"stratification": {"EGFRvIII": "positive"}},
                evidence_grade="moderate",
            ),
        ),
    )
    for proposal in proposals:
        proposal_store.decide_proposal(
            space_id=space_id,
            proposal_id=proposal.id,
            status="promoted",
            decision_reason="seeded promoted claim",
            decided_by=None,
        )
