import { z } from 'zod'

// Common Types
export interface PaginationParams {
  page?: number
  limit?: number
  offset?: number
}

export interface SortParams {
  field: string
  direction: 'asc' | 'desc'
}

export type DateString = string // ISO 8601 format
export type Timestamp = number // Unix timestamp in milliseconds

export type PrimitiveFilterValue = string | number | boolean | null | DateString
export type FilterValue = PrimitiveFilterValue | PrimitiveFilterValue[]

export interface FilterParams {
  field: string
  operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'nin' | 'contains' | 'startswith' | 'endswith'
  value: FilterValue
}

export interface SearchParams {
  query?: string
  filters?: FilterParams[]
  sort?: SortParams
  pagination?: PaginationParams
}

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: ApiError
  meta?: ApiMeta
}

export interface ApiError {
  code: string
  message: string
  details?: Record<string, unknown>
  field?: string
}

export interface ApiMeta {
  timestamp: string
  requestId: string
  version: string
}

export interface PaginatedResponse<T = unknown> extends ApiResponse<T[]> {
  meta: ApiMeta & {
    pagination: {
      page: number
      limit: number
      total: number
      totalPages: number
      hasNext: boolean
      hasPrev: boolean
    }
  }
}

export interface ValidationError {
  field: string
  message: string
  code?: string
}

export interface FormErrors {
  [field: string]: string | string[]
}

// HTTP Status Codes
export enum HttpStatus {
  OK = 200,
  CREATED = 201,
  NO_CONTENT = 204,
  BAD_REQUEST = 400,
  UNAUTHORIZED = 401,
  FORBIDDEN = 403,
  NOT_FOUND = 404,
  CONFLICT = 409,
  UNPROCESSABLE_ENTITY = 422,
  INTERNAL_SERVER_ERROR = 500,
}

// File Upload Types
export interface FileUpload {
  file: File
  name: string
  size: number
  type: string
  lastModified: number
}

export interface UploadProgress {
  loaded: number
  total: number
  percentage: number
}

// WebSocket Message Types
export interface WebSocketMessage<T = unknown> {
  type: string
  payload: T
  timestamp: string
  id?: string
}

export enum WebSocketEventType {
  INGESTION_STARTED = 'ingestion_started',
  INGESTION_PROGRESS = 'ingestion_progress',
  INGESTION_COMPLETED = 'ingestion_completed',
  INGESTION_FAILED = 'ingestion_failed',
  QUALITY_CHECK_COMPLETED = 'quality_check_completed',
  USER_ACTIVITY = 'user_activity',
  SYSTEM_ALERT = 'system_alert',
}

// Zod Schemas
export const PaginationParamsSchema = z.object({
  page: z.number().int().min(1).optional(),
  limit: z.number().int().min(1).max(100).optional(),
  offset: z.number().int().min(0).optional(),
})

export const SortParamsSchema = z.object({
  field: z.string(),
  direction: z.enum(['asc', 'desc']),
})

const PrimitiveFilterValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()])
const FilterValueSchema = z.union([PrimitiveFilterValueSchema, z.array(PrimitiveFilterValueSchema)])

export const FilterParamsSchema = z.object({
  field: z.string(),
  operator: z.enum(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 'contains', 'startswith', 'endswith']),
  value: FilterValueSchema,
})

export const SearchParamsSchema = z.object({
  query: z.string().optional(),
  filters: z.array(FilterParamsSchema).optional(),
  sort: SortParamsSchema.optional(),
  pagination: PaginationParamsSchema.optional(),
})

export const ApiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema.optional(),
    error: z.object({
      code: z.string(),
      message: z.string(),
      details: z.record(z.unknown()).optional(),
      field: z.string().optional(),
    }).optional(),
    meta: z.object({
      timestamp: z.string().datetime(),
      requestId: z.string(),
      version: z.string(),
    }).optional(),
  })

export const PaginatedResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  ApiResponseSchema(z.array(dataSchema)).extend({
    meta: z.object({
      timestamp: z.string().datetime(),
      requestId: z.string(),
      version: z.string(),
      pagination: z.object({
        page: z.number().int(),
        limit: z.number().int(),
        total: z.number().int(),
        totalPages: z.number().int(),
        hasNext: z.boolean(),
        hasPrev: z.boolean(),
      }),
    }),
  })
