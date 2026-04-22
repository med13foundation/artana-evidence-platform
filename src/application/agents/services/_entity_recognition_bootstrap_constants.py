"""Constants for entity recognition bootstrap helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONValue

_DEFAULT_BOOTSTRAP_RELATION_TYPE = "ASSOCIATED_WITH"
_DEFAULT_INTERACTION_RELATION_TYPE = "PHYSICALLY_INTERACTS_WITH"
_MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION = 2
_PUBMED_PUBLICATION_BASELINE_ENTITY_TYPES: tuple[str, ...] = (
    "PUBLICATION",
    "AUTHOR",
    "KEYWORD",
    "GENE",
    "PROTEIN",
    "VARIANT",
    "PHENOTYPE",
    "DRUG",
    "MECHANISM",
)
_PUBMED_PUBLICATION_BASELINE_RELATION_TYPES: tuple[
    tuple[str, str, str, bool, str | None],
    ...,
] = (
    (
        "MENTIONS",
        "Mentions",
        "Publication reference relationship for documented entities.",
        True,
        "MENTIONED_BY",
    ),
    (
        "SUPPORTS",
        "Supports",
        "Publication evidence support relationship.",
        True,
        "SUPPORTED_BY",
    ),
    (
        "CITES",
        "Cites",
        "Citation relationship between publications.",
        True,
        "CITED_BY",
    ),
    (
        "HAS_AUTHOR",
        "Has Author",
        "Authorship relationship from publication to author entity.",
        True,
        "AUTHOR_OF",
    ),
    (
        "HAS_KEYWORD",
        "Has Keyword",
        "Keyword tagging relationship from publication to keyword entity.",
        True,
        "KEYWORD_OF",
    ),
)
_PUBMED_PUBLICATION_BASELINE_CONSTRAINTS: tuple[tuple[str, str, str, bool], ...] = (
    ("PUBLICATION", "MENTIONS", "GENE", False),
    ("PUBLICATION", "MENTIONS", "PROTEIN", False),
    ("PUBLICATION", "MENTIONS", "VARIANT", False),
    ("PUBLICATION", "MENTIONS", "PHENOTYPE", False),
    ("PUBLICATION", "MENTIONS", "DRUG", False),
    ("PUBLICATION", "SUPPORTS", "GENE", False),
    ("PUBLICATION", "SUPPORTS", "PROTEIN", False),
    ("PUBLICATION", "SUPPORTS", "VARIANT", False),
    ("PUBLICATION", "SUPPORTS", "MECHANISM", False),
    ("PUBLICATION", "HAS_AUTHOR", "AUTHOR", False),
    ("PUBLICATION", "HAS_KEYWORD", "KEYWORD", False),
    ("PUBLICATION", "CITES", "PUBLICATION", False),
)
_PUBMED_METADATA_VARIABLE_SPECS: tuple[
    tuple[str, str, str, str, str, dict[str, JSONValue] | None, tuple[str, ...]],
    ...,
] = (
    (
        "VAR_PUBLICATION_TITLE",
        "publication_title",
        "Publication Title",
        "STRING",
        "Title of the academic publication.",
        None,
        ("title", "paper_title", "publication_title"),
    ),
    (
        "VAR_ABSTRACT",
        "abstract",
        "Abstract",
        "STRING",
        "Publication abstract text.",
        None,
        ("abstract", "abstract_text"),
    ),
    (
        "VAR_PUBLICATION_YEAR",
        "publication_year",
        "Publication Year",
        "INTEGER",
        "Year of publication.",
        {"min": 1900, "max": 2100},
        ("publication_year", "year", "pub_year"),
    ),
    (
        "VAR_PUBLICATION_DATE",
        "publication_date",
        "Publication Date",
        "DATE",
        "Calendar publication date for the article.",
        None,
        ("publication_date", "pub_date", "date_published"),
    ),
    (
        "VAR_JOURNAL_NAME",
        "journal_name",
        "Journal Name",
        "STRING",
        "Journal of publication.",
        None,
        ("journal", "journal_name"),
    ),
    (
        "VAR_PUBMED_ID",
        "pubmed_id",
        "PubMed ID",
        "STRING",
        "PubMed stable identifier for a publication.",
        None,
        ("pmid", "pubmed_id"),
    ),
    (
        "VAR_DOI",
        "doi",
        "DOI",
        "STRING",
        "Digital Object Identifier for a publication.",
        None,
        ("doi",),
    ),
    (
        "VAR_KEYWORDS",
        "keywords",
        "Keywords",
        "JSON",
        "Structured keyword list extracted from publication metadata.",
        None,
        ("keywords", "keyword_list"),
    ),
)


__all__ = [
    "_DEFAULT_BOOTSTRAP_RELATION_TYPE",
    "_DEFAULT_INTERACTION_RELATION_TYPE",
    "_MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION",
    "_PUBMED_METADATA_VARIABLE_SPECS",
    "_PUBMED_PUBLICATION_BASELINE_CONSTRAINTS",
    "_PUBMED_PUBLICATION_BASELINE_ENTITY_TYPES",
    "_PUBMED_PUBLICATION_BASELINE_RELATION_TYPES",
]
