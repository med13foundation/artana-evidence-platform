from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import pytest
from artana_api import ArtanaClient
from artana_api.exceptions import ArtanaRequestError
from artana_api_test_helpers import ENTITY_ID

if TYPE_CHECKING:
    from sqlalchemy import MetaData
    from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICES_ROOT = REPO_ROOT / "services"
_TEST_JWT_SECRET = "artana-sdk-integration-secret-for-tests-0123456789"
_TEST_BOOTSTRAP_KEY = "artana-bootstrap-secret-for-tests"
_TEST_USER_ID = "99999999-9999-9999-9999-999999999999"
_TEST_USER_EMAIL = "sdk-integration@example.com"
_CARDIOMYOPATHY_ID = "44444444-4444-4444-4444-444444444444"
_CDK8_ID = "22222222-2222-2222-2222-222222222222"


@dataclass(frozen=True, slots=True)
class _LiveHarnessService:
    http_client: httpx.Client
    base_url: str
    access_token: str
    bootstrap_key: str
    issue_access_token: Callable[[str, str, str], str]


def _reset_harness_schema(engine: object, base_metadata: object) -> None:
    sqlalchemy_engine = cast("Engine", engine)
    metadata = cast("MetaData", base_metadata)
    if sqlalchemy_engine.dialect.name == "sqlite":
        with sqlalchemy_engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            metadata.drop_all(bind=connection)
            metadata.create_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    metadata.drop_all(bind=sqlalchemy_engine)
    metadata.create_all(bind=sqlalchemy_engine)


def _drop_harness_schema(engine: object, base_metadata: object) -> None:
    sqlalchemy_engine = cast("Engine", engine)
    metadata = cast("MetaData", base_metadata)
    if sqlalchemy_engine.dialect.name == "sqlite":
        with sqlalchemy_engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            metadata.drop_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    metadata.drop_all(bind=sqlalchemy_engine)


