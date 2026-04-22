"""Type definitions for MARRVEL API responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


class MarrvelGeneInfo(TypedDict, total=False):
    """Gene information from MARRVEL /gene endpoint."""

    entrez_id: int | None
    symbol: str | None
    name: str | None
    chromosome: str | None
    map_location: str | None
    gene_type: str | None
    aliases: list[str]
    hgnc_id: str | None
    ensembl_id: str | None
    omim_id: str | None
    description: str | None


class MarrvelOmimEntry(TypedDict, total=False):
    """Single OMIM gene-phenotype association."""

    mim_number: int | None
    phenotype: str | None
    phenotype_mim_number: int | None
    inheritance: str | None
    inheritance_patterns: list[str]
    gene_symbol: str | None


class MarrvelDbnsfpVariant(TypedDict, total=False):
    """Variant pathogenicity prediction scores from dbNSFP."""

    variant: str | None
    hgvs: str | None
    gene_symbol: str | None
    sift_score: float | None
    sift_prediction: str | None
    polyphen2_score: float | None
    polyphen2_prediction: str | None
    lrt_score: float | None
    lrt_prediction: str | None
    cadd_phred: float | None
    cadd_raw: float | None
    revel_score: float | None
    phylop_score: float | None
    phastcons_score: float | None


class MarrvelClinvarEntry(TypedDict, total=False):
    """ClinVar variant from MARRVEL /clinvar endpoint."""

    clinvar_id: str | None
    variant_position: str | None
    clinical_significance: str | None
    review_status: str | None
    condition: str | None
    last_evaluated: str | None
    gene_symbol: str | None


class MarrvelGeno2mpEntry(TypedDict, total=False):
    """Rare-disease cohort variant entry from MARRVEL /geno2mp endpoint."""

    hg19Chr: str | None
    hg19Pos: int | None
    ref: str | None
    alt: str | None
    hpoProfiles: list[JSONObject]


class MarrvelGnomadConstraint(TypedDict, total=False):
    """Gene-level constraint data from MARRVEL /gnomad endpoint."""

    entrezId: int | None
    ensemblId: str | None
    syn: JSONObject
    mis: JSONObject
    lof: JSONObject


class MarrvelStructuralVariantEntry(TypedDict, total=False):
    """Structural variant overlap record from DGV or DECIPHER."""

    accessionId: str | None
    hg19Chr: str | None
    hg19Start: int | None
    hg19Stop: int | None
    subType: str | None
    samples: list[str]


class MarrvelOrthologEntry(TypedDict, total=False):
    """Ortholog or alignment entry from DIOPT or AGR expression endpoints."""

    entrezId1: int | None
    taxonId1: int | None
    entrezId2: int | None
    taxonId2: int | None
    score: int | float | None
    confidence: str | None
    gene1: JSONObject
    gene2: JSONObject


class MarrvelGtexExpression(TypedDict, total=False):
    """GTEx expression response keyed by tissue groups."""

    ensemblId: str | None
    symbol: str | None
    data: JSONObject


class MarrvelPharosTarget(TypedDict, total=False):
    """Targetability context from MARRVEL /pharos endpoint."""

    id: str | None
    accession: str | None
    name: str | None
    idgTDL: str | None
    idgFamily: str | None
    description: str | None


class MarrvelVariantResolution(TypedDict, total=False):
    """Variant normalization payload from Mutalyzer or TransVar."""

    chr: str | None
    pos: int | str | None
    ref: str | None
    alt: str | None
    gene: JSONObject
    candidates: list[JSONObject]
    errors: list[str] | None


class MarrvelAggregatedRecord(TypedDict, total=False):
    """Aggregated record for a single gene across all MARRVEL endpoints."""

    gene_symbol: str
    taxon_id: int
    record_type: str  # "gene", "omim", "dbnsfp_variant", "clinvar_variant"
    gene_info: MarrvelGeneInfo | None
    omim_entries: list[MarrvelOmimEntry]
    dbnsfp_variants: list[MarrvelDbnsfpVariant]
    clinvar_entries: list[MarrvelClinvarEntry]
    geno2mp_entries: list[MarrvelGeno2mpEntry]
    gnomad_gene: MarrvelGnomadConstraint | None
    dgv_entries: list[MarrvelStructuralVariantEntry]
    diopt_orthologs: list[MarrvelOrthologEntry]
    diopt_alignments: list[MarrvelOrthologEntry]
    gtex_expression: MarrvelGtexExpression | None
    ortholog_expression: list[MarrvelOrthologEntry]
    pharos_targets: list[MarrvelPharosTarget]
    source: str  # always "marrvel"
    fetched_at: str | None
