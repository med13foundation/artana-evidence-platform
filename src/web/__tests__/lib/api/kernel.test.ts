import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/lib/api/client'
import {
  createKernelEntity,
  createKernelObservation,
  createKernelRelation,
  createManualHypothesis,
  deleteKernelEntity,
  fetchKernelEntities,
  fetchKernelEntity,
  fetchKernelGraphDocument,
  fetchKernelGraphExport,
  fetchKernelObservation,
  fetchKernelObservations,
  fetchKernelProvenance,
  fetchKernelProvenanceRecord,
  fetchKernelRelations,
  fetchKernelSubgraph,
  fetchHypotheses,
  fetchRelationClaimEvidence,
  fetchRelationClaims,
  updateKernelEntity,
  updateKernelRelationCurationStatus,
  updateRelationClaimStatus,
} from '@/lib/api/kernel'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPatch: jest.fn(),
  apiPut: jest.fn(),
  apiDelete: jest.fn(),
}))

jest.mock('@/lib/api/graph-base-url', () => ({
  resolveGraphApiBaseUrl: () => 'https://artana-evidence-db.example.com',
}))

describe('kernel api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiDelete = apiDelete as jest.MockedFunction<typeof apiDelete>
  const mockApiPatch = apiPatch as jest.MockedFunction<typeof apiPatch>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const mockApiPut = apiPut as jest.MockedFunction<typeof apiPut>
  const token = 'space-token'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('calls bounded subgraph endpoint with auth token', async () => {
    const mockResponse = {
      nodes: [],
      edges: [],
      meta: {
        mode: 'starter',
        seed_entity_ids: [],
        requested_depth: 2,
        requested_top_k: 25,
        pre_cap_node_count: 0,
        pre_cap_edge_count: 0,
        truncated_nodes: false,
        truncated_edges: false,
      },
    }
    mockApiPost.mockResolvedValue(mockResponse)

    const payload = {
      mode: 'starter' as const,
      seed_entity_ids: [],
      max_nodes: 180,
      max_edges: 260,
    }
    const result = await fetchKernelSubgraph('space-1', payload, token)

    expect(mockApiPost).toHaveBeenCalledWith('/v1/spaces/space-1/graph/subgraph', payload, {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
    expect(result).toEqual(mockResponse)
  })

  it('routes graph-owned relation reads to the standalone graph service', async () => {
    const mockResponse = {
      relations: [],
      total: 0,
      offset: 0,
      limit: 50,
    }
    mockApiGet.mockResolvedValue(mockResponse)

    const result = await fetchKernelRelations(
      'space-1',
      {
        relation_type: 'ASSOCIATED_WITH',
        node_ids: ['entity-a', 'entity-b'],
      },
      token,
    )

    expect(mockApiGet).toHaveBeenCalledWith('/v1/spaces/space-1/relations', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        relation_type: 'ASSOCIATED_WITH',
        node_ids: 'entity-a,entity-b',
        offset: 0,
        limit: 50,
      },
    })
    expect(result).toEqual(mockResponse)
  })

  it('routes graph-owned relation writes to the standalone graph service', async () => {
    mockApiPost.mockResolvedValueOnce({
      id: 'relation-1',
      research_space_id: 'space-1',
      source_id: 'entity-a',
      relation_type: 'ASSOCIATED_WITH',
      target_id: 'entity-b',
      confidence: 0.88,
      aggregate_confidence: 0.88,
      source_count: 1,
      highest_evidence_tier: 'COMPUTATIONAL',
      curation_status: 'DRAFT',
      evidence_summary: 'Manual edge',
      evidence_sentence: 'MED13 is associated with developmental delay.',
      evidence_sentence_source: 'verbatim_span',
      evidence_sentence_confidence: 'high',
      evidence_sentence_rationale: null,
      paper_links: [],
      provenance_id: null,
      reviewed_by: null,
      reviewed_at: null,
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })
    mockApiPut.mockResolvedValueOnce({
      id: 'relation-1',
      research_space_id: 'space-1',
      source_id: 'entity-a',
      relation_type: 'ASSOCIATED_WITH',
      target_id: 'entity-b',
      confidence: 0.88,
      aggregate_confidence: 0.88,
      source_count: 1,
      highest_evidence_tier: 'COMPUTATIONAL',
      curation_status: 'APPROVED',
      evidence_summary: 'Manual edge',
      evidence_sentence: 'MED13 is associated with developmental delay.',
      evidence_sentence_source: 'verbatim_span',
      evidence_sentence_confidence: 'high',
      evidence_sentence_rationale: null,
      paper_links: [],
      provenance_id: null,
      reviewed_by: 'user-1',
      reviewed_at: '2026-03-12T00:10:00Z',
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:10:00Z',
    })

    await createKernelRelation(
      'space-1',
      {
        source_id: 'entity-a',
        relation_type: 'ASSOCIATED_WITH',
        target_id: 'entity-b',
        assessment: {
          support_band: 'SUPPORTED',
          grounding_level: 'SPAN',
          mapping_status: 'RESOLVED',
          speculation_level: 'DIRECT',
          confidence_rationale: 'Manual test relation is supported by a cited span.',
        },
        evidence_summary: 'Manual edge',
        evidence_sentence: 'MED13 is associated with developmental delay.',
        evidence_sentence_source: 'verbatim_span',
        evidence_sentence_confidence: 'high',
        evidence_sentence_rationale: null,
        evidence_tier: 'COMPUTATIONAL',
        provenance_id: null,
      },
      token,
    )
    await updateKernelRelationCurationStatus('space-1', 'relation-1', { curation_status: 'APPROVED' }, token)

    expect(mockApiPost).toHaveBeenNthCalledWith(
      1,
      '/v1/spaces/space-1/relations',
      {
        source_id: 'entity-a',
        relation_type: 'ASSOCIATED_WITH',
        target_id: 'entity-b',
        assessment: {
          support_band: 'SUPPORTED',
          grounding_level: 'SPAN',
          mapping_status: 'RESOLVED',
          speculation_level: 'DIRECT',
          confidence_rationale: 'Manual test relation is supported by a cited span.',
        },
        evidence_summary: 'Manual edge',
        evidence_sentence: 'MED13 is associated with developmental delay.',
        evidence_sentence_source: 'verbatim_span',
        evidence_sentence_confidence: 'high',
        evidence_sentence_rationale: null,
        evidence_tier: 'COMPUTATIONAL',
        provenance_id: null,
      },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiPut).toHaveBeenNthCalledWith(
      1,
      '/v1/spaces/space-1/relations/relation-1',
      { curation_status: 'APPROVED' },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('routes graph-owned provenance reads to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      provenance: [
        {
          id: 'prov-1',
          research_space_id: 'space-1',
          source_type: 'PUBMED',
          source_ref: 'pmid:123456',
          extraction_run_id: 'run-123',
          mapping_method: 'manual',
          mapping_confidence: 0.94,
          agent_model: 'gpt-5',
          raw_input: { title: 'Graph provenance fixture' },
          created_at: '2026-03-12T00:00:00Z',
          updated_at: '2026-03-12T00:00:00Z',
        },
      ],
      total: 1,
      offset: 0,
      limit: 50,
    })
    mockApiGet.mockResolvedValueOnce({
      id: 'prov-1',
      research_space_id: 'space-1',
      source_type: 'PUBMED',
      source_ref: 'pmid:123456',
      extraction_run_id: 'run-123',
      mapping_method: 'manual',
      mapping_confidence: 0.94,
      agent_model: 'gpt-5',
      raw_input: { title: 'Graph provenance fixture' },
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })

    await fetchKernelProvenance('space-1', { source_type: 'PUBMED' }, token)
    await fetchKernelProvenanceRecord('space-1', 'prov-1', token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/spaces/space-1/provenance', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        source_type: 'PUBMED',
        offset: 0,
        limit: 50,
      },
    })
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/spaces/space-1/provenance/prov-1', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
  })

  it('routes entity reads and writes to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      entities: [],
      total: 0,
      offset: 0,
      limit: 50,
    })
    mockApiPost.mockResolvedValueOnce({
      entity: {
        id: 'entity-a',
        research_space_id: 'space-1',
        entity_type: 'GENE',
        display_label: 'MED13',
        metadata: {},
        created_at: '2026-03-12T00:00:00Z',
        updated_at: '2026-03-12T00:00:00Z',
      },
      created: true,
    })
    mockApiGet.mockResolvedValueOnce({
      id: 'entity-a',
      research_space_id: 'space-1',
      entity_type: 'GENE',
      display_label: 'MED13',
      metadata: {},
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })
    mockApiPut.mockResolvedValueOnce({
      id: 'entity-a',
      research_space_id: 'space-1',
      entity_type: 'GENE',
      display_label: 'MED13 updated',
      metadata: { source: 'test' },
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })
    mockApiDelete.mockResolvedValueOnce(undefined)

    await fetchKernelEntities('space-1', { type: 'GENE' }, token)
    await createKernelEntity(
      'space-1',
      {
        entity_type: 'GENE',
        display_label: 'MED13',
        metadata: {},
        identifiers: {},
      },
      token,
    )
    await fetchKernelEntity('space-1', 'entity-a', token)
    await updateKernelEntity(
      'space-1',
      'entity-a',
      { display_label: 'MED13 updated', metadata: { source: 'test' } },
      token,
    )
    await deleteKernelEntity('space-1', 'entity-a', token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/spaces/space-1/entities', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: { type: 'GENE', offset: 0, limit: 50 },
    })
    expect(mockApiPost).toHaveBeenNthCalledWith(
      1,
      '/v1/spaces/space-1/entities',
      {
        entity_type: 'GENE',
        display_label: 'MED13',
        metadata: {},
        identifiers: {},
      },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/spaces/space-1/entities/entity-a', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
    expect(mockApiPut).toHaveBeenCalledWith(
      '/v1/spaces/space-1/entities/entity-a',
      { display_label: 'MED13 updated', metadata: { source: 'test' } },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiDelete).toHaveBeenCalledWith('/v1/spaces/space-1/entities/entity-a', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
  })

  it('routes observation reads and writes to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      observations: [],
      total: 0,
      offset: 0,
      limit: 50,
    })
    mockApiPost.mockResolvedValueOnce({
      id: 'obs-1',
      research_space_id: 'space-1',
      subject_id: 'entity-a',
      variable_id: 'VAR_TEST_NOTE',
      value_numeric: null,
      value_text: 'hello graph service',
      value_date: null,
      value_coded: null,
      value_boolean: null,
      value_json: null,
      unit: null,
      observed_at: null,
      provenance_id: null,
      confidence: 1,
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })
    mockApiGet.mockResolvedValueOnce({
      id: 'obs-1',
      research_space_id: 'space-1',
      subject_id: 'entity-a',
      variable_id: 'VAR_TEST_NOTE',
      value_numeric: null,
      value_text: 'hello graph service',
      value_date: null,
      value_coded: null,
      value_boolean: null,
      value_json: null,
      unit: null,
      observed_at: null,
      provenance_id: null,
      confidence: 1,
      created_at: '2026-03-12T00:00:00Z',
      updated_at: '2026-03-12T00:00:00Z',
    })

    await fetchKernelObservations('space-1', { subject_id: 'entity-a' }, token)
    await createKernelObservation(
      'space-1',
      {
        subject_id: 'entity-a',
        variable_id: 'VAR_TEST_NOTE',
        value: 'hello graph service',
        unit: null,
        observed_at: null,
        provenance_id: null,
        confidence: 1,
      },
      token,
    )
    await fetchKernelObservation('space-1', 'obs-1', token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/spaces/space-1/observations', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: { subject_id: 'entity-a', offset: 0, limit: 50 },
    })
    expect(mockApiPost).toHaveBeenCalledWith(
      '/v1/spaces/space-1/observations',
      {
        subject_id: 'entity-a',
        variable_id: 'VAR_TEST_NOTE',
        value: 'hello graph service',
        unit: null,
        observed_at: null,
        provenance_id: null,
        confidence: 1,
      },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/spaces/space-1/observations/obs-1', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
  })

  it('routes claim-ledger reads and mutations to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      claims: [],
      total: 0,
      offset: 0,
      limit: 50,
    })
    mockApiGet.mockResolvedValueOnce({
      claim_id: 'claim-1',
      evidence: [],
      total: 0,
    })
    mockApiPatch.mockResolvedValue({
      id: 'claim-1',
      claim_status: 'RESOLVED',
    })

    await fetchRelationClaims('space-1', { polarity: 'SUPPORT' }, token)
    await fetchRelationClaimEvidence('space-1', 'claim-1', token)
    await updateRelationClaimStatus('space-1', 'claim-1', { claim_status: 'RESOLVED' }, token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/spaces/space-1/claims', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        polarity: 'SUPPORT',
        offset: 0,
        limit: 50,
      },
    })
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/spaces/space-1/claims/claim-1/evidence', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
    expect(mockApiPatch).toHaveBeenCalledWith(
      '/v1/spaces/space-1/claims/claim-1',
      { claim_status: 'RESOLVED' },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('routes manual hypothesis workflows to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      hypotheses: [],
      total: 0,
      offset: 0,
      limit: 50,
    })
    mockApiPost.mockResolvedValueOnce({ claim_id: 'hyp-1' })

    await fetchHypotheses('space-1', { limit: 10 }, token)
    await createManualHypothesis('space-1', { statement: 'Hypothesis', rationale: 'Reason' }, token)

    expect(mockApiGet).toHaveBeenCalledWith('/v1/spaces/space-1/hypotheses', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        offset: 0,
        limit: 10,
      },
    })
    expect(mockApiPost).toHaveBeenNthCalledWith(
      1,
      '/v1/spaces/space-1/hypotheses/manual',
      { statement: 'Hypothesis', rationale: 'Reason' },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('routes graph export and document reads to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({
      nodes: [],
      edges: [],
    })
    mockApiPost.mockResolvedValueOnce({
      nodes: [],
      edges: [],
      meta: {
        mode: 'seeded',
        seed_entity_ids: ['entity-a'],
        requested_depth: 1,
        requested_top_k: 10,
        pre_cap_entity_node_count: 1,
        pre_cap_canonical_edge_count: 0,
        truncated_entity_nodes: false,
        truncated_canonical_edges: false,
        included_claims: true,
        included_evidence: true,
        max_claims: 10,
        evidence_limit_per_claim: 2,
        counts: {
          entity_nodes: 1,
          claim_nodes: 0,
          evidence_nodes: 0,
          canonical_edges: 0,
          claim_participant_edges: 0,
          claim_evidence_edges: 0,
        },
      },
    })

    await fetchKernelGraphExport('space-1', token)
    await fetchKernelGraphDocument(
      'space-1',
      {
        mode: 'seeded',
        seed_entity_ids: ['entity-a'],
        depth: 1,
        top_k: 10,
        max_nodes: 20,
        max_edges: 20,
        include_claims: true,
        include_evidence: true,
        max_claims: 10,
        evidence_limit_per_claim: 2,
      },
      token,
    )

    expect(mockApiGet).toHaveBeenCalledWith('/v1/spaces/space-1/graph/export', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
    expect(mockApiPost).toHaveBeenCalledWith(
      '/v1/spaces/space-1/graph/document',
      {
        mode: 'seeded',
        seed_entity_ids: ['entity-a'],
        depth: 1,
        top_k: 10,
        max_nodes: 20,
        max_edges: 20,
        include_claims: true,
        include_evidence: true,
        max_claims: 10,
        evidence_limit_per_claim: 2,
      },
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('throws when token is not provided', async () => {
    await expect(
      fetchKernelSubgraph(
        'space-1',
        {
          mode: 'starter',
          seed_entity_ids: [],
        },
        undefined,
      ),
    ).rejects.toThrow('Authentication token is required for fetchKernelSubgraph')
  })
})
