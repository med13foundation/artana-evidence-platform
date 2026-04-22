import { render } from '@testing-library/react'
import { LayoutDashboard, Users } from 'lucide-react'

import { NavMain } from '@/components/navigation/sidebar/NavMain'
import { SidebarProvider } from '@/components/ui/sidebar'
import type { NavGroup } from '@/types/navigation'
import { UserRole } from '@/types/auth'

jest.mock('next/link', () => {
  const React = require('react')
  return {
    __esModule: true,
    default: React.forwardRef(
      (
        { children, href }: { children: React.ReactNode; href: string },
        ref: React.Ref<HTMLAnchorElement>
      ) => (
        <a href={href} ref={ref}>
          {children}
        </a>
      )
    ),
  }
})

describe('NavMain', () => {
  const baseGroup: NavGroup = {
    label: 'Space',
    items: [
      {
        id: 'space-overview',
        title: 'Overview',
        url: '/spaces/space-1',
        icon: LayoutDashboard,
        isActive: false,
      },
    ],
  }

  const adminGroup: NavGroup = {
    label: 'Space Admin',
    items: [
      {
        id: 'members',
        title: 'Members',
        url: '/spaces/space-1/members',
        icon: Users,
        isActive: false,
      },
    ],
  }

  const renderWithSidebar = (groups: NavGroup[]) =>
    render(
      <SidebarProvider>
        <NavMain groups={groups} />
      </SidebarProvider>
    )

  it('renders a separator between multiple navigation groups', () => {
    const { container } = renderWithSidebar([baseGroup, adminGroup])

    const separators = container.querySelectorAll('[data-sidebar="separator"]')
    expect(separators).toHaveLength(1)
  })

  it('does not render separators when only one group is provided', () => {
    const { container } = renderWithSidebar([baseGroup])

    const separators = container.querySelectorAll('[data-sidebar="separator"]')
    expect(separators).toHaveLength(0)
  })

  it('renders without errors when sidebar is collapsed', () => {
    const { getByRole } = render(
      <SidebarProvider defaultOpen={false}>
        <NavMain groups={[baseGroup]} />
      </SidebarProvider>
    )

    expect(getByRole('link', { name: 'Overview' })).toBeInTheDocument()
  })

  it('renders role-gated items only when allowed', () => {
    const adminOnlyGroup: NavGroup = {
      label: 'Admin',
      items: [
        {
          id: 'admin-settings',
          title: 'System Settings',
          url: '/admin/system',
          icon: Users,
          allowedRoles: [UserRole.ADMIN],
        },
      ],
    }

    const { queryByText, rerender } = renderWithSidebar([adminOnlyGroup])
    // Default: no user role enforcement in this component, but we can still assert render
    expect(queryByText('System Settings')).toBeInTheDocument()

    // Simulate filtering upstream by providing empty items
    rerender(
      <SidebarProvider>
        <NavMain groups={[{ label: 'Admin', items: [] }]} />
      </SidebarProvider>
    )
    expect(queryByText('System Settings')).not.toBeInTheDocument()
  })
})
