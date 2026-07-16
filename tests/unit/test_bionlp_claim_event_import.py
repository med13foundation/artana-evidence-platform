"""Regression tests for deterministic BioNLP event-gold adaptation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.validation.claim_events.bionlp_import import (
    TG04_DEVELOPMENT_DOCUMENT_IDS,
    build_bionlp_fixture,
    load_standoff_document,
    select_document_ids,
)


def _write_document(
    root: Path,
    *,
    document_id: str = "PMID-test",
    text: str = "Kinase A increased expression of protein B.",
    a1: str = "T1\tProtein 0 8\tKinase A\nT2\tProtein 33 42\tprotein B\n",
    a2: str = (
        "T3\tPositive_regulation 9 18\tincreased\n"
        "E1\tPositive_regulation:T3 Cause:T1 Theme:T2\n"
    ),
) -> None:
    (root / f"{document_id}.txt").write_text(text, encoding="utf-8")
    (root / f"{document_id}.a1").write_text(a1, encoding="utf-8")
    (root / f"{document_id}.a2").write_text(a2, encoding="utf-8")


def test_build_fixture_preserves_expert_trigger_roles_and_spans(tmp_path: Path) -> None:
    _write_document(tmp_path)

    fixture = build_bionlp_fixture(
        root=tmp_path,
        document_ids=("PMID-test",),
        archive_sha256="a" * 64,
        source_url="https://bionlp-st.dbcls.jp/GE/2011/downloads/",
    )

    case = fixture["cases"][0]
    event = case["events"][0]
    assert event["trigger_span"] == "increased"
    assert event["event_type"] == "POSITIVE_REGULATION"
    assert event["source_span"] == "Kinase A increased expression of protein B"
    assert event["arguments"] == [
        {
            "argument_id": "T1",
            "event_role": "CAUSE",
            "participant_role": "GENE_OR_PROTEIN",
            "exact_span": "Kinase A",
            "source_start": 0,
        },
        {
            "argument_id": "T2",
            "event_role": "THEME",
            "participant_role": "GENE_OR_PROTEIN",
            "exact_span": "protein B",
            "source_start": 33,
        },
    ]
    assert event["value_status"] == "UNADJUDICATED"
    assert event["projection_adjudication"] == "UNADJUDICATED"


def test_import_maps_negation_without_asserting_positive_event(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        a2=(
            "T3\tPositive_regulation 9 18\tincreased\n"
            "E1\tPositive_regulation:T3 Cause:T1 Theme:T2\n"
            "M1\tNegation E1\n"
        ),
    )

    fixture = build_bionlp_fixture(
        root=tmp_path,
        document_ids=("PMID-test",),
        archive_sha256="a" * 64,
        source_url="https://bionlp-st.dbcls.jp/GE/2011/downloads/",
    )

    event = fixture["cases"][0]["events"][0]
    assert event["polarity"] == "REFUTE"
    assert event["epistemic_status"] == "ASSERTED"


def test_import_rejects_source_offset_mismatch(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        a1="T1\tProtein 0 8\tWrong A!\nT2\tProtein 33 42\tprotein B\n",
    )

    with pytest.raises(ValueError, match="text-bound annotation mismatch"):
        load_standoff_document(tmp_path, "PMID-test")


def test_import_remaps_raw_offsets_to_artana_normalized_text(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        text="Title \nKinase A increased expression of protein B.\n",
        a1="T1\tProtein 7 15\tKinase A\nT2\tProtein 40 49\tprotein B\n",
        a2=(
            "T3\tPositive_regulation 16 25\tincreased\n"
            "E1\tPositive_regulation:T3 Cause:T1 Theme:T2\n"
        ),
    )

    document = load_standoff_document(tmp_path, "PMID-test")

    assert document.source_text == "Title\nKinase A increased expression of protein B."
    assert document.text_bounds["T1"].start == 6
    assert document.text_bounds["T2"].start == 39
    assert document.text_bounds["T3"].start == 15


def test_import_excludes_nested_event_identity_the_agent_cannot_express(
    tmp_path: Path,
) -> None:
    _write_document(
        tmp_path,
        a2=(
            "T3\tGene_expression 19 29\texpression\n"
            "T4\tPositive_regulation 9 18\tincreased\n"
            "E1\tGene_expression:T3 Theme:T2\n"
            "E2\tPositive_regulation:T4 Theme:E1 Cause:T1\n"
        ),
    )

    fixture = build_bionlp_fixture(
        root=tmp_path,
        document_ids=("PMID-test",),
        archive_sha256="a" * 64,
        source_url="https://bionlp-st.dbcls.jp/GE/2011/downloads/",
    )

    assert fixture["cases"][0]["events"] == []
    assert fixture["metadata"]["empty_control_document_ids"] == ["PMID-test"]
    assert fixture["metadata"]["representability_stress_document_ids"] == ["PMID-test"]
    assert fixture["metadata"]["event_exclusions"][0]["reason"] == (
        "insufficient_direct_arguments"
    )
    assert fixture["metadata"]["event_exclusions"][1]["reason"] == (
        "nested_event_argument"
    )


def test_import_rejects_unknown_event_category(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        a2=("T3\tActivation 9 18\tincreased\nE1\tActivation:T3 Cause:T1 Theme:T2\n"),
    )

    with pytest.raises(ValueError, match="unmapped BioNLP event category 'Activation'"):
        build_bionlp_fixture(
            root=tmp_path,
            document_ids=("PMID-test",),
            archive_sha256="a" * 64,
            source_url="https://bionlp-st.dbcls.jp/GE/2011/downloads/",
        )


def test_development_selection_is_frozen_and_unique() -> None:
    assert len(TG04_DEVELOPMENT_DOCUMENT_IDS) == 40
    assert len(set(TG04_DEVELOPMENT_DOCUMENT_IDS)) == 40


def test_content_blind_selection_uses_document_id_hash_order(tmp_path: Path) -> None:
    for document_id in ("doc-c", "doc-a", "doc-b"):
        (tmp_path / f"{document_id}.txt").write_text("source", encoding="utf-8")

    expected = tuple(
        sorted(
            ("doc-c", "doc-a", "doc-b"),
            key=lambda item: (hashlib.sha256(item.encode()).hexdigest(), item),
        )[:2],
    )

    assert select_document_ids(tmp_path, count=2) == expected
