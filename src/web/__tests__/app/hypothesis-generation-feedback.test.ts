import { buildHypothesisGenerationFeedback } from '@/app/(dashboard)/spaces/[spaceId]/curation/hypotheses/hypothesis-generation-feedback'
import type { GenerateHypothesesResponse } from '@/types/kernel'

function buildResponse(
  overrides: Partial<GenerateHypothesesResponse>,
): GenerateHypothesesResponse {
  return {
    run_id: 'run-1',
    requested_seed_count: 1,
    used_seed_count: 1,
    candidates_seen: 1,
    created_count: 0,
    deduped_count: 0,
    errors: [],
    hypotheses: [],
    ...overrides,
  }
}

describe('buildHypothesisGenerationFeedback', () => {
  it('returns success tone when hypotheses were created', () => {
    const feedback = buildHypothesisGenerationFeedback(
      buildResponse({ created_count: 3, deduped_count: 2 }),
    )

    expect(feedback.tone).toBe('success')
    expect(feedback.summary).toBe('Staged 3 candidate hypotheses for review.')
    expect(feedback.details).toEqual([])
  })

  it('returns actionable error details for zero-result runs', () => {
    const feedback = buildHypothesisGenerationFeedback(
      buildResponse({
        used_seed_count: 0,
        candidates_seen: 0,
        errors: ['no_seed_entities_resolved', 'all_candidates_deduped'],
        deduped_count: 4,
      }),
    )

    expect(feedback.tone).toBe('error')
    expect(feedback.summary).toBe(
      'Exploration completed but produced no candidate hypotheses.',
    )
    expect(feedback.details).toEqual(
      expect.arrayContaining([
        'No seeds were resolved for this space.',
        'No seed entities were available for graph exploration.',
        'Candidates were found but all were duplicates of existing hypotheses.',
      ]),
    )
  })

  it.each([
    {
      code: 'no_candidates_discovered',
      expected: 'Graph exploration returned no candidate hypotheses.',
    },
    {
      code: 'all_candidates_below_threshold',
      expected: 'Candidates were found but all scored below the acceptance threshold.',
    },
    {
      code: 'no_candidates_selected',
      expected: 'Candidates were found but none passed final selection.',
    },
  ])('maps known zero-result error code "$code"', ({ code, expected }) => {
    const feedback = buildHypothesisGenerationFeedback(
      buildResponse({
        created_count: 0,
        errors: [code],
      }),
    )

    expect(feedback.tone).toBe('error')
    expect(feedback.details).toContain(expected)
  })

  it('maps seed discovery and endpoint unresolved parametric errors', () => {
    const feedback = buildHypothesisGenerationFeedback(
      buildResponse({
        errors: [
          'seed_discovery_failed:123:timeout',
          'candidate_endpoint_unresolved:source',
        ],
      }),
    )

    expect(feedback.details).toEqual(
      expect.arrayContaining([
        'Seed discovery failed (timeout).',
        'Some candidates were dropped because source/target entities could not be resolved.',
      ]),
    )
  })

  it('falls back to humanized text for unknown error codes', () => {
    const feedback = buildHypothesisGenerationFeedback(
      buildResponse({
        errors: ['unexpected_graph_runtime_error'],
      }),
    )

    expect(feedback.details).toContain('unexpected graph runtime error')
  })
})
