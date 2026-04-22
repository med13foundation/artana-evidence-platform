import { render, screen, waitFor } from '@testing-library/react'
import { SidebarWrapper } from '@/components/navigation/sidebar/SidebarWrapper'
import { SessionProvider } from 'next-auth/react'
import type { Session } from 'next-auth'
import { UserRole } from '@/types/auth'
import type { ResearchSpace } from '@/types/research-space'
import { SpaceStatus } from '@/types/research-space'
import { SpaceContextProvider } from '@/components/space-context-provider'

jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
}))

jest.mock('@/components/navigation/sidebar/WorkspaceDropdown', () => ({
  WorkspaceDropdown: () => <div data-testid="workspace-dropdown" />,
}))

jest.mock('next-auth/react', () => {
  const original = jest.requireActual('next-auth/react')
  return {
    __esModule: true,
    ...original,
    useSession: () => ({
      data: {
        user: {
          id: 'user-1',
          email: 'test@example.com',
          full_name: 'Test User',
          role: UserRole.ADMIN,
          access_token: 'token.part.two',
        },
      } as Session,
      status: 'authenticated',
    }),
  }
})

function renderWrapper(spaces: ResearchSpace[] = []) {
  return render(
    <SessionProvider
      session={{
        user: {
          id: 'user-1',
          email: 'test@example.com',
          full_name: 'Test User',
          username: 'test-user',
          role: UserRole.ADMIN,
          email_verified: true,
          access_token: 'token.part.two',
          expires_at: Date.now() + 3600_000,
        },
        expires: new Date(Date.now() + 3600_000).toISOString(),
      }}
    >
      <SpaceContextProvider
        initialSpaces={spaces}
        initialSpaceId={spaces[0]?.id ?? null}
        initialTotal={spaces.length}
      >
        <SidebarWrapper currentMembership={null}>
          <div data-testid="content">Content</div>
        </SidebarWrapper>
      </SpaceContextProvider>
    </SessionProvider>
  )
}

describe('SidebarWrapper', () => {
  it('renders provided initial spaces without triggering loading state', async () => {
    const spaces: ResearchSpace[] = [
      {
        id: 'space-1',
        slug: 'alpha',
        name: 'Alpha',
        description: '',
        owner_id: 'user-1',
        status: 'active' as SpaceStatus,
        settings: {},
        tags: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]

    renderWrapper(spaces)

    expect(screen.getByText('Content')).toBeInTheDocument()
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    await waitFor(() => {
      const triggers = screen.getAllByRole('button')
      expect(triggers.length).toBeGreaterThan(0)
    })
  })
})
