'use client'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { DataDiscoveryContent } from '@/components/data-discovery/DataDiscoveryContent'
import { Button } from '@/components/ui/button'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import { CreateDataSourceDialog } from './CreateDataSourceDialog'

interface DiscoverSourcesDialogProps {
  spaceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  discoveryState: OrchestratedSessionState | null
  discoveryCatalog: SourceCatalogEntry[]
  discoveryError?: string | null
  onSourceAdded?: () => void | Promise<void>
}

export function DiscoverSourcesDialog({
  spaceId,
  open,
  onOpenChange,
  discoveryState,
  discoveryCatalog,
  discoveryError,
  onSourceAdded,
}: DiscoverSourcesDialogProps) {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)

  const handleComplete = () => {
    onSourceAdded?.()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] max-w-7xl flex-col p-0">
        <DialogHeader className="shrink-0 border-b px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogTitle>Discover Data Sources</DialogTitle>
              <DialogDescription>
                Browse and test available data sources before adding them to your research space.
              </DialogDescription>
            </div>
            <Button variant="outline" onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="mr-2 size-4" />
              Create Custom Source
            </Button>
          </div>
        </DialogHeader>
        <div className="flex-1 overflow-hidden p-6">
          <DataDiscoveryContent
            spaceId={spaceId}
            isModal={true}
            orchestratedState={discoveryState}
            catalog={discoveryCatalog}
            errorMessage={discoveryError}
            onComplete={handleComplete}
          />
        </div>
        <CreateDataSourceDialog
          spaceId={spaceId}
          open={isCreateDialogOpen}
          onOpenChange={setIsCreateDialogOpen}
          onCreated={handleComplete}
        />
      </DialogContent>
    </Dialog>
  )
}
