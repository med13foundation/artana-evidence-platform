"""Runtime logic for ontology-normalized convergence queries."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.proposal_store import (
    HarnessProposalRecord,
    HarnessProposalStore,
)

from .contracts import (
    ConvergenceProvenance,
    ConvergenceSpecificity,
    OntologyConvergenceClaimResponse,
    OntologyConvergenceNodeResponse,
    OntologyConvergenceQueryRequest,
    OntologyConvergenceQueryResponse,
)

_TEXT_NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")
_CURIE_PATTERN = re.compile(r"^([A-Za-z]+)[:_](.+)$")
_KNOWN_ONTOLOGY_PREFIXES = frozenset({"GO", "HP", "MONDO", "MP"})
_ONTOLOGY_ID_KEYS = (
    "ontology_id",
    "ontology_curie",
    "normalized_id",
    "hpo_id",
    "hpo_curie",
    "hp_id",
    "mp_id",
    "mp_curie",
    "mondo_id",
    "mondo_curie",
    "go_id",
    "go_curie",
    "id",
)
_LABEL_KEYS = (
    "proposed_object_label",
    "object_label",
    "target_label",
    "display_label",
    "label",
    "hpo_term",
    "disease",
    "phenotype",
    "process",
    "name",
)
_GENE_KEYS = (
    "gene_symbol",
    "gene",
    "proposed_subject_label",
    "subject_label",
    "subject",
    "proposed_subject",
)
_NODE_TYPE_KEYS = ("node_kind", "entity_type", "target_type", "object_type")
_CONVERGENCE_NODE_TYPES = frozenset(
    {
        "phenotype",
        "disease",
        "process",
        "biological_process",
        "molecular_function",
        "pathway",
        "ontology_term",
    },
)
_MODEL_ORGANISM_MARKERS = (
    "model_organism",
    "model organism",
    "mgi",
    "zfin",
    "mouse",
    "murine",
    "zebrafish",
    "danio rerio",
)
_GENERIC_NDD_MARKERS = (
    "developmental delay",
    "global developmental delay",
    "intellectual disability",
    "neurodevelopment",
    "seizure",
    "epilepsy",
)
_ORGAN_OR_MODULE_MARKERS = (
    "atrial",
    "cardiac",
    "heart",
    "septal",
    "ventricular",
    "renal",
    "kidney",
    "craniofacial",
    "skeletal",
    "mediator",
    "module",
)


@dataclass(frozen=True, slots=True)
class _ClaimNode:
    proposal: HarnessProposalRecord
    gene_symbol: str
    label: str
    ontology_id: str | None
    normalized_key: str
    provenance: ConvergenceProvenance


@dataclass(slots=True)
class _NodeAccumulator:
    ontology_id: str | None
    normalized_key: str
    labels: Counter[str] = field(default_factory=Counter)
    claims: list[_ClaimNode] = field(default_factory=list)
    genes: set[str] = field(default_factory=set)

    def add(self, claim: _ClaimNode) -> None:
        self.labels[claim.label] += 1
        self.claims.append(claim)
        self.genes.add(claim.gene_symbol)


def run_ontology_convergence_query(
    *,
    space_id: UUID,
    request: OntologyConvergenceQueryRequest,
    proposal_store: HarnessProposalStore,
) -> OntologyConvergenceQueryResponse:
    """Group promoted claims into ontology-normalized cross-gene nodes."""

    gene_index = {gene: gene for gene in request.gene_set}
    gene_rank = {gene: index for index, gene in enumerate(request.gene_set)}
    groups: dict[str, _NodeAccumulator] = {}
    for proposal in proposal_store.list_proposals(
        space_id=space_id,
        status="promoted",
    ):
        claim_node = _claim_node_from_proposal(
            proposal=proposal,
            gene_index=gene_index,
        )
        if claim_node is None:
            continue
        if not _matches_provenance_filter(
            claim_node.provenance,
            request.provenance_filter,
        ):
            continue
        group = groups.setdefault(
            claim_node.normalized_key,
            _NodeAccumulator(
                ontology_id=claim_node.ontology_id,
                normalized_key=claim_node.normalized_key,
            ),
        )
        group.add(claim_node)

    nodes = [
        _node_response(group, gene_rank=gene_rank)
        for group in groups.values()
        if len(group.genes) >= request.min_gene_count
    ]
    nodes.sort(
        key=lambda node: (
            -node.claim_count,
            -len(node.contributing_genes),
            min(
                gene_rank.get(gene, len(gene_rank))
                for gene in node.contributing_genes
            ),
            node.ontology_id or "",
            node.label.casefold(),
        ),
    )
    return OntologyConvergenceQueryResponse(
        id=uuid4(),
        space_id=space_id,
        query=request,
        nodes=nodes,
        report_markdown=_report_markdown(nodes) if request.include_report else "",
        generated_at=datetime.now(UTC),
    )


def _claim_node_from_proposal(
    *,
    proposal: HarnessProposalRecord,
    gene_index: Mapping[str, str],
) -> _ClaimNode | None:
    gene_symbol = _extract_gene_symbol(proposal=proposal, gene_index=gene_index)
    if gene_symbol is None:
        return None
    label = _extract_node_label(proposal)
    if label == "":
        return None
    ontology_id = _extract_ontology_id(proposal)
    if not _is_convergence_node(proposal=proposal, label=label):
        return None
    normalized_key = ontology_id or f"text:{_normalize_label(label)}"
    if normalized_key == "text:":
        return None
    return _ClaimNode(
        proposal=proposal,
        gene_symbol=gene_symbol,
        label=label,
        ontology_id=ontology_id,
        normalized_key=normalized_key,
        provenance=_classify_provenance(proposal),
    )


def _extract_gene_symbol(
    *,
    proposal: HarnessProposalRecord,
    gene_index: Mapping[str, str],
) -> str | None:
    for raw_value in _proposal_text_values(
        proposal=proposal,
        keys=_GENE_KEYS,
        include_nested=True,
    ):
        gene = _normalize_gene_symbol(raw_value)
        if gene in gene_index:
            return gene_index[gene]
        if ":" in raw_value:
            suffix_gene = _normalize_gene_symbol(raw_value.rsplit(":", 1)[-1])
            if suffix_gene in gene_index:
                return gene_index[suffix_gene]
    return None


def _extract_node_label(proposal: HarnessProposalRecord) -> str:
    for raw_value in _proposal_text_values(
        proposal=proposal,
        keys=_LABEL_KEYS,
        include_nested=True,
    ):
        label = " ".join(raw_value.split())
        if label:
            return label
    return ""


def _extract_ontology_id(proposal: HarnessProposalRecord) -> str | None:
    for key, raw_value in _proposal_keyed_text_values(
        proposal=proposal,
        keys=_ONTOLOGY_ID_KEYS,
        include_nested=True,
    ):
        normalized = _normalize_ontology_id(raw_value, key=key)
        if normalized is not None:
            return normalized
    return None


def _is_convergence_node(
    *,
    proposal: HarnessProposalRecord,
    label: str,
) -> bool:
    node_type = _first_node_type(proposal)
    if node_type and node_type not in _CONVERGENCE_NODE_TYPES:
        return False
    normalized_label = _normalize_label(label)
    return " onset " not in f" {normalized_label} "


def _first_node_type(proposal: HarnessProposalRecord) -> str:
    for raw_value in _proposal_text_values(
        proposal=proposal,
        keys=_NODE_TYPE_KEYS,
        include_nested=True,
    ):
        normalized = _normalize_label(raw_value)
        if normalized:
            return normalized
    return ""


def _matches_provenance_filter(
    provenance: ConvergenceProvenance,
    provenance_filter: str,
) -> bool:
    return provenance_filter in ("all", provenance)


def _classify_provenance(
    proposal: HarnessProposalRecord,
) -> ConvergenceProvenance:
    text = " ".join(
        (
            proposal.proposal_type,
            proposal.source_kind,
            proposal.source_key,
            _flatten_text(proposal.payload),
            _flatten_text(proposal.metadata),
        ),
    ).casefold()
    if any(marker in text for marker in _MODEL_ORGANISM_MARKERS):
        return "model_organism"
    return "human"


def _node_response(
    group: _NodeAccumulator,
    *,
    gene_rank: Mapping[str, int],
) -> OntologyConvergenceNodeResponse:
    label = _preferred_label(group.labels)
    claims = [_claim_response(claim) for claim in group.claims]
    human_count = sum(1 for claim in group.claims if claim.provenance == "human")
    model_organism_count = len(group.claims) - human_count
    return OntologyConvergenceNodeResponse(
        ontology_id=group.ontology_id,
        normalized_key=group.normalized_key,
        label=label,
        synonyms=_synonyms(labels=group.labels, preferred_label=label),
        contributing_genes=sorted(
            group.genes,
            key=lambda gene: (gene_rank.get(gene, len(gene_rank)), gene),
        ),
        claim_count=len(group.claims),
        human_claim_count=human_count,
        model_organism_claim_count=model_organism_count,
        specificity=_specificity(label),
        claims=claims,
    )


def _claim_response(claim: _ClaimNode) -> OntologyConvergenceClaimResponse:
    proposal = claim.proposal
    return OntologyConvergenceClaimResponse(
        proposal_id=proposal.id,
        gene_symbol=claim.gene_symbol,
        label=claim.label,
        ontology_id=claim.ontology_id,
        provenance=claim.provenance,
        title=proposal.title,
        source_kind=proposal.source_kind,
        source_key=proposal.source_key,
        evidence_grade=proposal.evidence_grade,
        confidence=proposal.confidence,
    )


def _specificity(label: str) -> ConvergenceSpecificity:
    normalized = _normalize_label(label)
    if any(marker in normalized for marker in _ORGAN_OR_MODULE_MARKERS):
        return "organ_or_module_specific"
    if any(marker in normalized for marker in _GENERIC_NDD_MARKERS):
        return "generic_ndd"
    return "unclassified"


def _preferred_label(labels: Counter[str]) -> str:
    if not labels:
        return ""
    return sorted(labels.items(), key=lambda item: (-item[1], item[0].casefold()))[0][0]


def _synonyms(
    *,
    labels: Counter[str],
    preferred_label: str,
) -> list[str]:
    preferred_key = preferred_label.casefold()
    return sorted(
        (
            label
            for label in labels
            if label.casefold() != preferred_key
        ),
        key=str.casefold,
    )


def _report_markdown(nodes: Sequence[OntologyConvergenceNodeResponse]) -> str:
    lines = [
        "| ontology_id | label | genes | claims | human | model_organism | specificity |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        " | ".join(
            (
                f"| {node.ontology_id or '-'}",
                node.label,
                ", ".join(node.contributing_genes),
                str(node.claim_count),
                str(node.human_claim_count),
                str(node.model_organism_claim_count),
                f"{node.specificity} |",
            ),
        )
        for node in nodes
    )
    return "\n".join(lines)


def _proposal_text_values(
    *,
    proposal: HarnessProposalRecord,
    keys: Sequence[str],
    include_nested: bool,
) -> Iterable[str]:
    for _, value in _proposal_keyed_text_values(
        proposal=proposal,
        keys=keys,
        include_nested=include_nested,
    ):
        yield value


def _proposal_keyed_text_values(
    *,
    proposal: HarnessProposalRecord,
    keys: Sequence[str],
    include_nested: bool,
) -> Iterable[tuple[str, str]]:
    for source in (proposal.payload, proposal.metadata):
        yield from _keyed_text_values(
            source,
            keys=frozenset(keys),
            include_nested=include_nested,
        )


def _keyed_text_values(
    value: object,
    *,
    keys: frozenset[str],
    include_nested: bool,
) -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for raw_key, raw_value in value.items():
            if isinstance(raw_key, str) and raw_key in keys:
                for text in _string_values(raw_value):
                    yield raw_key, text
            if include_nested and _should_scan_nested(raw_key, raw_value):
                yield from _keyed_text_values(
                    raw_value,
                    keys=keys,
                    include_nested=include_nested,
                )
    elif include_nested and isinstance(value, list | tuple):
        for item in value:
            yield from _keyed_text_values(
                item,
                keys=keys,
                include_nested=include_nested,
            )


def _should_scan_nested(key: object, value: object) -> bool:
    if not isinstance(value, Mapping | list | tuple):
        return False
    if not isinstance(key, str):
        return True
    return key in {
        "anchors",
        "identifiers",
        "metadata",
        "proposed_subject_entity_candidate",
        "proposed_object_entity_candidate",
        "subject_entity_candidate",
        "object_entity_candidate",
        "target_entity_candidate",
    }


def _string_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        stripped = " ".join(value.split())
        if stripped:
            yield stripped
    elif isinstance(value, int | float):
        yield str(value)


def _normalize_ontology_id(value: str, *, key: str) -> str | None:
    normalized = value.strip().replace("_", ":")
    if not normalized:
        return None
    match = _CURIE_PATTERN.match(normalized)
    if match is not None:
        prefix, identifier = match.groups()
        prefix = "HP" if prefix.casefold() == "hpo" else prefix.upper()
        if prefix not in _KNOWN_ONTOLOGY_PREFIXES:
            return None
        return f"{prefix}:{identifier}"
    if normalized.isdigit():
        prefix = _ontology_prefix_for_key(key)
        if prefix is not None:
            return f"{prefix}:{normalized.zfill(7)}"
    return None


def _ontology_prefix_for_key(key: str) -> str | None:
    if key.startswith(("hpo", "hp")):
        return "HP"
    if key.startswith("mp"):
        return "MP"
    if key.startswith("mondo"):
        return "MONDO"
    if key.startswith("go"):
        return "GO"
    return None


def _normalize_gene_symbol(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "", value).upper()


def _normalize_label(value: str) -> str:
    return _TEXT_NORMALIZATION_PATTERN.sub(" ", value.casefold()).strip()


def _flatten_text(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(
            _flatten_text(item)
            for item in value.values()
        )
    if isinstance(value, list | tuple):
        return " ".join(_flatten_text(item) for item in value)
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return ""


__all__ = ["run_ontology_convergence_query"]
