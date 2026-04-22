"""LLM-judge mapper for ambiguous dictionary mappings."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    resolve_graph_domain_context,
)

from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
from src.domain.agents.contracts.assessment_compat import (
    assessment_payload,
    confidence_from_mapping_judge_contract,
)
from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate
from src.infrastructure.ingestion.types import MappedObservation, RawRecord

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import DictionarySearchResult
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.type_definitions.common import JSONObject


def _read_candidate_floor() -> float:
    raw_value = (
        os.getenv("ARTANA_LLM_JUDGE_MAPPER_CANDIDATE_FLOOR")
        or os.getenv("LLM_JUDGE_MAPPER_CANDIDATE_FLOOR")
        or "0.4"
    )
    try:
        parsed = float(raw_value)
    except ValueError:
        return 0.4
    return min(1.0, max(0.0, parsed))


def _read_top_k() -> int:
    raw_value = (
        os.getenv("ARTANA_LLM_JUDGE_MAPPER_TOP_K")
        or os.getenv("LLM_JUDGE_MAPPER_TOP_K")
        or "5"
    )
    try:
        parsed = int(raw_value)
    except ValueError:
        return 5
    return max(1, parsed)


def _read_vector_threshold() -> float:
    raw_value = (
        os.getenv("ARTANA_VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or os.getenv("VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or "0.7"
    )
    try:
        parsed = float(raw_value)
    except ValueError:
        return 0.7
    return min(1.0, max(0.0, parsed))


LLM_JUDGE_MAPPER_CANDIDATE_FLOOR = _read_candidate_floor()
LLM_JUDGE_MAPPER_TOP_K = _read_top_k()
LLM_JUDGE_VECTOR_THRESHOLD = _read_vector_threshold()
_VALUE_PREVIEW_LIMIT = 2000


class LLMJudgeMapper:
    """Maps ambiguous fields using a judge agent over dictionary candidates."""

    def __init__(
        self,
        dictionary_repository: DictionaryPort,
        mapping_judge_agent: MappingJudgePort,
        *,
        candidate_floor: float = LLM_JUDGE_MAPPER_CANDIDATE_FLOOR,
        top_k: int = LLM_JUDGE_MAPPER_TOP_K,
        vector_threshold: float = LLM_JUDGE_VECTOR_THRESHOLD,
    ) -> None:
        self.dictionary_repo = dictionary_repository
        self.mapping_judge_agent = mapping_judge_agent
        self.candidate_floor = min(1.0, max(0.0, candidate_floor))
        self.top_k = max(1, top_k)
        self.vector_threshold = min(1.0, max(0.0, vector_threshold))

    def map(self, record: RawRecord) -> list[MappedObservation]:
        observations: list[MappedObservation] = []
        subject_anchor = self._extract_subject_anchor(record)
        observed_at = self._extract_timestamp(record)
        domain_context = self._extract_domain_context(record)
        source_type = self._extract_source_type(record)

        for key, value in record.data.items():
            if value is None or value == "":
                continue

            search_results = self.dictionary_repo.dictionary_search(
                terms=[key],
                dimensions=["variables"],
                domain_context=domain_context,
                limit=self.top_k,
            )
            candidates = self._build_candidates(search_results)
            if not self._should_invoke_judge(candidates):
                continue

            context = MappingJudgeContext(
                field_key=key,
                field_value_preview=self._value_preview(value),
                source_id=record.source_id,
                source_type=source_type,
                domain_context=domain_context,
                record_metadata=record.metadata,
                candidates=candidates,
                request_source="ingestion_pipeline",
            )
            decision = self.mapping_judge_agent.judge(context)
            if (
                decision.decision != "matched"
                or decision.selected_variable_id is None
                or decision.selected_variable_id
                not in {candidate.variable_id for candidate in candidates}
            ):
                continue

            selected = self._resolve_selected_candidate(
                candidates,
                selected_variable_id=decision.selected_variable_id,
            )
            decision_assessment = assessment_payload(decision)
            observations.append(
                MappedObservation(
                    subject_anchor=subject_anchor,
                    variable_id=decision.selected_variable_id,
                    value=value,
                    unit=None,
                    observed_at=observed_at,
                    provenance={
                        "source_id": record.source_id,
                        "original_key": key,
                        "method": "llm_judge",
                        "judge_decision": decision.decision,
                        "judge_confidence": confidence_from_mapping_judge_contract(
                            decision,
                        ),
                        "judge_rationale": decision.selection_rationale,
                        "judge_agent_run_id": decision.agent_run_id,
                        **(
                            {"judge_assessment": decision_assessment}
                            if decision_assessment is not None
                            else {}
                        ),
                        "selected_candidate": (
                            selected.model_dump(mode="json")
                            if selected is not None
                            else None
                        ),
                        "candidates": [
                            candidate.model_dump(mode="json")
                            for candidate in candidates
                        ],
                        "metadata": record.metadata,
                    },
                ),
            )

        return observations

    def _build_candidates(
        self,
        search_results: list[DictionarySearchResult],
    ) -> list[MappingJudgeCandidate]:
        candidates: list[MappingJudgeCandidate] = []
        for result in search_results:
            if result.dimension != "variables":
                continue
            if result.match_method in {"exact", "synonym"}:
                continue
            if result.similarity_score < self.candidate_floor:
                continue
            candidates.append(
                MappingJudgeCandidate(
                    variable_id=result.entry_id,
                    display_name=result.display_name,
                    match_method=result.match_method,
                    similarity_score=result.similarity_score,
                    description=result.description,
                    metadata=result.metadata,
                ),
            )
        return candidates

    def _should_invoke_judge(self, candidates: list[MappingJudgeCandidate]) -> bool:
        if not candidates:
            return False

        best_vector_score = max(
            (
                candidate.similarity_score
                for candidate in candidates
                if candidate.match_method == "vector"
            ),
            default=0.0,
        )
        return best_vector_score < self.vector_threshold

    @staticmethod
    def _resolve_selected_candidate(
        candidates: list[MappingJudgeCandidate],
        *,
        selected_variable_id: str,
    ) -> MappingJudgeCandidate | None:
        for candidate in candidates:
            if candidate.variable_id == selected_variable_id:
                return candidate
        return None

    @staticmethod
    def _value_preview(value: object) -> str:
        rendered = str(value).strip()
        if len(rendered) <= _VALUE_PREVIEW_LIMIT:
            return rendered
        return f"{rendered[: _VALUE_PREVIEW_LIMIT - 3]}..."

    def _extract_domain_context(self, record: RawRecord) -> str | None:
        return resolve_graph_domain_context(
            domain_context_policy=create_graph_domain_context_policy(),
            metadata=record.metadata,
            source_type=self._extract_source_type(record),
            fallback=None,
        )

    def _extract_source_type(self, record: RawRecord) -> str | None:
        raw_value = record.metadata.get("type")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return None

    def _extract_subject_anchor(self, record: RawRecord) -> JSONObject:
        anchors: JSONObject = {}

        record_type = record.metadata.get("type")
        entity_type = record.metadata.get("entity_type")
        if (
            isinstance(record_type, str)
            and record_type == "pubmed"
            and entity_type == "PUBLICATION"
        ):
            for key in ["pmid", "doi", "title"]:
                if key in record.data and record.data[key] is not None:
                    anchors[key] = record.data[key]
            return anchors

        for key in [
            "mrn",
            "issuer",
            "patient_id",
            "email",
            "hgnc_id",
            "gene_symbol",
            "clinvar_id",
            "variant_id",
            "variation_id",
            "hgvs_notation",
            "hgvs",
            "rsid",
            "display_label",
            "label",
            "mechanism_name",
        ]:
            if key in record.data and record.data[key] is not None:
                anchors[key] = record.data[key]

        for key in ["source_record_id", "external_record_id"]:
            if key in anchors:
                continue
            raw_value = record.metadata.get(key)
            if raw_value is not None and raw_value != "":
                anchors[key] = raw_value

        if not anchors and record.source_id.strip():
            anchors["source_id"] = record.source_id.strip()
        return anchors

    def _extract_timestamp(self, record: RawRecord) -> datetime | None:
        for key in [
            "timestamp",
            "date",
            "created_at",
            "observed_at",
            "publication_date",
        ]:
            if key not in record.data:
                continue
            value = record.data[key]
            if not isinstance(value, str):
                continue
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        return None
