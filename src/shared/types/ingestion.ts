// Ingestion Types (placeholder - detailed types in data-source.ts)
export interface IngestionJobSummary {
  id: string
  dataSourceId: string
  status: string
  startedAt: string
  completedAt?: string
  recordsProcessed: number
  recordsSuccessful: number
  recordsFailed: number
}
