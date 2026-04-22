export type ScheduleFrequency =
  | 'manual'
  | 'hourly'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'cron'

export interface DataSourceIngestionSchedule {
  enabled: boolean
  frequency: ScheduleFrequency
  start_time?: string | null
  timezone: string
  cron_expression?: string | null
  backend_job_id?: string | null
  next_run_at?: string | null
  last_run_at?: string | null
}

export interface DataSourceQualityMetrics {
  completeness_score?: number | null
  consistency_score?: number | null
  timeliness_score?: number | null
  overall_score?: number | null
  last_assessed?: string | null
  issues_count?: number | null
}

export interface DataSource {
  id: string
  name: string
  description: string
  source_type: string
  status: string
  owner_id: string
  research_space_id: string | null
  config?: Record<string, unknown>
  ingestion_schedule?: DataSourceIngestionSchedule
  quality_metrics?: DataSourceQualityMetrics | null
  last_ingested_at?: string | null
  created_at: string
  updated_at: string
  tags?: string[]
}

export type SourceType =
  | 'api'
  | 'file_upload'
  | 'database'
  | 'web_scraping'
  | 'pubmed'
  | 'clinvar'

export type SourceStatus =
  | 'draft'
  | 'active'
  | 'inactive'
  | 'error'
  | 'pending_review'
  | 'archived'

export interface IngestionJobHistoryItem {
  id: string
  status: string
  trigger: string
  started_at: string | null
  completed_at: string | null
  records_processed: number
  records_failed: number
  records_skipped: number
  bytes_processed: number
  executed_query?: string | null
  query_generation?: IngestionQueryGenerationMetadata | null
  idempotency?: IngestionIdempotencyMetadata | null
  metadata_typed?: IngestionJobMetadata | null
  metadata?: Record<string, unknown>
}

export interface IngestionIdempotencyMetadata {
  query_signature?: string | null
  checkpoint_kind?: string | null
  checkpoint_before?: Record<string, unknown> | null
  checkpoint_after?: Record<string, unknown> | null
  new_records: number
  updated_records: number
  unchanged_records: number
  skipped_records: number
}

export interface IngestionQueryGenerationMetadata {
  run_id?: string | null
  model?: string | null
  decision?: string | null
  confidence?: number | null
}

export interface IngestionExtractionQueueMetadata {
  requested: number
  queued: number
  skipped: number
  version: number
}

export interface IngestionExtractionRunMetadata {
  source_id?: string | null
  ingestion_job_id?: string | null
  requested: number
  processed: number
  completed: number
  skipped: number
  failed: number
  started_at?: string | null
  completed_at?: string | null
}

export interface IngestionJobMetadata {
  executed_query?: string | null
  query_generation?: IngestionQueryGenerationMetadata | null
  idempotency?: IngestionIdempotencyMetadata | null
  extraction_queue?: IngestionExtractionQueueMetadata | null
  extraction_run?: IngestionExtractionRunMetadata | null
}
