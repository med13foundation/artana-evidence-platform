"""Ontology-normalized convergence query tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.dependencies import (
    get_proposal_store,
    get_research_space_store,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_init.convergence import (
    OntologyConvergenceQueryRequest,
    run_ontology_convergence_query,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from fastapi.testclient import TestClient

_TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_AUTH_HEADERS = {
    "X-TEST-USER-ID": str(_TEST_USER_ID),
    "X-TEST-USER-EMAIL": "convergence@example.com",
    "X-TEST-USER-ROLE": "researcher",
}


def test_convergence_query_groups_by_ontology_id_and_preserves_provenance() -> None:
    proposal_store = HarnessProposalStore()
    space_id = uuid4()
    _seed_convergence_claims(proposal_store=proposal_store, space_id=space_id)

    response = run_ontology_convergence_query(
        space_id=space_id,
        request=OntologyConvergenceQueryRequest(
            gene_set=("MED6", "MED11", "MED23", "MED25"),
            min_gene_count=2,
        ),
        proposal_store=proposal_store,
    )

    nodes_by_id = {node.ontology_id: node for node in response.nodes}
    seizure = nodes_by_id["HP:0001250"]
    assert seizure.label == "Seizure"
    assert seizure.contributing_genes == ["MED6", "MED11"]
    assert seizure.claim_count == 2
    assert seizure.human_claim_count == 2
    assert seizure.model_organism_claim_count == 0
    assert seizure.specificity == "generic_ndd"

    atrial_septal_defect = nodes_by_id["HP:0001631"]
    assert atrial_septal_defect.contributing_genes == ["MED23", "MED25"]
    assert atrial_septal_defect.human_claim_count == 1
    assert atrial_septal_defect.model_organism_claim_count == 1
    assert atrial_septal_defect.specificity == "organ_or_module_specific"
    assert "HP:0001631" in response.report_markdown

    assert "Infantile onset" not in {
        node.label for node in response.nodes
    }


def test_convergence_query_honors_provenance_filter_after_grouping() -> None:
    proposal_store = HarnessProposalStore()
    space_id = uuid4()
    _seed_convergence_claims(proposal_store=proposal_store, space_id=space_id)

    response = run_ontology_convergence_query(
        space_id=space_id,
        request=OntologyConvergenceQueryRequest(
            gene_set=("MED6", "MED11", "MED23", "MED25"),
            min_gene_count=2,
            provenance_filter="human",
        ),
        proposal_store=proposal_store,
    )

    assert [node.ontology_id for node in response.nodes] == ["HP:0001250"]
    assert response.nodes[0].human_claim_count == 2
    assert response.nodes[0].model_organism_claim_count == 0


def test_convergence_query_route_returns_queryable_result_and_report() -> None:
    built = _build_client()

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/convergence-queries",
        headers=_AUTH_HEADERS,
        json={
            "gene_set": ["MED6", "MED11", "MED23", "MED25"],
            "min_gene_count": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["gene_set"] == ["MED6", "MED11", "MED23", "MED25"]
    assert [node["ontology_id"] for node in payload["nodes"]] == [
        "HP:0001250",
        "HP:0001631",
    ]
    assert payload["nodes"][1]["model_organism_claim_count"] == 1
    assert "| ontology_id | label | genes |" in payload["report_markdown"]


class _BuiltClient:
    def __init__(self, *, client: TestClient, space_id: UUID) -> None:
        self.client = client
        self.space_id = space_id


def _build_client() -> _BuiltClient:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Convergence",
        description="Owned test space for convergence queries.",
    )
    proposal_store = HarnessProposalStore()
    _seed_convergence_claims(
        proposal_store=proposal_store,
        space_id=UUID(space.id),
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    return _BuiltClient(client=TestClient(app), space_id=UUID(space.id))


def _seed_convergence_claims(
    *,
    proposal_store: HarnessProposalStore,
    space_id: UUID,
) -> None:
    run_id = uuid4()
    proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            _claim(
                gene="MED6",
                label="Seizure",
                ontology_id="HP:0001250",
                source_kind="pubmed",
            ),
            _claim(
                gene="MED11",
                label="seizures",
                ontology_id="HP:0001250",
                source_kind="pubmed",
            ),
            _claim(
                gene="MED18",
                label="Infantile onset",
                ontology_id="",
                source_kind="pubmed",
                node_kind="onset_qualifier",
            ),
            _claim(
                gene="MED23",
                label="Atrial septal defect",
                ontology_id="HP:0001631",
                source_kind="pubmed",
            ),
            _claim(
                gene="MED25",
                label="Atrial septal defect",
                ontology_id="HP:0001631",
                source_kind="mgi_enrichment",
                provenance="model_organism",
            ),
            _claim(
                gene="BRCA1",
                label="Seizure",
                ontology_id="HP:0001250",
                source_kind="pubmed",
            ),
        ),
    )
    for proposal in proposals:
        proposal_store.decide_proposal(
            space_id=space_id,
            proposal_id=proposal.id,
            status="promoted",
            decision_reason="seeded convergence claim",
        )


def _claim(
    *,
    gene: str,
    label: str,
    ontology_id: str,
    source_kind: str,
    provenance: str = "human",
    node_kind: str = "phenotype",
) -> HarnessProposalDraft:
    identifiers = {"ontology_id": ontology_id} if ontology_id else {}
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind=source_kind,
        source_key=f"{source_kind}:{gene}:{label}",
        title=f"{gene} associated with {label}",
        summary=f"{gene} has reported association with {label}.",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[{"quote": f"{gene} association with {label}."}],
        payload={
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_subject": gene,
            "proposed_subject_label": gene,
            "proposed_object": label,
            "proposed_object_label": label,
            "proposed_object_entity_candidate": {
                "label": label,
                "entity_type": node_kind,
                "identifiers": identifiers,
            },
        },
        metadata={
            "gene_symbol": gene,
            "node_kind": node_kind,
            "provenance": provenance,
            "ontology_id": ontology_id,
        },
        claim_fingerprint=f"{gene}:{ontology_id or label}",
    )