def _ensure_service_environment() -> None:
    if str(SERVICES_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVICES_ROOT))

    os.environ["TESTING"] = "true"
    configured_database_url = os.environ.setdefault(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        f"sqlite:///{REPO_ROOT / '.pytest_artana_api_sdk.sqlite'}",
    )
    os.environ.setdefault(
        "DATABASE_URL",
        configured_database_url,
    )
    if configured_database_url.startswith("postgresql"):
        os.environ.setdefault("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")
        os.environ.setdefault("GRAPH_DB_SCHEMA", "graph_runtime")
    else:
        os.environ["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
        os.environ["GRAPH_DB_SCHEMA"] = "public"
    os.environ["AUTH_JWT_SECRET"] = _TEST_JWT_SECRET
    os.environ["ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"] = _TEST_BOOTSTRAP_KEY
    os.environ["GRAPH_JWT_SECRET"] = _TEST_JWT_SECRET
    os.environ["GRAPH_JWT_ISSUER"] = "graph-biomedical"
    os.environ["ARTANA_EVIDENCE_API_SERVICE_RELOAD"] = "0"
    os.environ["GRAPH_SERVICE_RELOAD"] = "0"


def _optional_external_dependency_roots() -> tuple[str, ...]:
    return (
        "artana",
        "email_validator",
        "fastapi",
        "jwt",
        "sqlalchemy",
        "yaml",
    )


def _import_service_module(module_name: str) -> ModuleType:
    try:
        __import__(module_name)
    except ModuleNotFoundError as exc:
        missing_root = exc.name.split(".", maxsplit=1)[0] if exc.name else ""
        if missing_root in _optional_external_dependency_roots():
            pytest.skip(
                f"SDK integration tests require optional service dependency '{missing_root}'.",
            )
        raise
    return cast(ModuleType, sys.modules[module_name])


def _build_access_token(
    *,
    jwt_module: ModuleType,
    auth_module: ModuleType,
    user_id: str = _TEST_USER_ID,
    email: str = _TEST_USER_EMAIL,
    username: str = "sdk-integration",
    full_name: str = "SDK Integration",
    role: str = "admin",
) -> str:
    secret = os.environ["AUTH_JWT_SECRET"]
    payload = {
        "iss": auth_module._TOKEN_ISSUER,
        "sub": user_id,
        "type": "access",
        "email": email,
        "username": username,
        "full_name": full_name,
        "role": role,
        "status": "active",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return cast(
        "str",
        jwt_module.encode(
            payload,
            secret,
            algorithm=auth_module._TOKEN_ALGORITHM,
        ),
    )


@contextmanager
def _live_service_context() -> Iterator[_LiveHarnessService]:
    _ensure_service_environment()
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    jwt_module = pytest.importorskip("jwt")

    agent_contracts = _import_service_module("artana_evidence_api.agent_contracts")
    app_module = _import_service_module("artana_evidence_api.app")
    artifact_store_module = _import_service_module("artana_evidence_api.artifact_store")
    approval_store_module = _import_service_module("artana_evidence_api.approval_store")
    auth_module = _import_service_module("artana_evidence_api.auth")
    database_module = _import_service_module("artana_evidence_api.database")
    chat_workflow_module = _import_service_module("artana_evidence_api.chat_workflow")
    chat_session_module = _import_service_module("artana_evidence_api.chat_sessions")
    document_store_module = _import_service_module("artana_evidence_api.document_store")
    document_binary_store_module = _import_service_module(
        "artana_evidence_api.document_binary_store",
    )
    dependencies_module = _import_service_module("artana_evidence_api.dependencies")
    graph_chat_runtime_module = _import_service_module(
        "artana_evidence_api.graph_chat_runtime",
    )
    graph_connection_runtime_module = _import_service_module(
        "artana_evidence_api.graph_connection_runtime",
    )
    hypothesis_runtime_module = _import_service_module(
        "artana_evidence_api.hypothesis_runtime",
    )
    graph_search_runtime_module = _import_service_module(
        "artana_evidence_api.graph_search_runtime",
    )
    graph_snapshot_module = _import_service_module("artana_evidence_api.graph_snapshot")
    harness_runtime_module = _import_service_module(
        "artana_evidence_api.harness_runtime",
    )
    proposal_store_module = _import_service_module("artana_evidence_api.proposal_store")
    pubmed_discovery_module = _import_service_module(
        "artana_evidence_api.pubmed_discovery",
    )
    graph_contracts_module = _import_service_module(
        "artana_evidence_api.types.graph_contracts",
    )
    base_model_module = _import_service_module("artana_evidence_api.models.base")
    _import_service_module("artana_evidence_api.models.api_key")
    _import_service_module("artana_evidence_api.models.user")
    research_onboarding_agent_runtime_module = _import_service_module(
        "artana_evidence_api.research_onboarding_agent_runtime",
    )
    research_onboarding_runtime_module = _import_service_module(
        "artana_evidence_api.research_onboarding_runtime",
    )
    research_space_store_module = _import_service_module(
        "artana_evidence_api.research_space_store",
    )
    research_state_module = _import_service_module("artana_evidence_api.research_state")
    run_registry_module = _import_service_module("artana_evidence_api.run_registry")
    schedule_store_module = _import_service_module("artana_evidence_api.schedule_store")

    EvidenceItem = agent_contracts.EvidenceItem
    GraphConnectionContract = agent_contracts.GraphConnectionContract
    GraphSearchContract = agent_contracts.GraphSearchContract
    GraphSearchResultEntry = agent_contracts.GraphSearchResultEntry
    OnboardingAssistantContract = agent_contracts.OnboardingAssistantContract
    OnboardingQuestion = agent_contracts.OnboardingQuestion
    OnboardingSection = agent_contracts.OnboardingSection
    OnboardingStatePatch = agent_contracts.OnboardingStatePatch
    OnboardingSuggestedAction = agent_contracts.OnboardingSuggestedAction
    ProposedRelation = agent_contracts.ProposedRelation

    create_app = app_module.create_app
    engine = database_module.engine
    HarnessArtifactStore = artifact_store_module.HarnessArtifactStore
    HarnessApprovalStore = approval_store_module.HarnessApprovalStore
    Base = base_model_module.Base
    HarnessChatSessionStore = chat_session_module.HarnessChatSessionStore
    HarnessDocumentBinaryStore = document_binary_store_module.HarnessDocumentBinaryStore
    HarnessDocumentStore = document_store_module.HarnessDocumentStore
    get_artifact_store = dependencies_module.get_artifact_store
    get_chat_session_store = dependencies_module.get_chat_session_store
    get_document_binary_store = dependencies_module.get_document_binary_store
    get_document_store = dependencies_module.get_document_store
    get_graph_api_gateway = dependencies_module.get_graph_api_gateway
    get_graph_chat_runner = dependencies_module.get_graph_chat_runner
    get_graph_connection_runner = dependencies_module.get_graph_connection_runner
    get_graph_search_runner = dependencies_module.get_graph_search_runner
    get_harness_execution_services = dependencies_module.get_harness_execution_services
    get_proposal_store = dependencies_module.get_proposal_store
    get_pubmed_discovery_service = dependencies_module.get_pubmed_discovery_service
    get_research_onboarding_runner = dependencies_module.get_research_onboarding_runner
    get_research_space_store = dependencies_module.get_research_space_store
    get_research_state_store = dependencies_module.get_research_state_store
    get_run_registry = dependencies_module.get_run_registry
    HarnessGraphConnectionRequest = (
        graph_connection_runtime_module.HarnessGraphConnectionRequest
    )
    HarnessGraphConnectionResult = (
        graph_connection_runtime_module.HarnessGraphConnectionResult
    )
    HarnessGraphSearchRequest = graph_search_runtime_module.HarnessGraphSearchRequest
    HarnessGraphSearchResult = graph_search_runtime_module.HarnessGraphSearchResult
    GraphChatEvidenceItem = graph_chat_runtime_module.GraphChatEvidenceItem
    GraphChatResult = graph_chat_runtime_module.GraphChatResult
    GraphChatVerification = graph_chat_runtime_module.GraphChatVerification
    HarnessGraphSnapshotStore = graph_snapshot_module.HarnessGraphSnapshotStore
    HarnessExecutionServices = harness_runtime_module.HarnessExecutionServices
    HarnessProposalStore = proposal_store_module.HarnessProposalStore
    HarnessResearchOnboardingContinuationRequest = (
        research_onboarding_agent_runtime_module.HarnessResearchOnboardingContinuationRequest
    )
    HarnessResearchOnboardingInitialRequest = (
        research_onboarding_agent_runtime_module.HarnessResearchOnboardingInitialRequest
    )
    HarnessResearchOnboardingResult = (
        research_onboarding_agent_runtime_module.HarnessResearchOnboardingResult
    )
    ResearchOnboardingContinuationRequest = (
        research_onboarding_runtime_module.ResearchOnboardingContinuationRequest
    )
    HarnessResearchSpaceStore = research_space_store_module.HarnessResearchSpaceStore
    HarnessResearchStateStore = research_state_module.HarnessResearchStateStore
    HarnessRunRegistry = run_registry_module.HarnessRunRegistry
    HarnessScheduleStore = schedule_store_module.HarnessScheduleStore
    AdvancedQueryParameters = pubmed_discovery_module.AdvancedQueryParameters
    DiscoveryProvider = pubmed_discovery_module.DiscoveryProvider
    DiscoverySearchJob = pubmed_discovery_module.DiscoverySearchJob
    DiscoverySearchStatus = pubmed_discovery_module.DiscoverySearchStatus
    KernelEntityListResponse = graph_contracts_module.KernelEntityListResponse
    KernelEntityResponse = graph_contracts_module.KernelEntityResponse
    KernelRelationClaimResponse = graph_contracts_module.KernelRelationClaimResponse
    execute_graph_chat_message = chat_workflow_module.execute_graph_chat_message
    execute_graph_connection_run = (
        graph_connection_runtime_module.execute_graph_connection_run
    )
    execute_graph_search_run = graph_search_runtime_module.execute_graph_search_run
    execute_hypothesis_run = hypothesis_runtime_module.execute_hypothesis_run
    execute_research_onboarding_continuation = (
        research_onboarding_runtime_module.execute_research_onboarding_continuation
    )
    execute_research_onboarding_run = (
        research_onboarding_runtime_module.execute_research_onboarding_run
    )
    TestClient = fastapi_testclient.TestClient

    @dataclass(frozen=True, slots=True)
    class _StubGraphHealthResponse:
        status: str
        version: str

    @dataclass(slots=True)
    class _ToolExecutionResult:
        result_json: str

    @dataclass(slots=True)
    class _TenantContext:
        tenant_id: str

    @dataclass(slots=True)
    class _PromotedClaim:
        id: str
        space_id: str
        source_entity_id: str
        target_entity_id: str
        relation_type: str
        claim_text: str
        evidence_summary: str | None

    @dataclass(slots=True)
    class _LiveGraphState:
        promoted_claims: list[_PromotedClaim] = field(default_factory=list)
        pubmed_jobs: dict[str, object] = field(default_factory=dict)

    state = _LiveGraphState()

    def _entity_label(entity_id: str) -> str:
        labels = {
            ENTITY_ID: "MED13",
            _CDK8_ID: "CDK8",
            _CARDIOMYOPATHY_ID: "cardiomyopathy",
        }
        return labels.get(entity_id, entity_id)

    def _entity_type(entity_id: str) -> str:
        if entity_id == _CARDIOMYOPATHY_ID:
            return "DISEASE"
        return "GENE"

    def _build_pubmed_job(
        *,
        owner_id: str,
        session_id: str | None,
        query_preview: str,
        gene_symbol: str | None,
        additional_terms: str | None = None,
        max_results: int = 25,
    ) -> object:
        now = datetime.now(UTC)
        job = DiscoverySearchJob(
            id=uuid5(
                NAMESPACE_URL,
                f"{owner_id}:{session_id or 'none'}:{query_preview}:{max_results}",
            ),
            owner_id=UUID(owner_id),
            session_id=UUID(session_id) if session_id is not None else None,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview=query_preview,
            parameters=AdvancedQueryParameters(
                gene_symbol=gene_symbol,
                search_term=query_preview,
                max_results=max_results,
                additional_terms=additional_terms,
            ),
            total_results=3,
            result_metadata={
                "preview_records": [
                    {
                        "pmid": f"pmid-{index}",
                        "title": f"Synthetic PubMed result {index}",
                        "query": query_preview,
                    }
                    for index in range(1, 4)
                ],
            },
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        state.pubmed_jobs[str(job.id)] = job
        return job

    class _StubGraphApiGateway:
        def __init__(self) -> None:
            self.closed = False

        def get_health(self) -> _StubGraphHealthResponse:
            return _StubGraphHealthResponse(status="ok", version="sdk-integration")

        def list_entities(
            self,
            *,
            space_id: UUID | str,
            q: str | None = None,
            entity_type: str | None = None,
            ids: list[str] | None = None,
            offset: int = 0,
            limit: int = 50,
        ) -> object:
            now = datetime.now(UTC)
            catalog = [
                KernelEntityResponse(
                    id=UUID(ENTITY_ID),
                    research_space_id=UUID(str(space_id)),
                    entity_type="GENE",
                    display_label="MED13",
                    aliases=["Mediator complex subunit 13"],
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
                KernelEntityResponse(
                    id=UUID(_CDK8_ID),
                    research_space_id=UUID(str(space_id)),
                    entity_type="GENE",
                    display_label="CDK8",
                    aliases=["Cyclin-dependent kinase 8"],
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
                KernelEntityResponse(
                    id=UUID(_CARDIOMYOPATHY_ID),
                    research_space_id=UUID(str(space_id)),
                    entity_type="DISEASE",
                    display_label="cardiomyopathy",
                    aliases=["dilated cardiomyopathy"],
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ]
            matched = catalog
            if ids:
                normalized_ids = {str(UUID(entity_id)) for entity_id in ids}
                matched = [
                    entity for entity in matched if str(entity.id) in normalized_ids
                ]
            if entity_type is not None:
                normalized_type = entity_type.strip().upper()
                matched = [
                    entity
                    for entity in matched
                    if entity.entity_type.upper() == normalized_type
                ]
            if isinstance(q, str) and q.strip() != "":
                normalized_query = q.strip().casefold()
                matched = [
                    entity
                    for entity in matched
                    if normalized_query in (entity.display_label or "").casefold()
                    or any(
                        normalized_query in alias.casefold() for alias in entity.aliases
                    )
                ]
            sliced = matched[offset : offset + limit]
            return KernelEntityListResponse(
                entities=sliced,
                total=len(matched),
                offset=offset,
                limit=limit,
            )

        def create_claim(
            self,
            *,
            space_id: UUID | str,
            request: object,
        ) -> object:
            now = datetime.now(UTC)
            claim_id = uuid4()
            source_entity_id = str(request.source_entity_id)
            target_entity_id = str(request.target_entity_id)
            state.promoted_claims.append(
                _PromotedClaim(
                    id=str(claim_id),
                    space_id=str(space_id),
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    relation_type=request.relation_type,
                    claim_text=request.claim_text or request.evidence_summary or "",
                    evidence_summary=request.evidence_summary,
                ),
            )
            return KernelRelationClaimResponse(
                id=claim_id,
                research_space_id=UUID(str(space_id)),
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=request.agent_run_id,
                source_type="HARNESS",
                relation_type=request.relation_type,
                target_type=_entity_type(target_entity_id),
                source_label=_entity_label(source_entity_id),
                target_label=_entity_label(target_entity_id),
                confidence=request.derived_confidence,
                validation_state="ALLOWED",
                validation_reason="sdk_integration_stub",
                persistability="PERSISTABLE",
                claim_status="OPEN",
                polarity="SUPPORT",
                claim_text=request.claim_text,
                claim_section=None,
                linked_relation_id=None,
                metadata=request.metadata,
                triaged_by=None,
                triaged_at=None,
                created_at=now,
                updated_at=now,
            )

        def create_relation(self, *, space_id, request):
            from dataclasses import dataclass, field

            @dataclass
            class _Rel:
                id: UUID = field(default_factory=uuid4)
                research_space_id: UUID = field(default_factory=uuid4)
                source_id: UUID = field(default_factory=uuid4)
                source_claim_id: UUID = field(default_factory=uuid4)
                relation_type: str = "ASSOCIATED_WITH"
                target_id: UUID = field(default_factory=uuid4)
                confidence: float = 0.5
                aggregate_confidence: float = 0.5
                source_count: int = 1
                highest_evidence_tier: str | None = "LITERATURE"
                curation_status: str = "DRAFT"
                evidence_summary: str | None = None
                provenance_id: UUID | None = None
                reviewed_by: UUID | None = None
                reviewed_at: object = None
                created_at: object = field(
                    default_factory=lambda: datetime.now(UTC),
                )
                updated_at: object = field(
                    default_factory=lambda: datetime.now(UTC),
                )

            rel = _Rel(
                research_space_id=UUID(str(space_id)),
                source_id=request.source_id,
                source_claim_id=uuid4(),
                relation_type=request.relation_type,
                target_id=request.target_id,
                confidence=request.derived_confidence,
                aggregate_confidence=request.derived_confidence,
                evidence_summary=getattr(request, "evidence_summary", None),
            )
            state.promoted_claims.append(
                _PromotedClaim(
                    id=str(rel.id),
                    space_id=str(space_id),
                    source_entity_id=str(request.source_id),
                    target_entity_id=str(request.target_id),
                    relation_type=request.relation_type,
                    claim_text=getattr(request, "evidence_sentence", None) or "",
                    evidence_summary=getattr(request, "evidence_summary", None),
                ),
            )
            return rel

        def close(self) -> None:
            self.closed = True

    class _FakeKernelRuntime:
        kernel: object | None = None

        def __init__(self) -> None:
            self._leases: dict[tuple[str, str], str] = {}

        def explain_tool_allowlist(
            self,
            *,
            tenant_id: str,
            run_id: str,
            visible_tool_names: set[str],
        ) -> dict[str, object]:
            del tenant_id, run_id
            return {
                "model": "sdk-test-model",
                "tenant_capabilities": [],
                "visible_tool_names_applied": True,
                "final_allowed_tools": sorted(visible_tool_names),
                "decisions": [
                    {
                        "tool_name": tool_name,
                        "decision": "allowed",
                        "reason": "sdk_integration_test",
                    }
                    for tool_name in sorted(visible_tool_names)
                ],
            }

        def get_events(self, *, run_id: str, tenant_id: str) -> tuple[object, ...]:
            del run_id, tenant_id
            return ()

        def tenant_context(self, *, tenant_id: str) -> _TenantContext:
            return _TenantContext(tenant_id=tenant_id)

        def acquire_run_lease(
            self,
            *,
            run_id: str,
            tenant_id: str,
            worker_id: str,
            ttl_seconds: int,
        ) -> bool:
            del ttl_seconds
            key = (tenant_id, run_id)
            if key in self._leases:
                return False
            self._leases[key] = worker_id
            return True

        def release_run_lease(
            self,
            *,
            run_id: str,
            tenant_id: str,
            worker_id: str,
        ) -> bool:
            key = (tenant_id, run_id)
            if self._leases.get(key) != worker_id:
                return False
            del self._leases[key]
            return True

        def _tool_payload(
            self,
            *,
            tenant_id: str,
            tool_name: str,
            arguments: object,
        ) -> dict[str, object]:
            if tool_name == "run_pubmed_search":
                query_preview = getattr(arguments, "search_term", "MED13")
                gene_symbol = getattr(arguments, "gene_symbol", None)
                additional_terms = getattr(arguments, "additional_terms", None)
                max_results = getattr(arguments, "max_results", 25)
                job = _build_pubmed_job(
                    owner_id=_TEST_USER_ID,
                    session_id=tenant_id,
                    query_preview=query_preview,
                    gene_symbol=gene_symbol,
                    additional_terms=additional_terms,
                    max_results=max_results,
                )
                return cast("dict[str, object]", job.model_dump(mode="json"))
            if tool_name == "suggest_relations":
                source_entity_ids = getattr(arguments, "source_entity_ids", [])
                source_entity_id = (
                    source_entity_ids[0]
                    if isinstance(source_entity_ids, list) and source_entity_ids
                    else ENTITY_ID
                )
                return {
                    "suggestions": [
                        {
                            "source_entity_id": source_entity_id,
                            "target_entity_id": _CARDIOMYOPATHY_ID,
                            "relation_type": "ASSOCIATED_WITH",
                            "final_score": 0.91,
                            "score_breakdown": {
                                "vector_score": 0.88,
                                "graph_overlap_score": 0.83,
                                "relation_prior_score": 0.92,
                            },
                            "constraint_check": {
                                "passed": True,
                                "source_entity_type": "GENE",
                                "relation_type": "ASSOCIATED_WITH",
                                "target_entity_type": "DISEASE",
                            },
                        },
                    ],
                    "total": 1,
                    "limit_per_source": getattr(arguments, "limit_per_source", 5),
                    "min_score": getattr(arguments, "min_score", 0.0),
                }
            return {}

        def step_tool(
            self,
            *,
            run_id: str,
            tenant_id: str,
            tool_name: str,
            arguments: object,
            step_key: str,
            parent_step_key: str | None = None,
        ) -> _ToolExecutionResult:
            del run_id, step_key, parent_step_key
            return _ToolExecutionResult(
                result_json=json.dumps(
                    self._tool_payload(
                        tenant_id=tenant_id,
                        tool_name=tool_name,
                        arguments=arguments,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )

        def reconcile_tool(
            self,
            *,
            run_id: str,
            tenant_id: str,
            tool_name: str,
            arguments: object,
            step_key: str,
            parent_step_key: str | None = None,
        ) -> str:
            del run_id, step_key, parent_step_key
            return json.dumps(
                self._tool_payload(
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    arguments=arguments,
                ),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )

    class _StubGraphSearchRunner:
        def _promoted_claims(self, *, space_id: str) -> list[_PromotedClaim]:
            return [
                claim for claim in state.promoted_claims if claim.space_id == space_id
            ]

        async def run(self, request: object) -> object:
            assert isinstance(request, HarnessGraphSearchRequest)
            promoted_claims = self._promoted_claims(
                space_id=request.research_space_id,
            )
            support_summary = "One highly relevant entity match."
            explanation = "Direct entity match in the graph."
            matching_relation_ids: list[str] = []
            if promoted_claims:
                promoted_claim = promoted_claims[-1]
                support_summary = (
                    f"1 grounded entity match plus {len(promoted_claims)} promoted "
                    "relation claim(s)."
                )
                explanation = (
                    "Direct entity match in the graph and a promoted relation claim "
                    f"for {_entity_label(promoted_claim.target_entity_id)}."
                )
                matching_relation_ids = [claim.id for claim in promoted_claims]
            contract = GraphSearchContract(
                decision="generated",
                research_space_id=request.research_space_id,
                original_query=request.question,
                interpreted_intent="Find graph evidence for the input question",
                query_plan_summary="Search the graph for matching entities and evidence.",
                total_results=1,
                results=[
                    GraphSearchResultEntry(
                        entity_id=ENTITY_ID,
                        entity_type="GENE",
                        display_label="MED13",
                        relevance_score=0.99,
                        matching_observation_ids=[],
                        matching_relation_ids=matching_relation_ids,
                        evidence_chain=[],
                        explanation=explanation,
                        support_summary=support_summary,
                    ),
                ],
                executed_path="agent",
                warnings=[],
                agent_run_id="sdk-graph-search-agent-run",
                confidence_score=0.97,
                rationale="The question maps cleanly to a known graph entity.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="sdk-graph-search",
                        excerpt=request.question,
                        relevance=0.95,
                    ),
                ],
            )
            return HarnessGraphSearchResult(
                contract=contract,
                agent_run_id=contract.agent_run_id,
                active_skill_names=("graph_search_skill",),
            )

    class _StubGraphChatRunner:
        async def run(self, request: object) -> object:
            normalized_question = request.question.strip().lower()
            refresh_mode = any(
                token in normalized_question
                for token in ("refresh", "latest", "pubmed")
            )
            verification = GraphChatVerification(
                status="needs_review" if refresh_mode else "verified",
                reason=(
                    "Needs literature refresh for a more current answer."
                    if refresh_mode
                    else "Grounded graph answer is sufficient for review."
                ),
                grounded_match_count=1,
                top_relevance_score=0.93,
                warning_count=0,
                allows_graph_write=not refresh_mode,
            )
            search = GraphSearchContract(
                decision="generated",
                research_space_id=request.research_space_id,
                original_query=request.question,
                interpreted_intent="Answer the graph chat question",
                query_plan_summary="Ground the answer in graph evidence.",
                total_results=1,
                results=[
                    GraphSearchResultEntry(
                        entity_id=ENTITY_ID,
                        entity_type="GENE",
                        display_label="MED13",
                        relevance_score=0.93,
                        matching_observation_ids=[],
                        matching_relation_ids=([] if refresh_mode else ["rel-med13"]),
                        evidence_chain=([] if refresh_mode else [{"kind": "claim"}]),
                        explanation="MED13 is the grounded anchor entity.",
                        support_summary="Synthetic grounded graph support for MED13.",
                    ),
                ],
                executed_path="agent",
                warnings=[],
                agent_run_id="sdk-graph-chat-agent-run",
                confidence_score=0.93,
                rationale="Grounded graph answer produced for integration testing.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="sdk-graph-chat",
                        excerpt=request.question,
                        relevance=0.93,
                    ),
                ],
            )
            result = GraphChatResult(
                answer_text=(
                    "Needs refreshed literature before proposing graph writes."
                    if refresh_mode
                    else "Grounded answer: MED13 has evidence-linked disease associations."
                ),
                chat_summary="Synthetic graph chat summary.",
                evidence_bundle=[
                    GraphChatEvidenceItem(
                        entity_id=ENTITY_ID,
                        entity_type="GENE",
                        display_label="MED13",
                        relevance_score=0.93,
                        support_summary="Grounded evidence for MED13.",
                        explanation="MED13 is directly grounded in the graph.",
                    ),
                ],
                warnings=[],
                verification=verification,
                search=search,
            )
            return result.with_active_skill_names(("graph_chat_skill",))

    class _StubGraphConnectionRunner:
        async def run(self, request: object) -> object:
            assert isinstance(request, HarnessGraphConnectionRequest)
            contract = GraphConnectionContract(
                decision="generated",
                source_type=request.source_type or "pubmed",
                research_space_id=request.research_space_id,
                seed_entity_id=request.seed_entity_id,
                proposed_relations=[
                    ProposedRelation(
                        source_id=request.seed_entity_id,
                        relation_type="ASSOCIATED_WITH",
                        target_id="44444444-4444-4444-4444-444444444444",
                        assessment={
                            "support_band": "STRONG",
                            "grounding_level": "GRAPH_INFERENCE",
                            "mapping_status": "NOT_APPLICABLE",
                            "speculation_level": "NOT_APPLICABLE",
                            "confidence_rationale": (
                                "The relationship is repeatedly observed in supporting evidence."
                            ),
                        },
                        confidence=0.88,
                        evidence_summary="Supported by literature-backed signals.",
                        evidence_tier="COMPUTATIONAL",
                        supporting_provenance_ids=[
                            "55555555-5555-5555-5555-555555555555",
                        ],
                        supporting_document_count=2,
                        reasoning="The relationship is repeatedly observed in supporting evidence.",
                    ),
                ],
                rejected_candidates=[],
                shadow_mode=request.shadow_mode,
                agent_run_id="sdk-graph-connection-agent-run",
                confidence_score=0.9,
                rationale="A supported relation candidate was found.",
                evidence=[
                    EvidenceItem(
                        source_type="paper",
                        locator="pmid:123456",
                        excerpt="MED13 is associated with a cardiomyopathy phenotype.",
                        relevance=0.9,
                    ),
                ],
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=contract.agent_run_id,
                active_skill_names=("graph_connection_skill",),
            )

    class _StubResearchOnboardingRunner:
        async def run_initial(self, request: object) -> object:
            assert isinstance(request, HarnessResearchOnboardingInitialRequest)
            question_prompt = "Which phenotype focus matters most?"
            contract = OnboardingAssistantContract(
                message_type="clarification_request",
                title=f"{request.research_title}: one detail before planning",
                summary="Need one clarification before producing the plan.",
                sections=[
                    OnboardingSection(
                        heading="Scope",
                        body=request.primary_objective or "No objective provided yet.",
                    ),
                ],
                questions=[
                    OnboardingQuestion(
                        id="phenotype-focus",
                        prompt=question_prompt,
                        helper_text=None,
                    ),
                ],
                suggested_actions=[
                    OnboardingSuggestedAction(
                        id="answer-question",
                        label="Answer question",
                        action_type="reply",
                    ),
                ],
                artifacts=[],
                state_patch=OnboardingStatePatch(
                    thread_status="your_turn",
                    onboarding_status="awaiting_researcher_reply",
                    pending_question_count=1,
                    objective=request.primary_objective or None,
                    explored_questions=[],
                    pending_questions=[question_prompt],
                    current_hypotheses=[],
                ),
                agent_run_id="sdk-onboarding-agent-initial",
                warnings=[],
                confidence_score=0.91,
                rationale="A single explicit clarification is enough for the next turn.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="research_onboarding_intake",
                        excerpt=request.research_title,
                        relevance=0.93,
                    ),
                ],
            )
            return HarnessResearchOnboardingResult(
                contract=contract,
                agent_run_id="sdk-onboarding-agent-initial",
                active_skill_names=("onboarding_skill",),
            )

        async def run_continuation(self, request: object) -> object:
            assert isinstance(request, HarnessResearchOnboardingContinuationRequest)
            contract = OnboardingAssistantContract(
                message_type="plan_ready",
                title="Initial research plan is ready",
                summary="There is enough context to proceed with a first plan.",
                sections=[
                    OnboardingSection(
                        heading="Captured focus",
                        body=request.reply_text,
                    ),
                ],
                questions=[],
                suggested_actions=[
                    OnboardingSuggestedAction(
                        id="review-plan",
                        label="Review plan",
                        action_type="review",
                    ),
                ],
                artifacts=[],
                state_patch=OnboardingStatePatch(
                    thread_status="review_needed",
                    onboarding_status="plan_ready",
                    pending_question_count=0,
                    objective=request.objective,
                    explored_questions=[
                        *list(request.explored_questions),
                        *list(request.pending_questions),
                    ],
                    pending_questions=[],
                    current_hypotheses=["MED13 may influence cardiomyopathy pathways."],
                ),
                agent_run_id="sdk-onboarding-agent-continuation",
                warnings=[],
                confidence_score=0.94,
                rationale="The reply closes the remaining open onboarding question.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="latest_reply",
                        excerpt=request.reply_text,
                        relevance=0.94,
                    ),
                ],
            )
            return HarnessResearchOnboardingResult(
                contract=contract,
                agent_run_id="sdk-onboarding-agent-continuation",
                active_skill_names=("onboarding_skill",),
            )

    class _StubPubMedDiscoveryService:
        async def run_pubmed_search(
            self,
            owner_id: UUID,
            request: object,
        ) -> object:
            return _build_pubmed_job(
                owner_id=str(owner_id),
                session_id=(
                    None if request.session_id is None else str(request.session_id)
                ),
                query_preview=request.parameters.search_term
                or request.parameters.gene_symbol
                or "MED13",
                gene_symbol=request.parameters.gene_symbol,
                additional_terms=request.parameters.additional_terms,
                max_results=request.parameters.max_results,
            )

        def get_search_job(
            self,
            owner_id: UUID,
            job_id: UUID,
        ) -> object | None:
            job = state.pubmed_jobs.get(str(job_id))
            if job is None or str(job.owner_id) != str(owner_id):
                return None
            return job

        def close(self) -> None:
            return None

    pubmed_discovery_service = _StubPubMedDiscoveryService()

    @contextmanager
    def _stub_pubmed_context() -> Iterator[object]:
        yield pubmed_discovery_service

    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    approval_store = HarnessApprovalStore()
    chat_session_store = HarnessChatSessionStore()
    document_binary_store = HarnessDocumentBinaryStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    research_space_store = HarnessResearchSpaceStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    graph_connection_runner = _StubGraphConnectionRunner()
    graph_chat_runner = _StubGraphChatRunner()
    graph_search_runner = _StubGraphSearchRunner()
    research_onboarding_runner = _StubResearchOnboardingRunner()

    async def _execution_override(run: object, services: object) -> object:
        if run.harness_id == "graph-search":
            payload = run.input_payload
            curation_statuses = payload.get("curation_statuses")
            return await execute_graph_search_run(
                space_id=UUID(run.space_id),
                run=run,
                question=str(payload.get("question", "")),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                top_k=int(payload.get("top_k", 10)),
                curation_statuses=(
                    [
                        status
                        for status in curation_statuses
                        if isinstance(status, str) and status.strip() != ""
                    ]
                    if isinstance(curation_statuses, list)
                    else None
                ),
                include_evidence_chains=bool(
                    payload.get("include_evidence_chains", True),
                ),
                artifact_store=services.artifact_store,
                run_registry=services.run_registry,
                runtime=services.runtime,
                graph_search_runner=services.graph_search_runner,
            )
        if run.harness_id == "graph-connections":
            payload = run.input_payload
            relation_types = payload.get("relation_types")
            return await execute_graph_connection_run(
                space_id=UUID(run.space_id),
                run=run,
                seed_entity_ids=[
                    item
                    for item in payload.get("seed_entity_ids", [])
                    if isinstance(item, str)
                ],
                source_type=(
                    payload.get("source_type")
                    if isinstance(payload.get("source_type"), str)
                    else None
                ),
                source_id=(
                    payload.get("source_id")
                    if isinstance(payload.get("source_id"), str)
                    else None
                ),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                relation_types=(
                    [
                        relation_type
                        for relation_type in relation_types
                        if isinstance(relation_type, str)
                        and relation_type.strip() != ""
                    ]
                    if isinstance(relation_types, list)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                shadow_mode=bool(payload.get("shadow_mode", True)),
                pipeline_run_id=(
                    payload.get("pipeline_run_id")
                    if isinstance(payload.get("pipeline_run_id"), str)
                    else None
                ),
                artifact_store=services.artifact_store,
                run_registry=services.run_registry,
                runtime=services.runtime,
                graph_connection_runner=services.graph_connection_runner,
            )
        if run.harness_id == "hypotheses":
            payload = run.input_payload
            relation_types = payload.get("relation_types")
            return await execute_hypothesis_run(
                space_id=UUID(run.space_id),
                run=run,
                seed_entity_ids=[
                    item
                    for item in payload.get("seed_entity_ids", [])
                    if isinstance(item, str)
                ],
                source_type=str(payload.get("source_type", "pubmed")),
                relation_types=(
                    [
                        relation_type
                        for relation_type in relation_types
                        if isinstance(relation_type, str)
                        and relation_type.strip() != ""
                    ]
                    if isinstance(relation_types, list)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                max_hypotheses=int(payload.get("max_hypotheses", 20)),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                artifact_store=services.artifact_store,
                run_registry=services.run_registry,
                proposal_store=services.proposal_store,
                runtime=services.runtime,
                graph_connection_runner=services.graph_connection_runner,
            )
        if run.harness_id == "research-onboarding":
            payload = run.input_payload
            if isinstance(payload.get("reply_text"), str):
                return await asyncio.to_thread(
                    execute_research_onboarding_continuation,
                    space_id=UUID(run.space_id),
                    research_title="",
                    request=ResearchOnboardingContinuationRequest(
                        thread_id=str(payload.get("thread_id", "")),
                        message_id=str(payload.get("message_id", "")),
                        intent=str(payload.get("intent", "")),
                        mode=str(payload.get("mode", "")),
                        reply_text=str(payload.get("reply_text", "")),
                        reply_html=str(payload.get("reply_html", "")),
                        attachments=(
                            list(payload.get("attachments"))
                            if isinstance(payload.get("attachments"), list)
                            else []
                        ),
                        contextual_anchor=(
                            payload.get("contextual_anchor")
                            if isinstance(payload.get("contextual_anchor"), dict)
                            else None
                        ),
                    ),
                    run_registry=services.run_registry,
                    artifact_store=services.artifact_store,
                    graph_api_gateway=services.graph_api_gateway_factory(),
                    research_state_store=services.research_state_store,
                    onboarding_runner=services.research_onboarding_runner,
                    existing_run=run,
                )
            return await asyncio.to_thread(
                execute_research_onboarding_run,
                space_id=UUID(run.space_id),
                research_title=str(payload.get("research_title", "")),
                primary_objective=str(payload.get("primary_objective", "")),
                space_description=str(payload.get("space_description", "")),
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                graph_api_gateway=services.graph_api_gateway_factory(),
                research_state_store=services.research_state_store,
                onboarding_runner=services.research_onboarding_runner,
                existing_run=run,
            )
        if run.harness_id != "graph-chat":
            msg = f"Unsupported harness in SDK integration override: {run.harness_id}"
            raise RuntimeError(msg)
        payload = run.input_payload
        session_id = UUID(str(payload.get("session_id")))
        session = services.chat_session_store.get_session(
            space_id=UUID(run.space_id),
            session_id=session_id,
        )
        if session is None:
            msg = f"Chat session '{session_id}' not found for run '{run.id}'."
            raise RuntimeError(msg)
        referenced_documents = tuple(
            document
            for document_id in payload.get("document_ids", [])
            if isinstance(document_id, str)
            for document in (
                services.document_store.get_document(
                    space_id=UUID(run.space_id),
                    document_id=document_id,
                ),
            )
            if document is not None
        )
        with services.pubmed_discovery_service_factory() as pubmed_discovery_service:
            return await execute_graph_chat_message(
                space_id=UUID(run.space_id),
                session=session,
                content=str(payload.get("question", "")),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                top_k=int(payload.get("top_k", 10)),
                include_evidence_chains=bool(
                    payload.get("include_evidence_chains", True),
                ),
                current_user_id=str(payload.get("current_user_id", run.space_id)),
                chat_session_store=services.chat_session_store,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                runtime=services.runtime,
                graph_api_gateway=services.graph_api_gateway_factory(),
                graph_chat_runner=services.graph_chat_runner,
                graph_snapshot_store=services.graph_snapshot_store,
                _pubmed_discovery_service=pubmed_discovery_service,
                research_state_store=services.research_state_store,
                proposal_store=services.proposal_store,
                referenced_documents=referenced_documents,
                refresh_pubmed_if_needed=bool(
                    payload.get("refresh_pubmed_if_needed", True),
                ),
                existing_run=run,
            )

    execution_services = HarnessExecutionServices(
        runtime=runtime,
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        document_store=document_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=graph_connection_runner,
        graph_chat_runner=graph_chat_runner,
        graph_search_runner=graph_search_runner,
        research_onboarding_runner=research_onboarding_runner,
        graph_api_gateway_factory=_StubGraphApiGateway,
        pubmed_discovery_service_factory=_stub_pubmed_context,
        execution_override=_execution_override,
    )

    _reset_harness_schema(engine, Base.metadata)
    app = create_app()
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_chat_session_store] = lambda: chat_session_store
    app.dependency_overrides[get_document_binary_store] = lambda: document_binary_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_graph_chat_runner] = lambda: graph_chat_runner
    app.dependency_overrides[get_graph_connection_runner] = (
        lambda: graph_connection_runner
    )
    app.dependency_overrides[get_graph_search_runner] = lambda: graph_search_runner
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: execution_services
    )
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_pubmed_discovery_service] = (
        lambda: pubmed_discovery_service
    )
    app.dependency_overrides[get_research_onboarding_runner] = (
        lambda: research_onboarding_runner
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    with TestClient(app) as test_client:
        try:
            yield _LiveHarnessService(
                http_client=cast(httpx.Client, test_client),
                base_url="http://testserver",
                access_token=_build_access_token(
                    jwt_module=cast(ModuleType, jwt_module),
                    auth_module=auth_module,
                ),
                bootstrap_key=_TEST_BOOTSTRAP_KEY,
                issue_access_token=lambda user_id, email, role="researcher": _build_access_token(
                    jwt_module=cast(ModuleType, jwt_module),
                    auth_module=auth_module,
                    user_id=user_id,
                    email=email,
                    username=email.split("@", maxsplit=1)[0],
                    full_name=email,
                    role=role,
                ),
            )
        finally:
            _drop_harness_schema(engine, Base.metadata)


@pytest.fixture
def live_service() -> Iterator[_LiveHarnessService]:
    with _live_service_context() as service:
        yield service


def _bootstrap_sdk_client(
    live_service: _LiveHarnessService,
    *,
    email: str = _TEST_USER_EMAIL,
    username: str = "sdk-integration",
    full_name: str = "SDK Integration",
    api_key_name: str = "SDK Integration Key",
) -> ArtanaClient:
    if email != _TEST_USER_EMAIL:
        client = ArtanaClient(
            base_url=live_service.base_url,
            access_token=live_service.issue_access_token(
                str(uuid5(NAMESPACE_URL, email)),
                email,
                "researcher",
            ),
            client=live_service.http_client,
        )
        client.spaces.ensure_default()
        return client

    bootstrap_client = ArtanaClient(
        base_url=live_service.base_url,
        client=live_service.http_client,
    )
    bootstrap = bootstrap_client.auth.bootstrap_api_key(
        bootstrap_key=live_service.bootstrap_key,
        email=email,
        username=username,
        full_name=full_name,
        api_key_name=api_key_name,
    )
    return ArtanaClient(
        base_url=live_service.base_url,
        api_key=bootstrap.api_key.api_key,
        client=live_service.http_client,
    )


@pytest.mark.integration
def test_sdk_integrates_with_service_for_spaces_graph_runs_and_artifacts(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(live_service)
    auth_context = client.auth.me()
    assert auth_context.user.email == _TEST_USER_EMAIL

    personal_space = client.spaces.ensure_default()
    assert personal_space.is_default is True

    listed_spaces = client.spaces.list()
    assert listed_spaces.total == 1
    assert listed_spaces.spaces[0].id == personal_space.id

    health = client.health()
    assert health.status == "ok"
    assert health.version == "0.1.0"

    graph_search = client.graph.search(question="What is known about MED13?")
    assert graph_search.run.space_id == personal_space.id
    assert graph_search.run.status == "completed"
    assert graph_search.result.results[0].display_label == "MED13"

    runs_after_search = client.runs.list()
    assert runs_after_search.total == 1
    fetched_run = client.runs.get(run_id=graph_search.run.id)
    assert fetched_run.id == graph_search.run.id
    assert fetched_run.harness_id == "graph-search"

    search_artifacts = client.artifacts.list(run_id=graph_search.run.id)
    search_artifact_keys = {artifact.key for artifact in search_artifacts.artifacts}
    assert "graph_search_result" in search_artifact_keys
    assert "run_manifest" in search_artifact_keys

    search_result_artifact = client.artifacts.get(
        run_id=graph_search.run.id,
        artifact_key="graph_search_result",
    )
    assert (
        search_result_artifact.content["result"]["results"][0]["display_label"]
        == "MED13"
    )

    search_workspace = client.artifacts.workspace(run_id=graph_search.run.id)
    assert search_workspace.snapshot["last_graph_search_result_key"] == (
        "graph_search_result"
    )

    project_space = client.spaces.create(
        name="SDK Integration Space",
        description="End-to-end SDK integration test project space.",
    )
    assert project_space.slug == "sdk-integration-space"

    graph_connection = client.graph.connect(
        seed_entity_ids=[ENTITY_ID],
        space_id=project_space.id,
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=3,
    )
    assert graph_connection.run.space_id == project_space.id
    assert graph_connection.outcomes[0].seed_entity_id == ENTITY_ID
    assert (
        graph_connection.outcomes[0].proposed_relations[0].relation_type
        == "ASSOCIATED_WITH"
    )

    project_runs = client.runs.list(space_id=project_space.id)
    assert project_runs.total == 1

    connection_artifacts = client.artifacts.list(
        run_id=graph_connection.run.id,
        space_id=project_space.id,
    )
    connection_artifact_keys = {
        artifact.key for artifact in connection_artifacts.artifacts
    }
    assert "graph_connection_result" in connection_artifact_keys

    client.spaces.delete(space_id=project_space.id, confirm=True)
    remaining_spaces = client.spaces.list()
    assert remaining_spaces.total == 1
    assert remaining_spaces.spaces[0].id == personal_space.id


@pytest.mark.integration
def test_sdk_integrates_with_service_for_onboarding_round_trip(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Onboarding Key",
    )

    started = client.onboarding.start(
        research_title="MED13",
        primary_objective="Understand cardiomyopathy mechanisms",
    )
    assert started.run.harness_id == "research-onboarding"
    assert started.assistant_message.message_type == "clarification_request"
    assert started.research_state.pending_questions == [
        "Which phenotype focus matters most?",
    ]

    continued = client.onboarding.reply(
        thread_id="thread-1",
        message_id="message-1",
        intent="answer",
        mode="reply",
        reply_text="Focus on cardiomyopathy outcomes first.",
    )
    assert continued.run.harness_id == "research-onboarding"
    assert continued.assistant_message.message_type == "plan_ready"
    assert continued.research_state.pending_questions == []
    assert continued.research_state.current_hypotheses == [
        "MED13 may influence cardiomyopathy pathways.",
    ]

    runs = client.runs.list()
    assert runs.total == 2

    onboarding_artifacts = client.artifacts.list(run_id=continued.run.id)
    onboarding_artifact_keys = {
        artifact.key for artifact in onboarding_artifacts.artifacts
    }
    assert "onboarding_assistant_message" in onboarding_artifact_keys
    assert "onboarding_agent_contract" in onboarding_artifact_keys

    workspace = client.artifacts.workspace(run_id=continued.run.id)
    assert workspace.snapshot["last_onboarding_message_key"] == (
        "onboarding_assistant_message"
    )


@pytest.mark.integration
def test_sdk_document_extraction_stages_reviewable_queue_items(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Documents Key",
    )

    ingestion = client.documents.submit_text(
        title="MED13 cardiomyopathy note",
        text="MED13 associates with cardiomyopathy.",
    )
    assert ingestion.run.harness_id == "document-ingestion"
    assert ingestion.document.source_type == "text"
    assert ingestion.document.extraction_status == "not_started"

    listed_documents = client.documents.list()
    assert listed_documents.total == 1
    assert listed_documents.documents[0].id == ingestion.document.id

    extracted = client.documents.extract(document_id=ingestion.document.id)
    assert extracted.run.harness_id == "document-extraction"
    assert extracted.proposal_count == 1
    assert extracted.document.last_extraction_run_id == extracted.run.id
    assert extracted.proposals[0].status == "pending_review"
    assert extracted.proposals[0].document_id == ingestion.document.id

    proposal_listing = client.proposals.list(document_id=ingestion.document.id)
    assert proposal_listing.total == 1
    assert proposal_listing.proposals[0].id == extracted.proposals[0].id

    queue_listing = client.review_queue.list(document_id=ingestion.document.id)
    assert queue_listing.total == 1
    assert queue_listing.items[0].item_type == "proposal"
    assert queue_listing.items[0].resource_id == extracted.proposals[0].id

    queue_item = client.review_queue.get(item_id=queue_listing.items[0].id)
    assert queue_item.available_actions == ["promote", "reject"]

    rejected = client.review_queue.act(
        item_id=queue_item.id,
        action="reject",
        reason="Keep this staged but not promoted for now.",
    )
    assert rejected.status == "rejected"
    assert rejected.decision_reason == "Keep this staged but not promoted for now."

    graph_search = client.graph.search(
        question="What is known about MED13 and cardiomyopathy?",
    )
    assert graph_search.result.results[0].matching_relation_ids == []


@pytest.mark.integration
def test_sdk_pdf_document_extraction_runs_enrichment_before_staging_proposals(
    monkeypatch,
    live_service: _LiveHarnessService,
) -> None:
    documents_router_module = _import_service_module(
        "artana_evidence_api.routers.documents",
    )
    document_extraction_module = _import_service_module(
        "artana_evidence_api.document_extraction",
    )
    monkeypatch.setattr(
        documents_router_module,
        "extract_pdf_text",
        lambda payload: document_extraction_module.DocumentTextExtraction(
            text_content="MED13 associates with cardiomyopathy.",
            page_count=2,
        ),
    )

    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="PDF Documents Key",
    )

    ingestion = client.documents.upload_pdf(
        file_path=b"%PDF-1.4\nsynthetic\n%%EOF\n",
        filename="med13.pdf",
        title="MED13 PDF note",
    )
    assert ingestion.run.harness_id == "document-ingestion"
    assert ingestion.document.source_type == "pdf"
    assert ingestion.document.page_count is None
    assert ingestion.document.text_content == ""
    assert ingestion.document.text_excerpt == ""
    assert ingestion.document.enrichment_status == "not_started"
    assert ingestion.document.last_enrichment_run_id is None

    extracted = client.documents.extract(document_id=ingestion.document.id)
    assert extracted.run.harness_id == "document-extraction"
    assert extracted.document.last_enrichment_run_id is not None
    assert extracted.document.page_count == 2
    assert extracted.document.enrichment_status == "completed"
    assert extracted.document.extraction_status == "completed"
    assert extracted.proposal_count == 1
    assert extracted.proposals[0].status == "pending_review"

    fetched_document = client.documents.get(document_id=ingestion.document.id)
    assert (
        fetched_document.last_enrichment_run_id
        == extracted.document.last_enrichment_run_id
    )
    assert fetched_document.last_extraction_run_id == extracted.run.id
    assert fetched_document.text_content == "MED13 associates with cardiomyopathy."


@pytest.mark.integration
def test_sdk_promoted_document_proposal_becomes_graph_visible(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Promotion Key",
    )

    ingestion = client.documents.submit_text(
        title="Promotion candidate",
        text="MED13 associates with cardiomyopathy.",
    )
    extracted = client.documents.extract(document_id=ingestion.document.id)
    queue_listing = client.review_queue.list(document_id=ingestion.document.id)
    assert queue_listing.total == 1

    promoted = client.review_queue.act(
        item_id=queue_listing.items[0].id,
        action="promote",
        metadata={"reviewer": "sdk-test"},
    )
    assert promoted.status == "promoted"
    assert promoted.metadata["reviewer"] == "sdk-test"

    graph_search = client.graph.search(
        question="What is known about MED13 and cardiomyopathy?",
    )
    assert graph_search.result.results[0].matching_relation_ids != []
    assert "promoted relation claim" in graph_search.result.results[0].explanation


@pytest.mark.integration
def test_sdk_chat_document_workflow_supports_refresh_and_review(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Chat Workflow Key",
    )

    workflow = client.chat.ask_with_text(
        question="Refresh the latest PubMed evidence for MED13 and cardiomyopathy.",
        title="MED13 evidence note",
        text="MED13 associates with cardiomyopathy.",
    )
    assert workflow.ingestion.run.harness_id == "document-ingestion"
    assert workflow.extraction.run.harness_id == "document-extraction"
    assert workflow.chat.run.harness_id == "graph-chat"
    assert workflow.chat.result.verification.status == "needs_review"
    assert workflow.chat.result.fresh_literature is not None
    assert workflow.chat.result.fresh_literature.total_results == 3
    assert "Referenced document context:" in workflow.chat.assistant_message.content
    assert workflow.chat.user_message.metadata["document_ids"] == [
        workflow.ingestion.document.id,
    ]

    session_detail = client.chat.get_session(session_id=workflow.chat.session.id)
    assert session_detail.session.id == workflow.chat.session.id
    assert [message.role for message in session_detail.messages] == [
        "user",
        "assistant",
    ]


@pytest.mark.integration
def test_sdk_chat_can_stage_graph_write_proposals_from_verified_chat(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Chat Review Key",
    )

    session = client.chat.create_session(title="Verified chat")
    chat_run = client.chat.send_message(
        session_id=session.id,
        content="What grounded graph evidence is there for MED13?",
        refresh_pubmed_if_needed=False,
    )
    assert chat_run.result.verification.status == "verified"
    assert chat_run.result.graph_write_candidates

    staged = client.chat.stage_graph_write_proposals(session_id=session.id)
    assert staged.proposal_count == 1
    assert staged.proposals[0].status == "pending_review"
    assert staged.proposals[0].source_kind == "chat_graph_write"

    generic_listing = client.proposals.list(run_id=chat_run.run.id)
    assert generic_listing.total == 1
    assert generic_listing.proposals[0].id == staged.proposals[0].id


@pytest.mark.integration
def test_sdk_chat_can_request_async_response_and_stream_url(
    live_service: _LiveHarnessService,
) -> None:
    client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Chat Async Key",
    )

    session = client.chat.create_session(title="Async chat")
    chat_run = client.chat.send_message(
        session_id=session.id,
        content="Summarize the grounded evidence in this space.",
        refresh_pubmed_if_needed=False,
        prefer_respond_async=True,
    )
    assert chat_run.run.status == "queued"
    assert chat_run.session.id == session.id
    assert chat_run.session.last_run_id == chat_run.run.id
    assert chat_run.session.status == "queued"
    assert chat_run.stream_url.endswith(
        f"/chat-sessions/{session.id}/messages/{chat_run.run.id}/stream",
    )


