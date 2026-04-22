import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import CurationHypothesesCard from '@/app/(dashboard)/spaces/[spaceId]/curation/curation-hypotheses-card'

const listHypothesesActionMock = jest.fn()
const createManualHypothesisActionMock = jest.fn()
const generateHypothesesActionMock = jest.fn()
const updateRelationClaimStatusActionMock = jest.fn()
const listClaimRelationsActionMock = jest.fn()
const createClaimRelationActionMock = jest.fn()
const updateClaimRelationReviewActionMock = jest.fn()
const listClaimsByEntityActionMock = jest.fn()

jest.mock('@/app/actions/kernel-hypotheses', () => ({
  listHypothesesAction: (...args: unknown[]) => listHypothesesActionMock(...args),
  createManualHypothesisAction: (...args: unknown[]) => createManualHypothesisActionMock(...args),
  generateHypothesesAction: (...args: unknown[]) => generateHypothesesActionMock(...args),
}))

jest.mock('@/app/actions/kernel-relations', () => ({
  updateRelationClaimStatusAction: (...args: unknown[]) => updateRelationClaimStatusActionMock(...args),
}))

jest.mock('@/app/actions/kernel-claim-relations', () => ({
  listClaimRelationsAction: (...args: unknown[]) => listClaimRelationsActionMock(...args),
  createClaimRelationAction: (...args: unknown[]) => createClaimRelationActionMock(...args),
  updateClaimRelationReviewAction: (...args: unknown[]) => updateClaimRelationReviewActionMock(...args),
  listClaimsByEntityAction: (...args: unknown[]) => listClaimsByEntityActionMock(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

const hypothesis = {
  claim_id: '11111111-1111-1111-1111-111111111111',
  polarity: 'HYPOTHESIS' as const,
  claim_status: 'OPEN' as const,
  validation_state: 'ALLOWED',
  persistability: 'PERSISTABLE' as const,
  confidence: 0.82,
  source_label: 'MED13',
  relation_type: 'ASSOCIATED_WITH',
  target_label: 'Autism',
  claim_text: 'MED13 may influence autism through transcription regulation.',
  origin: 'graph_agent',
  seed_entity_ids: ['22222222-2222-2222-2222-222222222222'],
  supporting_provenance_ids: ['33333333-3333-3333-3333-333333333333'],
  created_at: '2026-03-03T10:00:00Z',
  metadata: {
    origin: 'graph_agent',
  },
}

const secondHypothesis = {
  ...hypothesis,
  claim_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  source_label: 'Mediator complex',
  relation_type: 'CAUSES',
  target_label: 'Transcription dysregulation',
  claim_text: 'Mediator complex disruption may cause transcription dysregulation.',
  created_at: '2026-03-03T11:00:00Z',
}

describe('CurationHypothesesCard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    listHypothesesActionMock.mockResolvedValue({
      success: true,
      data: [hypothesis, secondHypothesis],
    })
    createManualHypothesisActionMock.mockResolvedValue({
      success: true,
      data: hypothesis,
    })
    generateHypothesesActionMock.mockResolvedValue({
      success: true,
      data: {
        run_id: 'run-1',
        requested_seed_count: 1,
        used_seed_count: 1,
        candidates_seen: 4,
        created_count: 1,
        deduped_count: 0,
        errors: [],
        hypotheses: [],
      },
    })
    updateRelationClaimStatusActionMock.mockResolvedValue({
      success: true,
      data: {
        id: hypothesis.claim_id,
      },
    })
    listClaimRelationsActionMock.mockResolvedValue({
      success: true,
      data: [
        {
          id: '55555555-5555-5555-5555-555555555555',
          research_space_id: 'space-1',
          source_claim_id: hypothesis.claim_id,
          target_claim_id: secondHypothesis.claim_id,
          relation_type: 'SUPPORTS',
          agent_run_id: null,
          source_document_id: null,
          confidence: 0.7,
          review_status: 'PROPOSED',
          evidence_summary: null,
          metadata: {},
          created_at: '2026-03-04T12:00:00Z',
        },
      ],
    })
    createClaimRelationActionMock.mockResolvedValue({
      success: true,
      data: {
        id: '44444444-4444-4444-4444-444444444444',
        research_space_id: 'space-1',
        source_claim_id: hypothesis.claim_id,
        target_claim_id: secondHypothesis.claim_id,
        relation_type: 'SUPPORTS',
        agent_run_id: null,
        source_document_id: null,
        confidence: 0.7,
        review_status: 'PROPOSED',
        evidence_summary: null,
        metadata: {},
        created_at: '2026-03-04T12:00:00Z',
      },
    })
    updateClaimRelationReviewActionMock.mockImplementation(
      async (_spaceId: string, relationId: string, reviewStatus: 'PROPOSED' | 'ACCEPTED' | 'REJECTED') => ({
        success: true,
        data: {
          id: relationId,
          research_space_id: 'space-1',
          source_claim_id: hypothesis.claim_id,
          target_claim_id: secondHypothesis.claim_id,
          relation_type: 'SUPPORTS',
          agent_run_id: null,
          source_document_id: null,
          confidence: 0.7,
          review_status: reviewStatus,
          evidence_summary: null,
          metadata: {},
          created_at: '2026-03-04T12:00:00Z',
        },
      }),
    )
    listClaimsByEntityActionMock.mockResolvedValue({
      success: true,
      data: { claims: [], total: 0, offset: 0, limit: 20 },
    })
  })

  it('loads hypotheses on mount', async () => {
    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    await waitFor(() => {
      expect(listHypothesesActionMock).toHaveBeenCalledWith('space-1')
    })
    expect(listClaimRelationsActionMock).toHaveBeenCalledWith('space-1', {
      offset: 0,
      limit: 200,
    })
    expect(screen.getAllByText('MED13 -> ASSOCIATED_WITH -> Autism').length).toBeGreaterThan(0)
  })

  it('logs a manual hypothesis', async () => {
    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    fireEvent.change(screen.getByLabelText('Hypothesis statement'), {
      target: { value: 'Manual statement' },
    })
    fireEvent.change(screen.getByLabelText('Rationale'), {
      target: { value: 'Manual rationale' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Log hypothesis' }))

    await waitFor(() => {
      expect(createManualHypothesisActionMock).toHaveBeenCalledWith('space-1', {
        statement: 'Manual statement',
        rationale: 'Manual rationale',
        seedEntityIds: [],
        sourceType: 'manual',
      })
    })
  })

  it('hides auto-generate button when feature flag is disabled', async () => {
    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={false} />)

    await waitFor(() => {
      expect(listHypothesesActionMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: 'Auto-generate from graph' })).not.toBeInTheDocument()
  })

  it('runs auto-generation and triage action', async () => {
    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    fireEvent.click(screen.getByRole('button', { name: 'Auto-generate from graph' }))

    await waitFor(() => {
      expect(generateHypothesesActionMock).toHaveBeenCalledWith('space-1', {
        seed_entity_ids: null,
        source_type: 'pubmed',
        max_depth: 2,
        max_hypotheses: 20,
      })
    })

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Needs mapping' }).length).toBeGreaterThan(0)
    })

    fireEvent.click(screen.getAllByRole('button', { name: 'Needs mapping' })[0])
    await waitFor(() => {
      expect(updateRelationClaimStatusActionMock).toHaveBeenCalledWith('space-1', hypothesis.claim_id, 'NEEDS_MAPPING')
    })
  })

  it('renders generation feedback details for zero-result auto-generation', async () => {
    generateHypothesesActionMock.mockResolvedValueOnce({
      success: true,
      data: {
        run_id: 'run-2',
        requested_seed_count: 1,
        used_seed_count: 1,
        candidates_seen: 4,
        created_count: 0,
        deduped_count: 0,
        errors: ['all_candidates_below_threshold'],
        hypotheses: [],
      },
    })

    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    fireEvent.click(screen.getByRole('button', { name: 'Auto-generate from graph' }))

    await waitFor(() => {
      expect(screen.getByText(/Exploration completed but produced no candidate hypotheses\./)).toBeInTheDocument()
    })
    expect(
      screen.getByText(/Candidates were found but all scored below the acceptance threshold\./),
    ).toBeInTheDocument()
  })

  it('renders hypothesis load error state', async () => {
    listHypothesesActionMock.mockResolvedValueOnce({
      success: false,
      error: 'Failed to load hypotheses',
    })

    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    await waitFor(() => {
      expect(screen.getAllByText('Failed to load hypotheses').length).toBeGreaterThan(0)
    })
  })

  it('creates and reviews claim relation links from the hypotheses card', async () => {
    render(<CurationHypothesesCard spaceId="space-1" canEdit={true} autoGenerationEnabled={true} />)

    await waitFor(() => {
      expect(screen.getAllByText('MED13 -> ASSOCIATED_WITH -> Autism').length).toBeGreaterThan(0)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Create claim link' }))

    await waitFor(() => {
      expect(createClaimRelationActionMock).toHaveBeenCalledWith('space-1', {
        source_claim_id: hypothesis.claim_id,
        target_claim_id: secondHypothesis.claim_id,
        relation_type: 'SUPPORTS',
        assessment: {
          support_band: 'SUPPORTED',
          grounding_level: 'GRAPH_INFERENCE',
          mapping_status: 'RESOLVED',
          speculation_level: 'DIRECT',
          confidence_rationale: 'Manual claim-link curation selected support_band=SUPPORTED.',
        },
        review_status: 'PROPOSED',
        metadata: { origin: 'manual_hypothesis_overlay' },
      })
    })

    fireEvent.click(screen.getAllByRole('button', { name: 'Accept' })[0])
    await waitFor(() => {
      expect(updateClaimRelationReviewActionMock).toHaveBeenCalledWith('space-1', expect.any(String), 'ACCEPTED')
    })
  })
})
