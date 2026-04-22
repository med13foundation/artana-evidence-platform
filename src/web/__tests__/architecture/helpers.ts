/**
 * Test utilities for architectural validation.
 * These helpers check that components follow Server-Side Orchestration patterns.
 */

import type { ComponentType, ReactElement } from 'react'
import { render } from '@testing-library/react'
import type { OrchestratedSessionState } from '@/types/generated'

/**
 * Check if a component receives OrchestratedSessionState as a prop.
 */
export function hasOrchestratedStateProp(
  component: ComponentType<unknown>,
  props: Record<string, unknown>
): boolean {
  return 'orchestratedState' in props || 'sessionState' in props
}

/**
 * Extract all useEffect calls from a component's source code.
 * This is a simple heuristic - in a real scenario, you'd use AST parsing.
 */
export function extractUseEffectPatterns(sourceCode: string): {
  hasDataFetching: boolean
  hasClientSideState: boolean
  patterns: string[]
} {
  const patterns: string[] = []
  let hasDataFetching = false
  let hasClientSideState = false

  // Check for common data fetching patterns
  const dataFetchingPatterns = [
    /useEffect\s*\([^)]*fetch\s*\(/,
    /useEffect\s*\([^)]*axios\s*\./,
    /useEffect\s*\([^)]*apiClient\s*\./,
    /useQuery|useMutation|useQueryClient/,
  ]

  // Check for client-side state management
  const statePatterns = [
    /useState\s*\([^)]*\[\]/,
    /useReducer/,
    /useContext.*State/,
  ]

  dataFetchingPatterns.forEach((pattern) => {
    if (pattern.test(sourceCode)) {
      hasDataFetching = true
      patterns.push(`Data fetching pattern: ${pattern.source}`)
    }
  })

  statePatterns.forEach((pattern) => {
    if (pattern.test(sourceCode)) {
      hasClientSideState = true
      patterns.push(`State pattern: ${pattern.source}`)
    }
  })

  return { hasDataFetching, hasClientSideState, patterns }
}

/**
 * Mock OrchestratedSessionState for testing.
 */
export function createMockOrchestratedState(): OrchestratedSessionState {
  return {
    session: {
      id: 'test-session-id',
      owner_id: 'test-user-id',
      research_space_id: 'test-space-id',
      name: 'Test Session',
      selected_sources: ['pubmed'],
      tested_sources: [],
      total_tests_run: 0,
      successful_tests: 0,
      is_active: true,
      last_activity_at: new Date().toISOString(),
      current_parameters: {
        gene_symbol: 'MED13',
        search_term: '',
        max_results: 100,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
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
}

/**
 * Check if a component is marked as "use client".
 */
export function isClientComponent(sourceCode: string): boolean {
  return /^['"]use client['"]/.test(sourceCode.trim())
}

/**
 * Check if a file contains "use server" directive (Server Action).
 */
export function isServerAction(sourceCode: string): boolean {
  return /^['"]use server['"]/.test(sourceCode.trim())
}

/**
 * Validate that a component follows Server-Side Orchestration:
 * 1. Receives OrchestratedSessionState as prop
 * 2. Does not fetch data client-side
 * 3. Uses Server Actions for mutations
 */
export interface OrchestrationValidationResult {
  isValid: boolean
  issues: string[]
  warnings: string[]
}

export function validateOrchestrationPattern(
  componentName: string,
  props: Record<string, unknown>,
  sourceCode?: string
): OrchestrationValidationResult {
  const issues: string[] = []
  const warnings: string[] = []

  // Check 1: Receives OrchestratedSessionState
  if (!hasOrchestratedStateProp({} as ComponentType<unknown>, props)) {
    warnings.push(
      `${componentName} should receive OrchestratedSessionState as a prop`
    )
  }

  // Check 2: No client-side data fetching (if source code available)
  if (sourceCode) {
    const patterns = extractUseEffectPatterns(sourceCode)
    if (patterns.hasDataFetching) {
      issues.push(
        `${componentName} contains client-side data fetching. Use Server Actions instead.`
      )
      issues.push(...patterns.patterns)
    }
  }

  return {
    isValid: issues.length === 0,
    issues,
    warnings,
  }
}
