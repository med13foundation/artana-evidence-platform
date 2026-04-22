"use client"

import * as React from "react"
import { Check, ChevronDown, Plus, SquareStack } from "lucide-react"
import { useRouter } from "next/navigation"

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { BrandLogo } from "@/components/branding/BrandLogo"
import { useSpaceContext } from "@/components/space-context-provider"
import { cn } from "@/lib/utils"
import type { ResearchSpace } from "@/types/research-space"

interface WorkspaceDropdownProps {
  /** Currently selected space (null if on dashboard) */
  currentSpace: ResearchSpace | null
  /** List of available spaces */
  spaces: ResearchSpace[]
  /** Logo configuration */
  logo: {
    src: string
    alt: string
    width: number
    height: number
  }
}

export function WorkspaceDropdown({
  currentSpace,
  spaces,
  logo,
}: WorkspaceDropdownProps) {
  const router = useRouter()
  const { currentSpaceId, setCurrentSpaceId } = useSpaceContext()

  const activeSpace = React.useMemo<ResearchSpace | null>(() => {
    if (currentSpace) {
      return currentSpace
    }
    if (currentSpaceId) {
      return spaces.find((space) => space.id === currentSpaceId) ?? null
    }
    return spaces[0] ?? null
  }, [currentSpace, currentSpaceId, spaces])

  const displayLabel = activeSpace?.name ?? "Select a space"
  const displaySlug = activeSpace?.slug ?? "Create or switch spaces"

  const handleSpaceSelect = React.useCallback(
    (space: ResearchSpace) => {
      setCurrentSpaceId(space.id)
      router.push(`/spaces/${space.id}`)
    },
    [router, setCurrentSpaceId]
  )

  const handleCreateSpace = React.useCallback(() => {
    router.push("/spaces/new")
  }, [router])

  const handleBrowseSpaces = React.useCallback(() => {
    router.push("/spaces")
  }, [router])

  return (
    <DropdownMenu>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              aria-label={displayLabel}
              className="gap-3 rounded-2xl bg-brand-primary/5 px-3 py-2.5 text-foreground transition-colors hover:bg-brand-primary/10 data-[state=open]:bg-brand-primary/15 data-[state=open]:text-foreground group-data-[collapsible=icon]:!justify-center group-data-[collapsible=icon]:!gap-0"
            >
              <div className="flex aspect-square size-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white/90 dark:bg-[#0F1C22]">
                <BrandLogo
                  alt={logo.alt}
                  width={logo.width}
                  height={logo.height}
                  className="size-8"
                />
              </div>
              <div className="grid min-w-0 flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate font-semibold tracking-[-0.01em] text-foreground">{displayLabel}</span>
                <span className="truncate pt-0.5 text-[11px] text-muted-foreground">
                  {displaySlug}
                </span>
              </div>
              <ChevronDown className="ml-1 size-4 shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
        </SidebarMenuItem>
      </SidebarMenu>
      <DropdownMenuContent
        align="start"
        className="w-[var(--radix-dropdown-menu-trigger-width)] min-w-[18rem] rounded-2xl border-sidebar-border/70 bg-popover/95 p-2 backdrop-blur"
      >
        <DropdownMenuLabel className="px-3 py-2">
          <div className="flex items-center gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-primary/10 text-brand-primary">
              <SquareStack className="size-4" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-foreground">{displayLabel}</div>
              <div className="truncate text-xs font-normal text-muted-foreground">{displaySlug}</div>
            </div>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {spaces.length > 0 ? (
          spaces.map((space) => {
            const isActive = space.id === activeSpace?.id
            return (
              <DropdownMenuItem
                key={space.id}
                onSelect={() => handleSpaceSelect(space)}
                className={cn(
                  "gap-3 rounded-xl px-3 py-2.5",
                  isActive && "bg-brand-primary/10"
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{space.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{space.slug}</div>
                </div>
                {isActive ? <Check className="size-4 text-brand-primary" /> : null}
              </DropdownMenuItem>
            )
          })
        ) : (
          <DropdownMenuItem disabled className="rounded-xl px-3 py-2.5">
            No spaces yet
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleBrowseSpaces} className="gap-3 rounded-xl px-3 py-2.5">
          <SquareStack className="size-4" />
          Browse spaces
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={handleCreateSpace} className="gap-3 rounded-xl px-3 py-2.5">
          <Plus className="size-4" />
          Create new space
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
