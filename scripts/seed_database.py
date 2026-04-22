#!/usr/bin/env python3
"""Seed the Artana Resource Library database with demo curation data."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from src.database.seed import ensure_source_catalog_seeded
from src.database.session import SessionLocal, engine
from src.models.database import (
    Base,
    EvidenceModel,
    GeneModel,
    PhenotypeModel,
    VariantModel,
)
from src.models.database.audit import AuditLog
from src.models.database.review import ReviewRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_gene(session: Session) -> GeneModel:
    gene = session.query(GeneModel).filter(GeneModel.gene_id == "MED13").one_or_none()
    if gene:
        return gene

    gene = GeneModel(
        gene_id="MED13",
        symbol="MED13",
        name="Mediator complex subunit 13",
        description="Component of the Mediator complex, a coactivator involved in regulated transcription of RNA polymerase II-dependent genes.",
        gene_type="protein_coding",
        chromosome="17",
        start_position=60000000,
        end_position=60020000,
        ensembl_id="ENSG00000108510",
        ncbi_gene_id=99968,
        uniprot_id="Q9UHV7_MED13",
    )
    session.add(gene)
    session.flush()
    return gene


def ensure_variant(session: Session, gene: GeneModel) -> VariantModel:
    variant = (
        session.query(VariantModel)
        .filter(VariantModel.variant_id == "VCV000999999")
        .one_or_none()
    )
    if variant:
        return variant

    variant = VariantModel(
        gene_id=gene.id,
        variant_id="VCV000999999",
        clinvar_id="VCV000999999",
        chromosome="17",
        position=60005000,
        reference_allele="A",
        alternate_allele="G",
        hgvs_genomic="chr17:g.60005000A>G",
        hgvs_protein="p.Val123Gly",
        hgvs_cdna="c.367A>G",
        variant_type="snv",
        clinical_significance="pathogenic",
        condition="Neurodevelopmental disorder",
        review_status="criteria_provided",
        allele_frequency=0.0002,
        gnomad_af=0.0003,
    )
    session.add(variant)
    session.flush()
    return variant


def ensure_phenotype(session: Session) -> PhenotypeModel:
    phenotype = (
        session.query(PhenotypeModel)
        .filter(PhenotypeModel.hpo_id == "HP:0001249")
        .one_or_none()
    )
    if phenotype:
        return phenotype

    phenotype = PhenotypeModel(
        hpo_id="HP:0001249",
        hpo_term="Intellectual disability",
        name="Intellectual disability",
        definition="Subnormal intellectual functioning originating during the developmental period.",
        synonyms='["Developmental delay", "Cognitive impairment"]',
        category="other",
        frequency_in_med13="frequent",
    )
    session.add(phenotype)
    session.flush()
    return phenotype


def ensure_evidence(
    session: Session,
    variant: VariantModel,
    phenotype: PhenotypeModel,
) -> EvidenceModel:
    evidence = (
        session.query(EvidenceModel)
        .filter(EvidenceModel.variant_id == variant.id)
        .filter(EvidenceModel.phenotype_id == phenotype.id)
        .one_or_none()
    )
    if evidence:
        return evidence

    evidence = EvidenceModel(
        variant_id=variant.id,
        phenotype_id=phenotype.id,
        evidence_level="strong",
        evidence_type="clinical_report",
        description="Published case report linking MED13 variant to intellectual disability.",
        summary="Primary publication supporting the association.",
        confidence_score=0.88,
        reviewed=True,
    )
    session.add(evidence)
    session.flush()
    return evidence


def ensure_review(session: Session, variant: VariantModel) -> None:
    existing = (
        session.query(ReviewRecord)
        .filter(ReviewRecord.entity_type == "variant")
        .filter(ReviewRecord.entity_id == variant.variant_id)
        .one_or_none()
    )
    if existing:
        return

    review = ReviewRecord(
        entity_type="variant",
        entity_id=variant.variant_id,
        status="pending",
        priority="high",
        quality_score=0.92,
        issues=2,
        last_updated=datetime.now(UTC),
    )
    session.add(review)


def ensure_audit_log(session: Session, variant: VariantModel) -> None:
    exists = (
        session.query(AuditLog)
        .filter(AuditLog.entity_type == "variant")
        .filter(AuditLog.entity_id == variant.variant_id)
        .first()
    )
    if exists:
        return

    session.add(
        AuditLog(
            action="comment",
            entity_type="variant",
            entity_id=variant.variant_id,
            user="demo-curator",
            details="Initial curator note seeded for demo dashboard.",
        ),
    )


def main() -> None:
    Base.metadata.create_all(bind=engine)
    logging.basicConfig(level=logging.INFO)

    session: Session | None = None
    try:
        session = SessionLocal()
        gene = ensure_gene(session)
        variant = ensure_variant(session, gene)
        phenotype = ensure_phenotype(session)
        ensure_evidence(session, variant, phenotype)
        ensure_review(session, variant)
        ensure_audit_log(session, variant)
        ensure_source_catalog_seeded(session)
        session.commit()
        logger.info("Seeded MED13 demo data for curation workflows.")
    except (
        SQLAlchemyError,
        RuntimeError,
        ValueError,
    ) as exc:  # pragma: no cover - seeding diagnostics
        if session is not None:
            session.rollback()
        message = f"Failed to seed database: {exc}"
        raise SystemExit(message) from exc
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    main()
