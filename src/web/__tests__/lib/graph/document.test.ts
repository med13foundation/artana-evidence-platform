import {
  buildClaimEvidencePreviewIndex,
  buildGraphModelFromDocument,
} from '@/lib/graph/document'
import { projectGraphByDisplayMode } from '@/lib/graph/model'
import type { KernelGraphDocumentResponse } from '@/types/kernel'

function makeGraphDocument(): KernelGraphDocumentResponse {
  return {
    nodes: [
      {
        id: 'n1',
        resource_id: 'n1',
        kind: 'ENTITY',
        type_label: 'GENE',
        label: 'MED13',
        confidence: null,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: null,
        metadata: {},
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 'n2',
        resource_id: 'n2',
        kind: 'ENTITY',
        type_label: 'PHENOTYPE',
        label: 'Cardiomyopathy',
        confidence: null,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: null,
        metadata: {},
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 'claim:claim-1',
        resource_id: 'claim-1',
        kind: 'CLAIM',
        type_label: 'CLAIM',
        label: 'MED13 may support cardiomyopathy',
        confidence: 0.84,
        curation_status: null,
        claim_status: 'OPEN',
        polarity: 'SUPPORT',
        canonical_relation_id: 'e1',
        metadata: {
          relation_type: 'ASSOCIATED_WITH',
          claim_text: 'MED13 may support cardiomyopathy',
        },
        created_at: '2026-03-02T00:00:00Z',
        updated_at: '2026-03-02T00:00:00Z',
      },
      {
        id: 'evidence:ev-1',
        resource_id: 'ev-1',
        kind: 'EVIDENCE',
        type_label: 'PAPER_EVIDENCE',
        label: 'PubMed evidence',
        confidence: 0.92,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: 'e1',
        metadata: {
          claim_id: 'claim-1',
          sentence: 'Expression of human CNOT1 rescues learning defects.',
          sentence_source: 'verbatim_span',
          sentence_confidence: 'high',
          paper_links: [
            {
              label: 'PubMed',
              url: 'https://pubmed.ncbi.nlm.nih.gov/40214304/',
              source: 'external_record_id',
            },
          ],
          raw_metadata: {
            pmid: '40214304',
          },
        },
        created_at: '2026-03-03T00:00:00Z',
        updated_at: '2026-03-03T00:00:00Z',
      },
    ],
    edges: [
      {
        id: 'e1',
        resource_id: 'e1',
        kind: 'CANONICAL_RELATION',
        source_id: 'n1',
        target_id: 'n2',
        type_label: 'ASSOCIATED_WITH',
        label: 'ASSOCIATED_WITH',
        confidence: 0.91,
        curation_status: 'APPROVED',
        claim_id: null,
        canonical_relation_id: 'e1',
        evidence_id: null,
        metadata: {
          source_count: 2,
          highest_evidence_tier: 'LITERATURE',
          support_claim_count: 1,
          refute_claim_count: 0,
          has_conflict: false,
          linked_claim_ids: ['claim-1'],
        },
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 'claim-participant:cp-1',
        resource_id: 'cp-1',
        kind: 'CLAIM_PARTICIPANT',
        source_id: 'n1',
        target_id: 'claim:claim-1',
        type_label: 'SUBJECT',
        label: 'Subject',
        confidence: 0.84,
        curation_status: null,
        claim_id: 'claim-1',
        canonical_relation_id: 'e1',
        evidence_id: null,
        metadata: {},
        created_at: '2026-03-02T00:00:00Z',
        updated_at: '2026-03-02T00:00:00Z',
      },
      {
        id: 'claim-participant:cp-2',
        resource_id: 'cp-2',
        kind: 'CLAIM_PARTICIPANT',
        source_id: 'n2',
        target_id: 'claim:claim-1',
        type_label: 'OBJECT',
        label: 'Object',
        confidence: 0.84,
        curation_status: null,
        claim_id: 'claim-1',
        canonical_relation_id: 'e1',
        evidence_id: null,
        metadata: {},
        created_at: '2026-03-02T00:00:00Z',
        updated_at: '2026-03-02T00:00:00Z',
      },
      {
        id: 'claim-evidence:ev-1',
        resource_id: 'ev-1',
        kind: 'CLAIM_EVIDENCE',
        source_id: 'claim:claim-1',
        target_id: 'evidence:ev-1',
        type_label: 'EVIDENCE',
        label: 'Evidence',
        confidence: 0.92,
        curation_status: null,
        claim_id: 'claim-1',
        canonical_relation_id: 'e1',
        evidence_id: 'ev-1',
        metadata: {},
        created_at: '2026-03-03T00:00:00Z',
        updated_at: '2026-03-03T00:00:00Z',
      },
    ],
    meta: {
      mode: 'seeded',
      seed_entity_ids: ['n1'],
      requested_depth: 1,
      requested_top_k: 25,
      pre_cap_entity_node_count: 2,
      pre_cap_canonical_edge_count: 1,
      truncated_entity_nodes: false,
      truncated_canonical_edges: false,
      included_claims: true,
      included_evidence: true,
      max_claims: 250,
      evidence_limit_per_claim: 3,
      counts: {
        entity_nodes: 2,
        claim_nodes: 1,
        evidence_nodes: 1,
        canonical_edges: 1,
        claim_participant_edges: 2,
        claim_evidence_edges: 1,
      },
    },
  }
}

describe('graph document adapter', () => {
  it('normalizes document nodes and edges into the graph model', () => {
    const model = buildGraphModelFromDocument(makeGraphDocument())

    expect(model.nodeById['claim:claim-1']?.origin).toBe('claim')
    expect(model.nodeById['claim:claim-1']?.claimText).toBe('MED13 may support cardiomyopathy')
    expect(model.nodeById['evidence:ev-1']?.origin).toBe('evidence')
    expect(model.nodeById['evidence:ev-1']?.entityType).toBe('PAPER')
    expect(model.edgeById.e1?.canonicalClaimCount).toBe(1)
    expect(model.edgeById['claim-participant:cp-1']?.claimStatus).toBe('OPEN')
    expect(model.edgeById['claim-evidence:ev-1']?.relationType).toBe('SUPPORTED_BY')
    expect(model.edgeById['claim-evidence:ev-1']?.evidenceSourceBadge).toBe('PMID: 40214304')
  })

  it('keeps evidence out of claims mode while preserving in-memory previews', () => {
    const model = buildGraphModelFromDocument(makeGraphDocument())
    const claimsMode = projectGraphByDisplayMode(model, 'CLAIMS')
    const previews = buildClaimEvidencePreviewIndex(model)

    expect(claimsMode.edges.some((edge) => edge.origin === 'evidence')).toBe(false)
    expect(claimsMode.nodes.some((node) => node.origin === 'evidence')).toBe(false)
    expect(previews['claim-1']).toEqual({
      state: 'ready',
      sentence: 'Expression of human CNOT1 rescues learning defects.',
      sourceLabel: 'PMID: 40214304',
    })
  })
})
