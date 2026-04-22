import type { QueryClient, QueryFilters, QueryKey } from '@tanstack/react-query'

export type QuerySnapshotEntry<TData> = [QueryKey, TData | undefined]

export function snapshotQueries<TData>(
  queryClient: QueryClient,
  filters: QueryFilters,
): QuerySnapshotEntry<TData>[] {
  return queryClient
    .getQueriesData<TData>(filters)
    .map(([queryKey, value]) => [queryKey, value])
}

export function restoreQuerySnapshot<TData>(
  queryClient: QueryClient,
  snapshots: QuerySnapshotEntry<TData>[],
): void {
  snapshots.forEach(([queryKey, value]) => {
    queryClient.setQueryData(queryKey, value)
  })
}

export function patchQueries<TData>(
  queryClient: QueryClient,
  filters: QueryFilters,
  updater: (current: TData) => TData,
): QuerySnapshotEntry<TData>[] {
  const snapshots = snapshotQueries<TData>(queryClient, filters)

  snapshots.forEach(([queryKey, value]) => {
    if (value !== undefined) {
      queryClient.setQueryData<TData>(queryKey, updater(value))
    }
  })

  return snapshots
}
