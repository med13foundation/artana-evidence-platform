"use client"

import * as React from "react"
import Link from "next/link"
import { ChevronRight } from "lucide-react"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import type { NavGroup, NavItem } from "@/types/navigation"
import { hasSubItems } from "@/types/navigation"

interface NavMainProps {
  /** Navigation groups to render */
  groups: NavGroup[]
}

export function NavMain({ groups }: NavMainProps) {
  return (
    <>
      {groups.map((group, groupIndex) => (
        <React.Fragment key={group.label || `group-${groupIndex}`}>
          {groupIndex > 0 && (
            <SidebarSeparator aria-hidden="true" className="my-1" />
          )}
          <SidebarGroup>
            {group.label && (
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            )}
            <SidebarMenu>
              {group.items.map((item) => (
                <NavMainItem key={item.id} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroup>
        </React.Fragment>
      ))}
    </>
  )
}

interface NavMainItemProps {
  item: NavItem
}

function NavMainItem({ item }: NavMainItemProps) {
  // If item has sub-items, render as collapsible
  if (hasSubItems(item)) {
    return (
      <Collapsible
        asChild
        defaultOpen={item.isActive}
        className="group/collapsible"
      >
        <SidebarMenuItem>
          <CollapsibleTrigger asChild>
            <SidebarMenuButton
              tooltip={item.title}
              isActive={item.isActive}
            >
              <item.icon />
              <span>{item.title}</span>
              <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
            </SidebarMenuButton>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <SidebarMenuSub>
              {item.items.map((subItem) => (
                <SidebarMenuSubItem key={subItem.url}>
                  <SidebarMenuSubButton
                    asChild
                    isActive={subItem.isActive}
                  >
                    <Link href={subItem.url}>
                      <span>{subItem.title}</span>
                    </Link>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              ))}
            </SidebarMenuSub>
          </CollapsibleContent>
        </SidebarMenuItem>
      </Collapsible>
    )
  }

  // Simple navigation item (no sub-items)
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        tooltip={item.title}
        isActive={item.isActive}
      >
        <Link href={item.url}>
          <item.icon />
          <span>{item.title}</span>
          {item.badge !== undefined && (
            <span className="ml-auto flex size-5 items-center justify-center rounded-full bg-sidebar-accent text-xs font-medium text-sidebar-accent-foreground">
              {item.badge}
            </span>
          )}
          {item.hasNotification && (
            <span className="ml-auto flex size-2 rounded-full bg-destructive" />
          )}
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}
