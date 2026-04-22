"""Public synchronous client for the Artana Evidence API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Literal, Self, TypeVar, overload
from uuid import UUID

import httpx
from pydantic import BaseModel

from ._json import JSONValue
from .config import ArtanaConfig
from .exceptions import (
    ArtanaConfigurationError,
    ArtanaRequestError,
    ArtanaResponseValidationError,
)
from .models import (
    Artifact,
    ArtifactListResponse,
    AuthContextResponse,
    AuthCredentialResponse,
    BootstrapApiKeyRequest,
    ChatDocumentWorkflowResponse,
    ChatGraphWriteCandidate,
    ChatGraphWriteProposalResponse,
    ChatMessageAcceptedResponse,
    ChatMessageRunResponse,
    ChatSession,
    ChatSessionDetailResponse,
    CreateApiKeyRequest,
    CreateSpaceRequest,
    DocumentDetail,
    DocumentExtractionResponse,
    DocumentIngestionResponse,
    DocumentListResponse,
    GraphConnectionRequest,
    GraphConnectionRunResponse,
    GraphSearchRequest,
    GraphSearchRunResponse,
    HealthResponse,
    Proposal,
    ProposalListResponse,
    PubMedSearchJob,
    PubMedSearchParameters,
    PubMedSearchRequest,
    ReviewQueueActionRequest,
    ReviewQueueItem,
    ReviewQueueListResponse,
    ResearchOnboardingReplyRequest,
    ResearchOnboardingRunResponse,
    ResearchOnboardingStartRequest,
    ResearchOnboardingTurnResponse,
    ResearchSpace,
    ResearchSpaceListResponse,
    Run,
    RunListResponse,
    Workspace,
)

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
MultipartFileValue = tuple[str, bytes, str]
MultipartFormValue = MultipartFileValue | str
HTTP_202_ACCEPTED = 202


def _normalize_uuid(value: UUID | str, *, field_name: str) -> str:
    try:
        return str(value if isinstance(value, UUID) else UUID(str(value).strip()))
    except ValueError as exc:
        raise ArtanaConfigurationError(
            f"{field_name} must be a valid UUID.",
        ) from exc


def _normalize_seed_entity_ids(seed_entity_ids: list[UUID | str]) -> list[str]:
    return [
        _normalize_uuid(seed_entity_id, field_name="seed_entity_id")
        for seed_entity_id in seed_entity_ids
    ]


def _normalize_uuid_list(
    values: list[UUID | str],
    *,
    field_name: str,
) -> list[str]:
    return [_normalize_uuid(value, field_name=field_name) for value in values]


def _normalize_non_empty_identifier(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized == "":
        raise ArtanaConfigurationError(f"{field_name} must not be empty.")
    return normalized


def _resolve_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
    response_text = response.text.strip()
    if response_text:
        return response_text
    return f"Request failed with status {response.status_code}."


class _ResourceBase:
    def __init__(self, client: ArtanaClient) -> None:
        self._client = client

    def _resolve_space_id(self, space_id: UUID | str | None) -> str:
        return self._client._resolve_space_id(space_id)


class ArtanaSpacesAPI(_ResourceBase):
    """Research-space resource helper."""

    def list(self) -> ResearchSpaceListResponse:
        return self._client._request_model(
            "GET",
            "/v1/spaces",
            response_model=ResearchSpaceListResponse,
        )

    def create(
        self,
        *,
        name: str,
        description: str = "",
    ) -> ResearchSpace:
        payload = CreateSpaceRequest(name=name, description=description)
        return self._client._request_model(
            "POST",
            "/v1/spaces",
            response_model=ResearchSpace,
            json_body=payload.model_dump(mode="json"),
        )

    def ensure_default(self) -> ResearchSpace:
        """Return the caller's personal default space, creating it if missing."""
        response = self._client._request_model(
            "PUT",
            "/v1/spaces/default",
            response_model=ResearchSpace,
        )
        self._client._resolved_default_space_id = response.id
        return response

    def delete(
        self,
        *,
        space_id: UUID | str | None = None,
        confirm: bool = False,
    ) -> None:
        resolved_space_id = self._resolve_space_id(space_id)
        self._client._request(
            "DELETE",
            f"/v1/spaces/{resolved_space_id}",
            params={"confirm": "true"} if confirm else None,
        )
        if self._client._resolved_default_space_id == resolved_space_id:
            self._client._resolved_default_space_id = None


