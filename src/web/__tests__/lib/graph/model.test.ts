import {
  augmentGraphModelWithClaimEvidence,
  buildGraphModel,
  filterGraphModel,
  mergeGraphModelWithRelationClaims,
  mergeGraphModels,
  projectGraphByDisplayMode,
  pruneGraphModelForRender,
  resolveEvidenceArticleUrlFromMetadata,
} from '@/lib/graph/model'
import type {
  ClaimEvidenceResponse,
  ClaimParticipantResponse,
  KernelGraphSubgraphResponse,
  RelationClaimResponse,
} from '@/types/kernel'

function makeSubgraphResponse(): KernelGraphSubgraphResponse {
  return {
    nodes: [
      {
        id: 'n1',
        research_space_id: 'space-1',
        entity_type: 'GENE',
        display_label: 'MED13',
        aliases: [],
        metadata: {},
        created_at: '2026-02-20T00:00:00Z',
        updated_at: '2026-02-20T00:00:00Z',
      },
      {
        id: 'n2',
        research_space_id: 'space-1',
        entity_type: 'PHENOTYPE',
        display_label: 'Cardiomyopathy',
        aliases: [],
        metadata: {},
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
      {
        id: 'n3',
        research_space_id: 'space-1',
        entity_type: 'PHENOTYPE',
        display_label: 'Arrhythmia',
        aliases: [],
        metadata: {},
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
    ],
    edges: [
      {
        id: 'e1',
        research_space_id: 'space-1',
        source_id: 'n1',
        relation_type: 'ASSOCIATED_WITH',
        target_id: 'n2',
        aggregate_confidence: 0.91,
        source_count: 2,
        highest_evidence_tier: 'LITERATURE',
        curation_status: 'APPROVED',
        provenance_id: null,
        reviewed_by: null,
        reviewed_at: null,
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
      {
        id: 'e2',
        research_space_id: 'space-1',
        source_id: 'n1',
        relation_type: 'CO_OCCURS_WITH',
        target_id: 'n3',
        aggregate_confidence: 0.52,
        source_count: 1,
        highest_evidence_tier: 'COMPUTATIONAL',
        curation_status: 'DRAFT',
        provenance_id: null,
        reviewed_by: null,
        reviewed_at: null,
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
    ],
    meta: {
      mode: 'starter',
      seed_entity_ids: [],
      requested_depth: 2,
      requested_top_k: 25,
      pre_cap_node_count: 3,
      pre_cap_edge_count: 2,
      truncated_nodes: false,
      truncated_edges: false,
    },
  }
}

describe('graph model', () => {
  it('normalizes nodes and edges from subgraph response', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    expect(model.stats.nodeCount).toBe(3)
    expect(model.stats.edgeCount).toBe(2)
    expect(model.nodeById.n1.label).toBe('MED13')
    expect(model.edgeById.e1.confidence).toBeCloseTo(0.91)
  })

  it('merges incoming graph without duplicating existing nodes/edges', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const incoming = buildGraphModel({
      nodes: [
        ...makeSubgraphResponse().nodes,
        {
          id: 'n4',
          research_space_id: 'space-1',
          entity_type: 'PHENOTYPE',
          display_label: 'Bradycardia',
          aliases: [],
          metadata: {},
          created_at: '2026-02-23T00:00:00Z',
          updated_at: '2026-02-23T00:00:00Z',
        },
      ],
      edges: [
        ...makeSubgraphResponse().edges,
        {
          id: 'e3',
          research_space_id: 'space-1',
          source_id: 'n1',
          relation_type: 'ASSOCIATED_WITH',
          target_id: 'n4',
          aggregate_confidence: 0.74,
          source_count: 1,
          highest_evidence_tier: 'LITERATURE',
          curation_status: 'UNDER_REVIEW',
          provenance_id: null,
          reviewed_by: null,
          reviewed_at: null,
          created_at: '2026-02-23T00:00:00Z',
          updated_at: '2026-02-23T00:00:00Z',
        },
      ],
    })

    const merged = mergeGraphModels(base, incoming)
    expect(merged.stats.nodeCount).toBe(4)
    expect(merged.stats.edgeCount).toBe(3)
  })

  it('filters by relation type and curation status', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    const filtered = filterGraphModel(
      model,
      new Set(['ASSOCIATED_WITH']),
      new Set(['APPROVED']),
    )
    expect(filtered.stats.edgeCount).toBe(1)
    expect(filtered.edges[0]?.relationType).toBe('ASSOCIATED_WITH')
    expect(filtered.edges[0]?.curationStatus).toBe('APPROVED')
  })

  it('prunes graph to render caps', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    const pruned = pruneGraphModelForRender(model, 2, 1)
    expect(pruned.model.stats.nodeCount).toBeLessThanOrEqual(2)
    expect(pruned.model.stats.edgeCount).toBeLessThanOrEqual(1)
    expect(pruned.truncatedNodes || pruned.truncatedEdges).toBe(true)
  })

  it('renders relation claims as explicit claim nodes with polarity metadata', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const claims: RelationClaimResponse[] = [
      {
        id: 'claim-1',
        research_space_id: 'space-1',
        source_type: 'GENE',
        source_label: 'MED13',
        target_type: 'PHENOTYPE',
        target_label: 'Cardiomyopathy',
        relation_type: 'ASSOCIATED_WITH',
        source_document_id: null,
        agent_run_id: null,
        confidence: 0.85,
        validation_state: 'ALLOWED',
        validation_reason: null,
        persistability: 'PERSISTABLE',
        claim_status: 'NEEDS_MAPPING',
        polarity: 'SUPPORT',
        claim_text: 'MED13 supports cardiomyopathy evidence.',
        claim_section: null,
        linked_relation_id: 'e1',
        metadata: {},
        triaged_by: null,
        triaged_at: null,
        created_at: '2026-03-04T00:00:00Z',
        updated_at: '2026-03-04T00:00:00Z',
      },
    ]

    const merged = mergeGraphModelWithRelationClaims(base, claims)
    const claimNode = merged.nodeById['claim-node:claim-1']
    const canonicalEdge = merged.edgeById.e1
    expect(claimNode).toBeDefined()
    expect(claimNode?.origin).toBe('claim')
    expect(claimNode?.claimPolarity).toBe('SUPPORT')
    expect(claimNode?.claimStatus).toBe('NEEDS_MAPPING')
    expect(claimNode?.claimText).toBe('MED13 supports cardiomyopathy evidence.')
    expect(canonicalEdge?.canonicalClaimCount).toBe(1)
    expect(canonicalEdge?.linkedClaimIds).toEqual(['claim-1'])
    expect(merged.edgeById['claim:claim-1:subject']).toBeDefined()
    expect(merged.edgeById['claim:claim-1:object']).toBeDefined()
  })

  it('uses claim participants to build role-based claim edges when available', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const claims: RelationClaimResponse[] = [
      {
        id: 'claim-roles-1',
        research_space_id: 'space-1',
        source_type: 'GENE',
        source_label: 'MED13',
        target_type: 'PHENOTYPE',
        target_label: 'Cardiomyopathy',
        relation_type: 'ASSOCIATED_WITH',
        source_document_id: null,
        agent_run_id: null,
        confidence: 0.88,
        validation_state: 'ALLOWED',
        validation_reason: null,
        persistability: 'PERSISTABLE',
        claim_status: 'NEEDS_MAPPING',
        polarity: 'SUPPORT',
        claim_text: 'Human wild-type CNOT1 rescues learning defects in Drosophila.',
        claim_section: null,
        linked_relation_id: 'e1',
        metadata: {},
        triaged_by: null,
        triaged_at: null,
        created_at: '2026-03-04T00:00:00Z',
        updated_at: '2026-03-04T00:00:00Z',
      },
    ]
    const participants: Record<string, ClaimParticipantResponse[]> = {
      'claim-roles-1': [
        {
          id: 'p-1',
          claim_id: 'claim-roles-1',
          research_space_id: 'space-1',
          label: 'MED13',
          entity_id: 'n1',
          role: 'SUBJECT',
          position: 0,
          qualifiers: {},
          created_at: '2026-03-04T00:00:00Z',
        },
        {
          id: 'p-2',
          claim_id: 'claim-roles-1',
          research_space_id: 'space-1',
          label: 'human wild-type CNOT1 (transgene)',
          entity_id: null,
          role: 'CONTEXT',
          position: 1,
          qualifiers: {},
          created_at: '2026-03-04T00:00:00Z',
        },
        {
          id: 'p-3',
          claim_id: 'claim-roles-1',
          research_space_id: 'space-1',
          label: 'learning defects (Drosophila)',
          entity_id: null,
          role: 'OUTCOME',
          position: 2,
          qualifiers: {},
          created_at: '2026-03-04T00:00:00Z',
        },
      ],
    }

    const merged = mergeGraphModelWithRelationClaims(base, claims, participants)
    const subjectEdge = merged.edgeById['claim:claim-roles-1:participant:p-1']
    const contextEdge = merged.edgeById['claim:claim-roles-1:participant:p-2']
    const outcomeEdge = merged.edgeById['claim:claim-roles-1:participant:p-3']

    expect(subjectEdge).toBeDefined()
    expect(contextEdge).toBeDefined()
    expect(outcomeEdge).toBeDefined()
    expect(subjectEdge?.relationType).toBe('SUBJECT')
    expect(contextEdge?.relationType).toBe('CONTEXT')
    expect(outcomeEdge?.relationType).toBe('OUTCOME')
    expect(subjectEdge?.claimParticipantRole).toBe('SUBJECT')
    expect(contextEdge?.claimParticipantRole).toBe('CONTEXT')
    expect(outcomeEdge?.claimParticipantRole).toBe('OUTCOME')
    expect(subjectEdge?.targetId).toBe('claim-node:claim-roles-1')
    expect(contextEdge?.targetId).toBe('claim-node:claim-roles-1')
    expect(outcomeEdge?.targetId).toBe('claim-node:claim-roles-1')
    expect(merged.edgeById['claim:claim-roles-1:subject']).toBeUndefined()
    expect(merged.edgeById['claim:claim-roles-1:object']).toBeUndefined()
  })

  it('projects relations-only mode by removing claim overlay edges', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const claims: RelationClaimResponse[] = [
      {
        id: 'claim-mode-1',
        research_space_id: 'space-1',
        source_type: 'GENE',
        source_label: 'MED13',
        target_type: 'PHENOTYPE',
        target_label: 'Cardiomyopathy',
        relation_type: 'ASSOCIATED_WITH',
        source_document_id: null,
        agent_run_id: null,
        confidence: 0.85,
        validation_state: 'ALLOWED',
        validation_reason: null,
        persistability: 'PERSISTABLE',
        claim_status: 'NEEDS_MAPPING',
        polarity: 'SUPPORT',
        claim_text: 'Claim text',
        claim_section: null,
        linked_relation_id: 'e1',
        metadata: {},
        triaged_by: null,
        triaged_at: null,
        created_at: '2026-03-04T00:00:00Z',
        updated_at: '2026-03-04T00:00:00Z',
      },
    ]
    const withClaims = mergeGraphModelWithRelationClaims(base, claims)

    const relationsOnly = projectGraphByDisplayMode(withClaims, 'RELATIONS_ONLY')
    const claimsMode = projectGraphByDisplayMode(withClaims, 'CLAIMS')
    const evidenceMode = projectGraphByDisplayMode(withClaims, 'EVIDENCE')

    expect(relationsOnly.edges.every((edge) => edge.origin === 'canonical')).toBe(true)
    expect(relationsOnly.edges.some((edge) => edge.origin === 'claim')).toBe(false)
    expect(claimsMode.edges.some((edge) => edge.origin === 'claim')).toBe(true)
    expect(evidenceMode.edges.some((edge) => edge.origin === 'claim')).toBe(true)
  })

  it('adds paper and dataset evidence nodes/edges in evidence augmentation', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const claims: RelationClaimResponse[] = [
      {
        id: 'claim-evidence-1',
        research_space_id: 'space-1',
        source_type: 'GENE',
        source_label: 'MED13',
        target_type: 'PHENOTYPE',
        target_label: 'Cardiomyopathy',
        relation_type: 'ASSOCIATED_WITH',
        source_document_id: null,
        agent_run_id: null,
        confidence: 0.84,
        validation_state: 'ALLOWED',
        validation_reason: null,
        persistability: 'PERSISTABLE',
        claim_status: 'NEEDS_MAPPING',
        polarity: 'SUPPORT',
        claim_text: 'Evidence-backed claim.',
        claim_section: null,
        linked_relation_id: 'e1',
        metadata: {},
        triaged_by: null,
        triaged_at: null,
        created_at: '2026-03-04T00:00:00Z',
        updated_at: '2026-03-04T00:00:00Z',
      },
    ]
    const withClaims = mergeGraphModelWithRelationClaims(base, claims)
    const evidenceRows: Record<string, ClaimEvidenceResponse[]> = {
      'claim-evidence-1': [
        {
          id: 'ev-paper-1',
          claim_id: 'claim-evidence-1',
          source_document_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
          agent_run_id: null,
          sentence: 'Expression of human CNOT1 rescues learning defects.',
          sentence_source: 'verbatim_span',
          sentence_confidence: 'high',
          sentence_rationale: null,
          figure_reference: null,
          table_reference: null,
          confidence: 0.92,
          metadata: {
            pmid: '12345678',
          },
          created_at: '2026-03-05T00:00:00Z',
        },
        {
          id: 'ev-dataset-1',
          claim_id: 'claim-evidence-1',
          source_document_id: null,
          agent_run_id: null,
          sentence: null,
          sentence_source: null,
          sentence_confidence: 'medium',
          sentence_rationale: null,
          figure_reference: null,
          table_reference: null,
          confidence: 0.72,
          metadata: {
            dataset_id: 'GSE9999',
            dataset_name: 'Drosophila rescue cohort',
          },
          created_at: '2026-03-05T00:00:00Z',
        },
      ],
    }

    const augmented = augmentGraphModelWithClaimEvidence(withClaims, evidenceRows)
    const paperNode = augmented.nodeById['evidence-node:ev-paper-1']
    const datasetNode = augmented.nodeById['evidence-node:ev-dataset-1']
    const paperEdge = augmented.edgeById['evidence:claim-evidence-1:ev-paper-1']
    const datasetEdge = augmented.edgeById['evidence:claim-evidence-1:ev-dataset-1']

    expect(paperNode?.origin).toBe('evidence')
    expect(paperNode?.entityType).toBe('PAPER')
    expect(datasetNode?.origin).toBe('evidence')
    expect(datasetNode?.entityType).toBe('DATASET')
    expect(paperEdge?.origin).toBe('evidence')
    expect(paperEdge?.relationType).toBe('SUPPORTED_BY')
    expect(paperEdge?.evidenceSourceBadge).toBe('PMID: 12345678')
    expect(paperNode?.metadata.source_url).toBe('https://pubmed.ncbi.nlm.nih.gov/12345678/')
    expect(datasetEdge?.origin).toBe('evidence')
    expect(datasetEdge?.relationType).toBe('DERIVED_FROM')
    expect(datasetEdge?.evidenceSourceBadge).toBe('Dataset: GSE9999')
  })

  it('resolves article URLs from evidence metadata with source_url, PMID, and DOI fallback', () => {
    expect(
      resolveEvidenceArticleUrlFromMetadata({
        source_url: 'https://example.org/paper/abc',
      }),
    ).toBe('https://example.org/paper/abc')
    expect(
      resolveEvidenceArticleUrlFromMetadata({
        pmid: '40214304',
      }),
    ).toBe('https://pubmed.ncbi.nlm.nih.gov/40214304/')
    expect(
      resolveEvidenceArticleUrlFromMetadata({
        doi: '10.1038/s41586-024-12345-6',
      }),
    ).toBe('https://doi.org/10.1038/s41586-024-12345-6')
  })
})
