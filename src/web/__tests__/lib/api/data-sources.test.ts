import { apiClient, authHeaders } from '@/lib/api/client'
import { createDataSourceInSpace } from '@/lib/api/data-sources'
import type { DataSource } from '@/types/data-source'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  authHeaders: jest.fn(),
}))

const mockApiClientPost = apiClient.post as jest.MockedFunction<typeof apiClient.post>
const mockAuthHeaders = authHeaders as jest.MockedFunction<typeof authHeaders>

function buildDataSource(overrides?: Partial<DataSource>): DataSource {
  return {
    id: '5740b40e-fa17-4d35-baa2-5d477ba5f8ca',
    name: 'PubMed (from Data Discovery)',
    description: 'Space-scoped source',
    source_type: 'pubmed',
    status: 'active',
    owner_id: 'f2158ff8-b679-448a-8853-f7f13f7d5c3d',
    research_space_id: '0ab67b4b-7bc8-4817-8106-c400b06fed8c',
    created_at: '2026-03-06T00:00:00Z',
    updated_at: '2026-03-06T00:00:00Z',
    ...overrides,
  }
}

describe('data sources api', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuthHeaders.mockImplementation((token?: string) => ({
      headers: { Authorization: `Bearer ${token ?? ''}` },
    }))
  })

  it('creates a space-scoped data source through the research space endpoint', async () => {
    const spaceId = '0ab67b4b-7bc8-4817-8106-c400b06fed8c'
    const payload = {
      name: 'PubMed (from Data Discovery)',
      description: 'Space-scoped source',
      source_type: 'pubmed',
      config: {},
      tags: ['discovery'],
    }
    const expected = buildDataSource()
    mockApiClientPost.mockResolvedValueOnce({ data: expected } as never)

    const result = await createDataSourceInSpace(spaceId, payload, 'test-token')

    expect(result).toEqual(expected)
    expect(mockApiClientPost).toHaveBeenCalledWith(
      `/research-spaces/${spaceId}/data-sources`,
      payload,
      { headers: { Authorization: 'Bearer test-token' } },
    )
  })

  it('rejects space-scoped create responses that are not attached to the requested space', async () => {
    const spaceId = '0ab67b4b-7bc8-4817-8106-c400b06fed8c'
    mockApiClientPost.mockResolvedValueOnce({
      data: buildDataSource({ research_space_id: null }),
    } as never)

    await expect(
      createDataSourceInSpace(
        spaceId,
        {
          name: 'Broken Source',
          source_type: 'pubmed',
          config: {},
        },
        'test-token',
      ),
    ).rejects.toThrow('Invalid space-scoped data source response payload')
  })
})
