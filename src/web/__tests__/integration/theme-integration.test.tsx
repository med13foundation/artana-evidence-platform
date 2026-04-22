import { render, screen } from '@testing-library/react'
import DashboardClient from '@/app/(dashboard)/dashboard/dashboard-client'
import { SpaceStatus } from '@/types/research-space'
import { UserRole } from '@/types/auth'

// Mock space context
jest.mock('@/components/space-context-provider', () => ({
  useSpaceContext: () => ({
    currentSpaceId: null,
    setCurrentSpaceId: jest.fn(),
    isLoading: false,
    spaces: [
      {
        id: 'space-1',
        name: 'Space One',
        slug: 'space-one',
        description: 'Space description',
        status: SpaceStatus.ACTIVE,
        tags: [],
        owner_id: 'user-1',
        settings: {},
        created_at: '',
        updated_at: '',
      },
    ],
    spaceTotal: 1,
  }),
  SpaceContextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock next-themes for integration testing
jest.mock('next-themes', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: jest.fn(),
}))

import { useTheme } from 'next-themes'

describe('Theme Integration', () => {
  const mockUseTheme = useTheme as jest.MockedFunction<typeof useTheme>

  beforeEach(() => {
    mockUseTheme.mockClear()
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: jest.fn(),
      themes: ['light', 'dark', 'system'],
    })
  })

  it('dashboard maintains functionality with theme system', () => {
    render(<DashboardClient userRole={UserRole.ADMIN} />)

    // Verify all dashboard elements are present
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Admin Console')
    expect(screen.getByText(/Select a research space/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Research Spaces/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /System Settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create Space/i })).toBeInTheDocument()
  })

  // Note: Theme toggle accessibility is tested in Header component tests
})
