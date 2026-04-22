import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import SpaceCurationClient from '@/app/(dashboard)/spaces/[spaceId]/space-curation-client'

const routerPushMock = jest.fn()
const routerRefreshMock = jest.fn()
const listClaimRelationsActionMock = jest.fn()
const listClaimParticipantsActionMock = jest.fn()
const listClaimsByEntityActionMock = jest.fn()
const updateClaimRelationReviewActionMock = jest.fn()
const getClaimParticipantCoverageActionMock = jest.fn()
const runClaimParticipantBackfillActionMock = jest.fn()
const listHypothesesActionMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: routerPushMock,
    replace: jest.fn(),
    refresh: routerRefreshMock,
  }),
}))

jest.mock('@/app/actions/kernel-relations', () => ({
  searchKernelRelationNodesAction: jest.fn().mockResolvedValue({
    success: true,
    data: { options: [], hasMore: false, nextOffset: 0 },
  }),
  updateKernelRelationStatusAction: jest.fn().mockResolvedValue({ success: true, data: {} }),
  updateRelationClaimStatusAction: jest.fn().mockResolvedValue({ success: true, data: {} }),
}))

jest.mock('@/app/actions/kernel-claim-relations', () => ({
  listClaimRelationsAction: (...args: unknown[]) => listClaimRelationsActionMock(...args),
  listClaimParticipantsAction: (...args: unknown[]) => listClaimParticipantsActionMock(...args),
  listClaimsByEntityAction: (...args: unknown[]) => listClaimsByEntityActionMock(...args),
  updateClaimRelationReviewAction: (...args: unknown[]) => updateClaimRelationReviewActionMock(...args),
  getClaimParticipantCoverageAction: (...args: unknown[]) => getClaimParticipantCoverageActionMock(...args),
  runClaimParticipantBackfillAction: (...args: unknown[]) => runClaimParticipantBackfillActionMock(...args),
}))

