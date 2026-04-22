"use client"

import type { ControllerRenderProps } from 'react-hook-form'
import { Check, Loader2, Search } from 'lucide-react'
import {
  FormControl,
  FormDescription,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { type InviteMemberFormData } from '@/lib/schemas/research-space'
import { type InvitableUserSearchState } from '@/hooks/use-invitable-user-search'

interface InviteMemberUserPickerProps {
  clearUserError: () => void
  field: ControllerRenderProps<InviteMemberFormData, 'user_id'>
  searchState: InvitableUserSearchState
}

export function InviteMemberUserPicker({
  clearUserError,
  field,
  searchState,
}: InviteMemberUserPickerProps) {
  const dismissSuggestionsLater = () => {
    window.setTimeout(searchState.closeSuggestions, 120)
  }

  const syncQuery = (value: string) => {
    searchState.updateQuery(value)
    if (searchState.selectedUser !== null && value.trim() === searchState.selectedUser.username) {
      return
    }
    field.onChange('')
  }

  const chooseUser = (userId: string) => {
    const chosenUser = searchState.searchResults.find((user) => user.id === userId)
    if (!chosenUser) {
      return
    }
    searchState.selectUser(chosenUser)
    field.onChange(chosenUser.id)
    clearUserError()
  }

  return (
    <FormItem>
      <FormLabel>User</FormLabel>
      <FormControl>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            value={searchState.searchQuery}
            onChange={(event) => syncQuery(event.target.value)}
            onFocus={searchState.openSuggestions}
            onBlur={dismissSuggestionsLater}
            placeholder="Search by username, name, or email"
            className="pl-9"
            autoComplete="off"
            aria-autocomplete="list"
            aria-expanded={searchState.showSuggestions}
            aria-controls="invite-member-user-results"
          />
          <input
            type="hidden"
            name={field.name}
            value={field.value}
            ref={field.ref}
            readOnly
          />
          {searchState.showSuggestions && searchState.searchQuery.trim().length > 0 ? (
            <div
              id="invite-member-user-results"
              role="listbox"
              className="absolute z-50 mt-2 max-h-64 w-full overflow-y-auto rounded-xl border bg-background p-1 shadow-lg"
            >
              {searchState.searching ? (
                <div className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Searching active users...
                </div>
              ) : searchState.searchError ? (
                <div className="px-3 py-2 text-sm text-destructive">
                  {searchState.searchError}
                </div>
              ) : searchState.searchResults.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  No active users found.
                </div>
              ) : (
                searchState.searchResults.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    role="option"
                    aria-selected={searchState.selectedUser?.id === user.id}
                    className="flex w-full items-start justify-between rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted"
                    onMouseDown={(event) => {
                      event.preventDefault()
                      chooseUser(user.id)
                    }}
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-foreground">{user.username}</div>
                      <div className="truncate text-sm text-muted-foreground">
                        {user.full_name} · {user.email}
                      </div>
                    </div>
                    {searchState.selectedUser?.id === user.id ? (
                      <Check className="mt-0.5 size-4 shrink-0 text-primary" />
                    ) : null}
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>
      </FormControl>
      <FormDescription>
        Start typing to find an active user to invite.
      </FormDescription>
      {searchState.selectedUser ? (
        <p className="text-sm text-muted-foreground">
          Selected: {searchState.selectedUser.full_name} (@{searchState.selectedUser.username})
        </p>
      ) : null}
      <FormMessage />
    </FormItem>
  )
}
