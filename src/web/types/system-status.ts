export interface MaintenanceModeState {
  is_active: boolean
  message: string | null
  activated_at: string | null
  activated_by: string | null
  last_updated_by: string | null
  last_updated_at: string | null
}

export interface MaintenanceModeResponse {
  state: MaintenanceModeState
}

export interface EnableMaintenanceRequest {
  message?: string | null
  force_logout_users?: boolean
}
