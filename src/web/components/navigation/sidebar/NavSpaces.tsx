"use client"

import * as React from "react"
import Link from "next/link"
import { FolderKanban, MoreHorizontal, Plus, Settings } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupAction,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import type { ResearchSpace } from "@/types/research-space"

interface NavSpacesProps {
  /** List of research spaces to display */
  spaces: ResearchSpace[]
  /** Maximum number of spaces to show before "View All" */
  maxVisible?: number
}

export function NavSpaces({ spaces, maxVisible = 5 }: NavSpacesProps) {
  const { isMobile } = useSidebar()

  const visibleSpaces = spaces.slice(0, maxVisible)
  const hasMoreSpaces = spaces.length > maxVisible

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>Research Spaces</SidebarGroupLabel>
      <SidebarGroupAction asChild title="Create New Space">
        <Link href="/spaces/new">
          <Plus className="size-4" />
          <span className="sr-only">Create New Space</span>
        </Link>
      </SidebarGroupAction>
      <SidebarMenu>
        {visibleSpaces.length > 0 ? (
          visibleSpaces.map((space) => (
            <SidebarMenuItem key={space.id}>
              <SidebarMenuButton asChild tooltip={space.name}>
                <Link href={`/spaces/${space.id}`}>
                  <SpaceIcon name={space.name} />
                  <span>{space.name}</span>
                </Link>
              </SidebarMenuButton>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuAction showOnHover>
                    <MoreHorizontal />
                    <span className="sr-only">More actions</span>
                  </SidebarMenuAction>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="w-48 rounded-lg"
                  side={isMobile ? "bottom" : "right"}
                  align={isMobile ? "end" : "start"}
                >
                  <DropdownMenuItem asChild>
                    <Link href={`/spaces/${space.id}`}>
                      <FolderKanban className="mr-2 size-4" />
                      <span>Open Space</span>
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href={`/spaces/${space.id}/settings`}>
                      <Settings className="mr-2 size-4" />
                      <span>Settings</span>
                    </Link>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          ))
        ) : (
          <SidebarMenuItem>
            <SidebarMenuButton asChild>
              <Link href="/spaces/new">
                <Plus className="size-4" />
                <span className="text-muted-foreground">Create your first space</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        )}

        {hasMoreSpaces && (
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="text-sidebar-foreground/70">
              <Link href="/spaces">
                <MoreHorizontal className="size-4" />
                <span>View all ({spaces.length})</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        )}
      </SidebarMenu>
    </SidebarGroup>
  )
}

/**
 * Space icon component - displays first letter of space name
 */
function SpaceIcon({ name }: { name: string }) {
  // Generate consistent color based on name
  const paletteClasses = [
    // Soft teal - primary brand color
    "bg-brand-primary/15 text-brand-primary",
    // Coral-peach - secondary warmth
    "bg-brand-secondary/20 text-brand-secondary",
    // Sunlight yellow accent with foreground text for contrast
    "bg-brand-accent/20 text-foreground",
  ]

  const safeName = name?.trim() || "?"
  const colorIndex = safeName.charCodeAt(0) % paletteClasses.length
  const colorClass = paletteClasses[colorIndex]

  return (
    <div
      data-testid="space-icon"
      className={`flex size-7 items-center justify-center rounded-md border border-sidebar-border/60 ${colorClass}`}
    >
      <span className="text-sm font-semibold">
        {safeName.charAt(0).toUpperCase()}
      </span>
    </div>
  )
}
