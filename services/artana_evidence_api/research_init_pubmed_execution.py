"""PubMed query execution helpers for research-init runs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping, Sequence
from typing import Protocol
from uuid import UUID

from artana_evidence_api.request_context import build_request_id_headers
from artana_evidence_api.research_init_helpers import (
    _HTTP_OK,
    _candidate_key,
    _merge_candidate,
    _PubMedCandidate,
    _PubMedCandidateReview,
)
from artana_evidence_api.research_init_models import (
    ResearchInitPubMedResultRecord,
    _PubMedQueryExecutionResult,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_array_or_empty,
    json_object,
)

__all__ = [
    "execute_pubmed_query",
    "pubmed_document_source_capture",
    "run_pubmed_query_executions",
]


class PubMedQueryBuilder(Protocol):
    def __call__(
        self,
        objective: str,
        seed_terms: list[str],
    ) -> Sequence[Mapping[str, str | None]]: ...


class PubMedQueryRunner(Protocol):
    def __call__(
        self,
        *,
        query_params: Mapping[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> Awaitable[_PubMedQueryExecutionResult]: ...


def pubmed_document_source_capture(
    *,
    candidate: _PubMedCandidate,
    review: _PubMedCandidateReview,
    sha256: str,
    ingestion_run_id: str,
) -> JSONObject:
    locator = (
        f"pubmed:{candidate.pmid}"
        if candidate.pmid
        else f"pubmed:document:{sha256[:16]}"
    )
    citation = _pubmed_candidate_citation(candidate)
    return source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
        capture_method="research_plan",
        locator=locator,
        external_id=candidate.pmid,
        citation=citation,
        run_id=ingestion_run_id,
        query=", ".join(candidate.queries),
        query_payload={
            "queries": list(candidate.queries),
            "pmid": candidate.pmid,
            "doi": candidate.doi,
            "pmc_id": candidate.pmc_id,
        },
        result_count=1,
        provenance=compact_provenance(
            source="research-init-pubmed",
            review_method=review.method,
            review_label=review.label,
            review_confidence=review.confidence,
            sha256=sha256,
        ),
    )


def _pubmed_candidate_citation(candidate: _PubMedCandidate) -> str | None:
    citation_parts: list[str] = [candidate.title.strip()]
    if candidate.journal:
        citation_parts.append(candidate.journal.strip())
    citation = ". ".join(part for part in citation_parts if part)
    return citation or None


async def execute_pubmed_query(  # noqa: PLR0912, PLR0915
    *,
    query_params: Mapping[str, str | None],
    owner_id: UUID,
    max_results_per_query: int,
    max_previews_per_query: int,
) -> _PubMedQueryExecutionResult:
    """Execute one PubMed query family and return discovered candidates."""
    from artana_evidence_api.pubmed_discovery import (
        AdvancedQueryParameters,
        LocalPubMedDiscoveryService,
        RunPubmedSearchRequest,
    )

    local_errors: list[str] = []
    local_candidates: dict[str, _PubMedCandidate] = {}
    pubmed_service = LocalPubMedDiscoveryService()

    try:
        params = AdvancedQueryParameters(
            search_term=query_params.get("search_term"),
            gene_symbol=query_params.get("gene_symbol"),
            max_results=max_results_per_query,
        )
        search_request = RunPubmedSearchRequest(parameters=params)
        job = await pubmed_service.run_pubmed_search(
            owner_id=owner_id,
            request=search_request,
        )
        total = job.total_results
        previews: list[JSONObject] = []
        for preview_value in json_array_or_empty(
            job.result_metadata.get("preview_records"),
        ):
            preview = json_object(preview_value)
            if preview is not None:
                previews.append(preview)

        pmids = [
            pmid
            for preview in previews[:max_previews_per_query]
            if isinstance((pmid := preview.get("pmid")), str) and pmid.strip() != ""
        ]
        abstracts_by_pmid: dict[str, str] = {}
        if pmids:
            try:
                import httpx
                from defusedxml import ElementTree

                async with httpx.AsyncClient(timeout=15.0) as efetch_client:
                    efetch_response = await efetch_client.get(
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                        params={
                            "db": "pubmed",
                            "id": ",".join(pmids),
                            "rettype": "abstract",
                            "retmode": "xml",
                            "tool": "artana-resource-library",
                        },
                        headers=build_request_id_headers(),
                    )
                    if efetch_response.status_code == _HTTP_OK:
                        root = ElementTree.fromstring(
                            efetch_response.content,
                        )
                        for article in root.findall(".//PubmedArticle"):
                            pmid_el = article.find(".//PMID")
                            if pmid_el is None:
                                continue
                            pmid_val = pmid_el.text or ""
                            doc_parts: list[str] = []
                            title_el = article.find(".//ArticleTitle")
                            if title_el is not None:
                                title_text = "".join(title_el.itertext()).strip()
                                if title_text:
                                    doc_parts.append(title_text)
                            abstract_el = article.find(".//Abstract")
                            if abstract_el is not None:
                                for text_el in abstract_el.findall("AbstractText"):
                                    label = text_el.get("Label", "")
                                    content = "".join(text_el.itertext()).strip()
                                    if content:
                                        doc_parts.append(
                                            f"{label}: {content}" if label else content,
                                        )
                            mesh_terms = [
                                mesh.text
                                for mesh in article.findall(
                                    ".//MeshHeading/DescriptorName",
                                )
                                if mesh.text
                            ]
                            if mesh_terms:
                                doc_parts.append(
                                    f"MeSH terms: {', '.join(mesh_terms)}",
                                )
                            keywords = [
                                keyword.text
                                for keyword in article.findall(".//Keyword")
                                if keyword.text
                            ]
                            if keywords:
                                doc_parts.append(
                                    f"Keywords: {', '.join(keywords)}",
                                )
                            if doc_parts:
                                abstracts_by_pmid[pmid_val] = "\n\n".join(doc_parts)
            except Exception as efetch_exc:  # noqa: BLE001
                local_errors.append(f"efetch failed: {efetch_exc}")

        for preview in previews[:max_previews_per_query]:
            title_value = preview.get("title")
            title_text = title_value.strip() if isinstance(title_value, str) else ""
            if not title_text:
                continue
            pmid_value = preview.get("pmid")
            pmid = (
                pmid_value
                if isinstance(pmid_value, str) and pmid_value.strip() != ""
                else None
            )
            xml_text = abstracts_by_pmid.get(pmid or "", "")
            if xml_text:
                text = xml_text
                journal_value = preview.get("journal")
                if isinstance(journal_value, str) and journal_value not in text:
                    text += f"\n\nJournal: {journal_value}"
                doi_value = preview.get("doi")
                if isinstance(doi_value, str) and doi_value.strip() != "":
                    text += f"\nDOI: {doi_value}"
            else:
                parts = [title_text]
                journal_value = preview.get("journal")
                if isinstance(journal_value, str) and journal_value.strip() != "":
                    parts.append(f"Published in: {journal_value}")
                doi_value = preview.get("doi")
                if isinstance(doi_value, str) and doi_value.strip() != "":
                    parts.append(f"DOI: {doi_value}")
                text = "\n".join(parts)

            pmc_id = preview.get("pmc_id")
            if isinstance(pmc_id, str) and pmc_id.strip() != "":
                try:
                    from artana_evidence_api.pubmed_full_text import (
                        fetch_pmc_open_access_full_text,
                    )

                    ft_result = await asyncio.to_thread(
                        fetch_pmc_open_access_full_text,
                        pmc_id,
                        timeout_seconds=15,
                    )
                    if ft_result.found and ft_result.content_text:
                        text = f"{title_text}\n\n{ft_result.content_text}"
                except Exception as full_text_exc:  # noqa: BLE001
                    local_errors.append(
                        "PMC full-text fetch failed for "
                        f"'{title_text[:80]}': {full_text_exc}",
                    )

            candidate = _PubMedCandidate(
                title=title_text,
                text=text,
                queries=[
                    search_term
                    for search_term in [query_params.get("search_term")]
                    if search_term
                ],
                pmid=pmid,
                doi=doi_value if isinstance(doi_value, str) else None,
                pmc_id=pmc_id if isinstance(pmc_id, str) else None,
                journal=(journal_value if isinstance(journal_value, str) else None),
            )
            key = _candidate_key(
                pmid=candidate.pmid,
                title=candidate.title,
            )
            existing_candidate = local_candidates.get(key)
            if existing_candidate is None:
                local_candidates[key] = candidate
            else:
                local_candidates[key] = _merge_candidate(
                    existing_candidate,
                    candidate,
                )

        return _PubMedQueryExecutionResult(
            query_result=ResearchInitPubMedResultRecord(
                query=query_params.get("search_term") or "",
                total_found=total,
                abstracts_ingested=len(abstracts_by_pmid),
            ),
            candidates=tuple(local_candidates.values()),
            errors=tuple(local_errors),
        )
    except Exception as exc:  # noqa: BLE001
        return _PubMedQueryExecutionResult(
            query_result=None,
            candidates=(),
            errors=(f"PubMed search failed for '{query_params}': {exc}",),
        )
    finally:
        pubmed_service.close()


async def run_pubmed_query_executions(
    *,
    objective: str,
    seed_terms: list[str],
    query_builder: PubMedQueryBuilder,
    query_runner: PubMedQueryRunner,
    owner_id: UUID,
    concurrency_limit: int,
    max_results_per_query: int,
    max_previews_per_query: int,
) -> tuple[_PubMedQueryExecutionResult, ...]:
    queries = query_builder(objective, seed_terms)
    if not queries:
        return ()

    query_semaphore = asyncio.Semaphore(concurrency_limit)

    async def _run_bounded_pubmed_query(
        query_params: Mapping[str, str | None],
    ) -> _PubMedQueryExecutionResult:
        async with query_semaphore:
            return await query_runner(
                query_params=query_params,
                owner_id=owner_id,
                max_results_per_query=max_results_per_query,
                max_previews_per_query=max_previews_per_query,
            )

    return tuple(
        await asyncio.gather(
            *(_run_bounded_pubmed_query(query_params) for query_params in queries),
        ),
    )
