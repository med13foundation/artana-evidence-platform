import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SpaceContextProvider } from '@/components/space-context-provider'
import { WorkspaceDropdown } from '@/components/navigation/sidebar/WorkspaceDropdown'
import { SidebarProvider } from '@/components/ui/sidebar'
import { SpaceStatus, type ResearchSpace } from '@/types/research-space'

const push = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push,
    replace: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
  usePathname: () => '/dashboard',
}))

describe('WorkspaceDropdown', () => {
  const baseSpace: Omit<ResearchSpace, 'id' | 'slug' | 'name' | 'owner_id'> = {
    description: '',
    status: SpaceStatus.ACTIVE,
    settings: {},
    tags: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  const spaces: ResearchSpace[] = [
    { ...baseSpace, id: 'space-1', slug: 'alpha', name: 'Alpha Space', owner_id: 'user-1' },
    { ...baseSpace, id: 'space-2', slug: 'beta', name: 'Beta Space', owner_id: 'user-1' },
  ]

  const renderDropdown = () =>
    render(
      <SidebarProvider>
        <SpaceContextProvider
          initialSpaces={spaces}
          initialSpaceId="space-2"
          initialTotal={spaces.length}
        >
          <WorkspaceDropdown
            currentSpace={null}
            spaces={spaces}
            logo={{
              src: '/logo.svg',
              alt: 'MED13',
              width: 24,
              height: 24,
            }}
          />
        </SpaceContextProvider>
      </SidebarProvider>
    )

  beforeEach(() => {
    push.mockClear()
  })

  it('shows the active research space name in the header trigger', () => {
    renderDropdown()

    expect(screen.getByRole('button', { name: 'Beta Space' })).toBeInTheDocument()
    expect(screen.getByText('beta')).toBeInTheDocument()
  })

  it('opens a space menu and navigates when another space is selected', async () => {
    const user = userEvent.setup()
    renderDropdown()

    await user.click(screen.getByRole('button', { name: 'Beta Space' }))
    await user.click(screen.getByText('Alpha Space'))

    expect(push).toHaveBeenCalledWith('/spaces/space-1')
  })

  it('offers a create new space action', async () => {
    const user = userEvent.setup()
    renderDropdown()

    await user.click(screen.getByRole('button', { name: 'Beta Space' }))
    await user.click(screen.getByText('Create new space'))

    expect(push).toHaveBeenCalledWith('/spaces/new')
  })
})
