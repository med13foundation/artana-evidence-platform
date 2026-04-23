"""Document extraction helpers for the standalone harness service."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_reviewed_candidate_claim
from artana_evidence_api.step_helpers import run_single_step_with_policy
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from pydantic import BaseModel, ConfigDict, Field

try:  # pragma: no cover - import guard
    from pypdf import PdfReader
except ModuleNotFoundError:  # pragma: no cover - exercised in env-dependent tests
    PdfReader = None

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

logger = logging.getLogger(__name__)

def _graph_ai_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_LEADING_FILLER_RE = re.compile(
    r"^(?:the|a|an|this|that|these|those|our|their|its)\s+",
    re.IGNORECASE,
)
_TRAILING_CONTEXT_RE = re.compile(
    r"\s+(?:in|during|among|across|within|via|through|after|before|under|with)\s+"
    r"[A-Za-z0-9][A-Za-z0-9()\-/, ]*$",
    re.IGNORECASE,
)
_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")
_MIN_COMPOUND_SEGMENT_TOKEN_COUNT = 2
_MIN_EXACT_SPLIT_MATCH_COUNT = 2
_GOAL_CONTEXT_MAX_ITEMS = 3
_GOAL_CONTEXT_MAX_TEXT_LENGTH = 180
_MAX_ENTITY_LABEL_WORDS = 4
_MIN_ENTITY_LABEL_LENGTH = 2
_MAX_AI_ENTITY_PRE_RESOLUTION_LABELS = 4
_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS = 2.0
_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS = 5.0
_LLM_PROPOSAL_REVIEW_TIMEOUT_SECONDS = 5.0
_MIN_GOAL_CONTEXT_TOKEN_LENGTH = 4
_DIRECT_GOAL_TOKEN_OVERLAP_MIN = 3
_SUBJECT_CONTEXT_MARKERS = (
    " that ",
    " showed ",
    " shows ",
    " found ",
    " finds ",
    " suggests ",
    " suggested ",
    " demonstrated ",
    " demonstrates ",
    " indicates ",
    " indicated ",
    " observed ",
    " reports ",
    " reported ",
)
_COMMON_CONTEXT_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "into",
        "this",
        "these",
        "those",
        "their",
        "there",
        "have",
        "has",
        "been",
        "were",
        "which",
        "about",
        "through",
        "between",
        "within",
        "using",
        "used",
        "study",
        "review",
        "paper",
        "research",
        "space",
        "goal",
        "goals",
        "objective",
        "question",
        "questions",
    },
)
_FACTUAL_HEDGE_MARKERS = (
    " may ",
    " might ",
    " could ",
    " possible ",
    " possibly ",
    " suggests ",
    " suggest ",
    " suggested ",
    " appears ",
    " appear ",
    " likely ",
    " potential ",
)
_ENTITY_LABEL_PREFIXES = (
    "loss of ",
    "deficiency of ",
    "depletion of ",
    "deletion of ",
    "overexpression of ",
    "underexpression of ",
    "mutation in ",
    "mutations in ",
    "variant in ",
    "variants in ",
)
_RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9\- ]{1,80}?)\s+"
            r"(?P<lemma>regulates|activated|activates|inhibits|interacts with|"
            r"interact with|associates with|associate with|associated with|"
            r"is associated with|was associated with|were associated with|"
            r"has been associated with|have been associated with|linked to|"
            r"is linked to|was linked to|were linked to|has been linked to|"
            r"have been linked to|causes|caused|drives|driven|promotes|"
            r"promoted|supports|supported|results in|resulted in|leads to|"
            r"led to|contributes to|contributed to|correlates with|"
            r"correlated with|is correlated with|was correlated with|"
            r"were correlated with)\s+"
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+regulated by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "REGULATES",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+caused by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "CAUSES",
    ),
)
_LEMMA_RELATION_TYPES = {
    "activate": "ACTIVATES",
    "activated": "ACTIVATES",
    "activates": "ACTIVATES",
    "associate with": "ASSOCIATED_WITH",
    "associated with": "ASSOCIATED_WITH",
    "associates with": "ASSOCIATED_WITH",
    "caused": "CAUSES",
    "causes": "CAUSES",
    "contribute to": "ASSOCIATED_WITH",
    "contributed to": "ASSOCIATED_WITH",
    "contributes to": "ASSOCIATED_WITH",
    "correlated with": "ASSOCIATED_WITH",
    "drive": "ASSOCIATED_WITH",
    "driven": "ASSOCIATED_WITH",
    "drives": "ASSOCIATED_WITH",
    "has been associated with": "ASSOCIATED_WITH",
    "has been linked to": "ASSOCIATED_WITH",
    "have been associated with": "ASSOCIATED_WITH",
    "have been linked to": "ASSOCIATED_WITH",
    "interact with": "INTERACTS_WITH",
    "inhibits": "INHIBITS",
    "interacts with": "INTERACTS_WITH",
    "is associated with": "ASSOCIATED_WITH",
    "is correlated with": "ASSOCIATED_WITH",
    "is linked to": "ASSOCIATED_WITH",
    "lead to": "CAUSES",
    "leads to": "CAUSES",
    "led to": "CAUSES",
    "linked to": "ASSOCIATED_WITH",
    "promote": "ACTIVATES",
    "promoted": "ACTIVATES",
    "promotes": "ACTIVATES",
    "regulate": "REGULATES",
    "regulates": "REGULATES",
    "reported": "ASSOCIATED_WITH",
    "resulted in": "CAUSES",
    "results in": "CAUSES",
    "support": "ASSOCIATED_WITH",
    "supported": "ASSOCIATED_WITH",
    "supports": "ASSOCIATED_WITH",
    "was associated with": "ASSOCIATED_WITH",
    "was correlated with": "ASSOCIATED_WITH",
    "was linked to": "ASSOCIATED_WITH",
    "were associated with": "ASSOCIATED_WITH",
    "were correlated with": "ASSOCIATED_WITH",
    "were linked to": "ASSOCIATED_WITH",
}


@dataclass(frozen=True, slots=True)
class ExtractedRelationCandidate:
    """One relation-like statement extracted from document text."""

    subject_label: str
    relation_type: str
    object_label: str
    sentence: str


@dataclass(frozen=True, slots=True)
class DocumentTextExtraction:
    """Normalized extracted text and metadata for one uploaded PDF."""

    text_content: str
    page_count: int | None


FactualSupportScale = Literal["strong", "moderate", "tentative", "unsupported"]
GoalRelevanceScale = Literal[
    "direct",
    "supporting",
    "peripheral",
    "off_target",
    "unscoped",
]
PriorityScale = Literal["prioritize", "review", "background", "ignore"]

_FACTUAL_SUPPORT_SCORES: dict[FactualSupportScale, float] = {
    "strong": 0.92,
    "moderate": 0.72,
    "tentative": 0.46,
    "unsupported": 0.18,
}
_GOAL_RELEVANCE_SCORES: dict[GoalRelevanceScale, float] = {
    "direct": 0.96,
    "supporting": 0.72,
    "peripheral": 0.38,
    "off_target": 0.12,
    "unscoped": 0.5,
}
_PRIORITY_SCORES: dict[PriorityScale, float] = {
    "prioritize": 0.96,
    "review": 0.72,
    "background": 0.36,
    "ignore": 0.08,
}


@dataclass(frozen=True, slots=True)
class DocumentExtractionReviewContext:
    """Research-goal context used to review extracted claims."""

    objective: str | None
    current_hypotheses: tuple[str, ...] = ()
    pending_questions: tuple[str, ...] = ()
    explored_questions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentProposalReview:
    """One categorical review for an extracted proposal."""

    factual_support: FactualSupportScale
    goal_relevance: GoalRelevanceScale
    priority: PriorityScale
    rationale: str
    factual_rationale: str
    relevance_rationale: str
    method: str
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentProposalReviewDiagnostics:
    """Runtime diagnostics for the proposal-review LLM pass."""

    llm_review_status: Literal[
        "not_needed",
        "completed",
        "unavailable",
        "fallback_error",
    ]
    llm_review_error: str | None = None

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics into JSON-safe metadata."""
        payload: JSONObject = {
            "llm_review_status": self.llm_review_status,
            "llm_review_attempted": self.llm_review_status
            in {"completed", "fallback_error"},
            "llm_review_failed": self.llm_review_status
            in {"unavailable", "fallback_error"},
        }
        if self.llm_review_error is not None:
            payload["llm_review_error"] = self.llm_review_error
        return payload


