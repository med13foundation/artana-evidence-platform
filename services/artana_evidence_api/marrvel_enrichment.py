"""Shared helpers for MARRVEL-driven proposal enrichment."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Coroutine, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from threading import Thread
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.marrvel_client import (
    MARRVEL_API_BASE_URL,
    MARRVEL_API_FALLBACK_BASE_URL,
)
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryService
from artana_evidence_api.proposal_actions import infer_graph_entity_type_from_label
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.step_helpers import StepClientLike, run_single_step_with_policy
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

MARRVEL_GRAPH_ENTITY_CANDIDATE_LIMIT = 50
MARRVEL_GRAPH_GENE_LIMIT = 10
MARRVEL_LLM_GENE_LIMIT = 5
MARRVEL_MAX_GENE_SYMBOL_LENGTH = 10
_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE = 0.5
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")


def _marrvel_bootstrap_proposal_metadata(
    *,
    gene_symbol: str,
    phenotype_label: str,
) -> JSONObject:
    """Return metadata for MARRVEL proposals awaiting qualitative review."""
    return {
        "source_type": "marrvel",
        "source": "marrvel",
        "gene_symbol": gene_symbol,
        "subject_label": gene_symbol,
        "object_label": phenotype_label,
        "bootstrap_claim_path": "structured_source_bootstrap_draft",
        "claim_generation_mode": "deterministic_structured_draft_unreviewed",
        "requires_qualitative_review": True,
        "direct_graph_promotion_allowed": False,
    }


@dataclass(frozen=True, slots=True)
class MarrvelPhenotypeAssociation:
    """One OMIM phenotype association returned through MARRVEL."""

    gene_symbol: str
    phenotype_label: str


class _AsyncCloseableKernel(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _MarrvelGeneInferenceRuntime:
    """Kernel-backed runtime context for one MARRVEL gene inference step."""

    kernel: _AsyncCloseableKernel
    client: StepClientLike
    model_id: str
    tenant: object


class _MarrvelGeneInferenceResult(BaseModel):
    """Structured gene-symbol response returned by the kernel model step."""

    model_config = ConfigDict(strict=True)

    gene_symbols: list[str] = Field(
        default_factory=list,
        max_length=MARRVEL_LLM_GENE_LIMIT,
    )


def prioritize_marrvel_gene_labels(
    labels: list[str],
    *,
    objective: str,
    limit: int,
) -> list[str]:
    """Rank gene labels by objective relevance while filtering non-gene noise."""
    objective_tokens = {token.upper() for token in _TOKEN_PATTERN.findall(objective)}
    ranked_labels: list[tuple[int, int, str]] = []
    seen_labels: set[str] = set()

    for index, label in enumerate(labels):
        normalized = label.strip().upper()
        if normalized == "" or normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        if infer_graph_entity_type_from_label(normalized) != "GENE":
            continue
        exact_objective_match = 1 if normalized in objective_tokens else 0
        ranked_labels.append((exact_objective_match, -index, normalized))

    ranked_labels.sort(reverse=True)
    return [label for _score, _index, label in ranked_labels[:limit]]


def parse_marrvel_gene_symbols(
    raw_response: str,
    *,
    objective: str,
    limit: int = MARRVEL_LLM_GENE_LIMIT,
) -> list[str]:
    """Parse one LLM gene-symbol response into prioritized HGNC labels."""
    raw = raw_response.strip()
    if raw == "" or raw.upper() == "NONE":
        return []

    candidate_labels = [
        gene.strip().upper()
        for gene in raw.split(",")
        if gene.strip() and len(gene.strip()) <= MARRVEL_MAX_GENE_SYMBOL_LENGTH
    ]
    return prioritize_marrvel_gene_labels(
        candidate_labels,
        objective=objective,
        limit=limit,
    )


def _build_marrvel_gene_inference_prompt(*, objective: str) -> str:
    """Build one structured prompt for kernel-backed MARRVEL gene inference."""
    return (
        "You are a biomedical research assistant. "
        "Given the following research objective, list the most relevant human "
        "gene symbols (HGNC symbols) that should be searched in MARRVEL.\n\n"
        f"Research objective: {objective}\n\n"
        'Return ONLY JSON in the form {"gene_symbols": ["BRCA1", "TP53"]}. '
        f"Return at most {MARRVEL_LLM_GENE_LIMIT} symbols. "
        'If no specific genes are relevant, return {"gene_symbols": []}.'
    )


def _coerce_marrvel_gene_labels(
    output: object,
    *,
    objective: str,
    limit: int,
) -> list[str]:
    """Normalize one kernel step output into prioritized gene labels."""
    if isinstance(output, _MarrvelGeneInferenceResult):
        candidate_labels = list(output.gene_symbols)
    elif isinstance(output, Mapping):
        raw_gene_symbols = output.get("gene_symbols")
        if isinstance(raw_gene_symbols, str):
            return parse_marrvel_gene_symbols(
                raw_gene_symbols,
                objective=objective,
                limit=limit,
            )
        if not isinstance(raw_gene_symbols, Sequence) or isinstance(
            raw_gene_symbols,
            bytes | bytearray | str,
        ):
            return []
        candidate_labels = [str(symbol) for symbol in raw_gene_symbols]
    elif isinstance(output, Sequence) and not isinstance(
        output,
        bytes | bytearray | str,
    ):
        candidate_labels = [str(symbol) for symbol in output]
    elif isinstance(output, str):
        return parse_marrvel_gene_symbols(
            output,
            objective=objective,
            limit=limit,
        )
    else:
        return []
    return prioritize_marrvel_gene_labels(
        candidate_labels,
        objective=objective,
        limit=limit,
    )


def _build_marrvel_gene_inference_runtime(
    *,
    logger: logging.Logger,
) -> _MarrvelGeneInferenceRuntime:
    """Create the kernel-backed runtime context for MARRVEL gene inference."""
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
    from artana_evidence_api.runtime_support import (
        ModelCapability,
        create_artana_postgres_store,
        get_model_registry,
        normalize_litellm_model_id,
    )

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.CURATION)
    model_id = normalize_litellm_model_id(model_spec.model_id)
    logger.info(
        "MARRVEL gene inference using configured curation model %s",
        model_id,
    )
    kernel = ArtanaKernel(
        store=create_artana_postgres_store(),
        model_port=LiteLLMAdapter(timeout_seconds=float(model_spec.timeout_seconds)),
    )
    return _MarrvelGeneInferenceRuntime(
        kernel=kernel,
        client=SingleStepModelClient(kernel=kernel),
        model_id=model_id,
        tenant=TenantContext(
            tenant_id="marrvel-gene-inference",
            capabilities=frozenset(),
            budget_usd_limit=0.5,
        ),
    )


async def _run_marrvel_gene_inference_step(
    *,
    runtime: _MarrvelGeneInferenceRuntime,
    objective: str,
    limit: int,
) -> list[str]:
    """Execute one kernel-backed gene inference step and normalize output."""
    result = await run_single_step_with_policy(
        runtime.client,
        run_id="marrvel-gene-inference",
        tenant=runtime.tenant,
        model=runtime.model_id,
        prompt=_build_marrvel_gene_inference_prompt(objective=objective),
        output_schema=_MarrvelGeneInferenceResult,
        step_key="marrvel.gene_inference.v1",
        replay_policy="fork_on_drift",
    )
    return _coerce_marrvel_gene_labels(
        result.output,
        objective=objective,
        limit=limit,
    )


async def _infer_marrvel_gene_labels_async(
    *,
    objective: str,
    logger: logging.Logger,
    limit: int,
) -> list[str]:
    """Build and execute one MARRVEL gene inference runtime on a single loop."""
    runtime = _build_marrvel_gene_inference_runtime(logger=logger)
    try:
        logger.info("Inferring gene symbols from objective: %s", objective[:80])
        result = await _run_marrvel_gene_inference_step(
            runtime=runtime,
            objective=objective,
            limit=limit,
        )
        return [str(symbol) for symbol in result]
    finally:
        with suppress(Exception):
            await runtime.kernel.close()


def _run_coroutine_sync(
    coroutine: Coroutine[object, object, object],
) -> object:
    """Run one coroutine to completion from a synchronous context.

    When called from a background thread (e.g. via ``asyncio.to_thread``),
    ``asyncio.get_running_loop()`` may still detect the parent's event loop
    even though this thread cannot use it directly.  To avoid "Event loop
    is closed" errors we always create a **new, private event loop** on a
    dedicated thread and block until it finishes.
    """
    result: object = None
    error: BaseException | None = None

    def _runner() -> None:
        nonlocal result, error
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(coroutine)
            finally:
                loop.close()
        except BaseException as exc:  # noqa: BLE001
            error = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return result


# Public alias so callers outside this module don't import a private name.
run_coroutine_sync = _run_coroutine_sync


def infer_marrvel_gene_labels_from_objective(
    *,
    objective: str,
    logger: logging.Logger,
    limit: int = MARRVEL_LLM_GENE_LIMIT,
) -> list[str]:
    """Use the configured LLM to infer likely HGNC symbols from one objective."""
    if objective.strip() == "":
        return []

    try:
        from artana_evidence_api.runtime_support import has_configured_openai_api_key
    except Exception as exc:  # noqa: BLE001
        logger.debug("MARRVEL gene inference unavailable: %s", exc)
        return []

    if not has_configured_openai_api_key():
        logger.debug("MARRVEL gene inference skipped because OPENAI_API_KEY is missing")
        return []

    gene_labels: list[str] = []
    try:
        step_result = _run_coroutine_sync(
            _infer_marrvel_gene_labels_async(
                objective=objective,
                logger=logger,
                limit=limit,
            ),
        )
        if isinstance(step_result, list):
            gene_labels = [str(symbol) for symbol in step_result]
        else:
            gene_labels = []
    except Exception as exc:  # noqa: BLE001
        logger.debug("MARRVEL gene inference step failed: %s", exc)
        return []

    if gene_labels:
        logger.info("LLM inferred gene symbols: %s", gene_labels)
    return gene_labels


def _list_graph_gene_labels(
    *,
    space_id: UUID,
    objective: str,
    graph_api_gateway: GraphTransportBundle,
    logger: logging.Logger,
    candidate_limit: int = MARRVEL_GRAPH_ENTITY_CANDIDATE_LIMIT,
    limit: int = MARRVEL_GRAPH_GENE_LIMIT,
) -> list[str]:
    try:
        entity_list = graph_api_gateway.list_entities(
            space_id=space_id,
            entity_type="GENE",
            limit=candidate_limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MARRVEL enrichment: list_entities failed: %s", exc)
        return []

    all_gene_labels = [
        entity.display_label
        for entity in entity_list.entities
        if entity.display_label is not None and entity.display_label.strip() != ""
    ]
    prioritized_labels = prioritize_marrvel_gene_labels(
        all_gene_labels,
        objective=objective,
        limit=limit,
    )
    logger.warning(
        "MARRVEL enrichment: found %d gene entities (using %d prioritized): %s",
        len(all_gene_labels),
        len(prioritized_labels),
        prioritized_labels,
    )
    return prioritized_labels


def resolve_marrvel_gene_labels(
    *,
    space_id: UUID,
    objective: str,
    graph_api_gateway: GraphTransportBundle,
    logger: logging.Logger,
) -> list[str]:
    """Resolve gene labels from the graph first, then fall back to LLM inference."""
    graph_gene_labels = _list_graph_gene_labels(
        space_id=space_id,
        objective=objective,
        graph_api_gateway=graph_api_gateway,
        logger=logger,
    )
    if graph_gene_labels:
        return graph_gene_labels
    return infer_marrvel_gene_labels_from_objective(
        objective=objective,
        logger=logger,
    )


_ENRICHMENT_OWNER_ID = uuid4()
"""Sentinel owner ID for background enrichment calls.

