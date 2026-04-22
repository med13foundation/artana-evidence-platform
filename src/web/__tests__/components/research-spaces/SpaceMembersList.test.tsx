import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpaceMembersList } from '@/components/research-spaces/SpaceMembersList'
import { MembershipRole, type ResearchSpaceMembership } from '@/types/research-space'

function buildMembership(
  overrides: Partial<ResearchSpaceMembership> = {},
): ResearchSpaceMembership {
  return {
    id: 'membership-1',
    space_id: 'space-1',
    user_id: 'user-1',
    role: MembershipRole.RESEARCHER,
    invited_by: null,
    invited_at: null,
    joined_at: '2026-03-07T00:00:00Z',
    is_active: true,
    created_at: '2026-03-07T00:00:00Z',
    updated_at: '2026-03-07T00:00:00Z',
    user: {
      id: 'user-1',
      email: 'jane@example.com',
      username: 'jane',
      full_name: 'Dr. Jane Smith',
    },
    ...overrides,
  }
}

describe('SpaceMembersList', () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = HTMLElement.prototype.hasPointerCapture ?? (() => false)
    HTMLElement.prototype.setPointerCapture = HTMLElement.prototype.setPointerCapture ?? (() => undefined)
    HTMLElement.prototype.releasePointerCapture =
      HTMLElement.prototype.releasePointerCapture ?? (() => undefined)
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => undefined)
  })

  it('lets managers assign a research-space role from the member table', async () => {
    const user = userEvent.setup()
    const onUpdateRole = jest.fn()

    render(
      <SpaceMembersList
        memberships={[buildMembership()]}
        isLoading={false}
        errorMessage={null}
        canManage
        onUpdateRole={onUpdateRole}
      />,
    )

    const row = screen.getByText('Dr. Jane Smith').closest('tr')
    expect(row).not.toBeNull()
    expect(screen.queryByText('user-1')).not.toBeInTheDocument()

    const rowScope = within(row as HTMLTableRowElement)
    await user.click(rowScope.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'Admin' }))

    expect(onUpdateRole).toHaveBeenCalledWith('membership-1', MembershipRole.ADMIN)
  })

  it('keeps owner memberships read-only in the role column', () => {
    render(
      <SpaceMembersList
        memberships={[
          buildMembership({
            id: 'membership-owner',
            user_id: 'owner-user',
            role: MembershipRole.OWNER,
            user: {
              id: 'owner-user',
              email: 'owner@example.com',
              username: 'owner',
              full_name: 'Owner User',
            },
          }),
        ]}
        isLoading={false}
        errorMessage={null}
        canManage
        onUpdateRole={jest.fn()}
      />,
    )

    const row = screen.getByText('Owner User').closest('tr')
    expect(row).not.toBeNull()

    const rowScope = within(row as HTMLTableRowElement)
    expect(rowScope.queryByRole('combobox')).not.toBeInTheDocument()
    expect(rowScope.getByText('Owner')).toBeInTheDocument()
  })
})
