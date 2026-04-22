import type { ReactElement } from 'react'
import SpaceDetailPage from '@/app/(dashboard)/spaces/[spaceId]/page'
import { getServerSession } from 'next-auth'
import {
  fetchMyMembership,
  fetchResearchSpace,
  fetchSpaceCurationQueue,
  fetchSpaceCurationStats,
  fetchSpaceMembers,
  fetchSpaceOverview,
} from '@/lib/api/research-spaces'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import { fetchKernelEntities, fetchKernelRelations } from '@/lib/api/kernel'
import { SpaceStatus } from '@/types/research-space'

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

const redirectMock = jest.fn()

jest.mock('next/navigation', () => ({
  redirect: (...args: unknown[]) => redirectMock(...args),
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/space-detail-client', () => ({
  __esModule: true,
  default: () => <div>Space detail client</div>,
}))

jest.mock('@/lib/api/research-spaces', () => ({
  fetchMyMembership: jest.fn(),
  fetchResearchSpace: jest.fn(),
  fetchSpaceCurationQueue: jest.fn(),
  fetchSpaceCurationStats: jest.fn(),
  fetchSpaceMembers: jest.fn(),
  fetchSpaceOverview: jest.fn(),
}))

jest.mock('@/lib/api/data-sources', () => ({
  fetchDataSourcesBySpace: jest.fn(),
}))

jest.mock('@/lib/api/kernel', () => ({
  fetchKernelEntities: jest.fn(),
  fetchKernelRelations: jest.fn(),
}))

const VALID_SESSION = {
  user: {
    id: 'user-123',
    role: 'researcher',
    access_token: 'token-123',
  },
}

const SPACE = {
  id: 'space-123',
  slug: 'space-123',
  name: 'Space 123',
  description: 'Limited access space',
  owner_id: 'owner-999',
  status: SpaceStatus.ACTIVE,
  settings: {},
  tags: [],
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

describe('SpaceDetailPage (server)', () => {
  const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)

  beforeEach(() => {
    jest.clearAllMocks()
    ;(getServerSession as jest.Mock).mockResolvedValue(VALID_SESSION)
    ;(fetchSpaceMembers as jest.Mock).mockResolvedValue({
      memberships: [],
      total: 0,
      skip: 0,
      limit: 50,
    })
    ;(fetchSpaceOverview as jest.Mock).mockRejectedValue({
      response: {
        status: 403,
      },
    })
    ;(fetchResearchSpace as jest.Mock).mockResolvedValue(SPACE)
    ;(fetchMyMembership as jest.Mock).mockResolvedValue(null)
    ;(fetchDataSourcesBySpace as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 5,
      has_next: false,
      has_prev: false,
    })
    ;(fetchSpaceCurationStats as jest.Mock).mockResolvedValue({
      total: 0,
      pending: 0,
      approved: 0,
      rejected: 0,
    })
    ;(fetchSpaceCurationQueue as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      offset: 0,
      limit: 5,
    })
    ;(fetchKernelRelations as jest.Mock).mockResolvedValue({
      relations: [],
      total: 0,
      offset: 0,
      limit: 200,
    })
    ;(fetchKernelEntities as jest.Mock).mockResolvedValue({
      entities: [],
      total: 0,
      offset: 0,
      limit: 8,
    })
  })

  afterAll(() => {
    consoleWarnSpy.mockRestore()
  })

  it('falls back gracefully when the overview endpoint returns 403', async () => {
    const result = (await SpaceDetailPage({
      params: Promise.resolve({ spaceId: 'space-123' }),
    })) as ReactElement

    expect(redirectMock).not.toHaveBeenCalled()
    expect(fetchSpaceOverview).toHaveBeenCalledWith(
      'space-123',
      { data_source_limit: 5, queue_limit: 5 },
      'token-123',
    )
    expect(fetchResearchSpace).toHaveBeenCalledWith('space-123', 'token-123')
    expect(fetchMyMembership).toHaveBeenCalledWith('space-123', 'token-123')
    expect(fetchDataSourcesBySpace).not.toHaveBeenCalled()
    expect(fetchSpaceCurationStats).not.toHaveBeenCalled()
    expect(fetchSpaceCurationQueue).not.toHaveBeenCalled()
    expect(result.props).toEqual(
      expect.objectContaining({
        spaceId: 'space-123',
        space: SPACE,
        access: expect.objectContaining({
          hasSpaceAccess: false,
          showMembershipNotice: true,
        }),
      }),
    )
    expect(result).toBeTruthy()
  })
})
