from __future__ import annotations

from pathlib import Path

from artana_evidence_api.document_extraction_support.scientific_events import (
    EventArgumentTarget,
)

from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
    replay_development_directory,
)


def _write_fixture(root: Path) -> Path:
    devel = root / "devel"
    devel.mkdir()
    (devel / "PMID-1.txt").write_text("Drug inhibits growth with GeneA and GeneB.")
    (devel / "PMID-1.a1").write_text(
        "T1\tSimple_chemical 0 4\tDrug\n"
        "T4\tGene_or_gene_product 26 31\tGeneA\n"
        "T5\tGene_or_gene_product 36 41\tGeneB\n"
    )
    (devel / "PMID-1.a2").write_text(
        "T2\tNegative_regulation 5 13\tinhibits\n"
        "T3\tGrowth 14 20\tgrowth\n"
        "E1\tGrowth:T3 Theme:T4 Theme2:T5\n"
        "E2\tNegative_regulation:T2 Cause:T1 Theme:E1\n"
        "M1\tNegation E1\n"
        "M2\tSpeculation E2\n"
    )
    return devel


def test_projection_preserves_nested_events_roles_offsets_and_modifiers(
    tmp_path: Path,
) -> None:
    devel = _write_fixture(tmp_path)

    document = project_development_directory(devel)[0]
    inner, outer = document.events

    assert inner.source_event_type == "Growth"
    assert inner.artana_event_family is None
    assert tuple(argument.source_role for argument in inner.arguments) == (
        "Theme",
        "Theme2",
    )
    assert inner.modifiers[0].source_modifier_type == "Negation"
    assert outer.arguments[1].target_kind is EventArgumentTarget.EVENT
    assert outer.arguments[1].target_id == "E1"
    trigger = next(item for item in document.mentions if item.annotation_id == "T2")
    assert document.source_text[trigger.span.start : trigger.span.end] == "inhibits"


def test_replay_reports_no_semantic_mapping_or_information_loss(tmp_path: Path) -> None:
    report = replay_development_directory(_write_fixture(tmp_path))

    assert report.documents == 1
    assert report.events == 2
    assert report.participant_mentions == 3
    assert report.arguments == 4
    assert report.nested_arguments == 1
    assert report.modifiers == 2
    assert report.unresolved_references == 0
    assert report.unauthorized_semantic_mappings == 0
    assert report.mismatches == 0
