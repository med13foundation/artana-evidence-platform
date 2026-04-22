"use client"

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Loader2, SquareMousePointer } from 'lucide-react'
import { useSpaceContext } from '@/components/space-context-provider'
import { SpaceSelectorModal } from './SpaceSelectorModal'

interface SpaceSelectorProps {
  currentSpaceId?: string
  onSpaceChange?: (spaceId: string) => void
}

export function SpaceSelector({ currentSpaceId, onSpaceChange }: SpaceSelectorProps) {
  const { currentSpaceId: contextSpaceId, spaces, isLoading } = useSpaceContext()
  const [modalOpen, setModalOpen] = useState(false)
  const selectedSpaceId = currentSpaceId || contextSpaceId || ''

  const currentSpace = spaces.find((space) => space.id === selectedSpaceId)

  if (isLoading) {
    return (
      <Button variant="outline" disabled>
        <Loader2 className="mr-2 size-4 animate-spin" />
        <span className="text-sm">Loading...</span>
      </Button>
    )
  }

  if (spaces.length === 0) {
    return (
      <Button
        variant="outline"
        onClick={() => setModalOpen(true)}
        className="border-brand-primary/40 bg-brand-primary/5 text-foreground transition-colors hover:border-brand-primary/50 hover:bg-brand-primary/10 hover:!text-foreground"
      >
        <SquareMousePointer className="mr-2 size-4 text-brand-primary" />
        <span className="text-sm">No spaces</span>
      </Button>
    )
  }

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setModalOpen(true)}
        className="w-full justify-between border-brand-primary/40 bg-brand-primary/5 text-foreground transition-colors hover:border-brand-primary/50 hover:bg-brand-primary/10 hover:!text-foreground sm:w-auto sm:min-w-[200px]"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <SquareMousePointer className="size-4 shrink-0 text-brand-primary" />
          <div className="flex min-w-0 flex-1 flex-col items-start">
            <span className="w-full truncate text-sm font-medium">
              {currentSpace?.name || 'Select a space'}
            </span>

          </div>
        </div>
      </Button>
      <SpaceSelectorModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onSpaceChange={onSpaceChange}
      />
    </>
  )
}
