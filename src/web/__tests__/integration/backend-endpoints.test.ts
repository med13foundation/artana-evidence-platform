/**
 * Frontend-Backend Endpoint Integration Tests
 *
 * These tests validate that:
 * 1. Frontend calls the correct backend endpoints
 * 2. Request/response types match between frontend and backend
 * 3. Error handling is consistent
 * 4. Server Actions map to correct API routes
 */

import { describe, it, expect, jest, beforeEach } from '@jest/globals'
import type { OrchestratedSessionState, UpdateSelectionRequest } from '@/types/generated'

// Mock next-auth before imports
jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

// Mock next/cache
jest.mock('next/cache', () => ({
  revalidatePath: jest.fn(),
}))

// Mock API client
const mockGet = jest.fn<(path: string, config?: unknown) => Promise<{ data: OrchestratedSessionState }>>()
const mockPost = jest.fn<
  (path: string, payload?: unknown, config?: unknown) => Promise<{ data: OrchestratedSessionState }>
>()

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: mockGet,
    post: mockPost,
  },
  authHeaders: jest.fn((token: string) => ({
    headers: { Authorization: `Bearer ${token}` },
  })),
}))

// Mock auth
jest.mock('@/lib/auth', () => ({
  authOptions: {},
}))

// Import after mocks
const {
  fetchSessionState,
  updateSourceSelection,
} = require('@/app/actions/data-discovery')

