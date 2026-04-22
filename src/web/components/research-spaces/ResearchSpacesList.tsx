"use client"

import { ResearchSpaceCard } from './ResearchSpaceCard'
import { Button } from '@/components/ui/button'
import { Plus, Sparkles, FolderKanban } from 'lucide-react'
import Link from 'next/link'
import { Input } from '@/components/ui/input'
import { useState } from 'react'
import type { ResearchSpace } from '@/types/research-space'

interface ResearchSpacesListProps {
  spaces: ResearchSpace[]
  total: number
  errorMessage?: string | null
}

export function ResearchSpacesList({ spaces, total, errorMessage }: ResearchSpacesListProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const resolvedSpaces = Array.isArray(spaces) ? spaces : []
  const resolvedTotal = Number.isFinite(total) ? total : resolvedSpaces.length

  const filteredSpaces = resolvedSpaces.filter((space) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      space.name.toLowerCase().includes(query) ||
      space.slug.toLowerCase().includes(query) ||
      (space.description ?? '').toLowerCase().includes(query)
    )
  })

  if (errorMessage) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Research Spaces</h1>
            <p className="mt-1 text-muted-foreground">
              Manage your research workspaces and teams
            </p>
          </div>
          <Button asChild>
            <Link href="/spaces/new">
              <Plus className="mr-2 size-4" />
              Create Space
            </Link>
          </Button>
        </div>
        <div className="rounded-xl border border-destructive/30 bg-gradient-to-br from-destructive/10 via-background to-background p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
              <Sparkles className="size-5" />
            </div>
            <div className="space-y-2">
              <p className="text-sm text-destructive">
                {errorMessage}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => window.location.reload()}>
                  Retry
                </Button>
                <Button asChild>
                  <Link href="/spaces/new">
                    <Plus className="mr-2 size-4" />
                    Create Space
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Research Spaces</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your research workspaces and teams
          </p>
        </div>
        <Button asChild>
          <Link href="/spaces/new">
            <Plus className="mr-2 size-4" />
            Create Space
          </Link>
        </Button>
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <Input
            placeholder="Search spaces by name, slug, or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-sm"
          />
        </div>
      </div>

      {filteredSpaces && filteredSpaces.length === 0 ? (
        <div className="rounded-xl border border-dashed border-brand-primary/40 bg-gradient-to-r from-brand-primary/5 via-brand-secondary/5 to-background p-12 text-center shadow-sm">
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-white/80 text-brand-primary shadow-brand-sm">
            <FolderKanban className="size-5" />
          </div>
          <p className="mb-2 font-heading text-lg font-semibold">
            {searchQuery ? 'No spaces match your search' : 'No research spaces yet'}
          </p>
          <p className="mb-6 text-sm text-muted-foreground">
            {searchQuery
              ? 'Try a different keyword or clear your search.'
              : 'Create a space to organize research work and invite your team.'}
          </p>
          <div className="flex justify-center gap-3">
            {searchQuery ? (
              <Button variant="outline" onClick={() => setSearchQuery('')}>
                Clear search
              </Button>
            ) : null}
            <Button asChild>
              <Link href="/spaces/new">
                <Plus className="mr-2 size-4" />
                Create your first space
              </Link>
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredSpaces?.map((space) => (
            <ResearchSpaceCard key={space.id} space={space} />
          ))}
        </div>
      )}

      {resolvedTotal > resolvedSpaces.length && (
        <div className="text-center text-sm text-muted-foreground">
          Showing {resolvedSpaces.length} of {resolvedTotal} spaces
        </div>
      )}
    </div>
  )
}
