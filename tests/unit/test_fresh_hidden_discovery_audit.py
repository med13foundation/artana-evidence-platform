from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_fresh_hidden_discovery_audit import fresh_discovery_exit_code
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_authorization import (
    verify_fresh_discovery_authorization,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_gate import (
    FreshDiscoveryGateInputs,
    fresh_discovery_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_runner import (
    _target_arguments_preserved,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_unit import (
    select_fresh_hidden_unit,
)
from scripts.validation.claim_events.fixture import load_fixture

#: These checks read the corpus text itself, which this public repository does
#: not carry.  They are skipped, never deleted: the reason names the licence and
#: the exact command that restores them.
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)

_FIXTURE_PATH = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json",
)


def _baseline_gate() -> FreshDiscoveryGateInputs:
    return FreshDiscoveryGateInputs(
        authorization_verified=True,
        exposure_registry_verified=True,
        hidden_expert_event_count=0,
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=1,
        verification_decision_count=1,
        entailed_candidate_count=1,
        target_event_count=1,
        target_direction_preserved=True,
        target_polarity_asserted=True,
        target_arguments_preserved=True,
        generic_event_role_count=0,
        binding_rejection_count=0,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )


def test_fresh_discovery_gate_fails_closed_on_every_boundary() -> None:
    baseline = _baseline_gate()
    assert all(fresh_discovery_gate_requirements(baseline).values())
    assert all(
        fresh_discovery_gate_requirements(
            replace(
                baseline,
                extracted_candidate_count=3,
                verification_decision_count=3,
                entailed_candidate_count=3,
            ),
        ).values(),
    )

    mutations = (
        {"authorization_verified": False},
        {"exposure_registry_verified": False},
        {"hidden_expert_event_count": 1},
        {"agent_execution_complete": False},
        {"extraction_category": SourceUnitEligibilityCategory.HYPOTHESIS},
        {"verification_category": SourceUnitEligibilityCategory.NULL_RESULT},
        {"extraction_decision": SourceUnitDecision.NO_EVENT},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"extracted_candidate_count": 0},
        {"extracted_candidate_count": 4},
        {"verification_decision_count": 0},
        {"entailed_candidate_count": 0},
        {"target_event_count": 0},
        {"target_direction_preserved": False},
        {"target_polarity_asserted": False},
        {"target_arguments_preserved": False},
        {"generic_event_role_count": 1},
        {"binding_rejection_count": 1},
        {"model_transport_identity_field_count": 1},
        {"audit_identity_mismatch_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"extraction_provider_response_id_count": 0},
        {"verification_provider_response_id_count": 0},
        {"distinct_provider_response_id_count": 1},
        {"verified_provider_receipt_count": 1},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
    )
    for mutation in mutations:
        assert not all(
            fresh_discovery_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


@requires_corpus
def test_fresh_unit_is_frozen_unexposed_and_has_no_local_gold() -> None:
    selection = select_fresh_hidden_unit(load_fixture(_FIXTURE_PATH))

    assert selection.hidden_expert_event_count == 0
    assert selection.unit.index == 4
    assert selection.unit.unit_id == (
        "source-unit-20ebe2019ebdd3e3651c8886f9f60c7d171883555237b2df667a47f90bab35f0"
    )
    assert selection.unit.input_sha256 == (
        "517b4ab2c503e65ce9d1b11f6b77e2361215f642cd0c54eec6abbb785a88c905"
    )
    # The corpus sentence is licence-restricted, so it is pinned by digest
    # rather than quoted.  See scripts/validation/RESTRICTED_CORPORA.md.
    assert hashlib.sha256(selection.unit.text.encode("utf-8")).hexdigest() == (
        "7470319518ed1ce44e7195841143cfc1f91e4799babe8676f46d3a2255e148d3"
    )
    assert len(selection.exposure_registry_sha256) == 64
    assert selection.authoritative_article_url.endswith("/7537762/")


def test_target_requires_both_specific_material_arguments() -> None:
    """The matcher keys on entity names, so the inputs here are entity names.

    This case used to paste the argument surface exactly as the source document
    writes it -- name, space, parenthesised abbreviation.  That is a quoted span
    rather than the name of a thing, and the rule in
    `scripts/validation/RESTRICTED_CORPORA.md` covers a test input as squarely
    as it covers a fixture field.  The bare names exercise the same two
    branches, and the third case keeps the substring branch honest with a
    surface the corpus does not contain.
    """

    complete = (
        {"exact_span": "P-selectin"},
        {"exact_span": "nuclear factor-kappa B"},
    )
    assert _target_arguments_preserved(complete)
    assert _target_arguments_preserved(
        ({"exact_span": "P-selectin"}, {"exact_span": "NF-kappa B"}),
    )
    assert _target_arguments_preserved(
        (
            {"exact_span": "P-selectin"},
            {"exact_span": "synthetic nuclear factor-kappa B surface"},
        ),
    )
    assert not _target_arguments_preserved(complete[:1])
    assert not _target_arguments_preserved(
        ({"exact_span": "MCP-1"}, {"exact_span": "TNF-alpha"}),
    )


def test_fresh_authorization_report_is_hash_pinned(tmp_path: Path) -> None:
    """The pin moved when the report was redacted; see `fresh_authorization`.

    It is the same report and the same authorization -- two clauses that quoted
    restricted corpus prose were reworded, and no requirement, count or verdict
    in it changed.  The superseded digest and the reason are recorded next to
    the constant, because a pin that can be bumped without explanation pins
    nothing.
    """

    assert verify_fresh_discovery_authorization() == (
        "00968ba249fbffc85f016953ba762108042eabd77ef7d0653c3acc8f921ba568"
    )

    changed = tmp_path / "changed.md"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="report changed"):
        verify_fresh_discovery_authorization(changed)


def test_fresh_discovery_cli_exit_status_follows_gate() -> None:
    assert fresh_discovery_exit_code({"gate": {"passed": True}}) == 0
    assert fresh_discovery_exit_code({"gate": {"passed": False}}) == 1
    assert fresh_discovery_exit_code({}) == 1
