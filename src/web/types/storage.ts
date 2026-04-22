export const STORAGE_PROVIDERS = ['local_filesystem', 'google_cloud_storage'] as const
export type StorageProviderName = (typeof STORAGE_PROVIDERS)[number]

export const STORAGE_USE_CASES = ['pdf', 'export', 'raw_source', 'backup'] as const
export type StorageUseCase = (typeof STORAGE_USE_CASES)[number]

export interface LocalFilesystemConfig {
  provider: 'local_filesystem'
  base_path: string
  create_directories: boolean
  expose_file_urls: boolean
}

export interface GoogleCloudStorageConfig {
  provider: 'google_cloud_storage'
  bucket_name: string
  base_path: string
  credentials_secret_name: string
  public_read: boolean
  signed_url_ttl_seconds: number
}

export type StorageProviderConfig = LocalFilesystemConfig | GoogleCloudStorageConfig

export interface StorageConfiguration {
  id: string
  name: string
  provider: StorageProviderName
  config: StorageProviderConfig
  enabled: boolean
  supported_capabilities: string[]
  default_use_cases: StorageUseCase[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface StorageProviderTestResult {
  configuration_id: string
  provider: StorageProviderName
  success: boolean
  message?: string
  checked_at: string
  capabilities: string[]
  latency_ms?: number
  metadata: Record<string, unknown>
}

export interface StorageUsageMetrics {
  configuration_id: string
  total_files: number
  total_size_bytes: number
  last_operation_at?: string
  error_rate?: number
}

export interface StorageHealthReport {
  configuration_id: string
  provider: StorageProviderName
  status: 'healthy' | 'degraded' | 'offline'
  last_checked_at: string
  details: Record<string, unknown>
}

export interface StorageOperationRecord {
  id: string
  configuration_id: string
  user_id?: string
  operation_type: 'store' | 'retrieve' | 'delete' | 'list' | 'test'
  key: string
  file_size_bytes?: number
  status: 'success' | 'failed' | 'pending'
  error_message?: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface CreateStorageConfigurationRequest {
  name: string
  provider: StorageProviderName
  config: StorageProviderConfig
  supported_capabilities?: string[]
  default_use_cases: StorageUseCase[]
  metadata?: Record<string, unknown>
  enabled?: boolean
}

export type UpdateStorageConfigurationRequest = Partial<
  Omit<CreateStorageConfigurationRequest, 'provider'>
>

export interface StorageConfigurationListResponse {
  data: StorageConfiguration[]
  total: number
  page: number
  per_page: number
}

export interface StorageConfigurationStats {
  configuration: StorageConfiguration
  usage: StorageUsageMetrics | null
  health: StorageHealthReport | null
}

export interface StorageOverviewTotals {
  total_configurations: number
  enabled_configurations: number
  disabled_configurations: number
  healthy_configurations: number
  degraded_configurations: number
  offline_configurations: number
  total_files: number
  total_size_bytes: number
  average_error_rate: number | null
}

export interface StorageOverviewResponse {
  generated_at: string
  totals: StorageOverviewTotals
  configurations: StorageConfigurationStats[]
}
