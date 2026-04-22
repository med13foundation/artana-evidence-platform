import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSourceAvailabilitySection } from '@/components/system-settings/DataSourceAvailabilitySection'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { ResearchSpace } from '@/types/research-space'
import { SpaceStatus } from '@/types/research-space'

const mockUpdateGlobalAvailabilityAction = jest.fn()
const mockUpdateProjectAvailabilityAction = jest.fn()
const mockClearGlobalAvailabilityAction = jest.fn()
const mockClearProjectAvailabilityAction = jest.fn()
const mockBulkUpdateGlobalAvailabilityAction = jest.fn()

jest.mock('@/app/actions/data-source-availability', () => ({
  updateGlobalAvailabilityAction: (...args: unknown[]) =>
    mockUpdateGlobalAvailabilityAction(...args),
  updateProjectAvailabilityAction: (...args: unknown[]) =>
    mockUpdateProjectAvailabilityAction(...args),
  clearGlobalAvailabilityAction: (...args: unknown[]) =>
    mockClearGlobalAvailabilityAction(...args),
  clearProjectAvailabilityAction: (...args: unknown[]) =>
    mockClearProjectAvailabilityAction(...args),
  bulkUpdateGlobalAvailabilityAction: (...args: unknown[]) =>
    mockBulkUpdateGlobalAvailabilityAction(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}))

const baseCatalogEntry: SourceCatalogEntry = {
  id: 'catalog-1',
  name: 'Global API',
  description: 'Primary API source',
  category: 'Genomic Variant Databases',
  subcategory: null,
  tags: [],
  param_type: 'none',
  source_type: 'api',
  is_active: true,
  requires_auth: false,
  usage_count: 0,
  success_rate: 0,
  capabilities: {},
}

const baseAvailability: DataSourceAvailability = {
  catalog_entry_id: 'catalog-1',
  effective_permission_level: 'available',
  effective_is_active: true,
  global_rule: null,
  project_rules: [],
}

const baseSpaces: ResearchSpace[] = [
  {
    id: 'space-1',
    name: 'Space Alpha',
    slug: 'space-alpha',
    description: 'Test space',
    owner_id: 'user-1',
    status: SpaceStatus.ACTIVE,
    settings: {},
    tags: [],
    created_at: '',
    updated_at: '',
  },
]

describe('DataSourceAvailabilitySection', () => {
  const renderSection = (entries: SourceCatalogEntry[], summaries: DataSourceAvailability[]) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    return render(
      <QueryClientProvider client={queryClient}>
        <DataSourceAvailabilitySection
          catalogEntries={entries}
          availabilitySummaries={summaries}
          spaces={baseSpaces}
        />
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUpdateGlobalAvailabilityAction.mockResolvedValue({
      success: true,
      data: baseAvailability,
    })
    mockUpdateProjectAvailabilityAction.mockResolvedValue({
      success: true,
      data: baseAvailability,
    })
    mockClearGlobalAvailabilityAction.mockResolvedValue({
      success: true,
      data: baseAvailability,
    })
    mockClearProjectAvailabilityAction.mockResolvedValue({
      success: true,
      data: baseAvailability,
    })
    mockBulkUpdateGlobalAvailabilityAction.mockResolvedValue({
      success: true,
      data: [baseAvailability],
    })
  })

  it('renders list of data sources', () => {
    renderSection([baseCatalogEntry], [baseAvailability])
    expect(screen.getByText('Global API')).toBeInTheDocument()
  })

  it('opens manage dialog when button is clicked', async () => {
    const user = userEvent.setup()
    renderSection([baseCatalogEntry], [baseAvailability])

    await user.click(screen.getByRole('button', { name: /manage availability/i }))
    expect(await screen.findByText(/Global availability/i)).toBeInTheDocument()
  })

  it('calls mutation when activating globally', async () => {
    const user = userEvent.setup()
    renderSection([baseCatalogEntry], [baseAvailability])

    await user.click(screen.getByRole('button', { name: /manage availability/i }))
    const dialog = await screen.findByRole('dialog')
    const dialogSetAvailable = within(dialog).getByRole('button', { name: /Set Available/i })
    await user.click(dialogSetAvailable)

    expect(mockUpdateGlobalAvailabilityAction).toHaveBeenCalledWith('catalog-1', 'available')
  })

  it('filters data sources based on search input', async () => {
    const user = userEvent.setup()
    const secondEntry: SourceCatalogEntry = {
      ...baseCatalogEntry,
      id: 'catalog-2',
      name: 'Beta Source',
      description: 'Secondary beta data',
    }
    renderSection(
      [baseCatalogEntry, secondEntry],
      [
        baseAvailability,
        {
          ...baseAvailability,
          catalog_entry_id: 'catalog-2',
        },
      ],
    )

    const input = screen.getByPlaceholderText(/search by name/i)
    await user.clear(input)
    await user.type(input, 'Beta')

    expect(screen.getByText('Beta Source')).toBeInTheDocument()
    expect(screen.queryByText('Global API')).not.toBeInTheDocument()
  })

  it('applies bulk enable to filtered results', async () => {
    const user = userEvent.setup()
    const secondEntry: SourceCatalogEntry = {
      ...baseCatalogEntry,
      id: 'catalog-2',
      name: 'Beta Source',
      description: 'Secondary beta data',
    }
    renderSection(
      [baseCatalogEntry, secondEntry],
      [
        baseAvailability,
        {
          ...baseAvailability,
          catalog_entry_id: 'catalog-2',
        },
      ],
    )

    const input = screen.getByPlaceholderText(/search by name/i)
    await user.clear(input)
    await user.type(input, 'Beta')

    await user.click(screen.getByRole('button', { name: /Set Available/i }))

    expect(mockBulkUpdateGlobalAvailabilityAction).toHaveBeenCalledWith({
      permission_level: 'available',
      catalog_entry_ids: ['catalog-2'],
    })
  })
})
