"""Tests for categorical, authoritative PubMed source validation."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection.source_integrity.pubmed import (
    enrich_pubmed_preview_records,
    parse_pubmed_articles,
)
from defusedxml.common import EntitiesForbidden


def test_pubmed_xml_enriches_abstract_and_clear_identity() -> None:
    articles = parse_pubmed_articles(
        _article_xml(
            pmid="12345",
            doi="10.1000/clear",
            abstract=(
                '<AbstractText Label="RESULTS">A specific patient response.</AbstractText>'
            ),
        ),
    )

    records = enrich_pubmed_preview_records(
        preview_records=[
            {"pmid": "12345", "title": "Summary title", "doi": "10.1000/clear"},
        ],
        authoritative_articles=articles,
    )

    assert records[0]["title"] == "Canonical title"
    assert records[0]["abstract"] == "RESULTS: A specific patient response."
    assert records[0]["publication_types"] == ["Clinical Trial"]
    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_identity"] == "matched"
    assert validation["source_integrity"] == "clear"


@pytest.mark.parametrize(
    ("relation_type", "expected_integrity"),
    [
        ("ErratumIn", "correction_review"),
        ("ExpressionOfConcernIn", "expression_of_concern"),
        ("RetractionIn", "retracted"),
    ],
)
def test_pubmed_integrity_relations_are_preserved_and_categorized(
    relation_type: str,
    expected_integrity: str,
) -> None:
    articles = parse_pubmed_articles(
        _article_xml(
            pmid="12345",
            relation_type=relation_type,
            related_pmid="67890",
        ),
    )

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "12345", "title": "Summary title"}],
        authoritative_articles=articles,
    )

    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_integrity"] == expected_integrity
    assert validation["relations"] == [
        {
            "relation_type": relation_type,
            "target_id": "67890",
            "citation": "Related publication",
        },
    ]


def test_non_integrity_update_relation_does_not_block_source() -> None:
    articles = parse_pubmed_articles(
        _article_xml(pmid="12345", relation_type="UpdateIn"),
    )

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "12345"}],
        authoritative_articles=articles,
    )

    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_integrity"] == "clear"
    assert validation["relations"][0]["relation_type"] == "UpdateIn"


@pytest.mark.parametrize(
    ("publication_type", "expected_integrity"),
    [
        ("Retracted Publication", "retracted"),
        ("Retraction of Publication", "retracted"),
        ("Expression of Concern", "expression_of_concern"),
        ("Published Erratum", "correction_review"),
    ],
)
def test_publication_type_is_an_independent_integrity_signal(
    publication_type: str,
    expected_integrity: str,
) -> None:
    articles = parse_pubmed_articles(
        _article_xml(pmid="12345", publication_type=publication_type),
    )

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "12345"}],
        authoritative_articles=articles,
    )

    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_integrity"] == expected_integrity


def test_missing_authoritative_record_is_unresolved_not_false() -> None:
    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "new-record", "title": "Emerging hypothesis"}],
        authoritative_articles={},
    )

    assert records[0]["title"] == "Emerging hypothesis"
    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_identity"] == "unresolved"
    assert validation["source_integrity"] == "unresolved"
    assert "not evidence that the candidate is false" in validation["explanation"]


def test_authoritative_articles_are_matched_by_pmid_not_response_order() -> None:
    articles = parse_pubmed_articles(_article_xml(pmid="222"))
    articles.update(parse_pubmed_articles(_article_xml(pmid="111")))

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "111"}, {"pmid": "222"}, {"pmid": "333"}],
        authoritative_articles=articles,
    )

    assert records[0]["title"] == "Canonical title"
    assert records[1]["title"] == "Canonical title"
    first_validation = records[0]["source_validation"]
    second_validation = records[1]["source_validation"]
    missing_validation = records[2]["source_validation"]
    assert isinstance(first_validation, dict)
    assert isinstance(second_validation, dict)
    assert isinstance(missing_validation, dict)
    assert first_validation["authority_record_id"] == "111"
    assert second_validation["authority_record_id"] == "222"
    assert missing_validation["source_identity"] == "unresolved"


def test_duplicate_authoritative_pmid_fails_closed_as_unresolved() -> None:
    duplicate_payload = (
        "<PubmedArticleSet>"
        + _article_fragment(pmid="12345", publication_type="Clinical Trial")
        + _article_fragment(
            pmid="12345",
            publication_type="Retracted Publication",
        )
        + "</PubmedArticleSet>"
    )

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "12345"}],
        authoritative_articles=parse_pubmed_articles(duplicate_payload),
    )

    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_identity"] == "unresolved"
    assert validation["source_integrity"] == "unresolved"


def test_doi_disagreement_is_categorical_identity_mismatch() -> None:
    articles = parse_pubmed_articles(
        _article_xml(pmid="12345", doi="10.1000/authority"),
    )

    records = enrich_pubmed_preview_records(
        preview_records=[{"pmid": "12345", "doi": "10.1000/other"}],
        authoritative_articles=articles,
    )

    validation = records[0]["source_validation"]
    assert isinstance(validation, dict)
    assert validation["source_identity"] == "mismatched"


def test_pubmed_xml_parser_rejects_external_entities() -> None:
    malicious_xml = """<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <PubmedArticleSet><PubmedArticle><MedlineCitation>
    <PMID>12345</PMID><Article><ArticleTitle>&xxe;</ArticleTitle></Article>
    </MedlineCitation></PubmedArticle></PubmedArticleSet>"""

    with pytest.raises(EntitiesForbidden):
        parse_pubmed_articles(malicious_xml)


def _article_xml(
    *,
    pmid: str,
    doi: str | None = None,
    abstract: str = "<AbstractText>Focused abstract.</AbstractText>",
    relation_type: str | None = None,
    related_pmid: str = "67890",
    publication_type: str = "Clinical Trial",
) -> str:
    return (
        "<PubmedArticleSet>"
        + _article_fragment(
            pmid=pmid,
            doi=doi,
            abstract=abstract,
            relation_type=relation_type,
            related_pmid=related_pmid,
            publication_type=publication_type,
        )
        + "</PubmedArticleSet>"
    )


def _article_fragment(
    *,
    pmid: str,
    doi: str | None = None,
    abstract: str = "<AbstractText>Focused abstract.</AbstractText>",
    relation_type: str | None = None,
    related_pmid: str = "67890",
    publication_type: str = "Clinical Trial",
) -> str:
    article_id = f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else ""
    relation = (
        ""
        if relation_type is None
        else (
            "<CommentsCorrectionsList>"
            f'<CommentsCorrections RefType="{relation_type}">'
            "<RefSource>Related publication</RefSource>"
            f"<PMID>{related_pmid}</PMID>"
            "</CommentsCorrections>"
            "</CommentsCorrectionsList>"
        )
    )
    return f"""<PubmedArticle>
      <MedlineCitation>
        <PMID>{pmid}</PMID>
        <Article>
          <ArticleTitle>Canonical <i>title</i></ArticleTitle>
          <Abstract>{abstract}</Abstract>
          <PublicationTypeList><PublicationType>{publication_type}</PublicationType></PublicationTypeList>
        </Article>
        {relation}
      </MedlineCitation>
      <PubmedData><ArticleIdList>{article_id}</ArticleIdList></PubmedData>
    </PubmedArticle>"""
