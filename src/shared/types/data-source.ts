import { z } from 'zod'

// Enums
export enum SourceType {
  API = 'api',
  FILE = 'file',
  DATABASE = 'database',
  PUBMED = 'pubmed',
  CLINVAR = 'clinvar',
}

export enum SourceStatus {
  ACTIVE = 'active',
  DRAFT = 'draft',
  ERROR = 'error',
  PAUSED = 'paused',
}

export enum SourceTemplateCategory {
  CLINICAL = 'clinical',
  RESEARCH = 'research',
  PHARMACOGENOMIC = 'pharmacogenomic',
  FUNCTIONAL = 'functional',
  PATHOGENIC = 'pathogenic',
  OTHER = 'other',
}

export enum IngestionStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

export enum IngestionTrigger {
  MANUAL = 'manual',
  SCHEDULED = 'scheduled',
  WEBHOOK = 'webhook',
  API = 'api',
}

// Core Types
export interface DataSource {
  id: string
  ownerId: string
  name: string
  description?: string
  sourceType: SourceType
  status: SourceStatus
  config: DataSourceConfig
  templateId?: string
  ingestionSchedule?: IngestionSchedule
  qualityMetrics?: QualityMetrics
  lastIngestedAt?: string
  createdAt: string
  updatedAt: string
}

export interface DataSourceConfig {
  // API Configuration
  apiUrl?: string
  apiKey?: string
  authType?: 'none' | 'basic' | 'bearer' | 'api-key'
  headers?: Record<string, string>
  timeout?: number
  retryCount?: number

  // File Configuration
  filePath?: string
  fileFormat?: 'csv' | 'json' | 'xml' | 'tsv' | 'excel'
  delimiter?: string
  encoding?: string
  hasHeaders?: boolean
  columnMapping?: Record<string, string>

  // Database Configuration
  connectionString?: string
  query?: string
  tableName?: string
  batchSize?: number
}

export interface IngestionSchedule {
  frequency: 'manual' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'cron'
  startTime?: string
  timezone?: string
  enabled: boolean
  cronExpression?: string | null
  backendJobId?: string | null
}

export interface QualityMetrics {
  completenessScore?: number
  consistencyScore?: number
  timelinessScore?: number
  validityScore?: number
  overallScore?: number
  totalRecords?: number
  validRecords?: number
  invalidRecords?: number
  lastAssessed: string
  issues?: QualityIssue[]
}

export interface QualityIssue {
  type: 'missing_data' | 'invalid_format' | 'duplicate' | 'outlier' | 'inconsistency'
  severity: 'low' | 'medium' | 'high' | 'critical'
  field?: string
  message: string
  count: number
  sampleValues?: unknown[]
}

export interface SourceTemplate {
  id: string
  name: string
  description: string
  category: SourceTemplateCategory
  sourceType: SourceType
  config: DataSourceConfig
  validationRules?: ValidationRule[]
  uiConfig?: TemplateUIConfig
  isPublic: boolean
  createdBy: string
  createdAt: string
  updatedAt: string
}

export interface ValidationRule {
  field: string
  rule: 'required' | 'email' | 'url' | 'regex' | 'range' | 'enum'
  parameters?: Record<string, unknown>
  errorMessage?: string
}

export interface TemplateUIConfig {
  icon?: string
  color?: string
  fields: UIFieldConfig[]
}

export interface UIFieldConfig {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'multiselect' | 'textarea' | 'file' | 'date' | 'boolean'
  required: boolean
  placeholder?: string
  options?: string[]
  validation?: ValidationRule
  helpText?: string
}

export interface IngestionJob {
  id: string
  dataSourceId: string
  status: IngestionStatus
  trigger: IngestionTrigger
  startedAt: string
  completedAt?: string
  durationSeconds?: number
  recordsProcessed: number
  recordsSuccessful: number
  recordsFailed: number
  errors?: IngestionError[]
  metrics?: JobMetrics
}

export interface IngestionError {
  recordIndex?: number
  field?: string
  errorType: string
  message: string
  rawData?: unknown
}

export interface JobMetrics {
  durationSeconds?: number
  recordsPerSecond?: number
  memoryUsage?: number
  cpuUsage?: number
}

// Zod Schemas for Validation
export const DataSourceSchema = z.object({
  id: z.string().uuid(),
  ownerId: z.string().uuid(),
  name: z.string().min(1).max(100),
  description: z.string().optional(),
  sourceType: z.nativeEnum(SourceType),
  status: z.nativeEnum(SourceStatus),
  config: z.object({
    apiUrl: z.string().url().optional(),
    apiKey: z.string().optional(),
    authType: z.enum(['none', 'basic', 'bearer', 'api-key']).optional(),
    headers: z.record(z.string()).optional(),
    timeout: z.number().positive().optional(),
    retryCount: z.number().int().min(0).optional(),
    filePath: z.string().optional(),
    fileFormat: z.enum(['csv', 'json', 'xml', 'tsv', 'excel']).optional(),
    delimiter: z.string().optional(),
    encoding: z.string().optional(),
    hasHeaders: z.boolean().optional(),
    columnMapping: z.record(z.string()).optional(),
    connectionString: z.string().optional(),
    query: z.string().optional(),
    tableName: z.string().optional(),
    batchSize: z.number().int().positive().optional(),
  }),
  templateId: z.string().uuid().optional(),
  ingestionSchedule: z.object({
    frequency: z.enum(['manual', 'hourly', 'daily', 'weekly', 'monthly', 'cron']),
    startTime: z.string().optional(),
    timezone: z.string().optional(),
    enabled: z.boolean(),
    cronExpression: z.string().optional(),
    backendJobId: z.string().optional(),
  }).optional(),
  qualityMetrics: z.object({
    completenessScore: z.number().min(0).max(1).optional(),
    consistencyScore: z.number().min(0).max(1).optional(),
    timelinessScore: z.number().min(0).max(1).optional(),
    validityScore: z.number().min(0).max(1).optional(),
    overallScore: z.number().min(0).max(1).optional(),
    totalRecords: z.number().int().optional(),
    validRecords: z.number().int().optional(),
    invalidRecords: z.number().int().optional(),
    lastAssessed: z.string().datetime(),
    issues: z.array(z.object({
      type: z.enum(['missing_data', 'invalid_format', 'duplicate', 'outlier', 'inconsistency']),
      severity: z.enum(['low', 'medium', 'high', 'critical']),
      field: z.string().optional(),
      message: z.string(),
      count: z.number().int(),
      sampleValues: z.array(z.unknown()).optional(),
    })).optional(),
  }).optional(),
  lastIngestedAt: z.string().datetime().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})
