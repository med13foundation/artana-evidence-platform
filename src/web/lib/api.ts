import type { DashboardStats, RecentActivitiesResponse } from '@/types/dashboard'
import { apiClient, authHeaders } from '@/lib/api/client'

export async function fetchDashboardStats(token?: string): Promise<DashboardStats> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDashboardStats')
  }
  const resp = await apiClient.get('/api/dashboard', authHeaders(token))
  return resp.data as DashboardStats
}

export async function fetchRecentActivities(
  limit = 10,
  token?: string,
): Promise<RecentActivitiesResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRecentActivities')
  }
  const resp = await apiClient.get('/api/dashboard/activities', {
    params: { limit },
    ...authHeaders(token),
  })
  return resp.data as RecentActivitiesResponse
}
