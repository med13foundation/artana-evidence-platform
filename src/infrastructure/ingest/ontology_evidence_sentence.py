"""Evidence-sentence helpers for ontology hierarchy edges."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

_NAMESPACE_DISPLAY_NAMES = {
    "MONDO": "Monarch Disease Ontology",
    "HP": "Human Phenotype Ontology",
    "UBERON": "Uberon Anatomy Ontology",
    "GO": "Gene Ontology",
    "CL": "Cell Ontology",
}

_AI_EVIDENCE_GLOBAL_FLAG = "ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES"
_AI_EVIDENCE_NAMESPACE_FLAG_PREFIX = "ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES_"
_AI_EVIDENCE_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_MIN_AI_SENTENCE_LENGTH = 24


def _is_truthy_env(name: str) -> bool:
    """Return True when an env var is set to one of the recognized truthy values."""
    raw = os.environ.get(name, "").strip().lower()
    return raw in _AI_EVIDENCE_TRUTHY_VALUES


def _ai_evidence_enabled_for_namespace(namespace: str) -> bool:
    """Return True when AI evidence sentences should run for an ontology."""
    if not namespace:
        return _is_truthy_env(_AI_EVIDENCE_GLOBAL_FLAG)
    namespace_flag = f"{_AI_EVIDENCE_NAMESPACE_FLAG_PREFIX}{namespace.upper()}"
    if _is_truthy_env(namespace_flag):
        return True
    return _is_truthy_env(_AI_EVIDENCE_GLOBAL_FLAG)


def _ontology_namespace_from_term_id(term_id: str) -> str:
    """Extract the ontology namespace prefix from a term id like 'HP:0001250'."""
    if ":" in term_id:
        return term_id.split(":", 1)[0].strip() or "ontology"
    return "ontology"


def _build_hierarchy_evidence_sentence(
    *,
    child_name: str,
    parent_name: str,
    child_id: str,
    parent_id: str,
) -> str:
    """Generate a template evidence sentence for an IS_A hierarchy edge."""
    namespace = _ontology_namespace_from_term_id(child_id)
    ontology_name = _NAMESPACE_DISPLAY_NAMES.get(namespace, namespace)
    return (
        f"{child_name} is classified as a subtype of {parent_name} "
        f"in the {ontology_name} ({child_id} -> {parent_id})."
    )


def _build_hierarchy_evidence_summary(  # noqa: PLR0913
    *,
    child_id: str,
    parent_id: str,
    child_name: str,
    parent_name: str,
    child_definition: str,
    parent_definition: str,
    child_synonyms: tuple[str, ...],
    parent_synonyms: tuple[str, ...],
    ontology_name: str,
) -> str:
    """Build a dense evidence summary describing the IS_A edge for the LLM."""
    child_syns = ", ".join(child_synonyms[:5]) if child_synonyms else ""
    parent_syns = ", ".join(parent_synonyms[:5]) if parent_synonyms else ""
    lines: list[str] = [
        (
            f"Ontology hierarchy edge in {ontology_name}: "
            f"{child_name} ({child_id}) IS_A {parent_name} ({parent_id})."
        ),
    ]
    if child_definition:
        lines.append(f"Child definition: {child_definition}")
    if child_syns:
        lines.append(f"Child synonyms: {child_syns}")
    if parent_definition:
        lines.append(f"Parent definition: {parent_definition}")
    if parent_syns:
        lines.append(f"Parent synonyms: {parent_syns}")
    summary = " ".join(lines)
    return summary[:1990]


class OntologyEvidenceSentenceResolver:
    """Resolve template or AI-generated evidence sentences for ontology edges."""

    def __init__(
        self,
        *,
        evidence_sentence_harness: object | None,
        research_space_id: UUID,
        term_definition_cache: dict[str, str],
        term_synonyms_cache: dict[str, tuple[str, ...]],
    ) -> None:
        self._evidence_sentence_harness = evidence_sentence_harness
        self._space_id = research_space_id
        self._term_definition_cache = term_definition_cache
        self._term_synonyms_cache = term_synonyms_cache
        self._ai_sentence_cache: dict[tuple[str, str], str] = {}
        self._ai_sentence_stats: dict[str, dict[str, int]] = {}

    def resolve(  # noqa: PLR0913
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        child_name: str,
        parent_name: str,
        template_sentence: str,
        research_space_id: str | None,
    ) -> tuple[str, str, str]:
        """Return ``(sentence, source, confidence)`` for one hierarchy edge."""
        namespace = _ontology_namespace_from_term_id(child_term_id)
        if (
            self._evidence_sentence_harness is None
            or not _ai_evidence_enabled_for_namespace(namespace)
        ):
            return template_sentence, "artana_generated", "high"

        self._record_ai_stat(namespace, "requested")

        cache_key = (child_term_id, parent_term_id)
        cached = self._ai_sentence_cache.get(cache_key)
        if cached is not None:
            self._record_ai_stat(namespace, "cache_hit")
            confidence = "high" if cached == template_sentence else "medium"
            return cached, "artana_generated", confidence

        ai_sentence = self._try_generate_ai_evidence_sentence(
            child_term_id=child_term_id,
            parent_term_id=parent_term_id,
            child_name=child_name,
            parent_name=parent_name,
            research_space_id=research_space_id,
        )
        if ai_sentence is None:
            self._record_ai_stat(namespace, "fallback")
            self._ai_sentence_cache[cache_key] = template_sentence
            return template_sentence, "artana_generated", "high"

        self._record_ai_stat(namespace, "generated")
        self._record_ai_stat(namespace, "total_sentence_chars", len(ai_sentence))
        self._ai_sentence_cache[cache_key] = ai_sentence
        return ai_sentence, "artana_generated", "medium"

    def get_stats(self) -> dict[str, dict[str, int]]:
        """Return a deep copy of the per-namespace AI evidence counters."""
        return {
            namespace: dict(counters)
            for namespace, counters in self._ai_sentence_stats.items()
        }

    def _record_ai_stat(
        self,
        namespace: str,
        counter: str,
        increment: int = 1,
    ) -> None:
        bucket = self._ai_sentence_stats.setdefault(
            namespace,
            {
                "requested": 0,
                "generated": 0,
                "fallback": 0,
                "cache_hit": 0,
                "total_sentence_chars": 0,
            },
        )
        bucket[counter] = bucket.get(counter, 0) + increment

    def _try_generate_ai_evidence_sentence(  # noqa: PLR0911
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        child_name: str,
        parent_name: str,
        research_space_id: str | None,
    ) -> str | None:
        harness = self._evidence_sentence_harness
        if harness is None:
            return None

        try:
            from artana_evidence_db.kernel_domain_models import (
                EvidenceSentenceGenerationRequest,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Evidence sentence harness import failed, using template: %s",
                exc,
            )
            return None

        namespace = _ontology_namespace_from_term_id(child_term_id)
        ontology_name = _NAMESPACE_DISPLAY_NAMES.get(namespace, namespace)
        evidence_summary = _build_hierarchy_evidence_summary(
            child_id=child_term_id,
            parent_id=parent_term_id,
            child_name=child_name,
            parent_name=parent_name,
            child_definition=self._term_definition_cache.get(child_term_id, ""),
            parent_definition=self._term_definition_cache.get(parent_term_id, ""),
            child_synonyms=self._term_synonyms_cache.get(child_term_id, ()),
            parent_synonyms=self._term_synonyms_cache.get(parent_term_id, ()),
            ontology_name=ontology_name,
        )
        resolved_space_id = (
            research_space_id if research_space_id is not None else str(self._space_id)
        )

        try:
            request = EvidenceSentenceGenerationRequest(
                research_space_id=resolved_space_id,
                source_type=f"ontology:{namespace.lower()}",
                relation_type="INSTANCE_OF",
                source_label=child_name,
                target_label=parent_name,
                evidence_summary=evidence_summary,
                evidence_excerpt=None,
                evidence_locator=f"{child_term_id}->{parent_term_id}",
                document_text=None,
                document_id=f"ontology:{namespace}",
                run_id=None,
                metadata={
                    "child_id": child_term_id,
                    "parent_id": parent_term_id,
                    "ontology_namespace": namespace,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Failed to build evidence sentence request for %s->%s: %s",
                child_term_id,
                parent_term_id,
                exc,
            )
            return None

        try:
            result = harness.generate(request)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Evidence sentence harness error for %s->%s: %s",
                child_term_id,
                parent_term_id,
                exc,
            )
            return None

        if result.outcome != "generated":
            logger.debug(
                "Evidence sentence harness failed for %s->%s: %s",
                child_term_id,
                parent_term_id,
                result.failure_reason,
            )
            return None

        sentence = (result.sentence or "").strip()
        if len(sentence) < _MIN_AI_SENTENCE_LENGTH:
            return None
        return sentence


__all__ = [
    "OntologyEvidenceSentenceResolver",
    "_build_hierarchy_evidence_sentence",
]
