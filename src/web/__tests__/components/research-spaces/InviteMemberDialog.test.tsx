import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InviteMemberDialog } from '@/components/research-spaces/InviteMemberDialog'
import {
  inviteMemberAction,
  searchInvitableUsersAction,
} from '@/app/actions/research-spaces'
import { MembershipRole } from '@/types/research-space'
import { toast } from 'sonner'

jest.mock('@/app/actions/research-spaces', () => ({
  inviteMemberAction: jest.fn(),
  searchInvitableUsersAction: jest.fn(),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

const mockInviteMemberAction = inviteMemberAction as jest.MockedFunction<
  typeof inviteMemberAction
>
const mockSearchInvitableUsersAction = searchInvitableUsersAction as jest.MockedFunction<
  typeof searchInvitableUsersAction
>

describe('InviteMemberDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('searches active users and invites the selected user', async () => {
    jest.useFakeTimers()

    const user = userEvent.setup({
      advanceTimers: jest.advanceTimersByTime,
    })
    const setDialogOpen = jest.fn()

    mockSearchInvitableUsersAction.mockResolvedValue({
      success: true,
      data: {
        query: 'jane',
        users: [
          {
            id: '00000000-0000-0000-0000-000000000002',
            username: 'jane.smith',
            full_name: 'Dr. Jane Smith',
            email: 'jane@example.com',
          },
        ],
        total: 1,
        limit: 8,
      },
    })
    mockInviteMemberAction.mockResolvedValue({
      success: true,
      data: {
        id: '00000000-0000-0000-0000-000000000012',
        space_id: 'space-1',
        user_id: '00000000-0000-0000-0000-000000000002',
        role: MembershipRole.VIEWER,
        invited_by: 'owner-1',
        invited_at: '2026-03-09T00:00:00Z',
        joined_at: null,
        is_active: true,
        created_at: '2026-03-09T00:00:00Z',
        updated_at: '2026-03-09T00:00:00Z',
        user: {
          id: '00000000-0000-0000-0000-000000000002',
          username: 'jane.smith',
          full_name: 'Dr. Jane Smith',
          email: 'jane@example.com',
        },
      },
    })

    render(
      <InviteMemberDialog
        spaceId="space-1"
        open
        setDialogOpen={setDialogOpen}
      />,
    )

    const searchInput = screen.getByPlaceholderText(/search by username, name, or email/i)
    await user.type(searchInput, 'jane')

    await act(async () => {
      jest.advanceTimersByTime(300)
    })

    await waitFor(() => {
      expect(mockSearchInvitableUsersAction).toHaveBeenCalledWith('space-1', 'jane')
    })

    await user.click(screen.getByRole('option', { name: /jane\.smith/i }))

    expect(searchInput).toHaveValue('jane.smith')
    expect(screen.getByText(/selected: dr\. jane smith \(@jane\.smith\)/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /send invitation/i }))

    await waitFor(() => {
      expect(mockInviteMemberAction).toHaveBeenCalledWith('space-1', {
        user_id: '00000000-0000-0000-0000-000000000002',
        role: MembershipRole.VIEWER,
      })
    })
    expect(setDialogOpen).toHaveBeenCalledWith(false)
    expect(toast.success).toHaveBeenCalledWith('Invitation sent')
  })
})