@dataclass(frozen=True, slots=True)
class DocumentCandidateExtractionDiagnostics:
    """Runtime diagnostics for relation-candidate discovery."""

    llm_candidate_status: Literal[
        "not_needed",
        "completed",
        "llm_empty",
        "fallback",
        "fallback_error",
        "unavailable",
    ]
    llm_candidate_error: str | None = None
    llm_candidate_count: int = 0
    fallback_candidate_count: int = 0

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics into JSON-safe metadata."""
        payload: JSONObject = {
            "llm_candidate_status": self.llm_candidate_status,
            "llm_candidate_attempted": self.llm_candidate_status
            in {"completed", "llm_empty", "fallback", "fallback_error"},
            "llm_candidate_failed": self.llm_candidate_status
            in {"fallback", "fallback_error", "unavailable"},
        }
        if self.llm_candidate_count > 0:
            payload["llm_candidate_count"] = self.llm_candidate_count
        if self.fallback_candidate_count > 0:
            payload["fallback_candidate_count"] = self.fallback_candidate_count
        if self.llm_candidate_error is not None:
            payload["llm_candidate_error"] = self.llm_candidate_error
        return payload


def sha256_hex(payload: bytes) -> str:
    """Return the SHA-256 digest for one document payload."""
    return hashlib.sha256(payload).hexdigest()


def _fingerprinted_step_key(prefix: str, *parts: str) -> str:
    """Return a stable per-input step key for replay-sensitive model calls."""
    payload = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}.{digest}"


def _llm_extraction_step_key(
    *,
    text: str,
    max_relations: int,
) -> str:
    """Return the stable extraction step key for one normalized document body."""
    normalized_text = normalize_text_document(text)
    return _fingerprinted_step_key(
        "research_init.llm_extraction.v1",
        str(max_relations),
        normalized_text[:4000],
    )


def _proposal_review_step_key(
    *,
    document: HarnessDocumentRecord,
    claims_text: str,
    goal_context_summary: str,
) -> str:
    """Return the stable proposal-review step key for one review payload."""
    return _fingerprinted_step_key(
        "document_extraction.proposal_review.v1",
        document.sha256,
        document.source_type,
        document.title,
        claims_text,
        goal_context_summary,
    )


def extract_pdf_text(payload: bytes) -> DocumentTextExtraction:
    """Extract text content from one PDF payload."""
    if PdfReader is None:
        raise RuntimeError(
            "PDF upload support requires the optional 'pypdf' dependency.",
        )
    reader = PdfReader(io.BytesIO(payload))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return DocumentTextExtraction(
        text_content="\n\n".join(text for text in page_texts if text.strip() != ""),
        page_count=len(reader.pages),
    )


def normalize_text_document(text: str) -> str:
    """Normalize one raw text submission for harness storage."""
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


def extract_relation_candidates(text: str) -> list[ExtractedRelationCandidate]:
    """Extract lightweight relation candidates from document text."""
    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return []
    candidates: list[ExtractedRelationCandidate] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(normalized_text):
        cleaned_sentence = " ".join(sentence.split()).strip()
        if cleaned_sentence == "":
            continue
        for pattern, fixed_relation_type in _RELATION_PATTERNS:
            match = pattern.search(cleaned_sentence)
            if match is None:
                continue
            subject_label = _clean_candidate_label(
                match.group("subject"),
                prefer_tail=True,
            )
            object_label = _clean_candidate_label(match.group("object"))
            relation_type = fixed_relation_type or _LEMMA_RELATION_TYPES.get(
                match.groupdict().get("lemma", "").strip().lower(),
                "ASSOCIATED_WITH",
            )
            if subject_label == "" or object_label == "":
                continue
            candidate_key = (
                subject_label.casefold(),
                relation_type,
                object_label.casefold(),
                cleaned_sentence.casefold(),
            )
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(
                ExtractedRelationCandidate(
                    subject_label=subject_label,
                    relation_type=relation_type,
                    object_label=object_label,
                    sentence=cleaned_sentence,
                ),
            )
            break
    return candidates


_LLM_EXTRACTION_SYSTEM_PROMPT = """You are a biomedical knowledge extraction system. Your task is to identify concrete biological relationships from research text and return them as structured triples.

Each triple has:
- subject: a single named biomedical entity. This MUST be a short canonical name, not a sentence fragment.
  GOOD: "BRCA1", "cisplatin", "EGFR", "T790M", "HRD", "PD-L1", "osimertinib", "triple-negative breast cancer", "DNA damage repair"
  BAD: "Inherited pathogenic variants in BRCA1", "In order to examine whether", "there are DNA repair functions", "the compound was found to"
  Rules: max 4 words. Use gene symbols (BRCA1 not "breast cancer gene 1"). Use drug names (cisplatin not "the platinum agent"). Use standard abbreviations (TNBC, NSCLC, HRD). For mutations, use the notation (T790M, V600E).
- relation_type: exactly one of these canonical types:

  Core causal relations:
    ASSOCIATED_WITH — generic biomedical association
    CAUSES — directional causal relationship
    TREATS — therapeutic relationship (intervention → condition)
    TARGETS — directed targeting (intervention → molecular entity)
    BIOMARKER_FOR — measurable signal linked to a condition
    PHYSICALLY_INTERACTS_WITH — physical interaction between molecules
    ACTIVATES — positive regulatory relationship
    REGULATES — generic regulatory relationship
    INHIBITS — negative regulatory relationship

  Extended scientific relations:
    UPSTREAM_OF — mechanistic ordering in pathway chains
    DOWNSTREAM_OF — inverse mechanistic ordering
    PART_OF — compositional relationship
    EXPRESSED_IN — expression in tissue/cell context
    PARTICIPATES_IN — entity participates in a process

  Evidence relations:
    SUPPORTS — evidence supporting a claim
    REFINES — more specific statement or mechanism

  If none of these fit, you may propose a new relation type using UPPER_SNAKE_CASE (e.g., CONFERS_RESISTANCE_TO, SENSITIZES_TO, CO_EXPRESSED_WITH). New types will be evaluated and registered by the system's ontology resolver.

- object: the target entity. Same rules as subject: short canonical name, max 4 words, no sentence fragments.
- sentence: the verbatim sentence from the input text that supports this relationship. Copy it exactly, do not paraphrase.

IMPORTANT — do NOT extract:
- Funding acknowledgments, grant numbers, or institutional affiliations
- Author names or contributions
- Study design descriptions that don't state a biological finding
- Sentences about methods or protocols without a biological conclusion
- Vague or speculative statements ("may play a role", "further research is needed")
- Relations where subject or object is not a specific named entity

Focus on:
- Concrete findings from results and conclusions
- Drug-target interactions (osimertinib TARGETS EGFR T790M)
- Resistance mechanisms (MET amplification CAUSES resistance to erlotinib)
- Biomarker associations (HRD score BIOMARKER_FOR platinum sensitivity)
- Pathway interactions (BRCA1 REGULATES DNA damage repair)
- Gene expression (PD-L1 EXPRESSED_IN tumor microenvironment)
- Therapeutic relationships (cisplatin TREATS triple-negative breast cancer)

