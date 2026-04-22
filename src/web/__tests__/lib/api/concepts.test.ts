import { apiGet, apiPost, apiPut } from '@/lib/api/client'
import {
  createSpaceConceptSet,
  fetchSpaceConceptPolicy,
  fetchSpaceConceptSets,
  upsertSpaceConceptPolicy,
} from '@/lib/api/concepts'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPatch: jest.fn(),
  apiPut: jest.fn(),
}))

jest.mock('@/lib/api/graph-base-url', () => ({
  resolveGraphApiBaseUrl: () => 'https://artana-evidence-db.example.com',
}))

describe('concepts api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const mockApiPut = apiPut as jest.MockedFunction<typeof apiPut>
  const token = 'space-token'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('routes concept reads to the standalone graph service', async () => {
    const mockResponse = {
      concept_sets: [],
      total: 0,
    }
    mockApiGet.mockResolvedValueOnce(mockResponse)
    mockApiGet.mockResolvedValueOnce(null)

    const listResult = await fetchSpaceConceptSets(
      'space-1',
      { include_inactive: true },
      token,
    )
    const policyResult = await fetchSpaceConceptPolicy('space-1', token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/spaces/space-1/concepts/sets', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        include_inactive: true,
      },
    })
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/spaces/space-1/concepts/policy', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
    })
    expect(listResult).toEqual(mockResponse)
    expect(policyResult).toBeNull()
  })

  it('routes concept writes to the standalone graph service', async () => {
    const createPayload = {
      name: 'Cancer genes',
      slug: 'cancer-genes',
      domain_context: 'biomedical',
    }
    const policyPayload = {
      mode: 'BALANCED' as const,
      minimum_edge_confidence: 0.7,
      minimum_distinct_documents: 2,
      allow_generic_relations: false,
      policy_payload: {},
    }
    mockApiPost.mockResolvedValue({ id: 'set-1' })
    mockApiPut.mockResolvedValue({ id: 'policy-1' })

    await createSpaceConceptSet('space-1', createPayload, token)
    await upsertSpaceConceptPolicy('space-1', policyPayload, token)

    expect(mockApiPost).toHaveBeenCalledWith(
      '/v1/spaces/space-1/concepts/sets',
      createPayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiPut).toHaveBeenCalledWith(
      '/v1/spaces/space-1/concepts/policy',
      policyPayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('throws when token is not provided', async () => {
    await expect(fetchSpaceConceptSets('space-1')).rejects.toThrow(
      'Authentication token is required for fetchSpaceConceptSets',
    )
  })
})
