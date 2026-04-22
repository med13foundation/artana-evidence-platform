"use client"

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { useSpaceContext } from '@/components/space-context-provider'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, Search, Folder, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SpaceSelectorModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSpaceChange?: (spaceId: string) => void
}

export function SpaceSelectorModal({
  open,
  onOpenChange,
  onSpaceChange,
}: SpaceSelectorModalProps) {
  const router = useRouter()
  const { currentSpaceId, setCurrentSpaceId, spaces, isLoading } = useSpaceContext()
  const [searchQuery, setSearchQuery] = useState('')

  // Filter spaces based on search query
  const filteredSpaces = useMemo(() => {
    if (!searchQuery.trim()) {
      return spaces
    }
    const query = searchQuery.toLowerCase()
    return spaces.filter(
      (space) =>
        space.name.toLowerCase().includes(query) ||
        space.slug.toLowerCase().includes(query) ||
        space.description?.toLowerCase().includes(query)
    )
  }, [spaces, searchQuery])

  const handleSpaceSelect = (spaceId: string) => {
    setCurrentSpaceId(spaceId)
    if (onSpaceChange) {
      onSpaceChange(spaceId)
    } else {
      router.push(`/spaces/${spaceId}`)
    }
    onOpenChange(false)
    setSearchQuery('')
  }

  const handleCreateNew = () => {
    onOpenChange(false)
    router.push('/spaces/new')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[95vw] max-w-3xl flex-col p-0 sm:w-full [&>button]:hidden">
        <DialogHeader className="border-b px-4 pb-3 pt-4 sm:px-6 sm:pb-4 sm:pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-0">
            <div>
              <DialogTitle className="text-lg font-semibold sm:text-xl">Select a space</DialogTitle>
              <DialogDescription className="sr-only">
                Choose a research space to work with or create a new one
              </DialogDescription>
            </div>
            <Button onClick={handleCreateNew} size="sm" className="w-full sm:w-auto">
              <Plus className="mr-2 size-4" />
              New space
            </Button>
          </div>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col">
          {/* Search Bar */}
          <div className="border-b px-4 pb-2 pt-3 sm:px-6 sm:pb-3 sm:pt-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search spaces"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
                autoFocus
              />
            </div>
          </div>

          {/* Spaces List - Table-like layout */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Loading spaces...</span>
              </div>
            ) : filteredSpaces.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-4 py-12 text-center sm:px-6">
                <Folder className="mb-4 size-10 text-muted-foreground sm:size-12" />
                <p className="text-sm text-muted-foreground">
                  {searchQuery
                    ? 'No spaces found matching your search'
                    : 'No spaces available'}
                </p>
              </div>
            ) : (
              <div className="px-4 py-2 sm:px-6">
                {/* Table Header - Hidden on mobile */}
                <div className="hidden grid-cols-[1fr_auto_auto] gap-4 border-b px-3 py-2 text-xs font-medium text-muted-foreground sm:grid">
                  <div>Name</div>
                  <div>Type</div>
                  <div className="text-right">ID</div>
                </div>
                {/* Table Rows */}
                <div className="divide-y">
                  {filteredSpaces.map((space) => {
                    const isSelected = space.id === currentSpaceId
                    return (
                      <button
                        key={space.id}
                        onClick={() => handleSpaceSelect(space.id)}
                        className={cn(
                          'w-full flex flex-col sm:grid sm:grid-cols-[1fr_auto_auto] sm:gap-4 px-3 py-3 hover:bg-brand-primary/5 transition-colors text-left',
                          isSelected && 'bg-brand-primary/10'
                        )}
                      >
                        <div className="flex min-w-0 flex-col sm:contents">
                          <div className="mb-1 flex items-center gap-2 sm:mb-0">
                            <span className="truncate text-sm font-medium text-foreground">
                              {space.name}
                            </span>
                            {isSelected && (
                              <span className="whitespace-nowrap rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">
                                Current
                              </span>
                            )}
                          </div>
                          {space.description && (
                            <span className="mb-2 truncate text-xs text-muted-foreground sm:hidden">
                              {space.description}
                            </span>
                          )}
                        </div>
                        <div className="hidden items-center sm:flex">
                          <span className="text-xs text-muted-foreground">Space</span>
                        </div>
                        <div className="flex items-center justify-between sm:justify-end">
                          <span className="font-mono text-xs text-muted-foreground sm:hidden">
                            Slug: {space.slug}
                          </span>
                          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
                            {space.slug}
                          </span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="border-t px-4 py-3 sm:px-6 sm:py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="w-full sm:w-auto">
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
