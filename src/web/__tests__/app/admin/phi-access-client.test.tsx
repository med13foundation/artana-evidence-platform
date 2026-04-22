import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PhiAccessClient from '@/app/(dashboard)/admin/phi-access/phi-access-client'
import type { UserListResponse } from '@/lib/api/users'

const mockUpdateUserAction = jest.fn()
const mockFetchUsersQueryAction = jest.fn()

jest.mock('@/app/actions/users', () => ({
  updateUserAction: (...args: unknown[]) => mockUpdateUserAction(...args),
}))

jest.mock('@/app/actions/admin-query', () => ({
  fetchUsersQueryAction: (...args: unknown[]) => mockFetchUsersQueryAction(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

const users: UserListResponse = {
  users: [
    {
      id: 'user-1',
      email: 'admin@artana.org',
      username: 'admin-user',
      full_name: 'Admin User',
      role: 'admin',
      status: 'active',
      email_verified: true,
      last_login: null,
      created_at: '2026-03-01T00:00:00.000Z',
    },
    {
      id: 'user-2',
      email: 'researcher@artana.org',
      username: 'researcher-user',
      full_name: 'Researcher User',
      role: 'researcher',
      status: 'active',
      email_verified: true,
      last_login: null,
      created_at: '2026-03-01T00:00:00.000Z',
    },
  ],
  total: 2,
  skip: 0,
  limit: 500,
}

const updatedUsers: UserListResponse = {
  ...users,
  users: [
    users.users[0],
    {
      ...users.users[1],
      role: 'admin',
    },
  ],
}

function renderClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <PhiAccessClient users={users} currentUserId="admin-self" />
    </QueryClientProvider>,
  )
}

describe('PhiAccessClient', () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = HTMLElement.prototype.hasPointerCapture ?? (() => false)
    HTMLElement.prototype.setPointerCapture = HTMLElement.prototype.setPointerCapture ?? (() => undefined)
    HTMLElement.prototype.releasePointerCapture =
      HTMLElement.prototype.releasePointerCapture ?? (() => undefined)
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => undefined)
  })

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetchUsersQueryAction.mockResolvedValue(updatedUsers)
    mockUpdateUserAction.mockResolvedValue({
      success: true,
      data: {
        user: {
          ...users.users[1],
          role: 'admin',
        },
      },
    })
  })

  it('updates role-dependent PHI counts after a role change succeeds', async () => {
    const user = userEvent.setup()
    renderClient()

    const researcherRow = screen.getByText('Researcher User').closest('tr')
    expect(researcherRow).not.toBeNull()

    const row = within(researcherRow as HTMLTableRowElement)

    await user.click(row.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'admin' }))
    await user.click(row.getByRole('button', { name: /^Save$/i }))

    await waitFor(() => {
      expect(mockUpdateUserAction).toHaveBeenCalledWith('user-2', { role: 'admin' })
    })

    await waitFor(() => {
      expect(screen.getAllByText('Allowed')).toHaveLength(2)
      expect(screen.queryByText('Blocked')).not.toBeInTheDocument()
    })
  })
})
