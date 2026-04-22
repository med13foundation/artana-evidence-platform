import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSourcesList } from '@/components/data-sources/DataSourcesList'
import { DiscoverSourcesDialog } from '@/components/data-sources/DiscoverSourcesDialog'
import {
  cancelSpaceSourcePipelineRunAction,
  fetchSourceWorkflowCardStatusAction,
  fetchSourceWorkflowEventsAction,
} from '@/app/actions/kernel-ingest'
import type { DataSource } from '@/types/data-source'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { OrchestratedSessionState } from '@/types/generated'
import type {
  SpaceWorkflowBootstrapPayload,
  SpaceWorkflowSourceCardPayload,
} from '@/types/kernel'

const mockRefresh = jest.fn()
const mockStreamBootstrapPayloadState: {
  current: SpaceWorkflowBootstrapPayload | null
} = { current: null }
const mockStreamCardPayloadsState: {
  current: SpaceWorkflowSourceCardPayload[]
} = { current: [] }
const mockStreamFallbackState: { current: boolean } = { current: false }
const mockFetchSpaceDataSourcesQueryAction = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: mockRefresh,
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
}))

jest.mock('@/app/actions/data-sources', () => ({
  configureDataSourceScheduleAction: jest.fn(),
  createDataSourceInSpaceAction: jest.fn(),
  deleteDataSourceAction: jest.fn(),
  fetchIngestionJobHistoryAction: jest.fn(),
  testDataSourceAiConfigurationAction: jest.fn(),
  updateDataSourceAction: jest.fn(),
}))

jest.mock('@/app/actions/kernel-ingest', () => ({
  cancelSpaceSourcePipelineRunAction: jest.fn(),
  fetchSourceWorkflowEventsAction: jest.fn(),
  fetchSourceWorkflowCardStatusAction: jest.fn(),
  runSpaceSourcePipelineAction: jest.fn(),
}))

jest.mock('@/app/actions/admin-query', () => ({
  fetchSpaceDataSourcesQueryAction: (...args: unknown[]) =>
    mockFetchSpaceDataSourcesQueryAction(...args),
}))

jest.mock('@/components/data-discovery/DataDiscoveryContent', () => ({
  DataDiscoveryContent: ({ onComplete }: { onComplete?: () => void }) => (
    <div>
      <button
        onClick={() => onComplete?.()}
        data-testid="mock-add-source"
      >
        Mock Add Source
      </button>
    </div>
  ),
}))

jest.mock('@/hooks/use-space-workflow-stream', () => {
  const React = require('react')
  return {
    useSpaceWorkflowStream: jest.fn((options) => {
      React.useEffect(() => {
        if (mockStreamBootstrapPayloadState.current !== null) {
          options.onBootstrap?.(mockStreamBootstrapPayloadState.current)
        }
        for (const payload of mockStreamCardPayloadsState.current) {
          options.onSourceCardStatus?.(payload)
        }
      }, [options.onBootstrap, options.onSourceCardStatus])
      return {
        isConnected: true,
        isFallbackActive: mockStreamFallbackState.current,
        lastError: null,
      }
    }),
  }
})

