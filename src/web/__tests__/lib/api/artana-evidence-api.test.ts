import { apiPost } from '@/lib/api/client'
import {
  generateHypotheses,
  searchKernelGraph,
} from '@/lib/api/artana-evidence-api'

jest.mock('@/lib/api/client', () => ({
  apiPost: jest.fn(),
}))

jest.mock('@/lib/api/harness-base-url', () => ({
  resolveArtanaEvidenceApiBaseUrl: () => 'https://artana-evidence-api.example.com',
}))

describe('graph harness api', () => {
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const token = 'space-token'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('routes hypothesis generation to the graph harness service', async () => {
    mockApiPost.mockResolvedValueOnce({
      run: {
        id: 'run-1',
        input_payload: {
          seed_entity_ids: ['entity-a'],
        },
      },
      candidate_count: 2,
      errors: [],
    })

    const response = await generateHypotheses(
      'space-1',
      { seed_entity_ids: ['entity-a'], max_hypotheses: 5 },
      token,
    )

    expect(mockApiPost).toHaveBeenCalledWith(
      '/v1/spaces/space-1/agents/hypotheses/runs',
      { seed_entity_ids: ['entity-a'], max_hypotheses: 5 },
      { token, timeout: 0, baseURL: 'https://artana-evidence-api.example.com' },
    )
    expect(response).toEqual({
      run_id: 'run-1',
      requested_seed_count: 1,
      used_seed_count: 1,
      candidates_seen: 2,
      created_count: 2,
      deduped_count: 0,
      errors: [],
      hypotheses: [],
    })
  })

  it('routes graph search to the graph harness service', async () => {
    mockApiPost.mockResolvedValueOnce({
      result: {
        confidence_score: 0.87,
        rationale: 'Harness graph search completed with ranked results.',
        evidence: [],
        decision: 'generated',
        research_space_id: 'space-1',
        original_query: 'MED13',
        interpreted_intent: 'MED13',
        query_plan_summary: 'Harness plan',
        total_results: 1,
        results: [],
        executed_path: 'agent',
        warnings: [],
        agent_run_id: 'run-graph-search-1',
      },
    })

    const response = await searchKernelGraph(
      'space-1',
      {
        question: 'MED13',
        max_depth: 2,
        top_k: 5,
        curation_statuses: ['ACCEPTED'],
        include_evidence_chains: true,
        force_agent: false,
      },
      token,
    )

    expect(mockApiPost).toHaveBeenCalledWith(
      '/v1/spaces/space-1/agents/graph-search/runs',
      {
        question: 'MED13',
        max_depth: 2,
        top_k: 5,
        curation_statuses: ['ACCEPTED'],
        include_evidence_chains: true,
      },
      { token, baseURL: 'https://artana-evidence-api.example.com' },
    )
    expect(response.executed_path).toBe('agent')
    expect(response.agent_run_id).toBe('run-graph-search-1')
  })

  it('throws when token is not provided', async () => {
    await expect(
      generateHypotheses('space-1', { seed_entity_ids: ['entity-a'] }, undefined),
    ).rejects.toThrow('Authentication token is required for generateHypotheses')

    await expect(
      searchKernelGraph(
        'space-1',
        {
          question: 'MED13',
        },
        undefined,
      ),
    ).rejects.toThrow('Authentication token is required for searchKernelGraph')
  })
})