Return up to 10 of the strongest, most specific relationships. Quality over quantity."""


# Canonical relation types matching GRAPH_SERVICE_BUILTIN_RELATION_TYPES.
# This set is validated against the graph domain config by
# test_constraint_profile_model.py::test_llm_valid_types_matches_builtin_types
# to ensure it stays in sync.  We cannot import from artana_evidence_db
# directly due to the service boundary.
_LLM_VALID_RELATION_TYPES = frozenset(
    {
        # Core causal
        "ASSOCIATED_WITH",
        "CAUSES",
        "TREATS",
        "TARGETS",
        "BIOMARKER_FOR",
        "PHYSICALLY_INTERACTS_WITH",
        "ACTIVATES",
        "REGULATES",
        "INHIBITS",
        "SENSITIZES_TO",
        "PHENOCOPY_OF",
        # Extended scientific
        "UPSTREAM_OF",
        "DOWNSTREAM_OF",
        "PART_OF",
        "COMPONENT_OF",
        "EXPRESSED_IN",
        "PARTICIPATES_IN",
        "LOCATED_IN",
        # Mechanistic / functional consequence
        "MODULATES",
        "LOSS_OF_FUNCTION",
        "GAIN_OF_FUNCTION",
        "PREDISPOSES_TO",
        "CO_OCCURS_WITH",
        "COLOCALIZES_WITH",
        "COMPENSATED_BY",
        "SUBSTRATE_OF",
        "TRANSPORTS",
        # Evidence / governance
        "SUPPORTS",
        "REFINES",
        "GENERALIZES",
        "INSTANCE_OF",
        "MENTIONS",
        "CITES",
        "HAS_AUTHOR",
        "HAS_KEYWORD",
    },
)

# Synonyms that map to canonical types (from graph_domain_config.py)
_LLM_RELATION_SYNONYMS: dict[str, str] = {
    # ASSOCIATED_WITH
    "ASSOCIATES_WITH": "ASSOCIATED_WITH",
    "LINKED_TO": "ASSOCIATED_WITH",
    "CORRELATED_WITH": "ASSOCIATED_WITH",
    "CORRELATES_WITH": "ASSOCIATED_WITH",
    "RELATED_TO": "ASSOCIATED_WITH",
    "CONNECTED_TO": "ASSOCIATED_WITH",
    "IMPLICATED_IN": "ASSOCIATED_WITH",
    "TIED_TO": "ASSOCIATED_WITH",
    "OBSERVED_IN": "ASSOCIATED_WITH",
    "REPORTED_IN": "ASSOCIATED_WITH",
    # CAUSES
    "LEADS_TO": "CAUSES",
    "RESULTS_IN": "CAUSES",
    "INDUCES": "CAUSES",
    "PRODUCES": "CAUSES",
    "CONTRIBUTES_TO": "CAUSES",
    "CONFERS": "CAUSES",
    "GIVES_RISE_TO": "CAUSES",
    "TRIGGERS": "CAUSES",
    "ELICITS": "CAUSES",
    "DRIVES": "CAUSES",
    "ENGENDERS": "CAUSES",
    # TREATS
    "THERAPEUTIC_FOR": "TREATS",
    "AMELIORATES": "TREATS",
    "ALLEVIATES": "TREATS",
    "USED_TO_TREAT": "TREATS",
    "REVERSES": "TREATS",
    "CURES": "TREATS",
    "MANAGES": "TREATS",
    "MITIGATES": "TREATS",
    "RESOLVES": "TREATS",
    # TARGETS
    "ACTS_ON": "TARGETS",
    "BINDS_TO": "TARGETS",
    "DIRECTED_AT": "TARGETS",
    "ENGAGES": "TARGETS",
    "ATTACKS": "TARGETS",
    "ACTS_AGAINST": "TARGETS",
    # BIOMARKER_FOR
    "PREDICTS": "BIOMARKER_FOR",
    "DIAGNOSTIC_FOR": "BIOMARKER_FOR",
    "PROGNOSTIC_FOR": "BIOMARKER_FOR",
    "INDICATIVE_OF": "BIOMARKER_FOR",
    "MARKER_FOR": "BIOMARKER_FOR",
    "PREDICTOR_OF": "BIOMARKER_FOR",
    "INDICATOR_OF": "BIOMARKER_FOR",
    "READ_OUT_FOR": "BIOMARKER_FOR",
    # PHYSICALLY_INTERACTS_WITH
    "INTERACTS_WITH": "PHYSICALLY_INTERACTS_WITH",
    "BINDS": "PHYSICALLY_INTERACTS_WITH",
    "COMPLEXES_WITH": "PHYSICALLY_INTERACTS_WITH",
    "DIMERIZES_WITH": "PHYSICALLY_INTERACTS_WITH",
    "FORMS_COMPLEX_WITH": "PHYSICALLY_INTERACTS_WITH",
    "INTERACTS_PHYSICALLY_WITH": "PHYSICALLY_INTERACTS_WITH",
    "DOCKS_WITH": "PHYSICALLY_INTERACTS_WITH",
    # ACTIVATES
    "STIMULATES": "ACTIVATES",
    "PROMOTES": "ACTIVATES",
    "ENHANCES": "ACTIVATES",
    "UPREGULATES": "ACTIVATES",
    "INDUCES_EXPRESSION_OF": "ACTIVATES",
    "TURNS_ON": "ACTIVATES",
    "INITIATES": "ACTIVATES",
    "SWITCHES_ON": "ACTIVATES",
    "AUGMENTS": "ACTIVATES",
    # INHIBITS
    "SUPPRESSES": "INHIBITS",
    "REPRESSES": "INHIBITS",
    "BLOCKS": "INHIBITS",
    "DOWNREGULATES": "INHIBITS",
    "ATTENUATES": "INHIBITS",
    "SILENCES": "INHIBITS",
    "DAMPENS": "INHIBITS",
    "ANTAGONIZES": "INHIBITS",
    "ABROGATES": "INHIBITS",
    "ABOLISHES": "INHIBITS",
    # REGULATES
    "MEDIATES": "REGULATES",
    "CONTROLS": "REGULATES",
    "GOVERNS": "REGULATES",
    "MODULATES_ACTIVITY_OF": "MODULATES",
    "INFLUENCES": "REGULATES",
    "ORCHESTRATES": "REGULATES",
    "COORDINATES": "REGULATES",
    # EXPRESSED_IN
    "EXPRESSED_WITHIN": "EXPRESSED_IN",
    "EXPRESSED_BY": "EXPRESSED_IN",
    "SHOWS_EXPRESSION_IN": "EXPRESSED_IN",
    "DETECTED_IN": "EXPRESSED_IN",
    "PRESENT_IN": "EXPRESSED_IN",
    "TRANSCRIBED_IN": "EXPRESSED_IN",
    "ENRICHED_IN": "EXPRESSED_IN",
    "ABUNDANT_IN": "EXPRESSED_IN",
    # PARTICIPATES_IN
    "INVOLVED_IN": "PARTICIPATES_IN",
    "FUNCTIONS_IN": "PARTICIPATES_IN",
    "TAKES_PART_IN": "PARTICIPATES_IN",
    "PLAYS_ROLE_IN": "PARTICIPATES_IN",
    "ACTIVE_IN": "PARTICIPATES_IN",
    "OPERATES_IN": "PARTICIPATES_IN",
    # LOCATED_IN
    "LOCALIZES_TO": "LOCATED_IN",
    "FOUND_IN": "LOCATED_IN",
    "RESIDES_IN": "LOCATED_IN",
    "LOCALIZED_TO": "LOCATED_IN",
    "PRESENT_AT": "LOCATED_IN",
    "SITUATED_IN": "LOCATED_IN",
    "CONFINED_TO": "LOCATED_IN",
    # PREDISPOSES_TO
    "RISK_FACTOR_FOR": "PREDISPOSES_TO",
    "INCREASES_RISK_OF": "PREDISPOSES_TO",
    "SUSCEPTIBILITY_TO": "PREDISPOSES_TO",
    "CONFERS_SUSCEPTIBILITY": "PREDISPOSES_TO",
    "ELEVATES_RISK_OF": "PREDISPOSES_TO",
    "PREDISPOSES": "PREDISPOSES_TO",
    # CO_OCCURS_WITH
    "COINCIDES_WITH": "CO_OCCURS_WITH",
    "COMORBID_WITH": "CO_OCCURS_WITH",
    "CO_PRESENTS_WITH": "CO_OCCURS_WITH",
    "COEXISTS_WITH": "CO_OCCURS_WITH",
    "FOUND_TOGETHER_WITH": "CO_OCCURS_WITH",
    # UPSTREAM_OF / DOWNSTREAM_OF
    "PRECEDES": "UPSTREAM_OF",
    "SIGNALS_TO": "UPSTREAM_OF",
    "FEEDS_INTO": "UPSTREAM_OF",
    "ACTS_BEFORE": "UPSTREAM_OF",
    "FOLLOWS": "DOWNSTREAM_OF",
    "TRIGGERED_BY": "DOWNSTREAM_OF",
    "RECEIVES_SIGNAL_FROM": "DOWNSTREAM_OF",
    "ACTS_AFTER": "DOWNSTREAM_OF",
    # PART_OF / COMPONENT_OF
    "SUBUNIT_OF": "PART_OF",
    "CONTAINED_IN": "PART_OF",
    "MEMBER_OF": "PART_OF",
    "BELONGS_TO": "PART_OF",
    "INCLUDED_IN": "PART_OF",
    "INTEGRAL_PART_OF": "PART_OF",
    "CONSTITUENT_OF": "COMPONENT_OF",
    "ELEMENT_OF": "COMPONENT_OF",
    "BUILDING_BLOCK_OF": "COMPONENT_OF",
    # SENSITIZES_TO
    "INCREASES_SENSITIVITY_TO": "SENSITIZES_TO",
    "CONFERS_SENSITIVITY_TO": "SENSITIZES_TO",
    "RENDERS_SENSITIVE_TO": "SENSITIZES_TO",
    # PHENOCOPY_OF
    "PHENOTYPICALLY_MIMICS": "PHENOCOPY_OF",
    "CLINICALLY_INDISTINGUISHABLE_FROM": "PHENOCOPY_OF",
    "MIMICS": "PHENOCOPY_OF",
    # COLOCALIZES_WITH
    "CO_LOCALIZES_WITH": "COLOCALIZES_WITH",
    "FOUND_WITH": "COLOCALIZES_WITH",
    "CO_EXPRESSED_WITH": "COLOCALIZES_WITH",
    # COMPENSATED_BY
    "RESCUED_BY": "COMPENSATED_BY",
    "FUNCTIONALLY_REPLACED_BY": "COMPENSATED_BY",
    "REDUNDANT_WITH": "COMPENSATED_BY",
    # SUBSTRATE_OF
    "CLEAVED_BY": "SUBSTRATE_OF",
    "PHOSPHORYLATED_BY": "SUBSTRATE_OF",
    "ACTED_UPON_BY": "SUBSTRATE_OF",
    # TRANSPORTS
    "CARRIES": "TRANSPORTS",
    "SHUTTLES": "TRANSPORTS",
    "TRANSLOCATES": "TRANSPORTS",
    "MOVES": "TRANSPORTS",
    "FERRIES": "TRANSPORTS",
    "EXPORTS": "TRANSPORTS",
    "IMPORTS": "TRANSPORTS",
    # MODULATES
    "AFFECTS": "MODULATES",
    "ALTERS": "MODULATES",
    "TUNES": "MODULATES",
    "ADJUSTS": "MODULATES",
    # LOSS_OF_FUNCTION / GAIN_OF_FUNCTION
    "LOF": "LOSS_OF_FUNCTION",
    "ABLATES_FUNCTION_OF": "LOSS_OF_FUNCTION",
    "KNOCKS_OUT": "LOSS_OF_FUNCTION",
    "INACTIVATES": "LOSS_OF_FUNCTION",
    "GOF": "GAIN_OF_FUNCTION",
    "CONFERS_ACTIVITY_TO": "GAIN_OF_FUNCTION",
    "HYPERACTIVATES": "GAIN_OF_FUNCTION",
    "CONSTITUTIVELY_ACTIVATES": "GAIN_OF_FUNCTION",
    # SUPPORTS
    "PROVIDES_EVIDENCE_FOR": "SUPPORTS",
    "BACKS": "SUPPORTS",
    "CORROBORATES": "SUPPORTS",
    "VALIDATES": "SUPPORTS",
    "CONFIRMS": "SUPPORTS",
    "REINFORCES": "SUPPORTS",
    # MENTIONS / CITES
    "REFERENCES": "MENTIONS",
    "DISCUSSES": "MENTIONS",
    "DESCRIBES": "MENTIONS",
    "NOTES": "MENTIONS",
    "REPORTS": "MENTIONS",
    "REFERENCES_PUBLICATION": "CITES",
    "REFERS_TO": "CITES",
    # INSTANCE_OF / REFINES / GENERALIZES
    "EXAMPLE_OF": "INSTANCE_OF",
    "IS_A": "INSTANCE_OF",
    "TYPE_OF": "INSTANCE_OF",
    "KIND_OF": "INSTANCE_OF",
    "NARROWS": "REFINES",
    "SPECIALIZES": "REFINES",
    "BROADENS": "GENERALIZES",
    "ABSTRACTS": "GENERALIZES",
    # HAS_AUTHOR / HAS_KEYWORD
    "AUTHORED_BY": "HAS_AUTHOR",
    "WRITTEN_BY": "HAS_AUTHOR",
    "TAGGED_WITH": "HAS_KEYWORD",
    "INDEXED_AS": "HAS_KEYWORD",
}


def _clean_llm_entity_label(raw: str) -> str:
    """Clean an LLM-generated entity label to a short canonical name."""
    label = raw.strip().strip(".,;:\"'")

    # If it's already short and looks like a proper entity, keep it
    words = label.split()
    if len(words) <= _MAX_ENTITY_LABEL_WORDS:
        return label

    # Try to extract the most entity-like portion
    # Look for gene symbols (all caps, 2-10 chars) or known patterns
    import re

    gene_match = re.search(r"\b([A-Z][A-Z0-9]{1,9}(?:[/-][A-Z0-9]+)?)\b", label)
    if gene_match:
        return gene_match.group(1)

    # Truncate to first 4 meaningful words, skip filler
    filler = {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "in",
        "of",
        "to",
        "for",
        "by",
        "with",
        "from",
        "on",
        "at",
        "is",
        "are",
        "was",
        "were",
        "and",
        "or",
        "whether",
        "order",
        "examine",
        "there",
        "both",
        "its",
    }
    meaningful = [w for w in words if w.lower() not in filler]
    if meaningful:
        return " ".join(meaningful[:4])

    return " ".join(words[:_MAX_ENTITY_LABEL_WORDS])


def build_llm_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build the structured output schema for one LLM extraction pass."""

    class LLMRelation(BaseModel):
        model_config = ConfigDict(strict=True)

        subject: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, 1-4 words "
                "(e.g. BRCA1, cisplatin, EGFR T790M)"
            ),
        )
        relation_type: str = Field(..., min_length=1, max_length=50)
        object: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, 1-4 words "
                "(e.g. TNBC, osimertinib, DNA damage repair)"
            ),
        )
        sentence: str = Field(..., min_length=1, max_length=1000)

    class LLMExtractionResult(BaseModel):
        model_config = ConfigDict(strict=True)

        relations: list[LLMRelation] = Field(
            default_factory=list,
            max_length=max_relations,
        )

    return LLMExtractionResult