describe('Frontend-Backend Endpoint Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    require('next-auth').getServerSession.mockResolvedValue({
      user: {
        access_token: 'test-token',
        expires_at: Date.now() + 3600 * 1000
      },
    })
  })

  describe('Data Discovery Endpoints', () => {
    describe('GET /data-discovery/sessions/{session_id}/state', () => {
      it('should call correct endpoint with authentication', async () => {
        const sessionId = 'test-session-123'
        const mockResponse: OrchestratedSessionState = {
          session: {
            id: sessionId,
            owner_id: 'user-123',
            research_space_id: 'space-123',
            name: 'Test Session',
            selected_sources: ['pubmed'],
            tested_sources: [],
            total_tests_run: 0,
            successful_tests: 0,
            is_active: true,
            current_parameters: {
              gene_symbol: 'MED13',
              search_term: '',
              max_results: 100,
            },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            last_activity_at: new Date().toISOString(),
          },
          capabilities: {
            supports_gene_search: true,
            supports_term_search: true,
            supported_parameters: ['gene_symbol', 'search_term'],
            max_results_limit: 500,
          },
          validation: {
            is_valid: true,
            issues: [],
          },
          view_context: {
            selected_count: 1,
            total_available: 5,
            can_run_search: true,
            categories: {},
          },
        }

        mockGet.mockResolvedValue({ data: mockResponse })

        const result = await fetchSessionState(sessionId)

        // Verify endpoint
        expect(mockGet).toHaveBeenCalledWith(
          `/data-discovery/sessions/${sessionId}/state`,
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: 'Bearer test-token',
            }),
          })
        )

        // Verify response structure
        expect(result).toEqual(mockResponse)
        expect(result.session.id).toBe(sessionId)
        expect(result.capabilities).toBeDefined()
        expect(result.validation).toBeDefined()
        expect(result.view_context).toBeDefined()
      })

      it('should handle 404 errors correctly', async () => {
        const sessionId = 'non-existent-session'
        const error = {
          response: {
            status: 404,
            data: { detail: 'Session not found' },
          },
        }

        mockGet.mockRejectedValue(error)

        await expect(fetchSessionState(sessionId)).rejects.toThrow(
          'Failed to load session state'
        )
      })

      it('should handle 500 errors correctly', async () => {
        const sessionId = 'test-session'
        const error = {
          response: {
            status: 500,
            data: { detail: 'Internal server error' },
          },
        }

        mockGet.mockRejectedValue(error)

        await expect(fetchSessionState(sessionId)).rejects.toThrow(
          'Failed to load session state'
        )
      })
    })

    describe('POST /data-discovery/sessions/{session_id}/selection', () => {
      it('should call correct endpoint with correct payload', async () => {
        const sessionId = 'test-session-123'
        const sourceIds = ['pubmed', 'clinvar']
        const path = '/data-discovery'

        const mockResponse: OrchestratedSessionState = {
          session: {
            id: sessionId,
            owner_id: 'user-123',
            research_space_id: 'space-123',
            name: 'Test Session',
            selected_sources: sourceIds,
            tested_sources: [],
            total_tests_run: 0,
            successful_tests: 0,
            is_active: true,
            current_parameters: {
              gene_symbol: 'MED13',
              search_term: '',
              max_results: 100,
            },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            last_activity_at: new Date().toISOString(),
          },
          capabilities: {
            supports_gene_search: true,
            supports_term_search: true,
            supported_parameters: ['gene_symbol', 'search_term'],
            max_results_limit: 500,
          },
          validation: {
            is_valid: true,
            issues: [],
          },
          view_context: {
            selected_count: 2,
            total_available: 5,
            can_run_search: true,
            categories: {},
          },
        }

        mockPost.mockResolvedValue({ data: mockResponse })

        const result = await updateSourceSelection(sessionId, sourceIds, path)

        // Verify endpoint and payload
        const expectedPayload: UpdateSelectionRequest = {
          source_ids: sourceIds,
        }

        expect(mockPost).toHaveBeenCalledWith(
          `/data-discovery/sessions/${sessionId}/selection`,
          expectedPayload,
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: 'Bearer test-token',
            }),
          })
        )

        // Verify response
        expect(result.success).toBe(true)
        expect(result.state).toEqual(mockResponse)
        expect(result.state?.session.selected_sources).toEqual(sourceIds)
      })

      it('should handle validation errors from backend', async () => {
        const sessionId = 'test-session-123'
        const invalidSourceIds: string[] = [] // Empty array should fail validation

        const error = {
          response: {
            status: 422,
            data: {
              detail: [
                {
                  msg: 'At least one source must be selected',
                  loc: ['body', 'source_ids'],
                },
              ],
            },
          },
        }

        mockPost.mockRejectedValue(error)

        const result = await updateSourceSelection(
          sessionId,
          invalidSourceIds,
          '/data-discovery'
        )

        expect(result.success).toBe(false)
        expect(result.error).toContain('At least one source must be selected')
        expect(result.error).toContain('source_ids')
      })

      it('should handle Pydantic validation errors correctly', async () => {
        const sessionId = 'test-session-123'
        const invalidSourceIds = ['invalid-source-id']

        const error = {
          response: {
            status: 422,
            data: {
              detail: [
                {
                  msg: 'Invalid source ID format',
                  loc: ['body', 'source_ids', 0],
                },
              ],
            },
          },
        }

        mockPost.mockRejectedValue(error)

        const result = await updateSourceSelection(
          sessionId,
          invalidSourceIds,
          '/data-discovery'
        )

        expect(result.success).toBe(false)
        expect(result.error).toContain('Invalid source ID format')
        expect(result.error).toContain('source_ids.0')
      })

      it('should handle network errors', async () => {
        const sessionId = 'test-session-123'
        const sourceIds = ['pubmed']

        const error = {
          message: 'Network Error',
          code: 'ECONNABORTED',
        }

        mockPost.mockRejectedValue(error)

        const result = await updateSourceSelection(
          sessionId,
          sourceIds,
          '/data-discovery'
        )

        expect(result.success).toBe(false)
        expect(result.error).toBe('Network Error')
      })
    })
  })

  describe('Request/Response Type Validation', () => {
    it('UpdateSelectionRequest should match backend schema', () => {
      const request: UpdateSelectionRequest = {
        source_ids: ['pubmed', 'clinvar'],
      }

      if (!request.source_ids) {
        throw new Error('source_ids should be defined')
      }

      expect(Array.isArray(request.source_ids)).toBe(true)
      expect(request.source_ids.length).toBeGreaterThan(0)
      expect(typeof request.source_ids[0]).toBe('string')
    })

    it('OrchestratedSessionState response should match backend DTO', () => {
      const state: OrchestratedSessionState = {
        session: {
          id: 'test-id',
          owner_id: 'user-id',
          research_space_id: 'space-id',
          name: 'Test Session',
          selected_sources: [],
          tested_sources: [],
          total_tests_run: 0,
          successful_tests: 0,
          is_active: true,
          current_parameters: {
            gene_symbol: 'MED13',
            search_term: '',
            max_results: 100,
          },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_activity_at: new Date().toISOString(),
        },
        capabilities: {
          supports_gene_search: true,
          supports_term_search: false,
          supported_parameters: [],
          max_results_limit: 500,
        },
        validation: {
          is_valid: true,
          issues: [],
        },
        view_context: {
          selected_count: 0,
          total_available: 0,
          can_run_search: false,
          categories: {},
        },
      }

      // Validate structure matches backend expectations
      expect(state.session).toBeDefined()
      expect(state.capabilities).toBeDefined()
      expect(state.validation).toBeDefined()
      expect(state.view_context).toBeDefined()
    })
  })

  describe('Error Handling Consistency', () => {
    it('should handle all HTTP error status codes', async () => {
      const errorCodes = [400, 401, 403, 404, 422, 500, 503]

      for (const statusCode of errorCodes) {
        mockPost.mockRejectedValueOnce({
          response: {
            status: statusCode,
            data: { detail: `Error ${statusCode}` },
          },
        })

        const result = await updateSourceSelection(
          'test-session',
          ['pubmed'],
          '/data-discovery'
        )

        expect(result.success).toBe(false)
        expect(result.error).toBeDefined()
      }
    })

    it('should preserve backend error messages in responses', async () => {
      const backendError = {
        response: {
          status: 422,
          data: {
            detail: 'Custom backend validation error message',
          },
        },
      }

      mockPost.mockRejectedValue(backendError)

      const result = await updateSourceSelection(
        'test-session',
        ['pubmed'],
        '/data-discovery'
      )

      expect(result.success).toBe(false)
      expect(result.error).toBe('Custom backend validation error message')
    })
  })
})
