'use client'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface EdgeSuggestionsControlValues {
  spaceId: string
  sourceEntityIds: string
  allowedRelationTypes: string
  targetEntityTypes: string
  minScore: string
}

interface EdgeSuggestionsControlMutations {
  setSpaceId: (value: string) => void
  setSourceEntityIds: (value: string) => void
  setAllowedRelationTypes: (value: string) => void
  setTargetEntityTypes: (value: string) => void
  setMinScore: (value: string) => void
}

interface EdgeSuggestionsControlCommands {
  generateSuggestions: () => void
  refreshEmbeddings: () => void
}

interface EdgeSuggestionsControlsProps {
  values: EdgeSuggestionsControlValues
  busy: boolean
  mutate: EdgeSuggestionsControlMutations
  commands: EdgeSuggestionsControlCommands
}

export function EdgeSuggestionsControls({
  values,
  busy,
  mutate,
  commands,
}: EdgeSuggestionsControlsProps) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="edge-space-id">Research Space ID</Label>
          <Input
            id="edge-space-id"
            value={values.spaceId}
            onChange={(event) => mutate.setSpaceId(event.target.value)}
            placeholder="Space UUID"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="edge-source-ids">Source Entity IDs (comma-separated)</Label>
          <Input
            id="edge-source-ids"
            value={values.sourceEntityIds}
            onChange={(event) => mutate.setSourceEntityIds(event.target.value)}
            placeholder="UUID, UUID"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="edge-relation-types">Allowed Relation Types</Label>
          <Input
            id="edge-relation-types"
            value={values.allowedRelationTypes}
            onChange={(event) => mutate.setAllowedRelationTypes(event.target.value)}
            placeholder="ASSOCIATED_WITH, TARGETS"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="edge-target-types">Target Entity Types</Label>
          <Input
            id="edge-target-types"
            value={values.targetEntityTypes}
            onChange={(event) => mutate.setTargetEntityTypes(event.target.value)}
            placeholder="PHENOTYPE, DISEASE"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="edge-min-score">Min Score</Label>
          <Input
            id="edge-min-score"
            value={values.minScore}
            onChange={(event) => mutate.setMinScore(event.target.value)}
            placeholder="0.70"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={commands.generateSuggestions} disabled={busy}>
          Generate suggestions
        </Button>
        <Button variant="outline" onClick={commands.refreshEmbeddings} disabled={busy}>
          Refresh source embeddings
        </Button>
      </div>
    </>
  )
}