const mockDataSources: DataSource[] = [
  {
    id: 'source-1',
    name: 'Test Source 1',
    description: 'Test description',
    source_type: 'api',
    status: 'active',
    owner_id: 'user-123',
    research_space_id: 'space-123',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
]

const discoveryState: OrchestratedSessionState | null = null
const dataSourcesResponse: DataSourceListResponse = {
  items: mockDataSources,
  total: 1,
  page: 1,
  limit: 20,
  has_next: false,
  has_prev: false,
}

function render(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false },
    },
  })

  return rtlRender(ui, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

beforeEach(() => {
  mockStreamBootstrapPayloadState.current = null
  mockStreamCardPayloadsState.current = []
  mockStreamFallbackState.current = false
  mockFetchSpaceDataSourcesQueryAction.mockResolvedValue(dataSourcesResponse)
  ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockResolvedValue({
    success: true,
    data: {
      last_pipeline_status: 'completed',
      pending_paper_count: 0,
      pending_relation_review_count: 0,
      extraction_extracted_count: 0,
      extraction_failed_count: 0,
      extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
      graph_edges_delta_last_run: 0,
      graph_edges_total: 0,
      last_failed_stage: null,
    },
  })
  ;(cancelSpaceSourcePipelineRunAction as jest.Mock).mockResolvedValue({
    success: true,
    data: {
      run_id: 'run-123',
      source_id: 'source-1',
      status: 'cancelled',
      cancelled: true,
    },
  })
  ;(fetchSourceWorkflowEventsAction as jest.Mock).mockResolvedValue({
    success: true,
    data: { events: [] },
  })
})

describe('DataSourcesList - Auto-refresh on Source Addition', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('invalidates the data source query when onSourceAdded callback is triggered', async () => {
    const user = userEvent.setup()

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    // Open the discover dialog
    const addButton = screen.getByRole('button', { name: /add from library/i })
    await user.click(addButton)

    // Wait for dialog to open
    await waitFor(() => {
      expect(screen.getByText(/discover data sources/i)).toBeInTheDocument()
    })

    // Simulate adding a source (this would normally happen in DataDiscoveryContent)
    const mockAddButton = screen.getByTestId('mock-add-source')
    await user.click(mockAddButton)

    expect(mockRefresh).not.toHaveBeenCalled()
  })

  it('displays updated data sources after rerender', async () => {
    const updatedDataSources = [
      ...mockDataSources,
      {
        id: 'source-2',
        name: 'New Source',
        description: 'Newly added source',
        source_type: 'pubmed',
        status: 'draft',
        owner_id: 'user-123',
        research_space_id: 'space-123',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]

    // Initial render with 1 source
    const { rerender } = render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    expect(screen.getByText('Test Source 1')).toBeInTheDocument()

    rerender(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: updatedDataSources,
          total: 2,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    // Verify new source appears
    await waitFor(() => {
      expect(screen.getByText('New Source')).toBeInTheDocument()
    })
  })
})

describe('DiscoverSourcesDialog - onSourceAdded prop', () => {
  it('calls onSourceAdded callback when source is added', async () => {
    const user = userEvent.setup()
    const onSourceAdded = jest.fn()

    render(
      <DiscoverSourcesDialog
        spaceId="space-123"
        open={true}
        onOpenChange={jest.fn()}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        onSourceAdded={onSourceAdded}
      />,
    )

    // Simulate adding a source
    const mockAddButton = screen.getByTestId('mock-add-source')
    await user.click(mockAddButton)

    await waitFor(() => {
      expect(onSourceAdded).toHaveBeenCalled()
    })
  })
})

describe('DataSourcesList - AI Controls', () => {
  it('shows a consolidated Configure menu for any connector with query_agent_source_type', async () => {
    const user = userEvent.setup()
    const connectorSource: DataSource = {
      id: 'source-future-connector',
      name: 'Future Connector Source',
      description: 'Generic connector source',
      source_type: 'api',
      status: 'active',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          agent_config: {
            is_ai_managed: true,
            query_agent_source_type: 'future_connector',
            agent_prompt: 'Use connector-specific terminology.',
          },
        },
      },
      ingestion_schedule: {
        enabled: true,
        frequency: 'daily',
        timezone: 'UTC',
        start_time: null,
        cron_expression: null,
        backend_job_id: null,
        next_run_at: null,
        last_run_at: null,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [connectorSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    const configureButton = screen.getByRole('button', {
      name: /configure future connector source/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(await screen.findByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
  })

  it('shows a consolidated Configure menu for ClinVar AI-managed sources', async () => {
    const user = userEvent.setup()
    const clinvarSource: DataSource = {
      id: 'source-clinvar',
      name: 'ClinVar Pathogenicity Benchmark',
      description: 'Curated benchmark set for pathogenicity tasks',
      source_type: 'api',
      status: 'active',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          agent_config: {
            is_ai_managed: true,
            query_agent_source_type: 'clinvar',
            agent_prompt: 'Use ClinVar terminology for variant queries.',
          },
        },
      },
      ingestion_schedule: {
        enabled: true,
        frequency: 'daily',
        timezone: 'UTC',
        start_time: null,
        cron_expression: null,
        backend_job_id: null,
        next_run_at: null,
        last_run_at: null,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [clinvarSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    const configureButton = screen.getByRole('button', {
      name: /configure clinvar pathogenicity benchmark/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(await screen.findByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
  })

  it('shows a consolidated Configure menu for ClinVar discovery sources without agent config', async () => {
    const user = userEvent.setup()
    const clinvarSource: DataSource = {
      id: 'source-clinvar-discovery',
      name: 'ClinVar (from Data Discovery)',
      description: 'Public archive connecting human genetic variants to phenotypes.',
      source_type: 'api',
      status: 'draft',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          catalog_entry_id: 'clinvar',
          query: 'MED13 pathogenic variant',
        },
      },
      ingestion_schedule: {
        enabled: false,
        frequency: 'manual',
        timezone: 'UTC',
        start_time: null,
        cron_expression: null,
        backend_job_id: null,
        next_run_at: null,
        last_run_at: null,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [clinvarSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    const configureButton = screen.getByRole('button', {
      name: /configure clinvar \(from data discovery\)/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(await screen.findByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
  })

  it('keeps AI buttons hidden for plain API sources without agent metadata', () => {
    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    expect(screen.queryByRole('button', { name: /^configure$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /configure schedule/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /configure ai/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /test ai/i })).not.toBeInTheDocument()
  })
})

describe('DataSourcesList - Artana progress display', () => {
  it('renders optional Artana stage progress badge when provided', () => {
    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'completed',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 10,
            artana_progress: {
              extraction: {
                run_id: 'extract:run:1',
                status: 'running',
                percent: 45,
                current_stage: 'extract',
              },
            },
          },
        }}
      />,
    )

    expect(screen.getByText(/Artana extraction 45%/i)).toBeInTheDocument()
  })

  it('shows early pipeline startup state instead of finalizing when ingestion has just started', async () => {
    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 10,
            artana_progress: {
              pipeline: {
                run_id: 'pipeline-run-1',
                status: 'running',
                percent: 0,
                current_stage: 'ingestion',
              },
            },
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/Stage: Starting ingestion/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/Artana ingestion 0%/i)).toBeInTheDocument()
    expect(screen.queryByText(/Finalizing run/i)).not.toBeInTheDocument()
  })
})

describe('DataSourcesList - Workflow streaming and fallback', () => {
  it('cancels a pre-existing active run after page load using backend-provided run id', async () => {
    const user = userEvent.setup()

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            active_pipeline_run_id: 'run-123',
            last_pipeline_status: 'running',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 0,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: /stop run for test source 1/i }))

    await waitFor(() => {
      expect(cancelSpaceSourcePipelineRunAction).toHaveBeenCalledWith(
        'space-123',
        'source-1',
        'run-123',
      )
    })
  })

  it('applies stream bootstrap updates to live workflow UI', async () => {
    mockStreamBootstrapPayloadState.current = {
      generated_at: '2026-03-02T20:00:00+00:00',
      sources: [
        {
          source_id: 'source-1',
          generated_at: '2026-03-02T20:00:00+00:00',
          workflow_status: {
            active_pipeline_run_id: 'run-stream-1',
            last_pipeline_status: 'running',
            last_failed_stage: null,
            pending_paper_count: 2,
            pending_relation_review_count: 1,
            extraction_extracted_count: 1,
            extraction_failed_count: 1,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 3,
            graph_edges_total: 10,
          },
          events: [
            {
              event_id: 'stream-event-1',
              occurred_at: '2026-03-02T20:00:00+00:00',
              category: 'run',
              stage: 'ingestion',
              status: 'running',
              message: 'Pipeline running from stream',
            },
          ],
        },
      ],
    }
    const draftDataSource: DataSource = {
      ...mockDataSources[0],
      status: 'draft',
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [draftDataSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 0,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/Live run in progress/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/Pipeline running from stream/i)).toBeInTheDocument()
  })

  it('keeps polling updates working when stream fallback is active', async () => {
    mockStreamFallbackState.current = true
    ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockResolvedValue({
      success: true,
      data: {
        last_pipeline_status: 'running',
        pending_paper_count: 1,
        pending_relation_review_count: 0,
        extraction_extracted_count: 0,
        extraction_failed_count: 0,
        extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
        graph_edges_delta_last_run: 0,
        graph_edges_total: 4,
        last_failed_stage: null,
      },
    })
    ;(fetchSourceWorkflowEventsAction as jest.Mock).mockResolvedValue({
      success: true,
      data: {
        events: [
          {
            event_id: 'poll-event-1',
            occurred_at: '2026-03-02T20:00:04+00:00',
            category: 'run',
            stage: 'ingestion',
            status: 'running',
            message: 'Poll backend event',
          },
        ],
      },
    })

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 1,
            pending_relation_review_count: 0,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 4,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(fetchSourceWorkflowCardStatusAction).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByText(/Poll backend event/i)).toBeInTheDocument()
    })
  })

  it('does not restart fallback polling on every status refresh while a run is active', async () => {
    mockStreamFallbackState.current = true
    ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockClear()
    ;(fetchSourceWorkflowEventsAction as jest.Mock).mockClear()
    ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockResolvedValue({
      success: true,
      data: {
        last_pipeline_status: 'running',
        pending_paper_count: 2,
        pending_relation_review_count: 17,
        extraction_extracted_count: 0,
        extraction_failed_count: 0,
        extraction_skipped_count: 0,
        extraction_timeout_failed_count: 0,
        graph_edges_delta_last_run: 0,
        graph_edges_total: 4,
        last_failed_stage: null,
      },
    })
    ;(fetchSourceWorkflowEventsAction as jest.Mock).mockResolvedValue({
      success: true,
      data: { events: [] },
    })

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 2,
            pending_relation_review_count: 17,
            extraction_extracted_count: 0,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 4,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(fetchSourceWorkflowCardStatusAction).toHaveBeenCalledTimes(1)
      expect(fetchSourceWorkflowEventsAction).toHaveBeenCalledTimes(1)
    })
  })

  it('does not keep polling forever when only review backlog remains after completion', async () => {
    mockStreamFallbackState.current = true
    ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockClear()
    ;(fetchSourceWorkflowEventsAction as jest.Mock).mockClear()

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'completed',
            pending_paper_count: 0,
            pending_relation_review_count: 17,
            extraction_extracted_count: 42,
            extraction_failed_count: 0,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 8,
            graph_edges_total: 21,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await new Promise((resolve) => setTimeout(resolve, 150))

    expect(fetchSourceWorkflowCardStatusAction).not.toHaveBeenCalled()
    expect(fetchSourceWorkflowEventsAction).not.toHaveBeenCalled()
  })
})
