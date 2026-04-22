"use client"

import { useEffect, useState } from 'react'
import { useSpaceContext } from '@/components/space-context-provider'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import {
  CloudDownload,
  Settings,
  ListChecks,
  LayoutDashboard,
  Users,
  Network,
  EllipsisVertical,
} from 'lucide-react'
import { KnowledgeGraphIcon } from '@/components/icons/KnowledgeGraphIcon'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface NavItem {
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  description?: string
}

export function SpaceNavigation() {
  const { currentSpaceId } = useSpaceContext()
  const pathname = usePathname()
  const [isMounted, setIsMounted] = useState(false)

  useEffect(() => {
    setIsMounted(true)
  }, [])

  if (!isMounted || !currentSpaceId) {
    return null
  }

  const basePath = `/spaces/${currentSpaceId}`

  const mainNavItems: NavItem[] = [
    {
      label: 'Overview',
      href: basePath,
      icon: LayoutDashboard,
      description: 'Space details and information',
    },
    {
      label: 'Data Sources',
      href: `${basePath}/data-sources`,
      icon: CloudDownload,
      description: 'Manage data sources and discover new ones',
    },
    {
      label: 'Data Curation',
      href: `${basePath}/curation`,
      icon: ListChecks,
      description: 'Curate and review data',
    },
    {
      label: 'Knowledge Graph',
      href: `${basePath}/knowledge-graph`,
      icon: KnowledgeGraphIcon,
      description: 'Explore knowledge graph',
    },
    {
      label: 'Concepts',
      href: `${basePath}/concepts`,
      icon: Network,
      description: 'Manage concept sets, aliases, and governance decisions',
    },
  ]

  const menuItems: NavItem[] = [
    {
      label: 'Members',
      href: `${basePath}/members`,
      icon: Users,
      description: 'Manage team members',
    },
    {
      label: 'Settings',
      href: `${basePath}/settings`,
      icon: Settings,
      description: 'Space configuration',
    },
  ]

  const isMenuActive = menuItems.some(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`)
  )

  return (
    <nav className="border-b border-border bg-card">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between overflow-x-auto">
          <div className="flex min-w-0 space-x-1">
            {mainNavItems.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`)
              const Icon = item.icon

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors',
                    'border-b-2 border-transparent hover:border-border hover:text-foreground',
                    'whitespace-nowrap',
                    isActive
                      ? 'border-primary text-foreground bg-accent/50'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  title={item.description}
                  prefetch={true}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="hidden sm:inline">{item.label}</span>
                  <span className="sm:hidden">{item.label.split(' ')[0]}</span>
                </Link>
              )
            })}
          </div>
          <div className="flex shrink-0">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className={cn(
                    'flex items-center justify-center size-9 rounded-md text-sm font-medium transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                    isMenuActive
                      ? 'text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                  )}
                  title="Space options"
                >
                  <EllipsisVertical className="size-5" strokeWidth={2.5} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                {menuItems.map((item) => {
                  const isActive =
                    pathname === item.href || pathname.startsWith(`${item.href}/`)
                  const Icon = item.icon

                  return (
                    <DropdownMenuItem key={item.href} asChild>
                      <Link
                        href={item.href}
                        className={cn(
                          'flex items-center gap-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50 hover:text-foreground',
                          isActive && 'bg-accent/50 text-foreground'
                        )}
                        prefetch={true}
                      >
                        <Icon className="size-4" />
                        <span>{item.label}</span>
                      </Link>
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </nav>
  )
}
