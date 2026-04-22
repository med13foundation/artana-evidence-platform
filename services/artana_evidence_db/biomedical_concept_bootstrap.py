"""Biomedical starter concept seeding for graph spaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

from artana_evidence_db.concept_repository import GraphConceptRepository
from artana_evidence_db.dictionary_repository import GraphDictionaryRepository
from artana_evidence_db.dictionary_management_service import (
    DictionaryManagementService,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
)
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from artana_evidence_db.space_models import GraphSpaceModel
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_SEED_CREATED_BY = "seed"
_SEED_SOURCE = "graph.biomedical.starter"
_SEED_DICTIONARY_DIMENSION = "biomedical_seed"


@dataclass(frozen=True, slots=True)
class BiomedicalStarterConceptMember:
    """One seed concept member within a biomedical starter set."""

    canonical_label: str
    dictionary_entry_id: str
    sense_key: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BiomedicalStarterConceptSet:
    """One seed concept set for biomedical graph spaces."""

    name: str
    slug: str
    domain_context: str
    description: str
    members: tuple[BiomedicalStarterConceptMember, ...]


BIOMEDICAL_STARTER_CONCEPT_SETS: tuple[BiomedicalStarterConceptSet, ...] = (
    BiomedicalStarterConceptSet(
        name="Biomedical Gene Concepts",
        slug="biomedical-gene-concepts",
        domain_context="genomics",
        description=(
            "Starter canonical gene concepts seeded for biomedical graph spaces."
        ),
        members=(
            BiomedicalStarterConceptMember(
                canonical_label="MED13",
                dictionary_entry_id="GENE:MED13",
                sense_key="gene",
                aliases=("mediator complex subunit 13",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="MED13L",
                dictionary_entry_id="GENE:MED13L",
                sense_key="gene",
                aliases=("mediator complex subunit 13 like",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="CCNC",
                dictionary_entry_id="GENE:CCNC",
                sense_key="gene",
                aliases=("cyclin C",),
            ),
        ),
    ),
    BiomedicalStarterConceptSet(
        name="Biomedical Phenotype Concepts",
        slug="biomedical-phenotype-concepts",
        domain_context="clinical",
        description=(
            "Starter phenotype concepts commonly reused in biomedical curation."
        ),
        members=(
            BiomedicalStarterConceptMember(
                canonical_label="Developmental Delay",
                dictionary_entry_id="PHENOTYPE:DEVELOPMENTAL_DELAY",
                sense_key="phenotype",
                aliases=("global developmental delay",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Intellectual Disability",
                dictionary_entry_id="PHENOTYPE:INTELLECTUAL_DISABILITY",
                sense_key="phenotype",
                aliases=("ID",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Hypotonia",
                dictionary_entry_id="PHENOTYPE:HYPOTONIA",
                sense_key="phenotype",
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Dilated Cardiomyopathy",
                dictionary_entry_id="PHENOTYPE:DILATED_CARDIOMYOPATHY",
                sense_key="phenotype",
                aliases=("DCM",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Autism Spectrum Disorder",
                dictionary_entry_id="PHENOTYPE:AUTISM_SPECTRUM_DISORDER",
                sense_key="phenotype",
                aliases=("ASD",),
            ),
        ),
    ),
    BiomedicalStarterConceptSet(
        name="Biomedical Pathway Concepts",
        slug="biomedical-pathway-concepts",
        domain_context="genomics",
        description=(
            "Starter pathway and regulatory-program concepts for biomedical spaces."
        ),
        members=(
            BiomedicalStarterConceptMember(
                canonical_label="Wnt Signaling",
                dictionary_entry_id="PATHWAY:WNT_SIGNALING",
                sense_key="pathway",
                aliases=("Wnt signaling pathway",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Mediator Complex",
                dictionary_entry_id="PATHWAY:MEDIATOR_COMPLEX",
                sense_key="pathway",
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Transcriptional Regulation",
                dictionary_entry_id="PATHWAY:TRANSCRIPTIONAL_REGULATION",
                sense_key="pathway",
            ),
        ),
    ),
    BiomedicalStarterConceptSet(
        name="Biomedical Mechanism Concepts",
        slug="biomedical-mechanism-concepts",
        domain_context="genomics",
        description=(
            "Starter mechanism concepts used to normalize common biomedical claims."
        ),
        members=(
            BiomedicalStarterConceptMember(
                canonical_label="Loss of Function",
                dictionary_entry_id="MECHANISM:LOSS_OF_FUNCTION",
                sense_key="mechanism",
                aliases=("LOF",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Haploinsufficiency",
                dictionary_entry_id="MECHANISM:HAPLOINSUFFICIENCY",
                sense_key="mechanism",
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Dominant Negative",
                dictionary_entry_id="MECHANISM:DOMINANT_NEGATIVE",
                sense_key="mechanism",
                aliases=("dominant-negative",),
            ),
            BiomedicalStarterConceptMember(
                canonical_label="Transcriptional Dysregulation",
                dictionary_entry_id="MECHANISM:TRANSCRIPTIONAL_DYSREGULATION",
                sense_key="mechanism",
            ),
        ),
    ),
)


def _normalize_label(value: str) -> str:
    return " ".join(value.split())


def _normalize_alias(value: str) -> str:
    return _normalize_label(value).lower()


def _seed_uuid(*, space_id: UUID, category: str, key: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"graph-biomedical-starter:{space_id}:{category}:{key}",
    )


def _ensure_dictionary_primitives(session: Session) -> None:
    dictionary_repo = GraphDictionaryRepository(
        session,
        builtin_domain_contexts=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts
        ),
        builtin_entity_types=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_entity_types
        ),
        builtin_relation_types=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_relation_types
        ),
        builtin_relation_synonyms=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_relation_synonyms
        ),
    )
    dictionary_repo.seed_builtin_dictionary_entries()

    # Ensure entity resolution policies exist for every builtin entity type.
    # Without these, POST /v1/spaces/{space_id}/entities rejects all entity
    # creation with "Unknown entity_type" — blocking all evidence ingestion.
    # Uses the correct per-type defaults (e.g. VARIANT needs both
    # gene_symbol + hgvs_notation to avoid merging distinct variants).
    for entity_type_def in GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_entity_types:
        policy_strategy, required_anchors, auto_merge_threshold = (
            DictionaryManagementService._resolve_default_resolution_policy(
                entity_type_def.entity_type,
            )
        )
        dictionary_repo.create_resolution_policy(
            entity_type=entity_type_def.entity_type,
            policy_strategy=policy_strategy,
            required_anchors=list(required_anchors),
            auto_merge_threshold=auto_merge_threshold,
            created_by=_SEED_CREATED_BY,
            source_ref=_SEED_SOURCE,
        )


def seed_biomedical_starter_concepts(
    session: Session,
    *,
    research_space_id: UUID | str,
) -> None:
    """Seed one graph space with canonical biomedical starter concepts."""
    space_uuid = (
        research_space_id
        if isinstance(research_space_id, UUID)
        else UUID(str(research_space_id).strip())
    )
    _ensure_dictionary_primitives(session)
    concept_repository = GraphConceptRepository(session)

    for concept_set_definition in BIOMEDICAL_STARTER_CONCEPT_SETS:
        existing_set = session.scalar(
            select(ConceptSetModel).where(
                ConceptSetModel.research_space_id == space_uuid,
                ConceptSetModel.slug == concept_set_definition.slug,
            ),
        )
        if existing_set is None:
            concept_set = concept_repository.create_concept_set(
                set_id=str(
                    _seed_uuid(
                        space_id=space_uuid,
                        category="concept-set",
                        key=concept_set_definition.slug,
                    ),
                ),
                research_space_id=str(space_uuid),
                name=concept_set_definition.name,
                slug=concept_set_definition.slug,
                domain_context=concept_set_definition.domain_context,
                description=concept_set_definition.description,
                created_by=_SEED_CREATED_BY,
                source_ref=_SEED_SOURCE,
                review_status="ACTIVE",
            )
            concept_set_id = concept_set.id
        else:
            concept_set_id = str(existing_set.id)

        for member_definition in concept_set_definition.members:
            existing_member = session.scalar(
                select(ConceptMemberModel).where(
                    ConceptMemberModel.research_space_id == space_uuid,
                    ConceptMemberModel.dictionary_dimension
                    == _SEED_DICTIONARY_DIMENSION,
                    ConceptMemberModel.dictionary_entry_id
                    == member_definition.dictionary_entry_id,
                    ConceptMemberModel.is_active.is_(True),
                ),
            )
            if existing_member is None:
                concept_member = concept_repository.create_concept_member(
                    member_id=str(
                        _seed_uuid(
                            space_id=space_uuid,
                            category="concept-member",
                            key=member_definition.dictionary_entry_id,
                        ),
                    ),
                    concept_set_id=concept_set_id,
                    research_space_id=str(space_uuid),
                    domain_context=concept_set_definition.domain_context,
                    canonical_label=_normalize_label(member_definition.canonical_label),
                    normalized_label=_normalize_alias(
                        member_definition.canonical_label,
                    ),
                    sense_key=member_definition.sense_key,
                    dictionary_dimension=_SEED_DICTIONARY_DIMENSION,
                    dictionary_entry_id=member_definition.dictionary_entry_id,
                    is_provisional=False,
                    metadata_payload={
                        "seed_source": _SEED_SOURCE,
                        "seed_slug": concept_set_definition.slug,
                    },
                    created_by=_SEED_CREATED_BY,
                    source_ref=_SEED_SOURCE,
                    review_status="ACTIVE",
                )
                concept_member_id = concept_member.id
            else:
                concept_member_id = str(existing_member.id)

            for alias in member_definition.aliases:
                normalized_alias = _normalize_alias(alias)
                existing_alias = session.scalar(
                    select(ConceptAliasModel).where(
                        ConceptAliasModel.research_space_id == space_uuid,
                        ConceptAliasModel.domain_context
                        == concept_set_definition.domain_context,
                        ConceptAliasModel.alias_normalized == normalized_alias,
                        ConceptAliasModel.is_active.is_(True),
                    ),
                )
                if existing_alias is not None:
                    continue
                concept_repository.create_concept_alias(
                    concept_member_id=concept_member_id,
                    research_space_id=str(space_uuid),
                    domain_context=concept_set_definition.domain_context,
                    alias_label=_normalize_label(alias),
                    alias_normalized=normalized_alias,
                    source="seed",
                    created_by=_SEED_CREATED_BY,
                    source_ref=_SEED_SOURCE,
                    review_status="ACTIVE",
                )


def seed_biomedical_starter_concepts_for_existing_spaces(session: Session) -> None:
    """Seed every existing graph space with biomedical starter concepts."""
    space_ids = session.scalars(select(GraphSpaceModel.id).order_by(GraphSpaceModel.id))
    for space_id in space_ids:
        seed_biomedical_starter_concepts(
            session,
            research_space_id=space_id,
        )


__all__ = [
    "BIOMEDICAL_STARTER_CONCEPT_SETS",
    "seed_biomedical_starter_concepts",
    "seed_biomedical_starter_concepts_for_existing_spaces",
]
