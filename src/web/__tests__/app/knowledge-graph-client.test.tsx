import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import KnowledgeGraphClient from '@/app/(dashboard)/spaces/[spaceId]/knowledge-graph-client'
import {
  fetchKernelGraphDocumentAction,
  searchKernelGraphAction,
} from '@/app/actions/kernel-graph'
import type {
  GraphSearchResponse,
  KernelGraphDocumentResponse,
} from '@/types/kernel'

const routerReplaceMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: jest.fn(),
    refresh: jest.fn(),
  }),
}))

jest.mock('@/app/actions/kernel-graph', () => ({
  fetchKernelGraphDocumentAction: jest.fn(),
  searchKernelGraphAction: jest.fn(),
}))

jest.mock('@/components/knowledge-graph/KnowledgeGraphCanvas', () => ({
  __esModule: true,
  default: ({
    graph,
    onNodeClick,
  }: {
    graph: {
      stats: { nodeCount: number; edgeCount: number }
      nodes: { id: string }[]
    }
    onNodeClick: (nodeId: string) => void
  }) => (
    <div data-testid="mock-graph-canvas">
      <div data-testid="mock-graph-node-count">{graph.stats.nodeCount}</div>
      <div data-testid="mock-graph-edge-count">{graph.stats.edgeCount}</div>
      {graph.nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick(node.id)} type="button">
          expand-{node.id}
        </button>
      ))}
    </div>
  ),
}))

class ResizeObserverMock {
  public observe(): void {}
  public unobserve(): void {}
  public disconnect(): void {}
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
})