``MarrvelDiscoveryService.search()`` requires an ``owner_id`` for result
retrieval authorization.  Enrichment callers never look up results by
owner, so a fixed sentinel is sufficient.
"""


def create_marrvel_discovery_service() -> MarrvelDiscoveryService:
    """Build a fresh ``MarrvelDiscoveryService`` instance.

    Mirrors ``create_pubmed_discovery_service()`` to give callers a
    consistent factory pattern across data sources.
    """
    return MarrvelDiscoveryService()


async def fetch_marrvel_associations_via_service(
    *,
    gene_labels: list[str],
    panels: list[str] | None = None,
    space_id: UUID | None = None,
    service: MarrvelDiscoveryService | None = None,
    logger: logging.Logger | None = None,
) -> list[MarrvelPhenotypeAssociation]:
    """Fetch OMIM phenotype associations through ``MarrvelDiscoveryService``.

    Replaces the former ``fetch_marrvel_phenotype_associations`` which used a
    raw ``httpx.Client``.  This version goes through the shared
    ``MarrvelIngestor`` (rate-limited, async, retries) and supports an
    optional ``panels`` parameter to widen beyond OMIM in the future.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    if service is None:
        service = create_marrvel_discovery_service()

    effective_panels = panels or ["omim"]
    effective_space_id = space_id or uuid4()

    associations: list[MarrvelPhenotypeAssociation] = []
    for gene_symbol in gene_labels:
        try:
            result = await service.search(
                owner_id=_ENRICHMENT_OWNER_ID,
                space_id=effective_space_id,
                gene_symbol=gene_symbol,
                panels=effective_panels,
            )
            gene_associations = MarrvelDiscoveryService.extract_omim_associations(
                result,
                gene_symbol,
            )
            logger.info(
                "MARRVEL: gene %s -> %d OMIM phenotype(s) (status=%s)",
                gene_symbol,
                len(gene_associations),
                result.status,
            )
            associations.extend(gene_associations)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MARRVEL: gene %s error: %s", gene_symbol, exc)

    return associations


