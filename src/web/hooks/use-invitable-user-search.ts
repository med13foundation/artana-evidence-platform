"use client"

import { useEffect, useState } from 'react'
import { searchInvitableUsersAction } from '@/app/actions/research-spaces'
import { type InvitableUserOption } from '@/types/research-space'

const USER_SEARCH_DEBOUNCE_MS = 250

interface UseInvitableUserSearchParams {
  spaceId: string
  open: boolean
}

export interface InvitableUserSearchState {
  searchError: string | null
  searchQuery: string
  searchResults: InvitableUserOption[]
  selectedUser: InvitableUserOption | null
  showSuggestions: boolean
  searching: boolean
  closeSuggestions: () => void
  openSuggestions: () => void
  reset: () => void
  selectUser: (user: InvitableUserOption) => void
  updateQuery: (value: string) => void
}

export function useInvitableUserSearch({
  spaceId,
  open,
}: UseInvitableUserSearchParams): InvitableUserSearchState {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<InvitableUserOption[]>([])
  const [selectedUser, setSelectedUser] = useState<InvitableUserOption | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [searching, setSearching] = useState(false)

  const reset = () => {
    setSearchQuery('')
    setSearchResults([])
    setSelectedUser(null)
    setSearchError(null)
    setShowSuggestions(false)
    setSearching(false)
  }

  useEffect(() => {
    if (!open) {
      setSearchQuery('')
      setSearchResults([])
      setSelectedUser(null)
      setSearchError(null)
      setShowSuggestions(false)
      setSearching(false)
    }
  }, [open])

  useEffect(() => {
    if (!open) {
      return
    }

    const normalizedQuery = searchQuery.trim()
    if (selectedUser !== null && normalizedQuery === selectedUser.username) {
      setSearching(false)
      setSearchError(null)
      setSearchResults([])
      return
    }

    if (normalizedQuery.length === 0) {
      setSearching(false)
      setSearchError(null)
      setSearchResults([])
      return
    }

    let cancelled = false
    const timeoutId = window.setTimeout(async () => {
      setSearching(true)
      const result = await searchInvitableUsersAction(spaceId, normalizedQuery)
      if (cancelled) {
        return
      }
      if (result.success) {
        setSearchResults(result.data.users)
        setSearchError(null)
      } else {
        setSearchResults([])
        setSearchError(result.error)
      }
      setSearching(false)
    }, USER_SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timeoutId)
    }
  }, [open, searchQuery, selectedUser, spaceId])

  const updateQuery = (value: string) => {
    setSearchQuery(value)
    setShowSuggestions(true)
    setSearchError(null)

    if (selectedUser !== null && value.trim() === selectedUser.username) {
      return
    }

    if (selectedUser !== null) {
      setSelectedUser(null)
    }
  }

  const selectUser = (user: InvitableUserOption) => {
    setSelectedUser(user)
    setSearchQuery(user.username)
    setSearchResults([])
    setSearchError(null)
    setShowSuggestions(false)
  }

  return {
    searchError,
    searchQuery,
    searchResults,
    selectedUser,
    showSuggestions,
    searching,
    closeSuggestions: () => setShowSuggestions(false),
    openSuggestions: () => setShowSuggestions(true),
    reset,
    selectUser,
    updateQuery,
  }
}
