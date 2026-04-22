import type { JSONObject } from '@/types/generated'

export interface ArtanaRunEvent {
  seq: number
  event_id: string
  event_type: string
  timestamp: string
  parent_step_key?: string | null
  step_key?: string | null
  tool_name?: string | null
  tool_outcome?: string | null
  payload: JSONObject
}

export interface ArtanaRunSummary {
  summary_type: string
  timestamp: string
  step_key?: string | null
  payload: JSONObject
}

export interface ArtanaRunAlert {
  code: string
  severity: string
  title: string
  description: string
  triggered_at?: string | null
  metadata: JSONObject
}

export interface ArtanaLinkedRecordSummary {
  record_type: string
  record_id: string
  research_space_id?: string | null
  source_id?: string | null
  document_id?: string | null
  source_type?: string | null
  status?: string | null
  label?: string | null
  created_at?: string | null
  updated_at?: string | null
  metadata: JSONObject
}

export interface ArtanaRawTableSummary {
  table_name: string
  row_count: number
  latest_created_at?: string | null
  sample_rows: JSONObject[]
}

export interface ArtanaRunTraceResponse {
  requested_run_id: string
  run_id: string
  candidate_run_ids: string[]
  space_id: string
  source_ids: string[]
  source_types: string[]
  status: string
  last_event_seq?: number | null
  last_event_type?: string | null
  progress_percent?: number | null
  current_stage?: string | null
  completed_stages: string[]
  started_at?: string | null
  updated_at?: string | null
  eta_seconds?: number | null
  blocked_on?: string | null
  failure_reason?: string | null
  error_category?: string | null
  explain: JSONObject
  alerts: ArtanaRunAlert[]
  events: ArtanaRunEvent[]
  summaries: ArtanaRunSummary[]
  linked_records: ArtanaLinkedRecordSummary[]
  raw_tables?: ArtanaRawTableSummary[] | null
}

export interface ArtanaRunListItem {
  run_id: string
  space_id: string
  source_ids: string[]
  source_type?: string | null
  status: string
  current_stage?: string | null
  updated_at?: string | null
  started_at?: string | null
  last_event_type?: string | null
  alert_count: number
  alert_codes: string[]
}

export interface ArtanaRunListCounters {
  running: number
  failed: number
  stuck: number
  drift_detected: number
  budget_warning: number
  tool_unknown_outcome: number
}

export interface ArtanaRunListResponse {
  runs: ArtanaRunListItem[]
  total: number
  page: number
  per_page: number
  counters: ArtanaRunListCounters
}

export interface ArtanaRunListParams {
  q?: string
  status?: string
  space_id?: string
  source_type?: string
  alert_code?: string
  since_hours?: number
  page?: number
  per_page?: number
}