function buildDocumentResponse(
  overrides: Partial<KernelGraphDocumentResponse> = {},
): KernelGraphDocumentResponse {
  return {
    nodes: [
      {
        id: 'n1',
        resource_id: 'n1',
        kind: 'ENTITY',
        type_label: 'GENE',
        label: 'MED13',
        confidence: null,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: null,
        metadata: {},
        created_at: '2026-02-20T00:00:00Z',
        updated_at: '2026-02-20T00:00:00Z',
      },
      {
        id: 'n2',
        resource_id: 'n2',
        kind: 'ENTITY',
        type_label: 'PHENOTYPE',
        label: 'Cardiomyopathy',
        confidence: null,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: null,
        metadata: {},
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
      {
        id: 'n3',
        resource_id: 'n3',
        kind: 'ENTITY',
        type_label: 'PHENOTYPE',
        label: 'Arrhythmia',
        confidence: null,
        curation_status: null,
        claim_status: null,
        polarity: null,
        canonical_relation_id: null,
        metadata: {},
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
    ],
    edges: [
      {
        id: 'e1',
        resource_id: 'e1',
        kind: 'CANONICAL_RELATION',
        source_id: 'n1',
        target_id: 'n2',
        type_label: 'ASSOCIATED_WITH',
        label: 'ASSOCIATED_WITH',
        confidence: 0.91,
        curation_status: 'APPROVED',
        claim_id: null,
        canonical_relation_id: 'e1',
        evidence_id: null,
        metadata: {
          source_count: 2,
          highest_evidence_tier: 'LITERATURE',
          support_claim_count: 0,
          refute_claim_count: 0,
          has_conflict: false,
          linked_claim_ids: [],
        },
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
      {
        id: 'e2',
        resource_id: 'e2',
        kind: 'CANONICAL_RELATION',
        source_id: 'n1',
        target_id: 'n3',
        type_label: 'CO_OCCURS_WITH',
        label: 'CO_OCCURS_WITH',
        confidence: 0.55,
        curation_status: 'DRAFT',
        claim_id: null,
        canonical_relation_id: 'e2',
        evidence_id: null,
        metadata: {
          source_count: 1,
          highest_evidence_tier: 'COMPUTATIONAL',
          support_claim_count: 0,
          refute_claim_count: 0,
          has_conflict: false,
          linked_claim_ids: [],
        },
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
    ],
    meta: {
      mode: 'starter',
      seed_entity_ids: [],
      requested_depth: 2,
      requested_top_k: 25,
      pre_cap_entity_node_count: 3,
      pre_cap_canonical_edge_count: 2,
      truncated_entity_nodes: false,
      truncated_canonical_edges: false,
      included_claims: true,
      included_evidence: true,
      max_claims: 250,
      evidence_limit_per_claim: 3,
      counts: {
        entity_nodes: 3,
        claim_nodes: 0,
        evidence_nodes: 0,
        canonical_edges: 2,
        claim_participant_edges: 0,
        claim_evidence_edges: 0,
      },
    },
    ...overrides,
  }
}

function buildSearchResponse(): GraphSearchResponse {
  return {
    confidence_score: 0.82,
    rationale: 'deterministic',
    evidence: [],
    decision: 'generated',
    research_space_id: 'space-1',
    original_query: 'med13 query',
    interpreted_intent: 'med13',
    query_plan_summary: 'summary',
    total_results: 6,
    results: [
      { entity_id: 'n1', entity_type: 'GENE', display_label: 'MED13', relevance_score: 0.9, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n2', entity_type: 'PHENOTYPE', display_label: 'P1', relevance_score: 0.8, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n3', entity_type: 'PHENOTYPE', display_label: 'P2', relevance_score: 0.7, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n4', entity_type: 'PHENOTYPE', display_label: 'P3', relevance_score: 0.6, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n5', entity_type: 'PHENOTYPE', display_label: 'P4', relevance_score: 0.5, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n6', entity_type: 'PHENOTYPE', display_label: 'P5', relevance_score: 0.4, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
    ],
    executed_path: 'deterministic',
    warnings: [],
    agent_run_id: null,
  }
}

describe('KnowledgeGraphClient', () => {
  const mockFetchKernelGraphDocument = fetchKernelGraphDocumentAction as jest.MockedFunction<
    typeof fetchKernelGraphDocumentAction
  >
  const mockSearchKernelGraph = searchKernelGraphAction as jest.MockedFunction<
    typeof searchKernelGraphAction
  >

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('auto-loads the unified graph document on first render when no query exists', async () => {
    mockFetchKernelGraphDocument.mockResolvedValue({
      success: true,
      data: buildDocumentResponse(),
    })

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledWith(
        'space-1',
        expect.objectContaining({
          mode: 'starter',
          seed_entity_ids: [],
          include_claims: true,
          include_evidence: true,
        }),
      )
    })
  })

  it('uses the top 5 search results as seeds for unified graph retrieval', async () => {
    mockSearchKernelGraph.mockResolvedValue({
      success: true,
      data: buildSearchResponse(),
    })
    mockFetchKernelGraphDocument.mockResolvedValue({
      success: true,
      data: buildDocumentResponse({
        meta: {
          ...buildDocumentResponse().meta,
          mode: 'seeded',
          seed_entity_ids: ['n1', 'n2', 'n3', 'n4', 'n5'],
          pre_cap_entity_node_count: 5,
          pre_cap_canonical_edge_count: 4,
        },
      }),
    })

    render(
      <KnowledgeGraphClient
        spaceId="space-1"
        initialQuestion="med13 query"
        initialTopK={25}
        initialMaxDepth={2}
      />,
    )

    await waitFor(() => {
      expect(mockSearchKernelGraph).toHaveBeenCalled()
      expect(mockFetchKernelGraphDocument).toHaveBeenCalled()
    })

    const payload = mockFetchKernelGraphDocument.mock.calls[0]?.[1]
    expect(payload).toEqual(
      expect.objectContaining({
        mode: 'seeded',
        seed_entity_ids: ['n1', 'n2', 'n3', 'n4', 'n5'],
      }),
    )
  })

  it('expands from node click and merges without duplicating edges', async () => {
    mockFetchKernelGraphDocument
      .mockResolvedValueOnce({
        success: true,
        data: buildDocumentResponse({
          nodes: buildDocumentResponse().nodes.slice(0, 2),
          edges: buildDocumentResponse().edges.slice(0, 1),
          meta: {
            ...buildDocumentResponse().meta,
            pre_cap_entity_node_count: 2,
            pre_cap_canonical_edge_count: 1,
            counts: {
              ...buildDocumentResponse().meta.counts,
              entity_nodes: 2,
              canonical_edges: 1,
            },
          },
        }),
      })
      .mockResolvedValueOnce({
        success: true,
        data: buildDocumentResponse({
          edges: [
            buildDocumentResponse().edges[0],
            {
              ...buildDocumentResponse().edges[0],
              id: 'e3',
              resource_id: 'e3',
              target_id: 'n3',
              canonical_relation_id: 'e3',
            },
          ],
          meta: {
            ...buildDocumentResponse().meta,
            mode: 'seeded',
          },
        }),
      })

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('1')
    })

    fireEvent.click(screen.getByRole('button', { name: 'expand-n1' }))

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledTimes(2)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('2')
    })
  })

  it('applies relation filters and updates visible graph edges', async () => {
    mockFetchKernelGraphDocument.mockResolvedValue({
      success: true,
      data: buildDocumentResponse(),
    })

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('2')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    const associatedWithCheckbox = screen.getByLabelText('ASSOCIATED_WITH')
    expect(associatedWithCheckbox).toBeChecked()
    fireEvent.click(associatedWithCheckbox)

    await waitFor(() => {
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('1')
    })

    const enableAllButton = screen.getByRole('button', { name: 'Enable all' })
    expect(enableAllButton).toBeEnabled()
    fireEvent.click(enableAllButton)

    await waitFor(() => {
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('2')
    })
  })

  it('passes trust preset curation filters through the graph document request', async () => {
    mockFetchKernelGraphDocument
      .mockResolvedValueOnce({
        success: true,
        data: buildDocumentResponse(),
      })
      .mockResolvedValueOnce({
        success: true,
        data: buildDocumentResponse(),
      })

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledTimes(1)
      expect(mockFetchKernelGraphDocument.mock.calls[0]?.[1]).toEqual(
        expect.objectContaining({
          curation_statuses: null,
        }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approved only' }))

    await waitFor(() => {
      expect(mockFetchKernelGraphDocument).toHaveBeenCalledTimes(2)
      expect(mockFetchKernelGraphDocument.mock.calls[1]?.[1]).toEqual(
        expect.objectContaining({
          curation_statuses: ['APPROVED'],
        }),
      )
    })
  })
})
