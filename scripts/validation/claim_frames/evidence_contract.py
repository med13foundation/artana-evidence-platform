"""Closed categories and field rules for claim-frame execution evidence."""

from __future__ import annotations

import re
from typing import Final, Literal

ATTEMPT_OUTCOMES: Final = frozenset(
    {
        "accepted",
        "schema_invalid",
        "semantic_invalid",
        "invocation_failed",
        "intentionally_skipped",
    },
)
ATTEMPT_ROLES: Final = frozenset(
    {
        "primary",
        "weak_review",
        "schema_retry",
        "zero_candidate_retry",
        "proposal_review",
        "claim_inventory",
        "claim_inventory_completeness",
        "claim_inventory_recovery",
        "claim_framing",
    },
)
PASS_ROLES: Final = frozenset(
    {
        "primary",
        "weak_review",
        "proposal_review",
        "claim_inventory",
        "claim_inventory_completeness",
        "claim_inventory_recovery",
        "claim_framing",
    }
)
DIAGNOSTIC_STATUSES: Final = frozenset(
    {
        "not_needed",
        "completed",
        "llm_empty",
        "fallback",
        "fallback_error",
        "unavailable",
        "semantic_incomplete",
    },
)
ROUTING_STATUSES: Final = frozenset(
    {"not_run", "complete", "candidate_overflow", "semantic_incomplete"},
)
FALLBACK_STATUSES: Final = frozenset(
    {"fallback", "fallback_error", "unavailable"},
)

SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE: Final = re.compile(r"^[0-9a-f]{40}$")
MIN_TYPED_ARGUMENTS: Final = 2
MIN_MULTI_FRAME_RELATIONS: Final = 2
NUMERIC_LEXEM_RE: Final = re.compile(
    r"^[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?$",
)
FALLBACK_MARKER_KEYS: Final = frozenset(
    {"fallback_output_used", "fallback_used", "used_fallback"},
)
FALLBACK_PROVENANCE_KEYS: Final = frozenset(
    {
        "extraction_method",
        "verification_method",
        "producer",
        "provenance",
        "source_method",
    },
)
QUALIFIER_FIELD_KEYS: Final = frozenset(
    {
        "biological_or_variant_state",
        "condition",
        "population",
        "intervention",
        "comparator",
        "outcome",
        "study_design",
        "treatment_setting",
        "timeframe",
        "threshold",
    },
)
FALLBACK_PROVENANCE_RE: Final = re.compile(r"(?:fallback|heuristic)", re.IGNORECASE)
SOURCE_EVIDENCE_CONTAINER_KEYS: Final = frozenset({"evidence", "source_evidence"})
SOURCE_EVIDENCE_FIELD_KEYS: Final = frozenset(
    {
        "exact_span",
        "evidence_span",
        "sentence",
        "source_span",
        "span",
    },
)
SOURCE_CITATION_FIELD_KEYS: Final = frozenset(
    {"citation", "citations", "doi", "locator", "pmid", "source_locator"},
)
QUALIFIER_SOURCE_FIELD_KEYS: Final = frozenset(
    {"evidence_span", "exact_span", "span", "value"},
)
SOURCE_MEASUREMENT_CONTAINER_KEYS: Final = frozenset(
    {"source_measurement", "source_measurements"},
)
SOURCE_MEASUREMENT_FIELD_KEYS: Final = frozenset(
    {
        "field_name",
        "literal_span",
        "source_hash",
        "source_locator",
        "unit",
        "value",
    },
)
SOURCE_MEASUREMENT_NUMERIC_FIELD_KEYS: Final = frozenset(
    {"literal_span", "value"},
)
INVENTORY_SOURCE_FIELD_KEYS: Final = frozenset(
    {
        "endpoint_a_span",
        "endpoint_b_span",
        "exact_span",
        "relation_cue_span",
        "source_locator",
    },
)
INVENTORY_REQUIRED_KEYS: Final = frozenset(
    {
        "endpoint_a_span",
        "endpoint_b_span",
        "endpoint_role_order",
        "exact_span",
        "relation_cue_span",
        "source_locator",
    },
)
TYPED_INVENTORY_REQUIRED_KEYS: Final = frozenset(
    {
        "arguments",
        "exact_span",
        "relation_cue_span",
        "source_locator",
    },
)
TYPED_ARGUMENT_REQUIRED_KEYS: Final = frozenset({"role", "exact_span"})
ROLE_QUALIFIER_FIELDS: Final = {
    "INTERVENTION": "intervention",
    "CONDITION": "condition",
    "POPULATION": "population",
    "VARIANT": "biological_or_variant_state",
    "OUTCOME": "outcome",
    "COMPARATOR": "comparator",
    "TIMEFRAME": "timeframe",
    "STUDY_DESIGN": "study_design",
    "TREATMENT_SETTING": "treatment_setting",
}
TYPED_ARGUMENT_ROLES: Final = frozenset(
    {
        *ROLE_QUALIFIER_FIELDS,
        "GENE_OR_PROTEIN",
        "CHEMICAL_OR_DRUG",
        "BIOMARKER",
        "EXPOSURE",
        "BIOLOGICAL_PROCESS",
        "ANATOMY",
        "MEASUREMENT",
        "OTHER_ENTITY",
    },
)
RELATION_REQUIRED_KEYS: Final = frozenset(
    {"object", "predicate", "sentence", "subject"},
)

_NUMERIC_ASSERTION_TOKEN = (
    r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?\s*%?"
)
_ASSESSMENT_CONCEPT = r"(?:confidence|probability|rating|score)"
AGENT_NUMERIC_ASSESSMENT_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        rf"\b{_ASSESSMENT_CONCEPT}\b\s*(?:[:=]\s*)?"
        rf"(?<![\w.]){_NUMERIC_ASSERTION_TOKEN}(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_ASSESSMENT_CONCEPT}\b"
        rf"(?:\s+[A-Za-z][\w'-]*){{0,5}}\s+"
        rf"(?:is|was|at|to|of)\s*"
        rf"(?<![\w.]){_NUMERIC_ASSERTION_TOKEN}(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?<![\w.]){_NUMERIC_ASSERTION_TOKEN}(?!\w)\s*"
        r"(?:as\s+)?(?:(?:my|its|the|our|model's|agent's)\s+)?"
        r"(?:confidence|probability|rating|score|confident)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:assign(?:s|ed|ing)?|giv(?:e|es|ing)|gave|"
        r"rat(?:e|es|ed|ing)|scor(?:e|es|ed|ing))\b\s+"
        r"(?:this|it|the\s+(?:claim|evidence|output|relation|answer|"
        r"assessment|result))(?:\s+[A-Za-z][\w'-]*){0,4}\s+"
        rf"(?<![\w.]){_NUMERIC_ASSERTION_TOKEN}(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?<![\w.]){_NUMERIC_ASSERTION_TOKEN}(?!\w)\s*"
        rf"(?:/|out\s+of)\s*{_NUMERIC_ASSERTION_TOKEN}(?!\w)",
        re.IGNORECASE,
    ),
)

AgentPayloadContext = Literal[
    "agent_text",
    "qualifier_collection",
    "qualifier",
    "source_evidence",
    "source_measurement_collection",
    "source_measurement",
]
