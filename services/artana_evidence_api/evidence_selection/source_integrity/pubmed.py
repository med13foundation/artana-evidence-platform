"""Parse authoritative PubMed XML into stable source-validation facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
from typing import Final
from xml.etree.ElementTree import Element

from artana_evidence_api.evidence_selection.source_integrity.contracts import (
    AuthoritativeSourceValidation,
    SourceIdentityStatus,
    SourceIntegrityStatus,
    SourceValidationRelation,
)
from artana_evidence_api.types.common import JSONObject, JSONValue
from defusedxml import ElementTree

_PUBMED_AUTHORITY: Final = "ncbi_pubmed"
_RETRACTION_RELATIONS: Final = frozenset(
    {
        "partialretractionin",
        "partialretractionof",
        "retractionin",
        "retractionof",
    },
)
_EXPRESSION_OF_CONCERN_RELATIONS: Final = frozenset(
    {"expressionofconcernin", "expressionofconcernfor"},
)
_CORRECTION_RELATIONS: Final = frozenset(
    {
        "correctedandrepublishedin",
        "correctedandrepublishedfrom",
        "erratumin",
        "erratumfor",
    },
)
_RETRACTION_PUBLICATION_TYPES: Final = frozenset(
    {"retracted publication", "retraction of publication"},
)
_EXPRESSION_OF_CONCERN_PUBLICATION_TYPES: Final = frozenset(
    {"expression of concern"},
)
_CORRECTION_PUBLICATION_TYPES: Final = frozenset(
    {"corrected and republished article", "published erratum"},
)


@dataclass(frozen=True, slots=True)
class PubMedAuthoritativeArticle:
    """Canonical PubMed article fields and authority-provided relationships."""

    pmid: str
    title: str | None
    abstract: str | None
    doi: str | None
    publication_types: tuple[str, ...]
    relations: tuple[SourceValidationRelation, ...]


def parse_pubmed_articles(xml_payload: str) -> dict[str, PubMedAuthoritativeArticle]:
    """Parse bounded NCBI EFetch XML into records keyed by PMID."""

    root = ElementTree.fromstring(xml_payload)
    articles: dict[str, PubMedAuthoritativeArticle] = {}
    duplicate_pmids: set[str] = set()
    for node in root.findall(".//PubmedArticle"):
        parsed = _parse_article(node)
        if parsed is None or parsed.pmid in duplicate_pmids:
            continue
        if parsed.pmid in articles:
            articles.pop(parsed.pmid)
            duplicate_pmids.add(parsed.pmid)
            continue
        articles[parsed.pmid] = parsed
    return articles


def enrich_pubmed_preview_records(
    *,
    preview_records: list[JSONObject],
    authoritative_articles: Mapping[str, PubMedAuthoritativeArticle],
) -> list[JSONObject]:
    """Merge canonical fields and categorical validation into preview records."""

    return [
        _enrich_preview_record(
            record=record,
            authoritative_article=authoritative_articles.get(_record_pmid(record)),
        )
        for record in preview_records
    ]


def unresolved_pubmed_preview_records(
    preview_records: list[JSONObject],
) -> list[JSONObject]:
    """Preserve records when authority validation is temporarily unresolved."""

    return [
        dict(
            record,
            source_validation=AuthoritativeSourceValidation(
                schema_version="authoritative_source_validation.v1",
                authority=_PUBMED_AUTHORITY,
                validation_method="efetch_xml",
                authority_record_id=_record_pmid(record) or None,
                source_identity=SourceIdentityStatus.UNRESOLVED,
                source_integrity=SourceIntegrityStatus.UNRESOLVED,
                explanation=(
                    "NCBI PubMed source validation could not be completed; absence "
                    "of a validation result is not evidence that the candidate is "
                    "false."
                ),
            ).to_json(),
        )
        for record in preview_records
    ]


def _parse_article(node: Element) -> PubMedAuthoritativeArticle | None:
    pmid = _text(node.find("./MedlineCitation/PMID"))
    if pmid is None:
        return None
    title = _text(node.find("./MedlineCitation/Article/ArticleTitle"))
    abstract = _abstract_text(node)
    doi = _article_id(node, id_type="doi") or _elocation_doi(node)
    publication_types = tuple(
        value
        for publication_type in node.findall(
            "./MedlineCitation/Article/PublicationTypeList/PublicationType",
        )
        if (value := _text(publication_type)) is not None
    )
    relations = tuple(
        relation
        for relation_node in node.findall(
            "./MedlineCitation/CommentsCorrectionsList/CommentsCorrections",
        )
        if (relation := _parse_relation(relation_node)) is not None
    )
    return PubMedAuthoritativeArticle(
        pmid=pmid,
        title=title,
        abstract=abstract,
        doi=doi,
        publication_types=publication_types,
        relations=relations,
    )


def _abstract_text(node: Element) -> str | None:
    sections: list[str] = []
    for abstract_node in node.findall(
        "./MedlineCitation/Article/Abstract/AbstractText",
    ):
        section_text = _text(abstract_node)
        if section_text is None:
            continue
        label = (abstract_node.attrib.get("Label") or "").strip()
        sections.append(f"{label}: {section_text}" if label else section_text)
    return "\n".join(sections) or None


def _article_id(node: Element, *, id_type: str) -> str | None:
    for article_id in node.findall("./PubmedData/ArticleIdList/ArticleId"):
        if (article_id.attrib.get("IdType") or "").strip().lower() == id_type:
            return _text(article_id)
    return None


def _elocation_doi(node: Element) -> str | None:
    for location in node.findall("./MedlineCitation/Article/ELocationID"):
        if (location.attrib.get("EIdType") or "").strip().lower() == "doi":
            return _text(location)
    return None


def _parse_relation(node: Element) -> SourceValidationRelation | None:
    relation_type = (node.attrib.get("RefType") or "").strip()
    citation = _text(node.find("./RefSource"))
    if not relation_type or citation is None:
        return None
    return SourceValidationRelation(
        relation_type=relation_type,
        target_id=_text(node.find("./PMID")),
        citation=citation,
    )


def _enrich_preview_record(
    *,
    record: JSONObject,
    authoritative_article: PubMedAuthoritativeArticle | None,
) -> JSONObject:
    enriched = dict(record)
    if authoritative_article is None:
        return unresolved_pubmed_preview_records([enriched])[0]
    identity = _identity_status(record, authoritative_article)
    integrity = _integrity_status(
        relations=authoritative_article.relations,
        publication_types=authoritative_article.publication_types,
    )
    if authoritative_article.title is not None:
        enriched["title"] = authoritative_article.title
    if authoritative_article.abstract is not None:
        enriched["abstract"] = authoritative_article.abstract
    if authoritative_article.doi is not None:
        enriched["doi"] = authoritative_article.doi
    if authoritative_article.publication_types:
        enriched["publication_types"] = list(
            authoritative_article.publication_types,
        )
    enriched["source_validation"] = AuthoritativeSourceValidation(
        schema_version="authoritative_source_validation.v1",
        authority=_PUBMED_AUTHORITY,
        validation_method="efetch_xml",
        authority_record_id=authoritative_article.pmid,
        source_identity=identity,
        source_integrity=integrity,
        explanation=_validation_explanation(identity=identity, integrity=integrity),
        relations=authoritative_article.relations,
    ).to_json()
    return enriched


def _identity_status(
    record: JSONObject,
    article: PubMedAuthoritativeArticle,
) -> SourceIdentityStatus:
    if _record_pmid(record) != article.pmid:
        return SourceIdentityStatus.MISMATCHED
    summary_doi = _normalized_scalar(record.get("doi"))
    if (
        summary_doi is not None
        and article.doi is not None
        and summary_doi.casefold() != article.doi.casefold()
    ):
        return SourceIdentityStatus.MISMATCHED
    return SourceIdentityStatus.MATCHED


def _integrity_status(
    *,
    relations: tuple[SourceValidationRelation, ...],
    publication_types: tuple[str, ...],
) -> SourceIntegrityStatus:
    relation_types = {
        relation.relation_type.replace(" ", "").casefold() for relation in relations
    }
    normalized_publication_types = {
        publication_type.casefold() for publication_type in publication_types
    }
    if (
        relation_types & _RETRACTION_RELATIONS
        or normalized_publication_types & _RETRACTION_PUBLICATION_TYPES
    ):
        return SourceIntegrityStatus.RETRACTED
    if (
        relation_types & _EXPRESSION_OF_CONCERN_RELATIONS
        or normalized_publication_types & _EXPRESSION_OF_CONCERN_PUBLICATION_TYPES
    ):
        return SourceIntegrityStatus.EXPRESSION_OF_CONCERN
    if (
        relation_types & _CORRECTION_RELATIONS
        or normalized_publication_types & _CORRECTION_PUBLICATION_TYPES
    ):
        return SourceIntegrityStatus.CORRECTION_REVIEW
    return SourceIntegrityStatus.CLEAR


def _validation_explanation(
    *,
    identity: SourceIdentityStatus,
    integrity: SourceIntegrityStatus,
) -> str:
    return (
        "NCBI PubMed EFetch verified the requested source identity and publication "
        f"integrity categories: identity={identity.value}, integrity={integrity.value}."
    )


def _record_pmid(record: Mapping[str, JSONValue]) -> str:
    return _normalized_scalar(record.get("pmid")) or ""


def _normalized_scalar(value: JSONValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _text(node: Element | None) -> str | None:
    if node is None:
        return None
    normalized = " ".join(unescape("".join(node.itertext())).split())
    return normalized or None


__all__ = [
    "PubMedAuthoritativeArticle",
    "enrich_pubmed_preview_records",
    "parse_pubmed_articles",
    "unresolved_pubmed_preview_records",
]