def build_marrvel_proposal_drafts(
    associations: list[MarrvelPhenotypeAssociation],
) -> tuple[HarnessProposalDraft, ...]:
    """Build proposal drafts from fetched MARRVEL phenotype associations."""
    proposal_drafts: list[HarnessProposalDraft] = []
    for association in associations:
        gene_symbol = association.gene_symbol
        phenotype_label = association.phenotype_label
        proposal_drafts.append(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="marrvel_omim",
                source_key=f"marrvel:omim:{gene_symbol}:{phenotype_label}",
                title=f"MARRVEL: {gene_symbol} associated with {phenotype_label}",
                summary=(
                    f"{gene_symbol} is associated with {phenotype_label} "
                    "(OMIM via MARRVEL)"
                ),
                confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                reasoning_path={
                    "source": "marrvel",
                    "gene_symbol": gene_symbol,
                    "omim_phenotype": phenotype_label,
                },
                evidence_bundle=[
                    {
                        "source_type": "marrvel_omim",
                        "locator": f"marrvel:omim:{gene_symbol}",
                        "excerpt": (
                            "OMIM phenotype association: "
                            f"{gene_symbol} -> {phenotype_label}"
                        ),
                        "relevance": 0.9,
                    },
                ],
                payload={
                    "proposed_claim_type": "ASSOCIATED_WITH",
                    "proposed_subject": gene_symbol,
                    "proposed_subject_label": gene_symbol,
                    "proposed_object": phenotype_label,
                    "proposed_object_label": phenotype_label,
                },
                metadata=_marrvel_bootstrap_proposal_metadata(
                    gene_symbol=gene_symbol,
                    phenotype_label=phenotype_label,
                ),
                claim_fingerprint=compute_claim_fingerprint(
                    gene_symbol,
                    "ASSOCIATED_WITH",
                    phenotype_label,
                ),
            ),
        )
    return tuple(proposal_drafts)


__all__ = [
    "MARRVEL_API_BASE_URL",
    "MARRVEL_API_FALLBACK_BASE_URL",
    "MARRVEL_GRAPH_ENTITY_CANDIDATE_LIMIT",
    "MARRVEL_GRAPH_GENE_LIMIT",
    "MARRVEL_LLM_GENE_LIMIT",
    "MARRVEL_MAX_GENE_SYMBOL_LENGTH",
    "MarrvelPhenotypeAssociation",
    "build_marrvel_proposal_drafts",
    "create_marrvel_discovery_service",
    "fetch_marrvel_associations_via_service",
    "infer_marrvel_gene_labels_from_objective",
    "parse_marrvel_gene_symbols",
    "prioritize_marrvel_gene_labels",
    "resolve_marrvel_gene_labels",
    "run_coroutine_sync",
]