def build_proposal_review_output_schema() -> type[BaseModel]:
    """Build the structured output schema for proposal review."""

    class ProposalReviewItem(BaseModel):
        model_config = ConfigDict(strict=True)

        index: int = Field(..., ge=0)
        factual_support: FactualSupportScale
        goal_relevance: GoalRelevanceScale
        priority: PriorityScale
        rationale: str = Field(..., min_length=1, max_length=400)
        factual_rationale: str = Field(..., min_length=1, max_length=240)
        relevance_rationale: str = Field(..., min_length=1, max_length=240)

    class ProposalReviewResult(BaseModel):
        model_config = ConfigDict(strict=True)

        reviews: list[ProposalReviewItem] = Field(default_factory=list)

    return ProposalReviewResult


async def extract_relation_candidates_with_llm(  # noqa: PLR0912, PLR0915
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> list[ExtractedRelationCandidate]:
    """Extract relation candidates using an LLM via ArtanaKernel.

    This function intentionally returns only the LLM-generated candidates.
    Use ``discover_relation_candidates()`` for LLM-first discovery with
    heuristic fallback and diagnostics.
    """
    from uuid import uuid4

    from artana_evidence_api.runtime_support import (
        ModelCapability,
        get_model_registry,
        has_configured_openai_api_key,
    )

    if not has_configured_openai_api_key():
        msg = "OPENAI_API_KEY not configured"
        raise RuntimeError(msg)

    output_schema = build_llm_extraction_output_schema(max_relations)

    # Create kernel components using Evidence API patterns
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter

    model_port = LiteLLMAdapter(timeout_seconds=60.0)
    kernel: ArtanaKernel | None = None
    store = None

    # Resolve model and normalize for LiteLLM (openai:gpt-5.4-mini → openai/gpt-5.4-mini)
    from artana_evidence_api.runtime_support import (
        create_artana_postgres_store,
        normalize_litellm_model_id,
    )

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    model_id = normalize_litellm_model_id(model_spec.model_id)

    tenant = TenantContext(
        tenant_id="research-init-extraction",
        capabilities=frozenset(),
        budget_usd_limit=1.0,
    )

    prompt = (
        f"{_LLM_EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"---\nTEXT TO ANALYZE:\n---\n{text[:4000]}\n---\n\n"
        f"Return the relations as JSON. Remember: subject and object must each be "
        f"a short canonical entity name (1-4 words, like BRCA1, cisplatin, EGFR T790M, TNBC). "
        f"Never use sentence fragments as entity names."
    )
    step_key = _llm_extraction_step_key(
        text=text,
        max_relations=max_relations,
    )

    try:
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        result = await run_single_step_with_policy(
            client,
            run_id=f"research-init-extraction:{uuid4()}",
            tenant=tenant,
            model=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

        output = result.output
        parsed = (
            output
            if isinstance(output, output_schema)
            else output_schema.model_validate(output)
        )

        # Convert to ExtractedRelationCandidate with label cleanup
        candidates: list[ExtractedRelationCandidate] = []
        unknown_relation_types: set[str] = set()

        for rel in parsed.relations:
            relation_type = rel.relation_type.upper().strip().replace(" ", "_")
            # Fast path: deterministic synonym map for well-known aliases
            relation_type = _LLM_RELATION_SYNONYMS.get(relation_type, relation_type)

            subject = _clean_llm_entity_label(rel.subject)
            obj = _clean_llm_entity_label(rel.object)

            # Skip if labels are empty or too generic after cleaning
            if (
                not subject
                or not obj
                or len(subject) < _MIN_ENTITY_LABEL_LENGTH
                or len(obj) < _MIN_ENTITY_LABEL_LENGTH
            ):
                continue

            # Track unknown types for AI resolution
            if relation_type not in _LLM_VALID_RELATION_TYPES:
                unknown_relation_types.add(relation_type)

            candidates.append(
                ExtractedRelationCandidate(
                    subject_label=subject,
                    relation_type=relation_type,
                    object_label=obj,
                    sentence=rel.sentence.strip(),
                ),
            )

        # AI-powered resolution for unknown relation types
        if unknown_relation_types:
            from artana_evidence_api.relation_type_resolver import RelationTypeAction

            try:
                preflight_service = _graph_ai_preflight_service()
                decisions = {
                    candidate: await preflight_service.resolve_relation_type(
                        space_id="llm-extraction",
                        relation_type=candidate,
                        known_types=sorted(_LLM_VALID_RELATION_TYPES),
                        space_context=space_context,
                        domain_context="biomedical",
                    )
                    for candidate in sorted(unknown_relation_types)
                }
                # Apply decisions: replace relation types in candidates
                for i, candidate in enumerate(candidates):
                    key = candidate.relation_type.strip().upper()
                    if key in decisions:
                        decision = decisions[key]
                        if decision.action in (
                            RelationTypeAction.MAP_TO_EXISTING,
                            RelationTypeAction.TYPO_CORRECTION,
                        ):
                            candidates[i] = ExtractedRelationCandidate(
                                subject_label=candidate.subject_label,
                                relation_type=decision.canonical_type,
                                object_label=candidate.object_label,
                                sentence=candidate.sentence,
                            )
                            logger.info(
                                "Relation type resolved: %s → %s (%s)",
                                key,
                                decision.canonical_type,
                                decision.action.value,
                            )
                        else:
                            # register_new: keep the canonical_type (cleaned)
                            candidates[i] = ExtractedRelationCandidate(
                                subject_label=candidate.subject_label,
                                relation_type=decision.canonical_type,
                                object_label=candidate.object_label,
                                sentence=candidate.sentence,
                            )
                            logger.info(
                                "New relation type will be registered: %s",
                                decision.canonical_type,
                            )
            except Exception:
                logger.exception(
                    "AI relation type resolution failed for %s; "
                    "keeping raw types (will resolve at promotion time)",
                    unknown_relation_types,
                )

        if not candidates:
            logger.debug(
                "LLM extraction returned zero usable candidates",
                extra={
                    "model_id": model_id,
                    "text_length": len(text),
                    "raw_relation_count": len(parsed.relations),
                    "usable_candidate_count": 0,
                },
            )
        return candidates
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()


async def discover_relation_candidates(  # noqa: PLR0911
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Discover relation candidates with LLM-first fallback and diagnostics."""
    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return (
            [],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="not_needed",
            ),
        )

    try:
        llm_candidates = await asyncio.wait_for(
            extract_relation_candidates_with_llm(
                normalized_text,
                max_relations=max_relations,
                space_context=space_context,
            ),
            timeout=_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.debug(
            "LLM relation extraction timed out, falling back to regex heuristics",
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
            },
        )
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="fallback_error",
                llm_candidate_error="LLM candidate extraction timed out",
                fallback_candidate_count=len(fallback_candidates),
            ),
        )
    except (ModuleNotFoundError, ImportError) as exc:
        logger.debug(
            "LLM relation extraction unavailable, falling back to regex heuristics: %s",
            str(exc),
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
                "exception_type": type(exc).__name__,
            },
        )
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="unavailable",
                llm_candidate_error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
            ),
        )
    except RuntimeError as exc:
        fallback_candidates = extract_relation_candidates(normalized_text)
        status: Literal["fallback_error", "unavailable"] = (
            "unavailable"
            if "OPENAI_API_KEY not configured" in str(exc)
            else "fallback_error"
        )
        if status == "unavailable":
            logger.debug(
                "LLM relation extraction unavailable, falling back to regex heuristics: %s",
                str(exc),
                extra={
                    "space_context_length": len(space_context),
                    "text_length": len(normalized_text),
                    "exception_type": type(exc).__name__,
                },
            )
        else:
            logger.warning(
                "LLM relation extraction failed, falling back to regex: %s",
                str(exc),
                extra={
                    "space_context_length": len(space_context),
                    "text_length": len(normalized_text),
                    "exception_type": type(exc).__name__,
                },
            )
        return (
            fallback_candidates,
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status=status,
                llm_candidate_error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM relation extraction failed, falling back to regex: %s",
            str(exc),
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
                "exception_type": type(exc).__name__,
            },
        )
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="fallback_error",
                llm_candidate_error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
            ),
        )

    if llm_candidates:
        return (
            llm_candidates,
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=len(llm_candidates),
            ),
        )

    fallback_candidates = extract_relation_candidates(normalized_text)
    return (
        fallback_candidates,
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="llm_empty",
            llm_candidate_error="LLM succeeded but returned zero usable candidates",
            fallback_candidate_count=len(fallback_candidates),
        ),
    )


async def extract_relation_candidates_with_diagnostics(
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Extract relation candidates with LLM-first fallback diagnostics."""
    return await discover_relation_candidates(
        text,
        max_relations=max_relations,
        space_context=space_context,
    )


_DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT = """You review extracted scientific claims for manual curation inside a research space.

Assess each claim on three categorical scales only. Never invent numbers.

1. factual_support
- strong: the quoted source sentence directly and clearly supports the claim as stated
- moderate: the claim is mostly supported, but the wording is broader or slightly stronger than the source
- tentative: the source is hedged, ambiguous, indirect, or only weakly supports the claim
- unsupported: the extracted claim is not actually supported by the provided source text

2. goal_relevance
- direct: tightly aligned with the active research objective, hypotheses, or pending questions
- supporting: useful supporting context for the current research direction
- peripheral: scientifically related but not central to the current research direction
- off_target: not meaningfully aligned with the current research direction
- unscoped: there is not enough active research-goal context to judge relevance

3. priority
- prioritize: strong candidate for immediate review in this space
- review: worth reviewing, but not top priority
- background: keep as background context only
- ignore: do not prioritize for this space

Important rules:
- factual_support and goal_relevance are independent; a strong fact can still be peripheral or off_target
- if there is no meaningful research-goal context, use goal_relevance=unscoped
- do not use outside world knowledge; judge only from the provided claim excerpt and research-space context
- keep rationales concise and specific
"""


def build_document_review_context(
    *,
    objective: str | None = None,
    current_hypotheses: list[str] | tuple[str, ...] | None = None,
    pending_questions: list[str] | tuple[str, ...] | None = None,
    explored_questions: list[str] | tuple[str, ...] | None = None,
) -> DocumentExtractionReviewContext:
    """Normalize research-goal context for document proposal review."""
    return DocumentExtractionReviewContext(
        objective=_normalized_optional_text(objective),
        current_hypotheses=_normalized_text_tuple(current_hypotheses),
        pending_questions=_normalized_text_tuple(pending_questions),
        explored_questions=_normalized_text_tuple(explored_questions),
    )


def _normalized_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized or None


def _normalized_text_tuple(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = _normalized_optional_text(value)
        if normalized is None or normalized.casefold() in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized.casefold())
    return tuple(normalized_values)


def _shorten_text(value: str, *, max_length: int) -> str:
    normalized = " ".join(value.split()).strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def _has_goal_context(review_context: DocumentExtractionReviewContext) -> bool:
    return any(
        (
            review_context.objective,
            review_context.current_hypotheses,
            review_context.pending_questions,
            review_context.explored_questions,
        ),
    )


def _goal_context_summary(review_context: DocumentExtractionReviewContext) -> str:
    lines: list[str] = []
    if review_context.objective is not None:
        lines.append(
            f"Objective: {_shorten_text(review_context.objective, max_length=400)}",
        )
    if review_context.current_hypotheses:
        lines.append(
            "Current hypotheses: "
            + "; ".join(
                _shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.current_hypotheses[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if review_context.pending_questions:
        lines.append(
            "Pending questions: "
            + "; ".join(
                _shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.pending_questions[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if review_context.explored_questions:
        lines.append(
            "Explored questions: "
            + "; ".join(
                _shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.explored_questions[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if not lines:
        return "No active research objective, hypothesis, or question context is available."
    return "\n".join(lines)


def _goal_context_tokens(
    review_context: DocumentExtractionReviewContext,
) -> set[str]:
    tokens: set[str] = set()
    values = (review_context.objective,) if review_context.objective is not None else ()
    for value in (
        *values,
        *review_context.current_hypotheses,
        *review_context.pending_questions,
        *review_context.explored_questions,
    ):
        for token in _TOKEN_RE.findall(value.casefold()):
            if (
                len(token) < _MIN_GOAL_CONTEXT_TOKEN_LENGTH
                or token in _COMMON_CONTEXT_STOPWORDS
            ):
                continue
            tokens.add(token)
    return tokens


def _derive_priority_scale(
    *,
    factual_support: FactualSupportScale,
    goal_relevance: GoalRelevanceScale,
) -> PriorityScale:
    direct_goal_priority: dict[FactualSupportScale, PriorityScale] = {
        "strong": "prioritize",
        "moderate": "review",
        "tentative": "background",
        "unsupported": "ignore",
    }
    if factual_support == "unsupported":
        return "ignore"
    if goal_relevance == "off_target":
        return "background" if factual_support == "strong" else "ignore"
    if goal_relevance == "direct":
        return direct_goal_priority[factual_support]
    if goal_relevance in {"supporting", "unscoped"}:
        return "review" if factual_support in {"strong", "moderate"} else "background"
    return "background"


def _build_fallback_document_review(
    *,
    candidate: ExtractedRelationCandidate,
    review_context: DocumentExtractionReviewContext,
) -> DocumentProposalReview:
    normalized_sentence = f" {candidate.sentence.casefold()} "
    if any(marker in normalized_sentence for marker in _FACTUAL_HEDGE_MARKERS):
        factual_support: FactualSupportScale = "tentative"
        factual_rationale = (
            "The source sentence uses hedged or indirect language, so the claim "
            "should be treated cautiously."
        )
    elif candidate.relation_type == "ASSOCIATED_WITH":
        factual_support = "moderate"
        factual_rationale = (
            "The source sentence states an association, but the extracted claim "
            "should remain below strong support by default."
        )
    else:
        factual_support = "strong"
        factual_rationale = (
            "The source sentence states the extracted relation directly and without "
            "obvious hedging language."
        )

    goal_tokens = _goal_context_tokens(review_context)
    if not goal_tokens:
        goal_relevance: GoalRelevanceScale = "unscoped"
        relevance_rationale = (
            "No active research objective or question context is available, so goal "
            "relevance cannot be judged precisely."
        )
    else:
        candidate_tokens = {
            token
            for token in _TOKEN_RE.findall(
                (
                    f"{candidate.subject_label} {candidate.relation_type} "
                    f"{candidate.object_label} {candidate.sentence}"
                ).casefold(),
            )
            if (
                len(token) >= _MIN_GOAL_CONTEXT_TOKEN_LENGTH
                and token not in _COMMON_CONTEXT_STOPWORDS
            )
        }
        overlap_count = len(goal_tokens & candidate_tokens)
        if overlap_count >= _DIRECT_GOAL_TOKEN_OVERLAP_MIN:
            goal_relevance = "direct"
            relevance_rationale = (
                "The extracted claim shares multiple core terms with the current "
                "research goal context."
            )
        elif overlap_count >= 1:
            goal_relevance = "supporting"
            relevance_rationale = (
                "The extracted claim overlaps with at least part of the current "
                "research goal context."
            )
        else:
            goal_relevance = "peripheral"
            relevance_rationale = (
                "The extracted claim appears scientifically related, but it does not "
                "overlap clearly with the current research goal context."
            )

    priority = _derive_priority_scale(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
    )
    rationale = (
        f"Factual support is {factual_support}; goal relevance is {goal_relevance}; "
        f"manual-review priority is {priority}."
    )
    return DocumentProposalReview(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
        priority=priority,
        rationale=rationale,
        factual_rationale=factual_rationale,
        relevance_rationale=relevance_rationale,
        method="heuristic_fallback_v1",
    )


def _apply_document_proposal_review(
    *,
    draft: HarnessProposalDraft,
    review: DocumentProposalReview,
    review_context: DocumentExtractionReviewContext,
) -> HarnessProposalDraft:
    factual_score = _FACTUAL_SUPPORT_SCORES[review.factual_support]
    relevance_score = _GOAL_RELEVANCE_SCORES[review.goal_relevance]
    priority_score = _PRIORITY_SCORES[review.priority]
    ranking = rank_reviewed_candidate_claim(
        factual_confidence=factual_score,
        goal_relevance=relevance_score,
        priority=priority_score,
        supporting_document_count=1,
        evidence_reference_count=1,
    )
    proposal_review_metadata: JSONObject = {
        "scale_version": "v1",
        "method": review.method,
        "factual_support": review.factual_support,
        "goal_relevance": review.goal_relevance,
        "priority": review.priority,
        "rationale": review.rationale,
        "factual_rationale": review.factual_rationale,
        "relevance_rationale": review.relevance_rationale,
        "goal_context_summary": _goal_context_summary(review_context),
    }
    if review.model_id is not None:
        proposal_review_metadata["model_id"] = review.model_id
    updated_evidence_bundle = [
        {
            **item,
            "relevance": relevance_score,
        }
        for item in draft.evidence_bundle
    ]
    return replace(
        draft,
        confidence=factual_score,
        ranking_score=ranking.score,
        reasoning_path={
            **draft.reasoning_path,
            "proposal_review": {
                "factual_support": review.factual_support,
                "goal_relevance": review.goal_relevance,
                "priority": review.priority,
                "rationale": review.rationale,
            },
        },
        evidence_bundle=updated_evidence_bundle,
        metadata={
            **draft.metadata,
            **ranking.metadata,
            "proposal_review": proposal_review_metadata,
        },
    )


def _review_from_draft_metadata(
    draft: HarnessProposalDraft,
) -> DocumentProposalReview | None:
    review_payload = draft.metadata.get("proposal_review")
    if not isinstance(review_payload, dict):
        return None
    factual_support = review_payload.get("factual_support")
    goal_relevance = review_payload.get("goal_relevance")
    priority = review_payload.get("priority")
    rationale = review_payload.get("rationale")
    factual_rationale = review_payload.get("factual_rationale")
    relevance_rationale = review_payload.get("relevance_rationale")
    method = review_payload.get("method")
    model_id = review_payload.get("model_id")
    valid_factual_values = set(_FACTUAL_SUPPORT_SCORES)
    valid_relevance_values = set(_GOAL_RELEVANCE_SCORES)
    valid_priority_values = set(_PRIORITY_SCORES)
    if (
        factual_support not in valid_factual_values
        or goal_relevance not in valid_relevance_values
        or priority not in valid_priority_values
        or not isinstance(rationale, str)
        or not isinstance(factual_rationale, str)
        or not isinstance(relevance_rationale, str)
        or not isinstance(method, str)
    ):
        return None
    return DocumentProposalReview(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
        priority=priority,
        rationale=rationale,
        factual_rationale=factual_rationale,
        relevance_rationale=relevance_rationale,
        method=method,
        model_id=model_id if isinstance(model_id, str) else None,
    )


async def review_document_extraction_drafts_with_diagnostics(  # noqa: PLR0912, PLR0915
    *,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    drafts: tuple[HarnessProposalDraft, ...],
    review_context: DocumentExtractionReviewContext | None = None,
) -> tuple[tuple[HarnessProposalDraft, ...], DocumentProposalReviewDiagnostics]:
    """Apply an LLM review pass to extracted document proposals when available."""
    if not drafts:
        return (
            drafts,
            DocumentProposalReviewDiagnostics(llm_review_status="not_needed"),
        )

    normalized_context = review_context or build_document_review_context()
    fallback_reviews: list[DocumentProposalReview] = []
    for index, draft in enumerate(drafts):
        existing_review = _review_from_draft_metadata(draft)
        if existing_review is not None:
            fallback_reviews.append(existing_review)
            continue
        if candidates:
            candidate = candidates[min(index, len(candidates) - 1)]
            fallback_reviews.append(
                _build_fallback_document_review(
                    candidate=candidate,
                    review_context=normalized_context,
                ),
            )
            continue
        fallback_reviews.append(
            DocumentProposalReview(
                factual_support="moderate",
                goal_relevance="unscoped",
                priority="review",
                rationale=(
                    "A fallback review was applied because no extracted candidate "
                    "context was available."
                ),
                factual_rationale=(
                    "The proposal was preserved for manual review without a richer "
                    "candidate-level confidence analysis."
                ),
                relevance_rationale=(
                    "Goal relevance could not be reviewed precisely for this "
                    "proposal."
                ),
                method="heuristic_fallback_v1",
            ),
        )

    def _apply_fallback_reviews() -> tuple[HarnessProposalDraft, ...]:
        return tuple(
            _apply_document_proposal_review(
                draft=draft,
                review=fallback_reviews[index],
                review_context=normalized_context,
            )
            for index, draft in enumerate(drafts)
        )

    try:
        from artana.agent import SingleStepModelClient
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter
        from artana_evidence_api.runtime_support import (
            ModelCapability,
            get_model_registry,
            has_configured_openai_api_key,
            normalize_litellm_model_id,
        )

    except Exception as exc:  # noqa: BLE001
        return (
            _apply_fallback_reviews(),
            DocumentProposalReviewDiagnostics(
                llm_review_status="unavailable",
                llm_review_error=str(exc),
            ),
        )

    if not has_configured_openai_api_key():
        return (
            _apply_fallback_reviews(),
            DocumentProposalReviewDiagnostics(
                llm_review_status="unavailable",
                llm_review_error="OPENAI_API_KEY not configured",
            ),
        )

    output_schema = build_proposal_review_output_schema()

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.JUDGE)
    model_id = normalize_litellm_model_id(model_spec.model_id)
    claim_blocks: list[str] = []
    for index, draft in enumerate(drafts):
        subject_label = draft.metadata.get(
            "resolved_subject_label",
        ) or draft.metadata.get(
            "subject_label",
        )
        object_label = draft.metadata.get(
            "resolved_object_label",
        ) or draft.metadata.get(
            "object_label",
        )
        relation_type = draft.payload.get("proposed_claim_type")
        claim_blocks.append(
            "\n".join(
                [
                    f"Claim {index}",
                    f"- subject: {subject_label}",
                    f"- relation_type: {relation_type}",
                    f"- object: {object_label}",
                    f"- excerpt: {_shorten_text(draft.summary, max_length=500)}",
                ],
            ),
        )
    claims_text = "\n\n".join(claim_blocks)
    goal_context = _goal_context_summary(normalized_context)
    prompt = (
        f"{_DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT}\n\n"
        f"RESEARCH SPACE CONTEXT\n{goal_context}\n\n"
        f"DOCUMENT\n"
        f"- title: {_shorten_text(document.title, max_length=200)}\n"
        f"- source_type: {document.source_type}\n\n"
        f"CLAIMS TO REVIEW\n{claims_text}\n\n"
        "Return one review for each claim index."
    )
    step_key = _proposal_review_step_key(
        document=document,
        claims_text=claims_text,
        goal_context_summary=goal_context,
    )

    from uuid import uuid4

    kernel: ArtanaKernel | None = None
    store = None
    tenant = TenantContext(
        tenant_id=f"document-proposal-review:{document.space_id}",
        capabilities=frozenset(),
        budget_usd_limit=1.0,
    )
    try:
        from artana_evidence_api.runtime_support import create_artana_postgres_store

        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=60.0),
        )
        client = SingleStepModelClient(kernel=kernel)
        result = await asyncio.wait_for(
            run_single_step_with_policy(
                client,
                run_id=f"document-proposal-review:{uuid4()}",
                tenant=tenant,
                model=model_id,
                prompt=prompt,
                output_schema=output_schema,
                step_key=step_key,
                replay_policy="fork_on_drift",
            ),
            timeout=_LLM_PROPOSAL_REVIEW_TIMEOUT_SECONDS,
        )
        output = result.output
        parsed = (
            output
            if isinstance(output, output_schema)
            else output_schema.model_validate(output)
        )
        reviews_by_index = {
            item.index: DocumentProposalReview(
                factual_support=item.factual_support,
                goal_relevance=item.goal_relevance,
                priority=item.priority,
                rationale=item.rationale.strip(),
                factual_rationale=item.factual_rationale.strip(),
                relevance_rationale=item.relevance_rationale.strip(),
                method="llm_judge_v1",
                model_id=model_spec.model_id,
            )
            for item in parsed.reviews
            if 0 <= item.index < len(drafts)
        }
    except TimeoutError:
        reviews_by_index = {}
        diagnostics = DocumentProposalReviewDiagnostics(
            llm_review_status="fallback_error",
            llm_review_error="LLM proposal review timed out",
        )
    except Exception as exc:  # noqa: BLE001
        reviews_by_index = {}
        diagnostics = DocumentProposalReviewDiagnostics(
            llm_review_status="fallback_error",
            llm_review_error=str(exc),
        )
    else:
        diagnostics = DocumentProposalReviewDiagnostics(llm_review_status="completed")
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()

    return (
        tuple(
            _apply_document_proposal_review(
                draft=draft,
                review=reviews_by_index.get(index, fallback_reviews[index]),
                review_context=normalized_context,
            )
            for index, draft in enumerate(drafts)
        ),
        diagnostics,
    )


async def review_document_extraction_drafts(  # noqa: PLR0915
    *,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    drafts: tuple[HarnessProposalDraft, ...],
    review_context: DocumentExtractionReviewContext | None = None,
) -> tuple[HarnessProposalDraft, ...]:
    """Apply an LLM review pass to extracted document proposals when available."""
    reviewed_drafts, _ = await review_document_extraction_drafts_with_diagnostics(
        document=document,
        candidates=candidates,
        drafts=drafts,
        review_context=review_context,
    )
    return reviewed_drafts


def _clean_candidate_label(
    raw_label: str,
    *,
    prefer_tail: bool = False,
) -> str:
    label = " ".join(raw_label.split()).strip(" .,:;")
    if prefer_tail:
        label = label.split(",")[-1].strip()
        for marker in _SUBJECT_CONTEXT_MARKERS:
            normalized_label = label.casefold()
            marker_index = normalized_label.rfind(marker.strip())
            if marker_index == -1:
                continue
            candidate_label = label[marker_index + len(marker.strip()) :].strip()
            if candidate_label != "":
                label = candidate_label
                break
    label = _LEADING_FILLER_RE.sub("", label)
    for prefix in _ENTITY_LABEL_PREFIXES:
        if label.casefold().startswith(prefix):
            label = label[len(prefix) :].strip()
            break
    label = _TRAILING_CONTEXT_RE.sub("", label).strip()
    return _PARENTHETICAL_SUFFIX_RE.sub("", label).strip(" .,:;")


def _split_compound_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> tuple[str, ...]:
    base_label = _clean_candidate_label(label)
    segments, contains_comma, contains_conjunction = _segment_compound_label(label)
    cleaned_segments: list[str] = []
    seen_labels: set[str] = set()
    for segment in segments:
        cleaned_segment = _clean_candidate_label(segment)
        if cleaned_segment == "":
            continue
        normalized_segment = cleaned_segment.casefold()
        if normalized_segment in seen_labels:
            continue
        seen_labels.add(normalized_segment)
        cleaned_segments.append(cleaned_segment)
    if len(cleaned_segments) <= 1:
        if base_label != "":
            return (base_label,)
        return tuple(cleaned_segments)
    if contains_comma:
        return tuple(cleaned_segments)
    if contains_conjunction and (
        all(
            _token_count(segment) >= _MIN_COMPOUND_SEGMENT_TOKEN_COUNT
            for segment in cleaned_segments
        )
        or _count_exact_entity_matches(
            space_id=space_id,
            labels=cleaned_segments,
            graph_api_gateway=graph_api_gateway,
        )
        >= _MIN_EXACT_SPLIT_MATCH_COUNT
    ):
        return tuple(cleaned_segments)
    if base_label != "":
        return (base_label,)
    return tuple(cleaned_segments)


def _segment_compound_label(label: str) -> tuple[list[str], bool, bool]:
    segments: list[str] = []
    current: list[str] = []
    parentheses_depth = 0
    contains_comma = False
    contains_conjunction = False
    index = 0
    while index < len(label):
        character = label[index]
        if character == "(":
            parentheses_depth += 1
            current.append(character)
            index += 1
            continue
        if character == ")":
            parentheses_depth = max(0, parentheses_depth - 1)
            current.append(character)
            index += 1
            continue
        if parentheses_depth == 0 and character == ",":
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_comma = True
            index += 1
            continue
        normalized_tail = label[index:].casefold()
        if parentheses_depth == 0 and normalized_tail.startswith(" and "):
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_conjunction = True
            index += len(" and ")
            continue
        if parentheses_depth == 0 and normalized_tail.startswith(" or "):
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_conjunction = True
            index += len(" or ")
            continue
        current.append(character)
        index += 1
    final_segment = "".join(current).strip()
    if final_segment != "":
        segments.append(final_segment)
    return segments, contains_comma, contains_conjunction


def _token_count(label: str) -> int:
    return len([token for token in label.split() if token != ""])


def _count_exact_entity_matches(
    *,
    space_id: UUID,
    labels: list[str],
    graph_api_gateway: GraphTransportBundle,
) -> int:
    return sum(
        1
        for label in labels
        if _resolve_exact_entity_label(
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        is not None
    )


def summarize_document_context(
    *,
    documents: tuple[HarnessDocumentRecord, ...],
    proposals_by_document_id: dict[str, list[JSONObject]],
) -> str | None:
    """Build a compact answer supplement for document-backed chat context."""
    if not documents:
        return None
    lines = ["Referenced document context:"]
    for document in documents:
        proposal_summaries = proposals_by_document_id.get(document.id, [])
        lines.append(
            f"- {document.title} [{document.source_type}] "
            f"({len(proposal_summaries)} staged proposal(s))",
        )
        for proposal_summary in proposal_summaries[:3]:
            summary = proposal_summary.get("summary")
            if isinstance(summary, str) and summary.strip() != "":
                lines.append(f"  - {summary.strip()}")
    return "\n".join(lines)


def build_document_extraction_drafts(
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    graph_api_gateway: GraphTransportBundle,
    review_context: DocumentExtractionReviewContext | None = None,
    ai_resolved_entities: dict[str, JSONObject] | None = None,
) -> tuple[tuple[HarnessProposalDraft, ...], list[JSONObject]]:
    """Resolve extracted document relations into staged harness proposals.

    Parameters
    ----------
    ai_resolved_entities:
        Optional mapping from ``label.casefold()`` → entity dict, produced by
        ``pre_resolve_entities_with_ai``.  When provided, AI-resolved matches
        take priority over deterministic substring matching.
    """
    drafts: list[HarnessProposalDraft] = []
    skipped_candidates: list[JSONObject] = []
    normalized_review_context = review_context or build_document_review_context()
    for index, candidate in enumerate(candidates):
        subject_match = _resolve_entity_label(
            space_id=space_id,
            label=candidate.subject_label,
            graph_api_gateway=graph_api_gateway,
            ai_resolved_entities=ai_resolved_entities,
        )
        subject_id = (
            _require_match_id(subject_match)
            if subject_match is not None
            else _build_unresolved_entity_id(candidate.subject_label)
        )
        resolved_subject_label = (
            candidate.subject_label
            if subject_match is None
            else _require_match_display_label(subject_match)
        )
        object_labels = _split_compound_entity_label(
            space_id=space_id,
            label=candidate.object_label,
            graph_api_gateway=graph_api_gateway,
        )
        for object_index, object_label in enumerate(object_labels):
            object_match = _resolve_entity_label(
                space_id=space_id,
                label=object_label,
                graph_api_gateway=graph_api_gateway,
                ai_resolved_entities=ai_resolved_entities,
            )
            object_id = (
                _require_match_id(object_match)
                if object_match is not None
                else _build_unresolved_entity_id(object_label)
            )
            resolved_object_label = (
                object_label
                if object_match is None
                else _require_match_display_label(object_match)
            )
            review = _build_fallback_document_review(
                candidate=ExtractedRelationCandidate(
                    subject_label=candidate.subject_label,
                    relation_type=candidate.relation_type,
                    object_label=object_label,
                    sentence=candidate.sentence,
                ),
                review_context=normalized_review_context,
            )
            split_applied = len(object_labels) > 1
            source_key = (
                f"{document.id}:{index}"
                if not split_applied
                else f"{document.id}:{index}:{object_index}"
            )
            claim_fingerprint = compute_claim_fingerprint(
                resolved_subject_label,
                candidate.relation_type,
                resolved_object_label,
            )
            drafts.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="document_extraction",
                    source_key=source_key,
                    document_id=document.id,
                    title=(
                        f"Extracted claim: {resolved_subject_label} "
                        f"{candidate.relation_type} {resolved_object_label}"
                    ),
                    summary=candidate.sentence,
                    confidence=0.5,
                    ranking_score=0.5,
                    reasoning_path={
                        "document_id": document.id,
                        "document_title": document.title,
                        "sentence": candidate.sentence,
                        "resolution_method": (
                            "graph_entity_search"
                            if subject_match is not None and object_match is not None
                            else "deferred_entity_resolution"
                        ),
                        "subject_label": candidate.subject_label,
                        "object_label": object_label,
                        "original_object_label": candidate.object_label,
                    },
                    evidence_bundle=[
                        {
                            "source_type": "paper",
                            "locator": f"document:{document.id}",
                            "excerpt": candidate.sentence,
                            "relevance": 0.5,
                        },
                    ],
                    payload={
                        "proposed_subject": subject_id,
                        "proposed_subject_label": candidate.subject_label,
                        "proposed_claim_type": candidate.relation_type,
                        "proposed_object": object_id,
                        "proposed_object_label": object_label,
                        "evidence_entity_ids": [
                            entity_id
                            for entity_id in (subject_id, object_id)
                            if not entity_id.startswith("unresolved:")
                        ],
                    },
                    metadata={
                        "document_id": document.id,
                        "document_title": document.title,
                        "document_source_type": document.source_type,
                        "subject_label": candidate.subject_label,
                        "object_label": object_label,
                        "original_object_label": candidate.object_label,
                        "resolved_subject_label": resolved_subject_label,
                        "resolved_object_label": resolved_object_label,
                        "subject_resolved": subject_match is not None,
                        "object_resolved": object_match is not None,
                        "object_split_applied": split_applied,
                        "origin": "document_extraction",
                    },
                    claim_fingerprint=claim_fingerprint,
                ),
            )
            drafts[-1] = _apply_document_proposal_review(
                draft=drafts[-1],
                review=review,
                review_context=normalized_review_context,
            )
    return tuple(drafts), skipped_candidates


def _require_match_id(match: JSONObject) -> str:
    entity_id = match.get("id")
    if isinstance(entity_id, str) and entity_id.strip() != "":
        return entity_id
    message = "Resolved graph entity match is missing an id"
    raise ValueError(message)


def _require_match_display_label(match: JSONObject) -> str:
    display_label = match.get("display_label")
    if isinstance(display_label, str) and display_label.strip() != "":
        return display_label
    return _require_match_id(match)


def _build_unresolved_entity_id(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return f"unresolved:{normalized or 'entity'}"


def resolve_graph_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    return _graph_ai_preflight_service().resolve_entity_label(
        space_id=space_id,
        label=label,
        graph_transport=graph_api_gateway,
    )


def _resolve_exact_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    try:
        response = graph_api_gateway.list_entities(
            space_id=space_id,
            q=label,
            limit=5,
        )
    except GraphServiceClientError:
        return None
    normalized_label = label.strip().casefold()
    for entity in response.entities:
        display_label = entity.display_label or ""
        aliases = entity.aliases
        exact_aliases = {alias.casefold() for alias in aliases}
        if (
            display_label.casefold() == normalized_label
            or normalized_label in exact_aliases
        ):
            return {
                "id": str(entity.id),
                "display_label": display_label or str(entity.id),
            }
    return None


def _resolve_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    ai_resolved_entities: dict[str, JSONObject] | None = None,
) -> JSONObject | None:
    """Resolve entity label, checking AI pre-resolution cache first."""
    # If AI pre-resolution already resolved this label, use that result
    if ai_resolved_entities is not None:
        cache_key = label.strip().casefold()
        if cache_key in ai_resolved_entities:
            return ai_resolved_entities[cache_key]

    return resolve_graph_entity_label(
        space_id=space_id,
        label=label,
        graph_api_gateway=graph_api_gateway,
    )


async def _resolve_entity_label_with_ai(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    space_context: str = "",
) -> JSONObject | None:
    return await _graph_ai_preflight_service().resolve_entity_label_with_ai(
        space_id=space_id,
        label=label,
        graph_transport=graph_api_gateway,
        space_context=space_context,
    )


async def pre_resolve_entities_with_ai(
    *,
    space_id: UUID,
    candidates: list[ExtractedRelationCandidate],
    graph_api_gateway: GraphTransportBundle,
    space_context: str = "",
) -> dict[str, JSONObject]:
    """Pre-resolve entity labels using AI before building proposals.

    Collects all unique entity labels from extraction candidates, runs them
    through the AI entity resolver, and returns a mapping from
    ``label.casefold()`` → ``{"id": ..., "display_label": ...}`` for labels
    that matched existing entities.

    Labels that should be created as new entities are NOT included in the
    result (so the caller falls through to the standard
    ``_build_unresolved_entity_id`` path).

    Call this BEFORE ``build_document_extraction_drafts`` and pass the result
    as ``ai_resolved_entities``.
    """
    import logging

    _logger = logging.getLogger(__name__)
    resolved: dict[str, JSONObject] = {}
    # Preserve first-seen order so the bounded AI budget is spent on the
    # earliest extraction labels instead of an arbitrary set iteration order.
    ordered_labels: list[str] = []
    seen_labels: set[str] = set()
    for candidate in candidates:
        for label in (candidate.subject_label, candidate.object_label):
            normalized_label = label.strip()
            if normalized_label == "":
                continue
            cache_key = normalized_label.casefold()
            if cache_key in seen_labels:
                continue
            seen_labels.add(cache_key)
            ordered_labels.append(normalized_label)

    ai_attempted_labels = 0
    ai_budget_exhausted = False

    for label in ordered_labels:
        # Skip labels that already resolve deterministically (exact match)
        deterministic = await asyncio.to_thread(
            _resolve_exact_entity_label,
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        if deterministic is not None:
            resolved[label.strip().casefold()] = deterministic
            continue

        if ai_attempted_labels >= _MAX_AI_ENTITY_PRE_RESOLUTION_LABELS:
            ai_budget_exhausted = True
            continue

        # Use AI resolution
        try:
            ai_attempted_labels += 1
            ai_result = await asyncio.wait_for(
                _resolve_entity_label_with_ai(
                    space_id=space_id,
                    label=label,
                    graph_api_gateway=graph_api_gateway,
                    space_context=space_context,
                ),
                timeout=_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS,
            )
            if ai_result is not None:
                resolved[label.strip().casefold()] = ai_result
                _logger.info(
                    "AI entity resolution: '%s' → '%s' (id=%s)",
                    label,
                    ai_result.get("display_label"),
                    ai_result.get("id"),
                )
        except TimeoutError:
            _logger.debug(
                "AI entity resolution timed out for '%s'; falling back to "
                "deterministic/unresolved handling",
                label,
            )
        except Exception:
            _logger.exception(
                "AI entity resolution failed for '%s', falling back to "
                "deterministic resolution",
                label,
            )

    if ai_budget_exhausted:
        _logger.info(
            "AI entity pre-resolution budget exhausted after %d labels; "
            "remaining labels will use deterministic/unresolved handling",
            _MAX_AI_ENTITY_PRE_RESOLUTION_LABELS,
        )

    return resolved


__all__ = [
    "DocumentCandidateExtractionDiagnostics",
    "DocumentTextExtraction",
    "DocumentExtractionReviewContext",
    "DocumentProposalReviewDiagnostics",
    "ExtractedRelationCandidate",
    "build_document_review_context",
    "build_document_extraction_drafts",
    "build_llm_extraction_output_schema",
    "build_proposal_review_output_schema",
    "discover_relation_candidates",
    "extract_pdf_text",
    "extract_relation_candidates",
    "extract_relation_candidates_with_diagnostics",
    "normalize_text_document",
    "pre_resolve_entities_with_ai",
    "review_document_extraction_drafts",
    "review_document_extraction_drafts_with_diagnostics",
    "resolve_graph_entity_label",
    "sha256_hex",
    "summarize_document_context",
]
