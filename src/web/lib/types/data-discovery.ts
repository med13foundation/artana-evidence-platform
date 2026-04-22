// TypeScript types for Data Source Discovery (aligned with generated DTOs)

import type {
  AddToSpaceRequest as AddToSpaceRequestModel,
  AdvancedQueryParametersModel,
  CreatePubmedPresetRequestModel,
  CreateSessionRequest as CreateSessionRequestModel,
  DataDiscoverySessionResponse,
  DiscoveryPresetResponse,
  DiscoverySearchJobResponse,
  ExecuteTestRequest as ExecuteTestRequestModel,
  PubmedDownloadRequestModel,
  QueryParametersModel,
  QueryTestResultResponse,
  QueryParameterCapabilities as QueryParameterCapabilitiesModel,
  RunPubmedSearchRequestModel,
  SourceCatalogEntry as SourceCatalogEntryModel,
  StorageOperationResponse,
  UpdateParametersRequest as UpdateParametersRequestModel,
} from '@/types/generated'

export type QueryParameterType = 'gene' | 'term' | 'gene_and_term' | 'none' | 'api'

export type TestResultStatus =
  | 'pending'
  | 'success'
  | 'error'
  | 'timeout'
  | 'validation_failed'

export type QueryParameters = QueryParametersModel

export type PubmedSortOption =
  | 'relevance'
  | 'publication_date'
  | 'author'
  | 'journal'
  | 'title'

export type AdvancedQueryParameters = AdvancedQueryParametersModel

export type QueryParameterCapabilities = QueryParameterCapabilitiesModel

export type SourceCatalogEntry = SourceCatalogEntryModel

export type QueryTestResult = QueryTestResultResponse

export type DataDiscoverySession = DataDiscoverySessionResponse

export type CreateSessionRequest = CreateSessionRequestModel

export type UpdateParametersRequest = UpdateParametersRequestModel

export type ExecuteTestRequest = ExecuteTestRequestModel

export type AddToSpaceRequest = AddToSpaceRequestModel

export interface PromoteSourceRequest {
  source_config?: Record<string, unknown>
}

export interface PromoteSourceResponse {
  data_source_id: string
  message: string
}

export type DiscoveryPreset = DiscoveryPresetResponse

export type DiscoverySearchJob = DiscoverySearchJobResponse

export type StorageOperationSummary = StorageOperationResponse

export type CreatePubmedPresetRequest = CreatePubmedPresetRequestModel

export type RunPubmedSearchRequest = RunPubmedSearchRequestModel

export type PubmedDownloadRequest = PubmedDownloadRequestModel
