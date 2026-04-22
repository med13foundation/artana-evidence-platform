import { QueryClient } from '@tanstack/react-query'
import {
  patchQueries,
  restoreQuerySnapshot,
  snapshotQueries,
} from '@/lib/query/cache-utils'

describe('cache-utils', () => {
  it('patches matching queries and restores the previous snapshot', () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    queryClient.setQueryData(['users', { limit: 25 }], { total: 1 })
    queryClient.setQueryData(['users', { limit: 500 }], { total: 2 })

    const beforePatch = snapshotQueries<{ total: number }>(queryClient, {
      queryKey: ['users'],
    })

    expect(beforePatch).toHaveLength(2)

    const snapshot = patchQueries<{ total: number }>(
      queryClient,
      { queryKey: ['users'] },
      (current) => ({ total: current.total + 1 }),
    )

    expect(queryClient.getQueryData<{ total: number }>(['users', { limit: 25 }])?.total).toBe(2)
    expect(queryClient.getQueryData<{ total: number }>(['users', { limit: 500 }])?.total).toBe(3)

    restoreQuerySnapshot(queryClient, snapshot)

    expect(queryClient.getQueryData<{ total: number }>(['users', { limit: 25 }])?.total).toBe(1)
    expect(queryClient.getQueryData<{ total: number }>(['users', { limit: 500 }])?.total).toBe(2)
  })
})
