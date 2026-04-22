import type { GenerateHypothesesResponse } from '@/types/kernel'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface HypothesisComposerModel {
  canEdit: boolean
  autoGenerationEnabled: boolean
  statement: string
  rationale: string
  seedInput: string
  isSubmitting: boolean
  isGenerating: boolean
  isLoading: boolean
  lastGeneration: GenerateHypothesesResponse | null
  feedbackMessage: string | null
  feedbackTone: 'default' | 'success' | 'error'
}

interface HypothesisComposerActions {
  setStatementValue: (value: string) => void
  setRationaleValue: (value: string) => void
  setSeedInputValue: (value: string) => void
  submitManual: () => Promise<void>
  runAutoGeneration: () => Promise<void>
  refreshHypotheses: () => Promise<void>
}

interface HypothesisComposerProps {
  model: HypothesisComposerModel
  actions: HypothesisComposerActions
}

export function HypothesisComposer({
  model,
  actions,
}: HypothesisComposerProps) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="curation-hypothesis-statement">Hypothesis statement</Label>
          <Input
            id="curation-hypothesis-statement"
            value={model.statement}
            onChange={(event) => actions.setStatementValue(event.target.value)}
            placeholder="e.g. MED13 mutations may influence autism through transcription dysregulation"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="curation-hypothesis-rationale">Rationale</Label>
          <Input
            id="curation-hypothesis-rationale"
            value={model.rationale}
            onChange={(event) => actions.setRationaleValue(event.target.value)}
            placeholder="Why this mechanism is plausible and worth triage"
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="curation-hypothesis-seeds">Seed entity IDs (optional)</Label>
        <Input
          id="curation-hypothesis-seeds"
          value={model.seedInput}
          onChange={(event) => actions.setSeedInputValue(event.target.value)}
          placeholder="UUIDs separated by comma or whitespace"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() => void actions.submitManual()}
          disabled={!model.canEdit || model.isSubmitting}
        >
          {model.isSubmitting ? 'Logging...' : 'Log hypothesis'}
        </Button>
        {model.autoGenerationEnabled ? (
          <Button
            variant="secondary"
            onClick={() => void actions.runAutoGeneration()}
            disabled={!model.canEdit || model.isGenerating}
          >
            {model.isGenerating ? 'Generating...' : 'Auto-generate from graph'}
          </Button>
        ) : null}
        <Button
          variant="outline"
          onClick={() => void actions.refreshHypotheses()}
          disabled={model.isLoading}
        >
          Refresh hypotheses
        </Button>
      </div>

      {model.feedbackMessage ? (
        <p
          className={
            model.feedbackTone === 'error'
              ? 'whitespace-pre-line text-sm text-destructive'
              : model.feedbackTone === 'success'
                ? 'whitespace-pre-line text-sm text-emerald-600'
                : 'whitespace-pre-line text-sm text-muted-foreground'
          }
        >
          {model.feedbackMessage}
        </p>
      ) : null}

      {model.lastGeneration ? (
        <div className="rounded-md border border-border/70 bg-muted/20 p-3 text-xs text-muted-foreground">
          Run {model.lastGeneration.run_id.slice(0, 8)}... • Seeds requested{' '}
          {model.lastGeneration.requested_seed_count} • Candidates staged{' '}
          {model.lastGeneration.created_count}
        </div>
      ) : null}
    </>
  )
}
