"use client"

import * as React from "react"
import Link from "next/link"
import {
  ChevronsUpDown,
  LogOut,
  Moon,
  Sun,
  User,
} from "lucide-react"
import { useTheme } from "next-themes"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import type { SidebarUserInfo } from "@/types/navigation"
import { useSignOut } from "@/hooks/use-sign-out"
import Image from "next/image"

interface NavUserProps {
  /** User information to display */
  user: SidebarUserInfo
}

export function NavUser({ user }: NavUserProps) {
  const { isMobile } = useSidebar()
  const { signOut, isSigningOut } = useSignOut()
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  // Avoid hydration mismatch with next-themes
  React.useEffect(() => {
    setMounted(true)
  }, [])

  const handleSignOut = async () => {
    await signOut()
  }

  const handleThemeToggle = () => {
    setTheme(theme === "light" ? "dark" : "light")
  }

  const isDark = mounted && theme === "dark"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <UserAvatar user={user} />
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{user.name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {user.email}
                </span>
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <UserAvatar user={user} />
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">{user.name}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {user.email}
                  </span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem asChild>
                <Link href="/settings">
                  <User className="mr-2 size-4" />
                  Profile & Settings
                </Link>
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleThemeToggle} className="cursor-pointer">
              {isDark ? (
                <>
                  <Sun className="mr-2 size-4" />
                  Light mode
                </>
              ) : (
                <>
                  <Moon className="mr-2 size-4" />
                  Dark mode
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleSignOut}
              disabled={isSigningOut}
              className="text-destructive focus:text-destructive"
            >
              <LogOut className="mr-2 size-4" />
              {isSigningOut ? "Signing out..." : "Sign out"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

/**
 * User avatar component
 */
function UserAvatar({ user }: { user: SidebarUserInfo }) {
  if (user.avatar) {
    return (
      <Image
        src={user.avatar}
        alt={user.name}
        width={32}
        height={32}
        className="size-8 rounded-lg object-cover"
      />
    )
  }

  // Generate initials from name
  const initials = user.name
    .split(" ")
    .map((n) => n.charAt(0))
    .slice(0, 2)
    .join("")
    .toUpperCase()

  return (
    <div className="flex size-9 items-center justify-center rounded-lg border border-sidebar-border bg-sidebar-primary/10 text-sidebar-primary">
      <span className="text-sm font-semibold">{initials}</span>
    </div>
  )
}
