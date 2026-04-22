from __future__ import annotations

import re
from dataclasses import dataclass

GENE_ID_PATTERN = re.compile(r"^[A-Z0-9_-]{1,50}$")
GENE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9_-]{1,20}$")
ENSEMBL_PATTERN = re.compile(r"^ENSG[0-9]+$")
UNIPROT_PATTERN = re.compile(r"^[A-Z0-9_-]+$")
CLINVAR_PATTERN = re.compile(r"^VCV[0-9]+$")
HPO_PATTERN = re.compile(r"^HP:[0-9]{7}$")

# Length constraints
VARIANT_ID_MAX_LEN = 100
HPO_TERM_MAX_LEN = 200
DOI_PATTERN = re.compile(r"^(10\.\d{4,9}/[-._;()/:A-Z0-9]+)$", re.IGNORECASE)


@dataclass(frozen=True)
class GeneIdentifier:
    gene_id: str
    symbol: str
    ensembl_id: str | None = None
    ncbi_gene_id: int | None = None
    uniprot_id: str | None = None

    def __post_init__(self) -> None:
        normalized_gene_id = self.gene_id.upper()
        normalized_symbol = self.symbol.upper()

        if not GENE_ID_PATTERN.fullmatch(normalized_gene_id):
            message = "gene_id must be 1-50 uppercase alphanumeric or _-/ characters"
            raise ValueError(message)
        if not GENE_SYMBOL_PATTERN.fullmatch(normalized_symbol):
            message = "symbol must be 1-20 uppercase alphanumeric or _-/ characters"
            raise ValueError(message)

        object.__setattr__(self, "gene_id", normalized_gene_id)
        object.__setattr__(self, "symbol", normalized_symbol)

        if self.ensembl_id and not ENSEMBL_PATTERN.fullmatch(self.ensembl_id):
            message = "ensembl_id must match ENSG#### pattern"
            raise ValueError(message)
        if self.uniprot_id and not UNIPROT_PATTERN.fullmatch(self.uniprot_id):
            message = "uniprot_id must contain uppercase alphanumerics, '_' or '-'"
            raise ValueError(message)
        if self.ncbi_gene_id is not None and self.ncbi_gene_id < 1:
            message = "ncbi_gene_id must be positive"
            raise ValueError(message)

    def __str__(self) -> str:
        return self.symbol


@dataclass(frozen=True)
class VariantIdentifier:
    variant_id: str
    clinvar_id: str | None = None
    hgvs_genomic: str | None = None
    hgvs_protein: str | None = None
    hgvs_cdna: str | None = None

    def __post_init__(self) -> None:
        if not self.variant_id or len(self.variant_id) > VARIANT_ID_MAX_LEN:
            message = "variant_id must be between 1 and 100 characters"
            raise ValueError(message)
        if self.clinvar_id and not CLINVAR_PATTERN.fullmatch(self.clinvar_id):
            message = "clinvar_id must match VCV#### format"
            raise ValueError(message)

    def __str__(self) -> str:
        return self.variant_id


@dataclass(frozen=True)
class PhenotypeIdentifier:
    hpo_id: str
    hpo_term: str

    def __post_init__(self) -> None:
        if not HPO_PATTERN.fullmatch(self.hpo_id):
            message = "hpo_id must match HP:####### format"
            raise ValueError(message)
        if not self.hpo_term or len(self.hpo_term) > HPO_TERM_MAX_LEN:
            message = "hpo_term must be 1-200 characters"
            raise ValueError(message)

    def __str__(self) -> str:
        return f"{self.hpo_id} ({self.hpo_term})"


@dataclass(frozen=True)
class PublicationIdentifier:
    pubmed_id: str | None = None
    pmc_id: str | None = None
    doi: str | None = None

    def __post_init__(self) -> None:
        if self.pubmed_id and not self.pubmed_id.isdigit():
            message = "pubmed_id must be numeric"
            raise ValueError(message)
        if self.pmc_id and not self.pmc_id.startswith("PMC"):
            message = "pmc_id must start with PMC"
            raise ValueError(message)
        if self.doi and not DOI_PATTERN.fullmatch(self.doi):
            message = "doi must follow DOI syntax (10.xxxx/...)"
            raise ValueError(message)

    def get_primary_id(self) -> str:
        return self.pmc_id or self.pubmed_id or (self.doi or "unknown")

    def __str__(self) -> str:
        return self.get_primary_id()


__all__ = [
    "GeneIdentifier",
    "PhenotypeIdentifier",
    "PublicationIdentifier",
    "VariantIdentifier",
]
