'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import type {
  OrchestratedSessionState,
  SourceCatalogEntry,
  ValidationIssueDTO,
} from '@/types/generated'
import {
  addSpaceDiscoverySources,
  updateSpaceDiscoverySelection,
} from '@/components/data-discovery/space-discovery-api'
import { SourceCatalog } from '@/components/data-discovery/SourceCatalog'

interface DataDiscoveryContentProps {
  spaceId: string
  orchestratedState: OrchestratedSessionState | null
  catalog: SourceCatalogEntry[]
  errorMessage?: string | null
  isModal?: boolean
  onComplete?: () => void
}

export function DataDiscoveryContent({
  spaceId,
  orchestratedState,
  catalog,
  errorMessage,
  isModal = false,
  onComplete,
}: DataDiscoveryContentProps) {
  const [state, setState] = useState<OrchestratedSessionState | null>(orchestratedState)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(orchestratedState?.session?.selected_sources ?? []),
  )
  const [isAdding, setIsAdding] = useState(false)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    setState(orchestratedState)
  }, [orchestratedState])

  useEffect(() => {
    if (!state?.session) {
      setSelectedIds(new Set())
      return
    }
    setSelectedIds(new Set(state.session.selected_sources))
  }, [state?.session?.selected_sources, state])

  const issues: ValidationIssueDTO[] = state?.validation?.issues ?? []
  const isValid = state?.validation?.is_valid !== false
  const viewContext = state?.view_context

  const groupedCatalog = useMemo(() => {
    const catalogEntries = Array.isArray(catalog) ? catalog : []
    const groups: Record<string, SourceCatalogEntry[]> = {}
    catalogEntries.forEach((entry) => {
      const key = entry.category || 'Uncategorized'
      if (!groups[key]) {
        groups[key] = []
      }
      groups[key].push(entry)
    })
    return groups
  }, [catalog])

  const handleToggle = (sourceId: string) => {
    if (!state?.session) {
      toast.error('Discovery session is unavailable. Please refresh.')
      return
    }
    const previousSelection = state.session.selected_sources
    const next = new Set(selectedIds)
    if (next.has(sourceId)) {
      next.delete(sourceId)
    } else {
      next.add(sourceId)
    }

    setSelectedIds(next)

    startTransition(async () => {
      const result = await updateSpaceDiscoverySelection(
        spaceId,
        state.session.id,
        Array.from(next),
      )

      if (!result.success) {
        toast.error(result.error)
        setSelectedIds(new Set(previousSelection))
        return
      }

      setState(result.state)
    })
  }

  const handleAddSelectedToSpace = async () => {
    if (!state?.session) {
      toast.error('Discovery session is unavailable. Please refresh.')
      return
    }
    if (selectedIds.size === 0) {
      toast.error('Select at least one source to add.')
      return
    }
    setIsAdding(true)
    const idsToPromote = Array.from(selectedIds)
    const result = await addSpaceDiscoverySources(
      spaceId,
      state.session.id,
      idsToPromote,
    )

    if (!result.success) {
      toast.error(result.error)
      setIsAdding(false)
      return
    }

    setIsAdding(false)
    toast.success(
      idsToPromote.length === 1
        ? 'Source added to this space.'
        : `${idsToPromote.length} sources added to this space.`,
    )
    onComplete?.()
  }

  const SelectView = () => {
    if (errorMessage) {
      return (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {errorMessage}
        </div>
      )
    }

    if (!state) {
      return (
        <div className="rounded-lg border border-dashed border-muted-foreground/40 bg-muted/40 p-4 text-sm text-muted-foreground">
          Loading discovery session...
        </div>
      )
    }

    if (!state.session) {
      return (
        <div className="rounded-lg border border-dashed border-muted-foreground/40 bg-muted/40 p-4 text-sm text-muted-foreground">
          Discovery session is unavailable. Refresh the page to try again.
        </div>
      )
    }

    if (!Array.isArray(catalog) || catalog.length === 0) {
      return <div className="p-4 text-center text-muted-foreground">No sources available</div>
    }

    return (
      <SourceCatalog
        groupedEntries={groupedCatalog}
        selectedIds={selectedIds}
        onToggle={handleToggle}
        isPending={isPending}
        validationIssues={issues}
        isValid={isValid}
      />
    )
  }

  const ModalLayout = ({ children }: { children: React.ReactNode }) => (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-hidden">
        <div className="h-full p-1">{children}</div>
      </div>
      <div className="border-t bg-background p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-muted-foreground">
            {selectedIds.size} source{selectedIds.size === 1 ? '' : 's'} selected
          </div>
          <Button
            onClick={handleAddSelectedToSpace}
            disabled={isAdding || selectedIds.size === 0 || isPending}
          >
            {isAdding || isPending ? 'Adding...' : 'Add selected to space'}
          </Button>
        </div>
      </div>
    </div>
  )

  const StandardLayout = ({ children }: { children: React.ReactNode }) => (
    <div className="space-y-6">
      <DashboardSection
        title="Select Sources"
        description="Pick sources to add directly to this research space"
      >
        {children}
      </DashboardSection>

      {state && viewContext && (
        <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-foreground">Session overview</div>
              <div>Selected sources: {viewContext.selected_count}</div>
              <div>Total available: {viewContext.total_available}</div>
            </div>
            <Button variant="outline" disabled={!viewContext.can_run_search}>
              {viewContext.can_run_search
                ? 'Run search (backend orchestrated)'
                : 'Select at least one source'}
            </Button>
          </div>
        </div>
      )}

    </div>
  )

  const Layout = isModal ? ModalLayout : StandardLayout

  return <Layout><SelectView /></Layout>
}