class ArtanaAuthAPI(_ResourceBase):
    """Authentication and API key management helper."""

    def bootstrap_api_key(
        self,
        *,
        bootstrap_key: str,
        email: str,
        username: str | None = None,
        full_name: str | None = None,
        role: str = "researcher",
        api_key_name: str = "Default SDK Key",
        api_key_description: str = "",
        create_default_space: bool = True,
    ) -> AuthCredentialResponse:
        payload = BootstrapApiKeyRequest(
            email=email,
            username=username,
            full_name=full_name,
            role=role,
            api_key_name=api_key_name,
            api_key_description=api_key_description,
            create_default_space=create_default_space,
        )
        return self._client._request_model(
            "POST",
            "/v1/auth/bootstrap",
            response_model=AuthCredentialResponse,
            json_body=payload.model_dump(mode="json"),
            headers={"X-Artana-Bootstrap-Key": bootstrap_key},
        )

    def me(self) -> AuthContextResponse:
        return self._client._request_model(
            "GET",
            "/v1/auth/me",
            response_model=AuthContextResponse,
        )

    def create_api_key(
        self,
        *,
        name: str = "Default SDK Key",
        description: str = "",
    ) -> AuthCredentialResponse:
        payload = CreateApiKeyRequest(
            name=name,
            description=description,
        )
        return self._client._request_model(
            "POST",
            "/v1/auth/api-keys",
            response_model=AuthCredentialResponse,
            json_body=payload.model_dump(mode="json"),
        )


class ArtanaGraphAPI(_ResourceBase):
    """Graph-oriented workflow resource helper."""

    def search(
        self,
        *,
        question: str,
        space_id: UUID | str | None = None,
        title: str | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
    ) -> GraphSearchRunResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        payload = GraphSearchRequest(
            question=question,
            title=title,
            model_id=model_id,
            max_depth=max_depth,
            top_k=top_k,
            curation_statuses=curation_statuses,
            include_evidence_chains=include_evidence_chains,
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/agents/graph-search/runs",
            response_model=GraphSearchRunResponse,
            json_body=payload.model_dump(mode="json"),
        )

    def connect(
        self,
        *,
        seed_entity_ids: list[UUID | str],
        space_id: UUID | str | None = None,
        title: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool = True,
        pipeline_run_id: str | None = None,
    ) -> GraphConnectionRunResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        payload = GraphConnectionRequest(
            seed_entity_ids=_normalize_seed_entity_ids(seed_entity_ids),
            title=title,
            source_type=source_type,
            source_id=source_id,
            model_id=model_id,
            relation_types=relation_types,
            max_depth=max_depth,
            shadow_mode=shadow_mode,
            pipeline_run_id=pipeline_run_id,
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/agents/graph-connections/runs",
            response_model=GraphConnectionRunResponse,
            json_body=payload.model_dump(mode="json"),
        )


class ArtanaOnboardingAPI(_ResourceBase):
    """Research onboarding workflow helper."""

    def start(
        self,
        *,
        research_title: str,
        space_id: UUID | str | None = None,
        primary_objective: str = "",
        space_description: str = "",
    ) -> ResearchOnboardingRunResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        payload = ResearchOnboardingStartRequest(
            research_title=research_title,
            primary_objective=primary_objective,
            space_description=space_description,
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/agents/research-onboarding/runs",
            response_model=ResearchOnboardingRunResponse,
            json_body=payload.model_dump(mode="json"),
        )

    def reply(
        self,
        *,
        thread_id: str,
        message_id: str,
        intent: str,
        mode: str,
        reply_text: str,
        space_id: UUID | str | None = None,
        reply_html: str = "",
        attachments: list[dict[str, JSONValue]] | None = None,
        contextual_anchor: dict[str, JSONValue] | None = None,
    ) -> ResearchOnboardingTurnResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        payload = ResearchOnboardingReplyRequest(
            thread_id=thread_id,
            message_id=message_id,
            intent=intent,
            mode=mode,
            reply_text=reply_text,
            reply_html=reply_html,
            attachments=[] if attachments is None else attachments,
            contextual_anchor=contextual_anchor,
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/agents/research-onboarding/turns",
            response_model=ResearchOnboardingTurnResponse,
            json_body=payload.model_dump(mode="json"),
        )


