"""Regressions for the V13 orthogonal semantic-axis contract."""

from __future__ import annotations

import hashlib

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.prompts import (
    V13_EXTRACTION_PROMPT_VERSION,
    v13_normalization_prompt,
    v13_normalization_prompt_v4,
    v13_normalization_prompt_v6,
    v13_source_unit_extraction_prompt,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)

_NEUTRAL_SOURCE = (
    "Regulation of Fas ligand expression and cell death by apoptosis-linked gene 4."
)


def test_v13_neutral_regulation_is_asserted_support() -> None:
    output = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "decision": "EXPLICIT_EVENT",
            "events": [
                {
                    "exact_span": _NEUTRAL_SOURCE,
                    "relation_cue_span": "Regulation",
                    "relation_cue_anchor": None,
                    "local_event_id": None,
                    "arguments": [
                        {
                            "role": "GENE_OR_PROTEIN",
                            "event_role": "CAUSE",
                            "exact_span": "apoptosis-linked gene 4",
                            "role_rationale": "The named gene is the regulator.",
                            "mention_anchors": [],
                            "referent_anchors": [],
                            "controlled_event_ref": None,
                        },
                        {
                            "role": "BIOLOGICAL_PROCESS",
                            "event_role": "THEME",
                            "exact_span": "Fas ligand expression",
                            "role_rationale": "The first coordinated target.",
                            "mention_anchors": [],
                            "referent_anchors": [],
                            "controlled_event_ref": None,
                        },
                        {
                            "role": "BIOLOGICAL_PROCESS",
                            "event_role": "THEME",
                            "exact_span": "cell death",
                            "role_rationale": "The second coordinated target.",
                            "mention_anchors": [],
                            "referent_anchors": [],
                            "controlled_event_ref": None,
                        },
                    ],
                    "source_locator": "normalized_extraction_text",
                    "claim_kind": "SCIENTIFIC_FINDING",
                    "event_type": "REGULATION",
                    "assertion_scope": "SOURCE_ASSERTED",
                    "polarity": "SUPPORT",
                    "epistemic_status": "ASSERTED",
                    "inventory_rationale": "The source asserts neutral regulation.",
                }
            ],
            "reasoning": "The source asserts one joint direction-neutral event.",
        }
    )

    event = output.events[0]
    assert event.effect_direction.value == "UNDIRECTED"
    assert event.claim_outcome.value == "SUPPORT"


def test_v13_prompt_defines_neutral_direction_without_changing_history() -> None:
    unit = enumerate_source_units(
        case_id="v13-visible-neutral", source_text=_NEUTRAL_SOURCE
    )[0]

    prompt = v13_source_unit_extraction_prompt(unit)

    assert f"prompt_version: {V13_EXTRACTION_PROMPT_VERSION}" in prompt
    assert "event_type REGULATION, polarity SUPPORT" in prompt
    assert "Never use polarity to" in prompt
    assert "prompt_version: tg04.finite_source_unit.extraction.v21" not in prompt


def test_v13_correction_prompt_authorizes_agent_reframe_not_deterministic_repair() -> (
    None
):
    unit = enumerate_source_units(
        case_id="v13-visible-neutral",
        source_text=_NEUTRAL_SOURCE,
    )[0]
    original_output = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "NO_EVENT",
            "decision": "NO_EVENT",
            "events": [],
            "reasoning": "Visible fixture for prompt construction.",
        }
    )
    original = bind_source_unit_extraction(original_output, unit=unit)

    prompt = v13_normalization_prompt(unit=unit, original=original)

    assert "return the corrected category yourself" in prompt
    assert "mark that mapping REFRAME" in prompt
    assert "deterministic binder" in prompt
    assert "will never make the change" in prompt
    assert (
        "prompt_version: tg04.finite_source_unit.structure_normalization.v5" in prompt
    )
    assert "outward-to-inner" in prompt
    assert "Never point an argument to its owning event" in prompt
    assert "Do not swap IDs" in prompt

    historical_prompt = v13_normalization_prompt_v4(unit=unit, original=original)
    assert (
        hashlib.sha256(historical_prompt.encode("utf-8")).hexdigest()
        == "6e19c5f66c2e0ff71ad0e9ee5b2c3f2f3aea5875ddeee2ae1ae351671b41cc91"
    )
    assert "structure_normalization.v4" in historical_prompt
    assert "CONTROLLED-EVENT REFERENCE OWNERSHIP" not in historical_prompt


def test_v13_v6_requires_explicit_multi_level_context_without_changing_v5() -> None:
    unit = enumerate_source_units(
        case_id="v13-visible-neutral",
        source_text=_NEUTRAL_SOURCE,
    )[0]
    original_output = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "NO_EVENT",
            "decision": "NO_EVENT",
            "events": [],
            "reasoning": "Visible fixture for prompt construction.",
        }
    )
    original = bind_source_unit_extraction(original_output, unit=unit)

    historical_prompt = v13_normalization_prompt(unit=unit, original=original)
    prompt = v13_normalization_prompt_v6(unit=unit, original=original)

    assert hashlib.sha256(historical_prompt.encode("utf-8")).hexdigest() == (
        "dd0cfe1c09646a41e2c14496c7f1417f19a0860d7725903c754f2f09193d002a"
    )
    assert "structure_normalization.v5" in historical_prompt
    assert "V13 CONTEXT-DIMENSION ELIGIBILITY" not in historical_prompt
    assert "structure_normalization.v6" in prompt
    assert "at least two distinct, mutually exclusive levels" in prompt
    assert "A single causal participant is not a multi-level comparison" in prompt
    assert "Never invent, translate, repair, duplicate, or paraphrase" in prompt
    assert "Never infer an unstated untreated" in prompt
    assert "Repeated-measures dose or time series" in prompt
    assert "Do not invent an abstract factor label" in prompt
    assert "Populate crossed_dimension_ids only when the source explicitly" in prompt