@pytest.mark.integration
def test_sdk_pubmed_search_round_trip_and_space_isolation(
    live_service: _LiveHarnessService,
) -> None:
    owner_client = _bootstrap_sdk_client(
        live_service,
        api_key_name="PubMed Owner Key",
    )
    owner_space = owner_client.spaces.ensure_default()

    job = owner_client.pubmed.search(
        gene_symbol="MED13",
        search_term="MED13 cardiomyopathy",
        max_results=25,
    )
    assert job.status == "completed"
    assert job.session_id == owner_space.id
    assert job.query_preview == "MED13 cardiomyopathy"

    fetched_job = owner_client.pubmed.get_job(job_id=job.id)
    assert fetched_job.id == job.id
    assert fetched_job.result_metadata["preview_records"][0]["pmid"] == "pmid-1"

    other_client = _bootstrap_sdk_client(
        live_service,
        email="sdk-pubmed-other@example.com",
        username="sdk-pubmed-other",
        full_name="SDK PubMed Other",
        api_key_name="PubMed Other Key",
    )

    with pytest.raises(ArtanaRequestError) as exc_info:
        other_client.pubmed.get_job(job_id=job.id, space_id=owner_space.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Space not found"


@pytest.mark.integration
def test_sdk_space_access_isolated_between_users(
    live_service: _LiveHarnessService,
) -> None:
    owner_client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Owner Key",
    )
    owner_space = owner_client.spaces.ensure_default()

    other_client = _bootstrap_sdk_client(
        live_service,
        email="sdk-other@example.com",
        username="sdk-other",
        full_name="SDK Other",
        api_key_name="Other Key",
    )

    other_spaces = other_client.spaces.list()
    assert other_spaces.total == 1
    assert other_spaces.spaces[0].is_default is True
    assert other_spaces.spaces[0].id != owner_space.id

    with pytest.raises(ArtanaRequestError) as exc_info:
        other_client.runs.list(space_id=owner_space.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Space not found"


@pytest.mark.integration
def test_sdk_documents_proposals_and_chat_sessions_are_space_isolated(
    live_service: _LiveHarnessService,
) -> None:
    owner_client = _bootstrap_sdk_client(
        live_service,
        api_key_name="Isolation Owner Key",
    )
    owner_space = owner_client.spaces.ensure_default()

    session = owner_client.chat.create_session(title="Owner chat")
    ingestion = owner_client.documents.submit_text(
        title="Owner document",
        text="MED13 associates with cardiomyopathy.",
    )
    extracted = owner_client.documents.extract(document_id=ingestion.document.id)

    other_client = _bootstrap_sdk_client(
        live_service,
        email="sdk-isolation-other@example.com",
        username="sdk-isolation-other",
        full_name="SDK Isolation Other",
        api_key_name="Isolation Other Key",
    )

    with pytest.raises(ArtanaRequestError) as document_exc:
        other_client.documents.get(
            document_id=ingestion.document.id,
            space_id=owner_space.id,
        )
    assert document_exc.value.status_code == 404
    assert document_exc.value.detail == "Space not found"

    with pytest.raises(ArtanaRequestError) as proposal_exc:
        other_client.proposals.get(
            proposal_id=extracted.proposals[0].id,
            space_id=owner_space.id,
        )
    assert proposal_exc.value.status_code == 404
    assert proposal_exc.value.detail == "Space not found"

    with pytest.raises(ArtanaRequestError) as chat_exc:
        other_client.chat.get_session(
            session_id=session.id,
            space_id=owner_space.id,
        )
    assert chat_exc.value.status_code == 404
    assert chat_exc.value.detail == "Space not found"


@pytest.mark.integration
def test_sdk_surfaces_service_auth_failures_from_real_routes(
    live_service: _LiveHarnessService,
) -> None:
    anonymous_client = ArtanaClient(
        base_url=live_service.base_url,
        client=live_service.http_client,
    )

    with pytest.raises(ArtanaRequestError) as exc_info:
        anonymous_client.spaces.list()

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"
