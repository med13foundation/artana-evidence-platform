import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchSpacesList } from '@/components/research-spaces/ResearchSpacesList'
import { SpaceStatus, type ResearchSpace } from '@/types/research-space'

jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode
    href: string
  }) {
    return <a href={href}>{children}</a>
  }
})

jest.mock('@/components/research-spaces/ResearchSpaceCard', () => ({
  ResearchSpaceCard: ({ space }: { space: ResearchSpace }) => <div>{space.name}</div>,
}))

function buildSpace(overrides?: Partial<ResearchSpace>): ResearchSpace {
  return {
    id: 'space-1',
    slug: 'alpha-space',
    name: 'Alpha Space',
    description: 'Primary research space',
    owner_id: 'user-1',
    status: SpaceStatus.ACTIVE,
    settings: {},
    tags: [],
    created_at: '2026-03-05T00:00:00Z',
    updated_at: '2026-03-05T00:00:00Z',
    ...overrides,
  }
}

describe('ResearchSpacesList', () => {
  it('renders safely when a space description is missing', async () => {
    const user = userEvent.setup()

    render(
      <ResearchSpacesList
        spaces={[buildSpace({ description: undefined as unknown as string })]}
        total={1}
      />,
    )

    const search = screen.getByPlaceholderText(
      /Search spaces by name, slug, or description/i,
    )
    await user.type(search, 'alpha')

    expect(screen.getByText('Alpha Space')).toBeInTheDocument()
  })
})
