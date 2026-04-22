"""Application service for graph-driven hypothesis generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from src.application.agents.services._hypothesis_generation_read_support import (
    load_active_hypothesis_fingerprints,
    normalize_candidates_for_seed,
    resolve_seed_entity_ids,
)
from src.application.agents.services._hypothesis_generation_support import (
    build_fingerprint,
    load_reasoning_path_candidates,
    normalize_optional_text,
    normalize_relation_types,
    normalize_seed_entity_ids,
    score_candidates,
)
from src.application.agents.services._hypothesis_generation_transfer_read_support import (
    load_transfer_candidates,
)
from src.application.agents.services._hypothesis_generation_write_support import (
    create_claim_from_candidate,
    create_claim_from_path_candidate,
    create_claim_from_transfer_candidate,
)
from src.application.services.claim_first_metrics import increment_metric
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelRelationClaim
    from artana_evidence_db.kernel_repositories import (
        KernelEntityRepository,
        KernelRelationRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelClaimEvidenceService,
        KernelClaimParticipantService,
        KernelReasoningPathService,
        KernelRelationClaimService,
    )

    from src.application.agents.services._hypothesis_generation_support import (
        PathCandidate,
        RawCandidate,
        ScoredCandidate,
        TransferCandidate,
    )
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.domain.ports import DictionaryPort


_SCORE_THRESHOLD = 0.45
_GRAPH_ORIGIN = "graph_agent"
_PATH_ORIGIN = "reasoning_path"


@dataclass(frozen=True)
class HypothesisGenerationServiceDependencies:
    """Dependencies required for hypothesis generation orchestration."""

    graph_connection_agent: GraphConnectionPort
    relation_claim_service: KernelRelationClaimService
    claim_participant_service: KernelClaimParticipantService
    claim_evidence_service: KernelClaimEvidenceService
    entity_repository: KernelEntityRepository
    relation_repository: KernelRelationRepository
    dictionary_service: DictionaryPort
    reasoning_path_service: KernelReasoningPathService | None = None


@dataclass(frozen=True)
class HypothesisGenerationResult:
    """Outcome of one hypothesis-generation run."""

    run_id: str
    requested_seed_count: int
    used_seed_count: int
    candidates_seen: int
    created_count: int
    deduped_count: int
    errors: tuple[str, ...]
    hypotheses: tuple[KernelRelationClaim, ...]


class HypothesisGenerationService:
    """Generate hypothesis relation claims from graph-agent exploration."""

    def __init__(self, dependencies: HypothesisGenerationServiceDependencies) -> None:
        self._graph_agent = dependencies.graph_connection_agent
        self._claims = dependencies.relation_claim_service
        self._participants = dependencies.claim_participant_service
        self._claim_evidence = dependencies.claim_evidence_service
        self._entities = dependencies.entity_repository
        self._relations = dependencies.relation_repository
        self._dictionary = dependencies.dictionary_service
        self._reasoning_paths = dependencies.reasoning_path_service

    async def generate_hypotheses(  # noqa: PLR0912, PLR0913, PLR0915, C901
        self,
        *,
        research_space_id: str,
        seed_entity_ids: list[str] | None,
        source_type: str,
        relation_types: list[str] | None,
        max_depth: int,
        max_hypotheses: int,
        model_id: str | None,
    ) -> HypothesisGenerationResult:
        """Run graph-agent exploration and persist top scored hypothesis claims."""
        run_id = str(uuid4())
        requested_seeds = normalize_seed_entity_ids(seed_entity_ids)
        requested_seed_count = len(requested_seeds)
        resolved_seed_ids = resolve_seed_entity_ids(
            relation_claim_service=self._claims,
            relation_repository=self._relations,
            entity_repository=self._entities,
            research_space_id=research_space_id,
            requested_seed_entity_ids=requested_seeds,
            max_hypotheses=max_hypotheses,
        )
        if not resolved_seed_ids:
            return HypothesisGenerationResult(
                run_id=run_id,
                requested_seed_count=requested_seed_count,
                used_seed_count=0,
                candidates_seen=0,
                created_count=0,
                deduped_count=0,
                errors=("no_seed_entities_resolved",),
                hypotheses=(),
            )

        normalized_relation_types = normalize_relation_types(relation_types)
        active_fingerprints = load_active_hypothesis_fingerprints(
            relation_claim_service=self._claims,
            research_space_id=research_space_id,
        )
        raw_candidates: list[RawCandidate] = []
        path_candidates: list[PathCandidate] = []
        transfer_candidates: list[TransferCandidate] = []
        errors: list[str] = []

        if self._reasoning_paths is not None:
            path_candidates, path_errors = load_reasoning_path_candidates(
                reasoning_path_service=self._reasoning_paths,
                research_space_id=research_space_id,
                seed_entity_ids=resolved_seed_ids,
                max_hypotheses=max_hypotheses,
            )
            errors.extend(path_errors)
            transfer_candidates, transfer_errors = load_transfer_candidates(
                reasoning_path_service=self._reasoning_paths,
                relation_repository=self._relations,
                relation_claim_service=self._claims,
                claim_participant_service=self._participants,
                claim_evidence_service=self._claim_evidence,
                entity_repository=self._entities,
                research_space_id=research_space_id,
                seed_entity_ids=resolved_seed_ids,
                path_candidates=path_candidates,
                max_hypotheses=max_hypotheses,
            )
            errors.extend(transfer_errors)

        for seed_entity_id in resolved_seed_ids:
            try:
                contract = await self._graph_agent.discover(
                    GraphConnectionContext(
                        seed_entity_id=seed_entity_id,
                        source_type=source_type,
                        research_space_id=research_space_id,
                        relation_types=normalized_relation_types,
                        max_depth=max_depth,
                        shadow_mode=True,
                    ),
                    model_id=model_id,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"seed_discovery_failed:{seed_entity_id}:{type(exc).__name__}",
                )
                continue

            seed_candidates, seed_errors = normalize_candidates_for_seed(
                dictionary_service=self._dictionary,
                entity_repository=self._entities,
                relation_repository=self._relations,
                research_space_id=research_space_id,
                seed_entity_id=seed_entity_id,
                candidates=contract.proposed_relations,
                graph_agent_run_id=normalize_optional_text(contract.agent_run_id),
            )
            raw_candidates.extend(seed_candidates)
            errors.extend(seed_errors)

        eligible_candidates = [
            candidate
            for candidate in sorted(
                score_candidates(raw_candidates),
                key=lambda item: (
                    -item.score,
                    -item.raw.relation_confidence,
                    item.raw.relation_type,
                ),
            )
            if candidate.score >= _SCORE_THRESHOLD
        ]
        created, deduped_count = self._emit_claims(
            research_space_id=research_space_id,
            run_id=run_id,
            max_hypotheses=max_hypotheses,
            active_fingerprints=active_fingerprints,
            eligible_candidates=eligible_candidates,
            path_candidates=path_candidates,
            transfer_candidates=transfer_candidates,
        )
        errors.extend(
            self._resolve_run_errors(
                created_count=len(created),
                raw_candidate_count=len(raw_candidates),
                eligible_candidate_count=len(eligible_candidates),
                deduped_count=deduped_count,
            ),
        )
        self._record_metrics(
            research_space_id=research_space_id,
            created_count=len(created),
            deduped_count=deduped_count,
            error_count=len(errors),
        )
        return HypothesisGenerationResult(
            run_id=run_id,
            requested_seed_count=requested_seed_count,
            used_seed_count=len(resolved_seed_ids),
            candidates_seen=(
                len(raw_candidates) + len(path_candidates) + len(transfer_candidates)
            ),
            created_count=len(created),
            deduped_count=deduped_count,
            errors=tuple(errors),
            hypotheses=tuple(created),
        )

    def _emit_claims(  # noqa: PLR0913, C901
        self,
        *,
        research_space_id: str,
        run_id: str,
        max_hypotheses: int,
        active_fingerprints: set[str],
        eligible_candidates: list[ScoredCandidate],
        path_candidates: list[PathCandidate],
        transfer_candidates: list[TransferCandidate],
    ) -> tuple[list[KernelRelationClaim], int]:
        created: list[KernelRelationClaim] = []
        deduped_count = 0
        emitted_fingerprints: set[str] = set()
        emitted_transfer_path_ids: set[str] = set()

        for transfer_candidate in transfer_candidates:
            if len(created) >= max_hypotheses:
                break
            fingerprint = build_fingerprint(
                source_entity_id=transfer_candidate.start_entity_id,
                relation_type=transfer_candidate.relation_type,
                target_entity_id=transfer_candidate.end_entity_id,
                origin=f"mechanism_transfer:{transfer_candidate.reasoning_path_id}",
            )
            if (
                fingerprint in active_fingerprints
                or fingerprint in emitted_fingerprints
            ):
                deduped_count += 1
                continue
            created.append(
                create_claim_from_transfer_candidate(
                    relation_claim_service=self._claims,
                    claim_participant_service=self._participants,
                    candidate=transfer_candidate,
                    research_space_id=research_space_id,
                    run_id=run_id,
                    fingerprint=fingerprint,
                ),
            )
            emitted_fingerprints.add(fingerprint)
            emitted_transfer_path_ids.add(transfer_candidate.reasoning_path_id)
            active_fingerprints.add(fingerprint)

        for path_candidate in path_candidates:
            if len(created) >= max_hypotheses:
                break
            if path_candidate.reasoning_path_id in emitted_transfer_path_ids:
                continue
            fingerprint = build_fingerprint(
                source_entity_id=path_candidate.start_entity_id,
                relation_type=path_candidate.relation_type,
                target_entity_id=path_candidate.end_entity_id,
                origin=f"{_PATH_ORIGIN}:{path_candidate.reasoning_path_id}",
            )
            if (
                fingerprint in active_fingerprints
                or fingerprint in emitted_fingerprints
            ):
                deduped_count += 1
                continue
            created.append(
                create_claim_from_path_candidate(
                    relation_claim_service=self._claims,
                    claim_participant_service=self._participants,
                    candidate=path_candidate,
                    research_space_id=research_space_id,
                    run_id=run_id,
                    fingerprint=fingerprint,
                ),
            )
            emitted_fingerprints.add(fingerprint)
            active_fingerprints.add(fingerprint)

        for scored_candidate in eligible_candidates:
            if len(created) >= max_hypotheses:
                break
            fingerprint = build_fingerprint(
                source_entity_id=scored_candidate.raw.source_entity_id,
                relation_type=scored_candidate.raw.relation_type,
                target_entity_id=scored_candidate.raw.target_entity_id,
                origin=_GRAPH_ORIGIN,
            )
            if (
                fingerprint in active_fingerprints
                or fingerprint in emitted_fingerprints
            ):
                deduped_count += 1
                continue
            created.append(
                create_claim_from_candidate(
                    relation_claim_service=self._claims,
                    claim_participant_service=self._participants,
                    candidate=scored_candidate,
                    research_space_id=research_space_id,
                    run_id=run_id,
                    fingerprint=fingerprint,
                    seed_entity_id=scored_candidate.raw.seed_entity_id,
                ),
            )
            emitted_fingerprints.add(fingerprint)
            active_fingerprints.add(fingerprint)

        return created, deduped_count

    @staticmethod
    def _resolve_run_errors(
        *,
        created_count: int,
        raw_candidate_count: int,
        eligible_candidate_count: int,
        deduped_count: int,
    ) -> list[str]:
        if created_count > 0:
            return []
        if raw_candidate_count == 0:
            return ["no_candidates_discovered"]
        if eligible_candidate_count == 0:
            return ["all_candidates_below_threshold"]
        if deduped_count >= eligible_candidate_count:
            return ["all_candidates_deduped"]
        return ["no_candidates_selected"]

    @staticmethod
    def _record_metrics(
        *,
        research_space_id: str,
        created_count: int,
        deduped_count: int,
        error_count: int,
    ) -> None:
        if created_count > 0:
            increment_metric(
                "hypotheses_auto_generated_total",
                delta=created_count,
                tags={"research_space_id": research_space_id},
            )
        if deduped_count > 0:
            increment_metric(
                "hypotheses_deduped_total",
                delta=deduped_count,
                tags={"research_space_id": research_space_id},
            )
        if error_count > 0:
            increment_metric(
                "hypotheses_generation_failed_total",
                delta=error_count,
                tags={"research_space_id": research_space_id},
            )


__all__ = [
    "HypothesisGenerationResult",
    "HypothesisGenerationService",
    "HypothesisGenerationServiceDependencies",
]
