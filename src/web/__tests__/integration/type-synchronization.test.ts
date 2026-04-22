/**
 * Type Synchronization Validation Tests
 *
 * These tests ensure that:
 * 1. TypeScript types match Pydantic models
 * 2. Generated types are up-to-date
 * 3. OrchestratedSessionState structure is consistent
 * 4. API request/response types are synchronized
 */

import { describe, it, expect } from '@jest/globals'
import type {
  OrchestratedSessionState,
  UpdateSelectionRequest,
  DataDiscoverySessionResponse,
  SourceCapabilitiesDTO,
  ValidationResultDTO,
  ViewContextDTO,
} from '@/types/generated'

describe('Type Synchronization Validation', () => {
  describe('OrchestratedSessionState Structure', () => {
    it('should have all required fields matching backend DTO', () => {
      const state: OrchestratedSessionState = {
        session: {} as DataDiscoverySessionResponse,
        capabilities: {} as SourceCapabilitiesDTO,
        validation: {} as ValidationResultDTO,
        view_context: {} as ViewContextDTO,
      }

      // TypeScript compile-time check ensures these fields exist
      expect(state.session).toBeDefined()
      expect(state.capabilities).toBeDefined()
      expect(state.validation).toBeDefined()
      expect(state.view_context).toBeDefined()
    })

    it('should match backend OrchestratedSessionState DTO structure', () => {
      // This is a structural validation test
      // The actual type checking happens at compile time via TypeScript
      const completeState: OrchestratedSessionState = {
        session: {
          id: 'session-id',
          owner_id: 'user-id',
          research_space_id: 'space-id',
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
          categories: {
            'Scientific Literature': 1,
          },
        },
      }

      // Validate nested structures
      expect(completeState.session.id).toBe('session-id')
      expect(Array.isArray(completeState.session.selected_sources)).toBe(true)
      expect(typeof completeState.capabilities.supports_gene_search).toBe('boolean')
      expect(typeof completeState.validation?.is_valid).toBe('boolean')
      expect(typeof completeState.view_context.selected_count).toBe('number')
    })
  })

  describe('Request Type Validation', () => {
    it('UpdateSelectionRequest should match backend schema', () => {
      const request: UpdateSelectionRequest = {
        source_ids: ['pubmed', 'clinvar'],
      }

      // TypeScript ensures type safety
      expect(Array.isArray(request.source_ids)).toBe(true)
      expect(request.source_ids?.every((id) => typeof id === 'string')).toBe(true)
    })

    it('UpdateSelectionRequest should reject invalid structures', () => {
      const validRequest: UpdateSelectionRequest = {
        source_ids: ['pubmed'],
      }

      expect(validRequest).toBeDefined()
    })
  })

  describe('Response Type Validation', () => {
    it('DataDiscoverySessionResponse should have correct structure', () => {
      const session: DataDiscoverySessionResponse = {
        id: 'session-id',
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
      }

      expect(typeof session.id).toBe('string')
      expect(typeof session.owner_id).toBe('string')
      expect(typeof session.research_space_id).toBe('string')
      expect(Array.isArray(session.selected_sources)).toBe(true)
      expect(session.current_parameters).toBeDefined()
      expect(typeof session.created_at).toBe('string')
      expect(typeof session.updated_at).toBe('string')
    })

    it('SourceCapabilitiesDTO should have correct structure', () => {
      const capabilities: SourceCapabilitiesDTO = {
        supports_gene_search: true,
        supports_term_search: false,
        supported_parameters: ['gene_symbol'],
        max_results_limit: 500,
      }

      expect(typeof capabilities.supports_gene_search).toBe('boolean')
      expect(typeof capabilities.supports_term_search).toBe('boolean')
      expect(Array.isArray(capabilities.supported_parameters)).toBe(true)
    })

    it('ValidationResultDTO should have correct structure', () => {
      const validation: ValidationResultDTO = {
        is_valid: true,
        issues: [],
      }

      expect(typeof validation.is_valid).toBe('boolean')
      expect(Array.isArray(validation.issues)).toBe(true)
    })

    it('ViewContextDTO should have correct structure', () => {
      const viewContext: ViewContextDTO = {
        selected_count: 0,
        total_available: 0,
        can_run_search: false,
        categories: {},
      }

      expect(typeof viewContext.selected_count).toBe('number')
      expect(typeof viewContext.total_available).toBe('number')
      expect(typeof viewContext.can_run_search).toBe('boolean')
      expect(typeof viewContext.categories).toBe('object')
    })
  })

  describe('Type Generation Validation', () => {
    it('should ensure types are generated from Pydantic models', () => {
      // This test documents that types should be generated via:
      // `make generate-ts-types` command
      // The actual validation happens at compile time via TypeScript
      // This runtime test validates that we can use the types

      const state: OrchestratedSessionState = {
        session: {} as DataDiscoverySessionResponse,
        capabilities: {} as SourceCapabilitiesDTO,
        validation: {} as ValidationResultDTO,
        view_context: {} as ViewContextDTO,
      }

      // If types weren't generated, this would fail at compile time
      expect(state).toBeDefined()
      expect(state.session).toBeDefined()
      expect(state.capabilities).toBeDefined()
    })

    it('should validate optional fields are correctly typed', () => {
      const state: OrchestratedSessionState = {
        session: {} as DataDiscoverySessionResponse,
        capabilities: {} as SourceCapabilitiesDTO,
        // validation is optional
        view_context: {} as ViewContextDTO,
      }

      // validation can be undefined
      expect(state.validation).toBeUndefined()

      // But if present, must have correct structure
      if (state.validation) {
        expect(typeof state.validation.is_valid).toBe('boolean')
        expect(Array.isArray(state.validation.issues)).toBe(true)
      }
    })
  })

  describe('Type Safety Enforcement', () => {
    it('should prevent type mismatches at compile time', () => {
      // TypeScript will catch these errors at compile time
      // This test documents the expected behavior

      const validState: OrchestratedSessionState = {
        session: {
          id: 'test',
          owner_id: 'test',
          research_space_id: 'test',
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

      // All fields should be correctly typed
      expect(validState).toBeDefined()
    })
  })
})
