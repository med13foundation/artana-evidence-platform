import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { compactId } from './use-claim-overlay-focus-path'

interface ClaimOverlayFocusPathCardProps {
  focusSourceEntityId: string
  focusTargetEntityId: string
  isPathFinding: boolean
  focusSummary: string | null
  focusedClaimIds: string[]
  setFocusSourceEntityId: (value: string) => void
  setFocusTargetEntityId: (value: string) => void
  findFocusPath: () => void
  clearFocusPath: () => void
}

export function ClaimOverlayFocusPathCard({
  focusSourceEntityId,
  focusTargetEntityId,
  isPathFinding,
  focusSummary,
  focusedClaimIds,
  setFocusSourceEntityId,
  setFocusTargetEntityId,
  findFocusPath,
  clearFocusPath,
}: ClaimOverlayFocusPathCardProps) {
  return (
    <Card className="border-border/80 bg-card">
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">Focus Path</p>
          <p className="text-xs text-muted-foreground">
            Find shortest claim-link path between two entities (using current review filter).
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto_auto]">
          <div className="space-y-1">
            <Label htmlFor="claim-overlay-focus-source">From entity ID</Label>
            <Input
              id="claim-overlay-focus-source"
              value={focusSourceEntityId}
              onChange={(event) => setFocusSourceEntityId(event.target.value)}
              placeholder="UUID"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="claim-overlay-focus-target">To entity ID</Label>
            <Input
              id="claim-overlay-focus-target"
              value={focusTargetEntityId}
              onChange={(event) => setFocusTargetEntityId(event.target.value)}
              placeholder="UUID"
            />
          </div>
          <Button type="button" className="self-end" disabled={isPathFinding} onClick={findFocusPath}>
            {isPathFinding ? 'Finding path...' : 'Find path'}
          </Button>
          <Button type="button" variant="outline" className="self-end" onClick={clearFocusPath}>
            Clear path
          </Button>
        </div>
        {focusSummary ? <p className="text-xs text-muted-foreground">{focusSummary}</p> : null}
        {focusedClaimIds.length > 0 ? (
          <p className="font-mono text-xs text-muted-foreground">
            {focusedClaimIds.map((claimId) => compactId(claimId)).join(' -> ')}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