jest.mock('@/app/actions/kernel-hypotheses', () => ({
  listHypothesesAction: (...args: unknown[]) => listHypothesesActionMock(...args),
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/curation/curation-hypotheses-card', () => ({
  __esModule: true,
  default: () => <div>Hypotheses</div>,
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

describe('SpaceCurationClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    listClaimRelationsActionMock.mockResolvedValue({ success: true, data: [] })
    listClaimParticipantsActionMock.mockResolvedValue({ success: true, data: [] })
    listClaimsByEntityActionMock.mockResolvedValue({
      success: true,
      data: { claims: [], total: 0, offset: 0, limit: 20 },
    })
    updateClaimRelationReviewActionMock.mockResolvedValue({ success: true, data: {} })
    getClaimParticipantCoverageActionMock.mockResolvedValue({
      success: true,
      data: {
        total_claims: 0,
        claims_with_any_participants: 0,
        claims_with_subject: 0,
        claims_with_object: 0,
        unresolved_subject_endpoints: 0,
        unresolved_object_endpoints: 0,
        unresolved_endpoint_rate: 0,
      },
    })
    runClaimParticipantBackfillActionMock.mockResolvedValue({
      success: true,
      data: {
        scanned_claims: 0,
        created_participants: 0,
        skipped_existing: 0,
        unresolved_endpoints: 0,
        dry_run: true,
      },
    })
    listHypothesesActionMock.mockResolvedValue({ success: true, data: [] })
  })

  const baseProps = {
    spaceId: 'space-1',
    relations: {
      relations: [
        {
          id: 'rel-1',
          research_space_id: 'space-1',
          source_id: 'ent-1',
          relation_type: 'ASSOCIATED_WITH',
          target_id: 'ent-2',
          confidence: 0.86,
          aggregate_confidence: 0.86,
          source_count: 1,
          highest_evidence_tier: 'LITERATURE',
          curation_status: 'DRAFT',
          provenance_id: null,
          reviewed_by: null,
          reviewed_at: null,
          created_at: '2026-02-26T00:00:00Z',
          updated_at: '2026-02-27T00:00:00Z',
          evidence_summary: 'Evidence summary',
          evidence_tier: 'LITERATURE',
        },
      ],
      total: 1,
      offset: 0,
      limit: 25,
    },
    relationsError: null,
    claims: {
      claims: [
        {
          id: 'claim-1',
          research_space_id: 'space-1',
          source_document_id: 'doc-1',
          agent_run_id: 'run-1',
          source_type: 'pubmed',
          relation_type: 'ASSOCIATED_WITH',
          target_type: 'DISEASE',
          source_label: 'MED13',
          target_label: 'Cardiomyopathy',
          confidence: 0.45,
          validation_state: 'FORBIDDEN',
          validation_reason: 'Out of ontology constraints',
          persistability: 'NON_PERSISTABLE' as const,
          claim_status: 'OPEN' as const,
          polarity: 'UNCERTAIN' as const,
          claim_text: 'MED13 was associated with cardiomyopathy in one cohort.',
          claim_section: 'results',
          linked_relation_id: null,
          metadata: {},
          triaged_by: null,
          triaged_at: null,
          created_at: '2026-02-27T00:00:00Z',
          updated_at: '2026-02-27T00:00:00Z',
        },
      ],
      total: 1,
      offset: 0,
      limit: 25,
    },
    claimsError: null,
    relationConflicts: {
      conflicts: [],
      total: 0,
      offset: 0,
      limit: 50,
    },
    entityLabelsById: {
      'ent-1': 'MED13',
      'ent-2': 'Cardiomyopathy',
    },
    canCurate: true,
    hypothesisGenerationEnabled: true,
    relationFilters: {
      graphMode: 'canonical' as const,
      relationType: '',
      curationStatus: '',
      validationState: '',
      sourceDocumentId: '',
      certaintyBand: '',
      nodeQuery: '',
      nodeIds: [],
      focusRelationId: '',
      offset: 0,
      limit: 25,
    },
    claimFilters: {
      claimStatus: '',
      validationState: '',
      persistability: '',
      polarity: '',
      relationType: '',
      sourceDocumentId: '',
      linkedRelationId: '',
      certaintyBand: '',
      offset: 0,
      limit: 25,
    },
  }

  it('renders graph relations tab with certainty and graph filters', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="graph" />)

    expect(screen.getByText('Graph Relations')).toBeInTheDocument()
    expect(screen.getByText('Extraction Claims')).toBeInTheDocument()
    expect(screen.getByText('AI High certainty')).toBeInTheDocument()
    expect(screen.getByText('Node IDs (optional)')).toBeInTheDocument()
    expect(screen.getByText('Approve')).toBeInTheDocument()
  })

  it('renders extraction claims tab with certainty and claim filters', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="claims" />)

    expect(screen.getByText('Hypotheses')).toBeInTheDocument()
    expect(screen.getByText('AI Low certainty')).toBeInTheDocument()
    expect(screen.getByText('Claim Status')).toBeInTheDocument()
    expect(screen.getByText('Validation State')).toBeInTheDocument()
    expect(screen.getByText('Polarity')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Needs mapping/i }),
    ).toBeInTheDocument()
  })

  it('renders conflict badge on graph cards when relation is conflicting', () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationConflicts={{
          conflicts: [
            {
              relation_id: 'rel-1',
              support_count: 3,
              refute_count: 1,
              support_claim_ids: ['claim-a', 'claim-b', 'claim-c'],
              refute_claim_ids: ['claim-d'],
            },
          ],
          total: 1,
          offset: 0,
          limit: 50,
        }}
      />,
    )

    expect(screen.getByText('Conflict 3/1')).toBeInTheDocument()
  })

  it('renders evidence sentence details and paper links in graph cards', () => {
    const propsWithSentence = {
      ...baseProps,
      relations: {
        ...baseProps.relations,
        relations: [
          {
            ...baseProps.relations.relations[0],
            evidence_summary: null,
            evidence_sentence:
              'MED13 variation was associated with cardiomyopathy in the study cohort.',
            evidence_sentence_source: 'artana_generated',
            paper_links: [
              {
                label: 'PubMed',
                url: 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
                source: 'external_record_id',
              },
            ],
          },
        ],
      },
    }

    render(<SpaceCurationClient {...propsWithSentence} activeTab="graph" />)

    expect(
      screen.getByText(
        'MED13 variation was associated with cardiomyopathy in the study cohort.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('AI-generated (not verbatim span)'),
    ).toBeInTheDocument()
    const sourceLink = screen.getByRole('link', { name: 'PubMed' })
    expect(sourceLink).toHaveAttribute(
      'href',
      'https://pubmed.ncbi.nlm.nih.gov/12345678/',
    )
    expect(sourceLink).toHaveAttribute('target', '_blank')
  })

  it('routes to claims tab when tab button is selected', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="graph" />)

    fireEvent.click(screen.getByRole('button', { name: 'Extraction Claims' }))

    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('/spaces/space-1/curation?')
    expect(String(lastCall)).toContain('tab=claims')
  })

  it('renders claim overlay mode with empty-state CTA in graph tab', async () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationFilters={{
          ...baseProps.relationFilters,
          graphMode: 'claim_overlay',
        }}
      />,
    )

    await waitFor(() => {
      expect(listClaimRelationsActionMock).toHaveBeenCalledWith('space-1', {
        offset: 0,
        limit: 200,
      })
    })
    expect(screen.getByText('Claim Overlay')).toBeInTheDocument()
    expect(
      screen.getByText(
        'No claim overlay edges exist yet. Create/review links from the hypotheses workflow.',
      ),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create Or Review Claim Links' }))
    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('tab=claims')
  })

  it('renders populated claim overlay and supports review/backfill actions', async () => {
    listClaimRelationsActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          id: 'edge-1',
          research_space_id: 'space-1',
          source_claim_id: 'claim-1',
          target_claim_id: 'claim-2',
          relation_type: 'SUPPORTS',
          agent_run_id: null,
          source_document_id: null,
          confidence: 0.82,
          review_status: 'PROPOSED',
          evidence_summary: null,
          metadata: {},
          created_at: '2026-03-04T00:00:00Z',
        },
      ],
    })
    listHypothesesActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          claim_id: 'claim-1',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.9,
          source_label: 'MED13',
          relation_type: 'ASSOCIATED_WITH',
          target_label: 'Autism',
          claim_text: 'Claim one',
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
        {
          claim_id: 'claim-2',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.88,
          source_label: 'Mediator',
          relation_type: 'CAUSES',
          target_label: 'Dysregulation',
          claim_text: 'Claim two',
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
      ],
    })
    listClaimParticipantsActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          id: 'participant-1',
          claim_id: 'claim-1',
          research_space_id: 'space-1',
          label: 'MED13',
          entity_id: 'ent-1',
          role: 'SUBJECT',
          position: 0,
          qualifiers: {},
          created_at: '2026-03-04T00:00:00Z',
        },
      ],
    })
    updateClaimRelationReviewActionMock.mockResolvedValueOnce({
      success: true,
      data: {
        id: 'edge-1',
        research_space_id: 'space-1',
        source_claim_id: 'claim-1',
        target_claim_id: 'claim-2',
        relation_type: 'SUPPORTS',
        agent_run_id: null,
        source_document_id: null,
        confidence: 0.82,
        review_status: 'ACCEPTED',
        evidence_summary: null,
        metadata: {},
        created_at: '2026-03-04T00:00:00Z',
      },
    })

    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationFilters={{
          ...baseProps.relationFilters,
          graphMode: 'claim_overlay',
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Source participants' })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Source participants' }))
    await waitFor(() => {
      expect(listClaimParticipantsActionMock).toHaveBeenCalledWith('space-1', 'claim-1')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
    await waitFor(() => {
      expect(updateClaimRelationReviewActionMock).toHaveBeenCalledWith(
        'space-1',
        'edge-1',
        'ACCEPTED',
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'Dry-run backfill' }))
    await waitFor(() => {
      expect(runClaimParticipantBackfillActionMock).toHaveBeenCalledWith('space-1', true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Backfill participants' }))
    await waitFor(() => {
      expect(runClaimParticipantBackfillActionMock).toHaveBeenCalledWith('space-1', false)
    })
  })

  it('opens claims queue filtered by relation when selecting canonical linked claims', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="graph" />)

    fireEvent.click(screen.getByRole('button', { name: 'Open linked claims' }))

    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('tab=claims')
    expect(String(lastCall)).toContain('linked_relation_id=rel-1')
  })

  it('opens graph view focused on linked relation from a claim', () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="claims"
        claims={{
          ...baseProps.claims,
          claims: [
            {
              ...baseProps.claims.claims[0],
              linked_relation_id: 'rel-1',
            },
          ],
        }}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Highlight linked relation' }))
    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('tab=graph')
    expect(String(lastCall)).toContain('focus_relation_id=rel-1')
  })

  it('renders conflict badge in claim queue for linked conflicting relations', () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="claims"
        claims={{
          ...baseProps.claims,
          claims: [
            {
              ...baseProps.claims.claims[0],
              linked_relation_id: 'rel-1',
            },
          ],
        }}
        relationConflicts={{
          conflicts: [
            {
              relation_id: 'rel-1',
              support_count: 5,
              refute_count: 2,
              support_claim_ids: ['claim-a'],
              refute_claim_ids: ['claim-b'],
            },
          ],
          total: 1,
          offset: 0,
          limit: 50,
        }}
      />,
    )

    expect(screen.getByText('Conflict 5/2')).toBeInTheDocument()
  })

  it('finds and highlights focus path in claim overlay mode', async () => {
    listClaimRelationsActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          id: 'edge-1',
          research_space_id: 'space-1',
          source_claim_id: 'claim-1',
          target_claim_id: 'claim-2',
          relation_type: 'SUPPORTS',
          agent_run_id: null,
          source_document_id: null,
          confidence: 0.82,
          review_status: 'PROPOSED',
          evidence_summary: 'Overlay path edge',
          metadata: {},
          created_at: '2026-03-04T00:00:00Z',
        },
      ],
    })
    listHypothesesActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          claim_id: 'claim-1',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.9,
          source_label: 'MED13',
          relation_type: 'ASSOCIATED_WITH',
          target_label: 'Autism',
          claim_text: 'Claim one',
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
        {
          claim_id: 'claim-2',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.88,
          source_label: 'Mediator',
          relation_type: 'CAUSES',
          target_label: 'Dysregulation',
          claim_text: 'Claim two',
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
      ],
    })
    listClaimsByEntityActionMock
      .mockResolvedValueOnce({
        success: true,
        data: {
          claims: [
            {
              ...baseProps.claims.claims[0],
              id: 'claim-1',
            },
          ],
          total: 1,
          offset: 0,
          limit: 200,
        },
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          claims: [
            {
              ...baseProps.claims.claims[0],
              id: 'claim-2',
            },
          ],
          total: 1,
          offset: 0,
          limit: 200,
        },
      })

    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationFilters={{
          ...baseProps.relationFilters,
          graphMode: 'claim_overlay',
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Find path' })).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('Overlay path edge')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('From entity ID'), {
      target: { value: 'entity-source' },
    })
    fireEvent.change(screen.getByLabelText('To entity ID'), {
      target: { value: 'entity-target' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Find path' }))

    await waitFor(() => {
      expect(listClaimsByEntityActionMock).toHaveBeenCalledWith(
        'space-1',
        'entity-source',
        { offset: 0, limit: 200 },
      )
      expect(listClaimsByEntityActionMock).toHaveBeenCalledWith(
        'space-1',
        'entity-target',
        { offset: 0, limit: 200 },
      )
    })
    await waitFor(() => {
      expect(
        screen.getByText('Focused path with 2 claims across 1 links.'),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Focus path')).toBeInTheDocument()
  })

  it('opens canonical graph relation directly from claim overlay edges', async () => {
    listClaimRelationsActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          id: 'edge-1',
          research_space_id: 'space-1',
          source_claim_id: 'claim-1',
          target_claim_id: 'claim-2',
          relation_type: 'SUPPORTS',
          agent_run_id: null,
          source_document_id: null,
          confidence: 0.82,
          review_status: 'PROPOSED',
          evidence_summary: 'Overlay path edge',
          metadata: {},
          created_at: '2026-03-04T00:00:00Z',
        },
      ],
    })
    listHypothesesActionMock.mockResolvedValueOnce({
      success: true,
      data: [
        {
          claim_id: 'claim-1',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.9,
          source_label: 'MED13',
          relation_type: 'ASSOCIATED_WITH',
          target_label: 'Autism',
          claim_text: 'Claim one',
          linked_relation_id: 'rel-1',
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
        {
          claim_id: 'claim-2',
          polarity: 'HYPOTHESIS',
          claim_status: 'OPEN',
          validation_state: 'ALLOWED',
          persistability: 'PERSISTABLE',
          confidence: 0.88,
          source_label: 'Mediator',
          relation_type: 'CAUSES',
          target_label: 'Dysregulation',
          claim_text: 'Claim two',
          linked_relation_id: null,
          origin: 'graph_agent',
          seed_entity_ids: [],
          supporting_provenance_ids: [],
          created_at: '2026-03-03T00:00:00Z',
          metadata: {},
        },
      ],
    })

    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationFilters={{
          ...baseProps.relationFilters,
          graphMode: 'claim_overlay',
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Open canonical relation' })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Open canonical relation' }))
    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('tab=graph')
    expect(String(lastCall)).toContain('focus_relation_id=rel-1')
  })

  it('renders focused relation badge when graph is opened from linked claim context', () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationFilters={{
          ...baseProps.relationFilters,
          focusRelationId: 'rel-1',
        }}
        claims={{
          ...baseProps.claims,
          claims: [
            {
              ...baseProps.claims.claims[0],
              linked_relation_id: 'rel-1',
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Focused from claim queue')).toBeInTheDocument()
  })
})
