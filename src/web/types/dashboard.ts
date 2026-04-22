export interface DashboardStats {
  pending_count: number
  approved_count: number
  rejected_count: number
  total_items: number
  entity_counts: Record<string, number>
}

export interface ActivityItem {
  title: string
  category: 'success' | 'warning' | 'info' | 'danger'
  icon: string
  timestamp: string
}

export interface RecentActivitiesResponse {
  activities: ActivityItem[]
  total: number
}
