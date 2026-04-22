import type { GenerateHypothesesResponse, HypothesisResponse } from '@/types/kernel'

import { ALL_FILTER_VALUE, type HypothesisClaimStatus } from './hypothesis-utils'

export interface UseHypothesesCardControllerParams {
  spaceId: string
  canEdit: boolean
  autoGenerationEnabled: boolean
}

export interface HypothesesCardState {
  hypotheses: HypothesisResponse[]
  statement: string
  rationale: string
  seedInput: string
  originFilter: string
  statusFilter: string
  certaintyFilter: string
  isLoading: boolean
  isSubmitting: boolean
  isGenerating: boolean
  pendingClaimId: string | null
  lastGeneration: GenerateHypothesesResponse | null
  error: string | null
  feedbackMessage: string | null
  feedbackTone: 'default' | 'success' | 'error'
}

export const INITIAL_STATE: HypothesesCardState = {
  hypotheses: [],
  statement: '',
  rationale: '',
  seedInput: '',
  originFilter: ALL_FILTER_VALUE,
  statusFilter: ALL_FILTER_VALUE,
  certaintyFilter: ALL_FILTER_VALUE,
  isLoading: false,
  isSubmitting: false,
  isGenerating: false,
  pendingClaimId: null,
  lastGeneration: null,
  error: null,
  feedbackMessage: null,
  feedbackTone: 'default',
}

export interface HypothesesCardController {
  hypotheses: HypothesisResponse[]
  filteredHypotheses: HypothesisResponse[]
  availableOrigins: string[]
  statement: string
  rationale: string
  seedInput: string
  originFilter: string
  statusFilter: string
  certaintyFilter: string
  isLoading: boolean
  isSubmitting: boolean
  isGenerating: boolean
  pendingClaimId: string | null
  lastGeneration: GenerateHypothesesResponse | null
  error: string | null
  feedbackMessage: string | null
  feedbackTone: 'default' | 'success' | 'error'
  changeStatement: (value: string) => void
  changeRationale: (value: string) => void
  changeSeedInput: (value: string) => void
  changeOriginFilter: (value: string) => void
  changeStatusFilter: (value: string) => void
  changeCertaintyFilter: (value: string) => void
  refreshHypotheses: () => Promise<void>
  submitManualHypothesis: () => Promise<void>
  runAutoGeneration: () => Promise<void>
  triageHypothesis: (
    hypothesis: HypothesisResponse,
    nextStatus: HypothesisClaimStatus,
  ) => Promise<void>
}