class ArtanaRunsAPI(_ResourceBase):
    """Harness-run lifecycle resource helper."""

    def list(self, *, space_id: UUID | str | None = None) -> RunListResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/runs",
            response_model=RunListResponse,
        )

    def get(
        self,
        *,
        run_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> Run:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_run_id = _normalize_uuid(run_id, field_name="run_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/runs/{resolved_run_id}",
            response_model=Run,
        )


class ArtanaArtifactsAPI(_ResourceBase):
    """Run artifact resource helper."""

    def list(
        self,
        *,
        run_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> ArtifactListResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_run_id = _normalize_uuid(run_id, field_name="run_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/runs/{resolved_run_id}/artifacts",
            response_model=ArtifactListResponse,
        )

    def get(
        self,
        *,
        run_id: UUID | str,
        artifact_key: str,
        space_id: UUID | str | None = None,
    ) -> Artifact:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_run_id = _normalize_uuid(run_id, field_name="run_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/runs/{resolved_run_id}/artifacts/"
            f"{artifact_key}",
            response_model=Artifact,
        )

    def workspace(
        self,
        *,
        run_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> Workspace:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_run_id = _normalize_uuid(run_id, field_name="run_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/runs/{resolved_run_id}/workspace",
            response_model=Workspace,
        )


class ArtanaDocumentsAPI(_ResourceBase):
    """Document ingestion and extraction resource helper."""

    def _read_pdf_payload(
        self,
        *,
        file_path: str | Path | bytes,
        filename: str | None,
    ) -> tuple[str, bytes]:
        if isinstance(file_path, bytes):
            if filename is None or filename.strip() == "":
                raise ArtanaConfigurationError(
                    "filename is required when upload_pdf receives raw bytes.",
                )
            return filename, file_path
        resolved_path = Path(file_path).expanduser().resolve()
        if not resolved_path.exists():
            raise ArtanaConfigurationError(
                f"PDF file not found: {resolved_path}",
            )
        if not resolved_path.is_file():
            raise ArtanaConfigurationError(
                f"PDF path must point to a file: {resolved_path}",
            )
        return (filename or resolved_path.name), resolved_path.read_bytes()

    def upload_pdf(
        self,
        *,
        file_path: str | Path | bytes,
        space_id: UUID | str | None = None,
        filename: str | None = None,
        title: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> DocumentIngestionResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_filename, payload = self._read_pdf_payload(
            file_path=file_path,
            filename=filename,
        )
        data: dict[str, str] = {}
        if isinstance(title, str) and title.strip() != "":
            data["title"] = title.strip()
        if metadata is not None:
            data["metadata_json"] = json.dumps(metadata)
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/documents/pdf",
            response_model=DocumentIngestionResponse,
            data=data or None,
            files={"file": (resolved_filename, payload, "application/pdf")},
        )

    def submit_text(
        self,
        *,
        title: str,
        text: str,
        space_id: UUID | str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> DocumentIngestionResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/documents/text",
            response_model=DocumentIngestionResponse,
            json_body={
                "title": title,
                "text": text,
                "metadata": {} if metadata is None else metadata,
            },
        )

    def list(
        self,
        *,
        space_id: UUID | str | None = None,
    ) -> DocumentListResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/documents",
            response_model=DocumentListResponse,
        )

    def get(
        self,
        *,
        document_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> DocumentDetail:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_document_id = _normalize_uuid(document_id, field_name="document_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/documents/{resolved_document_id}",
            response_model=DocumentDetail,
        )

    def extract(
        self,
        *,
        document_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> DocumentExtractionResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_document_id = _normalize_uuid(document_id, field_name="document_id")
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/documents/{resolved_document_id}/extract",
            response_model=DocumentExtractionResponse,
        )


class ArtanaReviewQueueAPI(_ResourceBase):
    """Unified human review resource helper."""

    def list(
        self,
        *,
        space_id: UUID | str | None = None,
        status: str | None = None,
        item_type: str | None = None,
        kind: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
        source_family: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> ReviewQueueListResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        params: dict[str, str] = {}
        if isinstance(status, str) and status.strip() != "":
            params["status"] = status.strip()
        if isinstance(item_type, str) and item_type.strip() != "":
            params["item_type"] = item_type.strip()
        if isinstance(kind, str) and kind.strip() != "":
            params["kind"] = kind.strip()
        if run_id is not None:
            params["run_id"] = _normalize_uuid(run_id, field_name="run_id")
        if document_id is not None:
            params["document_id"] = _normalize_uuid(
                document_id,
                field_name="document_id",
            )
        if isinstance(source_family, str) and source_family.strip() != "":
            params["source_family"] = source_family.strip()
        if offset is not None:
            if offset < 0:
                raise ArtanaConfigurationError("offset must be >= 0.")
            params["offset"] = str(offset)
        if limit is not None:
            if limit < 1:
                raise ArtanaConfigurationError("limit must be >= 1.")
            params["limit"] = str(limit)
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/review-queue",
            response_model=ReviewQueueListResponse,
            params=params or None,
        )

    def get(
        self,
        *,
        item_id: str,
        space_id: UUID | str | None = None,
    ) -> ReviewQueueItem:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_item_id = _normalize_non_empty_identifier(
            item_id,
            field_name="item_id",
        )
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/review-queue/{resolved_item_id}",
            response_model=ReviewQueueItem,
        )

    def act(
        self,
        *,
        item_id: str,
        action: str,
        space_id: UUID | str | None = None,
        reason: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> ReviewQueueItem:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_item_id = _normalize_non_empty_identifier(
            item_id,
            field_name="item_id",
        )
        payload = ReviewQueueActionRequest(
            action=action,
            reason=reason,
            metadata={} if metadata is None else metadata,
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/review-queue/{resolved_item_id}/actions",
            response_model=ReviewQueueItem,
            json_body=payload.model_dump(mode="json"),
        )


class ArtanaProposalsAPI(_ResourceBase):
    """Proposal review resource helper."""

    def list(
        self,
        *,
        space_id: UUID | str | None = None,
        status: str | None = None,
        proposal_type: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
    ) -> ProposalListResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        params: dict[str, str] = {}
        if isinstance(status, str) and status.strip() != "":
            params["status"] = status.strip()
        if isinstance(proposal_type, str) and proposal_type.strip() != "":
            params["proposal_type"] = proposal_type.strip()
        if run_id is not None:
            params["run_id"] = _normalize_uuid(run_id, field_name="run_id")
        if document_id is not None:
            params["document_id"] = _normalize_uuid(
                document_id,
                field_name="document_id",
            )
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/proposals",
            response_model=ProposalListResponse,
            params=params or None,
        )

    def get(
        self,
        *,
        proposal_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> Proposal:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_proposal_id = _normalize_uuid(proposal_id, field_name="proposal_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/proposals/{resolved_proposal_id}",
            response_model=Proposal,
        )

    def promote(
        self,
        *,
        proposal_id: UUID | str,
        space_id: UUID | str | None = None,
        reason: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> Proposal:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_proposal_id = _normalize_uuid(proposal_id, field_name="proposal_id")
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/proposals/{resolved_proposal_id}/promote",
            response_model=Proposal,
            json_body={
                "reason": reason,
                "metadata": {} if metadata is None else metadata,
            },
        )

    def reject(
        self,
        *,
        proposal_id: UUID | str,
        space_id: UUID | str | None = None,
        reason: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> Proposal:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_proposal_id = _normalize_uuid(proposal_id, field_name="proposal_id")
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/proposals/{resolved_proposal_id}/reject",
            response_model=Proposal,
            json_body={
                "reason": reason,
                "metadata": {} if metadata is None else metadata,
            },
        )


class ArtanaChatAPI(_ResourceBase):
    """Chat workflow resource helper."""

    def create_session(
        self,
        *,
        title: str | None = None,
        space_id: UUID | str | None = None,
    ) -> ChatSession:
        resolved_space_id = self._resolve_space_id(space_id)
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/chat-sessions",
            response_model=ChatSession,
            json_body={} if title is None else {"title": title},
        )

    def get_session(
        self,
        *,
        session_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> ChatSessionDetailResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_session_id = _normalize_uuid(session_id, field_name="session_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/chat-sessions/{resolved_session_id}",
            response_model=ChatSessionDetailResponse,
        )

    @overload
    def send_message(  # noqa: PLR0913
        self,
        *,
        session_id: UUID | str,
        content: str,
        space_id: UUID | str | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 10,
        include_evidence_chains: bool = True,
        document_ids: list[UUID | str] | None = None,
        refresh_pubmed_if_needed: bool = True,
        prefer_respond_async: Literal[False] = False,
    ) -> ChatMessageRunResponse: ...

    @overload
    def send_message(  # noqa: PLR0913
        self,
        *,
        session_id: UUID | str,
        content: str,
        space_id: UUID | str | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 10,
        include_evidence_chains: bool = True,
        document_ids: list[UUID | str] | None = None,
        refresh_pubmed_if_needed: bool = True,
        prefer_respond_async: Literal[True],
    ) -> ChatMessageAcceptedResponse: ...

    def send_message(  # noqa: PLR0913
        self,
        *,
        session_id: UUID | str,
        content: str,
        space_id: UUID | str | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 10,
        include_evidence_chains: bool = True,
        document_ids: list[UUID | str] | None = None,
        refresh_pubmed_if_needed: bool = True,
        prefer_respond_async: bool = False,
    ) -> ChatMessageRunResponse | ChatMessageAcceptedResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_session_id = _normalize_uuid(session_id, field_name="session_id")
        response = self._client._request(
            "POST",
            f"/v1/spaces/{resolved_space_id}/chat-sessions/{resolved_session_id}/messages",
            json_body={
                "content": content,
                "model_id": model_id,
                "max_depth": max_depth,
                "top_k": top_k,
                "include_evidence_chains": include_evidence_chains,
                "document_ids": (
                    []
                    if document_ids is None
                    else _normalize_uuid_list(
                        document_ids,
                        field_name="document_id",
                    )
                ),
                "refresh_pubmed_if_needed": refresh_pubmed_if_needed,
            },
            headers=({"Prefer": "respond-async"} if prefer_respond_async else None),
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArtanaResponseValidationError(
                "Artana API response was not valid JSON.",
            ) from exc
        try:
            if response.status_code == HTTP_202_ACCEPTED:
                return ChatMessageAcceptedResponse.model_validate(payload)
            return ChatMessageRunResponse.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ArtanaResponseValidationError(
                f"Artana API response validation failed: {exc}",
            ) from exc

    def stage_graph_write_proposals(
        self,
        *,
        session_id: UUID | str,
        space_id: UUID | str | None = None,
        candidates: list[ChatGraphWriteCandidate] | None = None,
    ) -> ChatGraphWriteProposalResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_session_id = _normalize_uuid(session_id, field_name="session_id")
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/chat-sessions/{resolved_session_id}/proposals/graph-write",
            response_model=ChatGraphWriteProposalResponse,
            json_body=(
                {}
                if candidates is None
                else {
                    "candidates": [
                        candidate.model_dump(mode="json") for candidate in candidates
                    ],
                }
            ),
        )

    def ask_with_pdf(  # noqa: PLR0913
        self,
        *,
        question: str,
        file_path: str | Path | bytes,
        space_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        session_title: str | None = None,
        filename: str | None = None,
        title: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 10,
        include_evidence_chains: bool = True,
        refresh_pubmed_if_needed: bool = True,
    ) -> ChatDocumentWorkflowResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_session_id = (
            self.create_session(
                title=session_title or title or question,
                space_id=resolved_space_id,
            ).id
            if session_id is None
            else _normalize_uuid(session_id, field_name="session_id")
        )
        ingestion = self._client.documents.upload_pdf(
            file_path=file_path,
            space_id=resolved_space_id,
            filename=filename,
            title=title,
            metadata=metadata,
        )
        extraction = self._client.documents.extract(
            document_id=ingestion.document.id,
            space_id=resolved_space_id,
        )
        chat = self.send_message(
            session_id=resolved_session_id,
            content=question,
            space_id=resolved_space_id,
            model_id=model_id,
            max_depth=max_depth,
            top_k=top_k,
            include_evidence_chains=include_evidence_chains,
            document_ids=[ingestion.document.id],
            refresh_pubmed_if_needed=refresh_pubmed_if_needed,
        )
        return ChatDocumentWorkflowResponse(
            ingestion=ingestion,
            extraction=extraction,
            chat=chat,
        )

    def ask_with_text(  # noqa: PLR0913
        self,
        *,
        question: str,
        title: str,
        text: str,
        space_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        session_title: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 10,
        include_evidence_chains: bool = True,
        refresh_pubmed_if_needed: bool = True,
    ) -> ChatDocumentWorkflowResponse:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_session_id = (
            self.create_session(
                title=session_title or title or question,
                space_id=resolved_space_id,
            ).id
            if session_id is None
            else _normalize_uuid(session_id, field_name="session_id")
        )
        ingestion = self._client.documents.submit_text(
            title=title,
            text=text,
            space_id=resolved_space_id,
            metadata=metadata,
        )
        extraction = self._client.documents.extract(
            document_id=ingestion.document.id,
            space_id=resolved_space_id,
        )
        chat = self.send_message(
            session_id=resolved_session_id,
            content=question,
            space_id=resolved_space_id,
            model_id=model_id,
            max_depth=max_depth,
            top_k=top_k,
            include_evidence_chains=include_evidence_chains,
            document_ids=[ingestion.document.id],
            refresh_pubmed_if_needed=refresh_pubmed_if_needed,
        )
        return ChatDocumentWorkflowResponse(
            ingestion=ingestion,
            extraction=extraction,
            chat=chat,
        )


class ArtanaPubMedAPI(_ResourceBase):
    """PubMed literature search helper."""

    def search(
        self,
        *,
        space_id: UUID | str | None = None,
        gene_symbol: str | None = None,
        search_term: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        publication_types: list[str] | None = None,
        languages: list[str] | None = None,
        sort_by: str = "relevance",
        max_results: int = 100,
        additional_terms: str | None = None,
    ) -> PubMedSearchJob:
        resolved_space_id = self._resolve_space_id(space_id)
        payload = PubMedSearchRequest(
            parameters=PubMedSearchParameters(
                gene_symbol=gene_symbol,
                search_term=search_term,
                date_from=date_from,
                date_to=date_to,
                publication_types=publication_types or [],
                languages=languages or [],
                sort_by=sort_by,
                max_results=max_results,
                additional_terms=additional_terms,
            ),
        )
        return self._client._request_model(
            "POST",
            f"/v1/spaces/{resolved_space_id}/pubmed/searches",
            response_model=PubMedSearchJob,
            json_body=payload.model_dump(mode="json"),
        )

    def get_job(
        self,
        *,
        job_id: UUID | str,
        space_id: UUID | str | None = None,
    ) -> PubMedSearchJob:
        resolved_space_id = self._resolve_space_id(space_id)
        resolved_job_id = _normalize_uuid(job_id, field_name="job_id")
        return self._client._request_model(
            "GET",
            f"/v1/spaces/{resolved_space_id}/pubmed/searches/{resolved_job_id}",
            response_model=PubMedSearchJob,
        )


class ArtanaClient:
    """Synchronous public client for the Artana Evidence API."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        openai_api_key: str | None = None,
        timeout_seconds: float = 30.0,
        default_space_id: UUID | str | None = None,
        default_headers: Mapping[str, str] | None = None,
        config: ArtanaConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if config is not None and any(
            value is not None
            for value in (
                base_url,
                api_key,
                access_token,
                openai_api_key,
                default_space_id,
                default_headers,
            )
        ):
            raise ArtanaConfigurationError(
                "Pass either config or individual ArtanaClient parameters, not both.",
            )

        resolved_config = config
        if resolved_config is None:
            if base_url is None:
                resolved_config = ArtanaConfig.from_env()
            else:
                normalized_default_space_id = (
                    None
                    if default_space_id is None
                    else _normalize_uuid(
                        default_space_id,
                        field_name="default_space_id",
                    )
                )
                resolved_config = ArtanaConfig(
                    base_url=base_url,
                    api_key=api_key,
                    access_token=access_token,
                    openai_api_key=openai_api_key,
                    timeout_seconds=timeout_seconds,
                    default_space_id=normalized_default_space_id,
                    default_headers=(
                        {} if default_headers is None else dict(default_headers)
                    ),
                )

        self._config = resolved_config
        self._resolved_default_space_id = self._config.default_space_id
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout_seconds,
        )

        self.spaces = ArtanaSpacesAPI(self)
        self.auth = ArtanaAuthAPI(self)
        self.graph = ArtanaGraphAPI(self)
        self.onboarding = ArtanaOnboardingAPI(self)
        self.runs = ArtanaRunsAPI(self)
        self.artifacts = ArtanaArtifactsAPI(self)
        self.documents = ArtanaDocumentsAPI(self)
        self.review_queue = ArtanaReviewQueueAPI(self)
        self.proposals = ArtanaProposalsAPI(self)
        self.chat = ArtanaChatAPI(self)
        self.pubmed = ArtanaPubMedAPI(self)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> ArtanaClient:
        """Build one client instance from environment variables."""
        return cls(config=ArtanaConfig.from_env(environ=environ))

    @property
    def config(self) -> ArtanaConfig:
        """Return the immutable config backing this client."""
        return self._config

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this SDK client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.close()

    def health(self) -> HealthResponse:
        """Return service health information."""
        return self._request_model(
            "GET",
            "/health",
            response_model=HealthResponse,
        )

    def _resolve_space_id(self, space_id: UUID | str | None) -> str:
        if space_id is not None:
            return _normalize_uuid(space_id, field_name="space_id")
        if self._resolved_default_space_id is not None:
            return self._resolved_default_space_id
        default_space = self.spaces.ensure_default()
        self._resolved_default_space_id = default_space.id
        return default_space.id

    def _request_model(
        self,
        method: str,
        path: str,
        *,
        response_model: type[ResponseModelT],
        json_body: JSONValue | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, MultipartFormValue] | None = None,
    ) -> ResponseModelT:
        response = self._request(
            method,
            path,
            json_body=json_body,
            params=params,
            headers=headers,
            data=data,
            files=files,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArtanaResponseValidationError(
                "Artana API response was not valid JSON.",
            ) from exc
        try:
            return response_model.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ArtanaResponseValidationError(
                f"Artana API response validation failed: {exc}",
            ) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: JSONValue | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, MultipartFormValue] | None = None,
    ) -> httpx.Response:
        merged_headers = self._build_headers(headers=headers, json_body=json_body)
        try:
            response = self._client.request(
                method,
                path,
                params=params,
                json=json_body,
                data=data,
                files=files,
                headers=merged_headers,
            )
        except httpx.HTTPError as exc:
            raise ArtanaRequestError(str(exc)) from exc

        if response.is_error:
            detail = _resolve_error_detail(response)
            raise ArtanaRequestError(
                f"Artana API request failed with status {response.status_code}: {detail}",
                status_code=response.status_code,
                detail=detail,
            )
        return response

    def _build_headers(
        self,
        *,
        headers: Mapping[str, str] | None,
        json_body: JSONValue | None,
    ) -> dict[str, str]:
        merged_headers = dict(self._config.default_headers)
        if headers is not None:
            merged_headers.update(headers)
        if (
            self._config.access_token is not None
            and "Authorization" not in merged_headers
        ):
            merged_headers["Authorization"] = f"Bearer {self._config.access_token}"
        if (
            self._config.api_key is not None
            and self._config.artana_api_key_header not in merged_headers
        ):
            merged_headers[self._config.artana_api_key_header] = self._config.api_key
        if (
            self._config.openai_api_key is not None
            and self._config.openai_api_key_header not in merged_headers
        ):
            merged_headers[self._config.openai_api_key_header] = (
                self._config.openai_api_key
            )
        if json_body is not None and "Content-Type" not in merged_headers:
            merged_headers["Content-Type"] = "application/json"
        return merged_headers


__all__ = ["ArtanaClient"]
