import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '@/components/theme-provider'
import type { SpaceContextValue } from '@/components/space-context-provider'
import DashboardClient from '@/app/(dashboard)/dashboard/dashboard-client'
import { SpaceStatus } from '@/types/research-space'
import { UserRole } from '@/types/auth'

// Mock ThemeProvider to avoid DOM prop warnings
jest.mock('@/components/theme-provider', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock space context
const mockSetCurrentSpaceId = jest.fn()
const baseSpaceContext: SpaceContextValue = {
  currentSpaceId: 'space-1',
  setCurrentSpaceId: mockSetCurrentSpaceId,
  isLoading: false,
  spaces: [
    {
      id: 'space-1',
      name: 'Space One',
      slug: 'space-one',
      description: 'First space',
      status: SpaceStatus.ACTIVE,
      tags: [] as string[],
      owner_id: 'user-1',
      settings: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'space-2',
      name: 'Space Two',
      slug: 'space-two',
      description: 'Second space',
      status: SpaceStatus.ACTIVE,
      tags: [] as string[],
      owner_id: 'user-2',
      settings: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  spaceTotal: 2,
}

const mockUseSpaceContext = jest.fn<SpaceContextValue, []>(() => baseSpaceContext)

jest.mock('@/components/space-context-provider', () => ({
  useSpaceContext: () => mockUseSpaceContext(),
  SpaceContextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Test wrapper with providers
const renderWithProviders = (component: React.ReactElement) => {
  return render(
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      {component}
    </ThemeProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the admin console hero and description', () => {
    renderWithProviders(<DashboardClient userRole={UserRole.ADMIN} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Admin Console')
    expect(
      screen.getByText(/Select a research space to manage project-level data/i),
    ).toBeInTheDocument()
  })

  it('shows admin actions for creating spaces and opening system settings', () => {
    renderWithProviders(<DashboardClient userRole={UserRole.ADMIN} />)
    expect(screen.getByRole('button', { name: /System Settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create Space/i })).toBeInTheDocument()
  })

  it('lists research spaces the admin can access', () => {
    renderWithProviders(<DashboardClient userRole={UserRole.ADMIN} />)
    expect(screen.getAllByText('Space One').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Space Two').length).toBeGreaterThan(0)
  })

  it('shows the current space when one is selected', () => {
    renderWithProviders(<DashboardClient userRole={UserRole.ADMIN} />)
    expect(screen.getByText(/Current space/i)).toBeInTheDocument()
    expect(screen.getAllByText('Space One').length).toBeGreaterThan(0)
  })

  it('renders empty state when no spaces are available', () => {
    mockUseSpaceContext.mockReturnValueOnce({
      currentSpaceId: null,
      setCurrentSpaceId: mockSetCurrentSpaceId,
      isLoading: false,
      spaces: [],
      spaceTotal: 0,
    })

    renderWithProviders(<DashboardClient userRole={UserRole.ADMIN} />)
    expect(screen.getByText(/No research spaces yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create your first space/i })).toBeInTheDocument()
  })
})
