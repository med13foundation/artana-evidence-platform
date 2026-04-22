"use client"

import * as React from "react"
import { usePathname } from "next/navigation"
import Link from "next/link"
import { Search, Bell, Plus, ChevronRight } from "lucide-react"

import { SidebarTrigger, SidebarTriggerRight } from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { buildBreadcrumbs } from "@/lib/navigation-config"
import { cn } from "@/lib/utils"
import type { ResearchSpace } from "@/types/research-space"

interface GlobalHeaderProps {
  /** Current research space (if in space context) */
  currentSpace?: ResearchSpace | null
}

export function GlobalHeader({ currentSpace }: GlobalHeaderProps) {
  const pathname = usePathname()
  const breadcrumbs = buildBreadcrumbs(pathname, currentSpace)

  // Determine primary action based on context
  const primaryAction = React.useMemo(() => {
    if (pathname.startsWith("/spaces/") && currentSpace) {
      return {
        label: "Data Sources",
        href: `/spaces/${currentSpace.id}/data-sources`,
      }
    }
    return {
      label: "New Space",
      href: "/spaces/new",
    }
  }, [pathname, currentSpace])

  return (
    <header
      className={cn(
        "sticky top-2 z-50 flex h-14 shrink-0 items-center gap-2 rounded-2xl border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 px-3 sm:px-4 mx-2 sm:mx-4 mt-2 mb-4 shadow-brand-sm transition-all duration-300 ease-in-out"
      )}
    >
      {/* Sidebar toggle and breadcrumbs */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5 sm:gap-2">
        <SidebarTrigger className="-ml-1 shrink-0" />
        <Separator orientation="vertical" className="mr-1 h-4 shrink-0 sm:mr-2" />

        {/* Breadcrumbs */}
        <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center">
          <ol className="flex min-w-0 items-center gap-1 text-sm sm:gap-1.5">
            {breadcrumbs.map((item, index) => {
              // Hide intermediate breadcrumbs on mobile, show only first and last
              const isIntermediate = index > 0 && index < breadcrumbs.length - 1
              const shouldHideOnMobile = isIntermediate && breadcrumbs.length > 2

              return (
                <React.Fragment key={item.label}>
                  {index > 0 && (
                    <li aria-hidden="true" className="shrink-0">
                      <ChevronRight className="size-3.5 text-muted-foreground" />
                    </li>
                  )}
                  <li className={shouldHideOnMobile ? "hidden sm:block" : "min-w-0"}>
                    {item.href && !item.isCurrent ? (
                      <Link
                        href={item.href}
                        className="truncate text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {item.label}
                      </Link>
                    ) : (
                      <span
                        className={
                          item.isCurrent
                            ? "truncate font-medium text-foreground"
                            : "truncate text-muted-foreground"
                        }
                        aria-current={item.isCurrent ? "page" : undefined}
                      >
                        {item.label}
                      </span>
                    )}
                  </li>
                </React.Fragment>
              )
            })}
          </ol>
        </nav>
      </div>

      {/* Center: Search (future: Command palette trigger) */}
      <div className="hidden max-w-md flex-1 justify-center md:flex">
        <Button
          variant="outline"
          type="button"
          aria-disabled
          disabled
          className="relative h-9 w-full justify-start text-sm text-muted-foreground sm:pr-12"
          title="Command palette coming soon"
        >
          <Search className="mr-2 size-4" />
          <span>Search...</span>
          <kbd className="pointer-events-none absolute right-1.5 top-1.5 hidden h-6 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-xs font-medium opacity-100 sm:flex">
            <span className="text-xs">⌘</span>K
          </kbd>
        </Button>
      </div>

      {/* Right: Actions */}
      <div className="flex shrink-0 items-center justify-end gap-1.5 sm:gap-2">
        <Button variant="ghost" size="icon" className="size-8 sm:size-9">
          <Bell className="size-4" />
          <span className="sr-only">Notifications</span>
        </Button>

        <Button asChild size="sm" className="gap-1.5">
          <Link href={primaryAction.href}>
            <Plus className="size-4" />
            <span className="hidden sm:inline">{primaryAction.label}</span>
          </Link>
        </Button>

        <Separator orientation="vertical" className="ml-1 h-4 shrink-0 sm:ml-2" />
        <SidebarTriggerRight className="size-8 sm:size-9" />
      </div>
    </header>
  )
}
