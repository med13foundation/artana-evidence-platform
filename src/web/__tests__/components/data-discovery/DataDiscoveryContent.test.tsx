import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataDiscoveryContent } from '@/components/data-discovery/DataDiscoveryContent'
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'

const mockUpdateSelection = jest.fn()
const mockAddSources = jest.fn()

jest.mock('@/components/data-discovery/space-discovery-api', () => ({
  updateSpaceDiscoverySelection: (...args: unknown[]) => mockUpdateSelection(...args),
  addSpaceDiscoverySources: (...args: unknown[]) => mockAddSources(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

const catalog: SourceCatalogEntry[] = [
  {
    id: 'pubmed',
    name: 'PubMed',
    description: 'Biomedical literature database',
    category: 'Scientific Literature',
    subcategory: null,
    source_type: 'pubmed',
    param_type: 'gene',
    is_active: true,
    requires_auth: false,
    usage_count: 0,
    success_rate: 1,
    tags: [],
    capabilities: {},
  },
]

const baseState: OrchestratedSessionState = {
  session: {
    id: 'session-123',
    owner_id: 'user-123',
    research_space_id: 'space-123',
    name: 'Test Session',
    selected_sources: [],
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
  capabilities: {},
  validation: { is_valid: true, issues: [] },
  view_context: {
    selected_count: 0,
    total_available: 1,
    can_run_search: false,
    categories: {},
  },
}

describe('DataDiscoveryContent', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders an empty catalog state when the catalog payload is malformed', () => {
    render(
      <DataDiscoveryContent
        spaceId="space-123"
        orchestratedState={baseState}
        catalog={{ unexpected: true } as unknown as SourceCatalogEntry[]}
      />,
    )

    expect(screen.getByText(/No sources available/i)).toBeInTheDocument()
  })

  it('calls updateSpaceDiscoverySelection when toggling a source', async () => {
    const user = userEvent.setup()
    const nextState: OrchestratedSessionState = {
      ...baseState,
      session: {
        ...baseState.session,
        selected_sources: ['pubmed'],
      },
      view_context: {
        ...baseState.view_context,
        selected_count: 1,
        can_run_search: true,
      },
    }

    mockUpdateSelection.mockResolvedValue({ success: true, state: nextState })

    render(
      <DataDiscoveryContent
        spaceId="space-123"
        orchestratedState={baseState}
        catalog={catalog}
        isModal={true}
      />,
    )

    const entryButton = screen.getByRole('button', { name: /PubMed/i })
    await user.click(entryButton)

    await waitFor(() => {
      expect(mockUpdateSelection).toHaveBeenCalledWith(
        'space-123',
        'session-123',
        ['pubmed'],
      )
    })
  })

  it('calls addSpaceDiscoverySources and onComplete on success', async () => {
    const user = userEvent.setup()
    const onComplete = jest.fn()
    const selectedState: OrchestratedSessionState = {
      ...baseState,
      session: {
        ...baseState.session,
        selected_sources: ['pubmed'],
      },
      view_context: {
        ...baseState.view_context,
        selected_count: 1,
        can_run_search: true,
      },
    }

    mockAddSources.mockResolvedValue({ success: true, addedCount: 1 })

    render(
      <DataDiscoveryContent
        spaceId="space-123"
        orchestratedState={selectedState}
        catalog={catalog}
        isModal={true}
        onComplete={onComplete}
      />,
    )

    const addButton = screen.getByRole('button', { name: /add selected to space/i })
    await user.click(addButton)

    await waitFor(() => {
      expect(mockAddSources).toHaveBeenCalledWith(
        'space-123',
        'session-123',
        ['pubmed'],
      )
      expect(onComplete).toHaveBeenCalled()
    })
  })
})
