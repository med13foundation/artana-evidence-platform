"use client"

import { useSession } from 'next-auth/react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useSignOut } from '@/hooks/use-sign-out'
import { User, LogOut, Loader2, Moon, Sun, Settings, ShieldCheck } from 'lucide-react'
import { useTheme } from 'next-themes'
import Link from 'next/link'

export function UserMenu() {
  const { data: session } = useSession()
  const { signOut, isSigningOut } = useSignOut()
  const { theme, setTheme } = useTheme()

  const userEmail = session?.user?.email || 'User'
  const userName = session?.user?.full_name || userEmail
  const userRole = session?.user?.role || 'User'
  const isAdmin = session?.user?.role === 'admin'

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="relative size-9 rounded-full border border-border p-0 hover:bg-accent">
          <div className="flex size-full items-center justify-center rounded-full bg-primary/10">
            <User className="size-4 text-primary" />
          </div>
          <span className="sr-only">Open user menu</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="end" forceMount>
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">{userName}</p>
            <p className="text-xs leading-none text-muted-foreground">{userEmail}</p>
            <p className="text-xs leading-none text-muted-foreground">{userRole}</p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings" className="cursor-pointer">
            <Settings className="mr-2 size-4" />
            <span>Settings</span>
          </Link>
        </DropdownMenuItem>
        {isAdmin && (
          <DropdownMenuItem asChild>
            <Link href="/system-settings" className="cursor-pointer">
              <ShieldCheck className="mr-2 size-4" />
              <span>System Settings</span>
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          className="cursor-pointer"
        >
          {theme === 'light' ? (
            <>
              <Moon className="mr-2 size-4" />
              <span>Dark mode</span>
            </>
          ) : (
            <>
              <Sun className="mr-2 size-4" />
              <span>Light mode</span>
            </>
          )}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={signOut}
          disabled={isSigningOut}
          className="cursor-pointer text-destructive focus:text-destructive"
        >
          {isSigningOut ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              <span>Signing out...</span>
            </>
          ) : (
            <>
              <LogOut className="mr-2 size-4" />
              <span>Sign out</span>
            </>
          )}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
