import { apiGet, apiPatch, apiPost } from '@/lib/api/client'
import {
  createDictionaryVariable,
  fetchDictionaryRelationConstraints,
  fetchDictionaryVariables,
  mergeDictionaryRelationType,
  revokeDictionaryVariable,
  setDictionaryVariableReviewStatus,
} from '@/lib/api/dictionary'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPatch: jest.fn(),
}))

jest.mock('@/lib/api/graph-base-url', () => ({
  resolveGraphApiBaseUrl: () => 'https://artana-evidence-db.example.com',
}))

describe('dictionary api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiPatch = apiPatch as jest.MockedFunction<typeof apiPatch>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const token = 'admin-token'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('routes dictionary reads to the standalone graph service', async () => {
    mockApiGet.mockResolvedValueOnce({ variables: [], total: 0, offset: 0, limit: 100 })
    mockApiGet.mockResolvedValueOnce({
      constraints: [],
      total: 0,
      offset: 0,
      limit: 100,
    })

    await fetchDictionaryVariables({ domain_context: 'general' }, token)
    await fetchDictionaryRelationConstraints({ source_type: 'GENE' }, token)

    expect(mockApiGet).toHaveBeenNthCalledWith(1, '/v1/dictionary/variables', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        domain_context: 'general',
      },
    })
    expect(mockApiGet).toHaveBeenNthCalledWith(2, '/v1/dictionary/relation-constraints', {
      token,
      baseURL: 'https://artana-evidence-db.example.com',
      params: {
        source_type: 'GENE',
      },
    })
  })

  it('routes dictionary writes to the standalone graph service', async () => {
    const createPayload = {
      id: 'VAR_WEB_TEST',
      canonical_name: 'web_test',
      display_name: 'Web Test',
      data_type: 'STRING' as const,
      domain_context: 'general',
      sensitivity: 'INTERNAL' as const,
      constraints: {},
      description: 'Created from a web test',
    }
    const revokePayload = { reason: 'obsolete' }
    const reviewPayload = { review_status: 'PENDING_REVIEW' as const }
    const mergePayload = { target_id: 'REL_TARGET', reason: 'duplicate' }

    mockApiPost.mockResolvedValue({})
    mockApiPatch.mockResolvedValue({})

    await createDictionaryVariable(createPayload, token)
    await revokeDictionaryVariable('VAR_WEB_TEST', revokePayload, token)
    await setDictionaryVariableReviewStatus('VAR_WEB_TEST', reviewPayload, token)
    await mergeDictionaryRelationType('REL_SOURCE', mergePayload, token)

    expect(mockApiPost).toHaveBeenNthCalledWith(
      1,
      '/v1/dictionary/variables',
      createPayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiPost).toHaveBeenNthCalledWith(
      2,
      '/v1/dictionary/variables/VAR_WEB_TEST/revoke',
      revokePayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiPatch).toHaveBeenCalledWith(
      '/v1/dictionary/variables/VAR_WEB_TEST/review-status',
      reviewPayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
    expect(mockApiPost).toHaveBeenNthCalledWith(
      3,
      '/v1/dictionary/relation-types/REL_SOURCE/merge',
      mergePayload,
      { token, baseURL: 'https://artana-evidence-db.example.com' },
    )
  })

  it('requires an auth token', async () => {
    await expect(fetchDictionaryVariables()).rejects.toThrow(
      'Authentication token is required for fetchDictionaryVariables',
    )
  })
})
