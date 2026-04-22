import { render, screen } from '@testing-library/react'

import { NavSpaces } from '@/components/navigation/sidebar/NavSpaces'
import { SidebarProvider } from '@/components/ui/sidebar'
import { SpaceStatus, type ResearchSpace } from '@/types/research-space'
import { renderHook } from '@testing-library/react'
import { useSidebar } from '@/components/ui/sidebar'

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

describe('NavSpaces', () => {
  const baseSpace: Omit<ResearchSpace, 'id' | 'slug' | 'name' | 'owner_id'> = {
    description: '',
    status: SpaceStatus.ACTIVE,
    settings: {},
    tags: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  const spaces: ResearchSpace[] = [
    { ...baseSpace, id: 'space-1', slug: 'alpha', name: 'Alpha', owner_id: 'user-1' },
    { ...baseSpace, id: 'space-2', slug: 'beta', name: 'Beta', owner_id: 'user-1' },
    { ...baseSpace, id: 'space-3', slug: 'charlie', name: 'Charlie', owner_id: 'user-1' },
  ]

  const renderNav = () =>
    render(
      <SidebarProvider>
        <NavSpaces spaces={spaces} />
      </SidebarProvider>
    )

  it('uses brand-aligned palette classes for space icons', () => {
    renderNav()
    const icons = screen.getAllByTestId('space-icon')
    expect(icons).toHaveLength(3)

    const classList = icons.map((icon) => icon.className)
    expect(classList.some((cls) => cls.includes('bg-brand-primary/15'))).toBe(true)
    expect(classList.some((cls) => cls.includes('bg-brand-secondary/20'))).toBe(true)
    expect(classList.some((cls) => cls.includes('bg-brand-accent/20'))).toBe(true)
    icons.forEach((icon) => {
      expect(icon.className).toContain('border-sidebar-border/60')
    })
  })

  it('keeps rail icon sizing stable in collapsed mode', () => {
    const { result } = renderHook(() => useSidebar(), {
      wrapper: ({ children }) => <SidebarProvider defaultOpen={false}>{children}</SidebarProvider>,
    })
    expect(result.current.state).toBe('collapsed')
  })
})
