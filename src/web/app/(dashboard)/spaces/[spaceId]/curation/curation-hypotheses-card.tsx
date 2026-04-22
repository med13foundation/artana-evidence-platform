'use client'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import { HypothesisComposer } from './hypotheses/hypothesis-composer'
import { HypothesisFilters } from './hypotheses/hypothesis-filters'
import { HypothesisList } from './hypotheses/hypothesis-list'
import { HypothesisClaimRelations } from './hypotheses/hypothesis-claim-relations'
import { useHypothesesCardController } from './hypotheses/use-hypotheses-card-controller'

interface CurationHypothesesCardProps {
  spaceId: string
  canEdit: boolean
  autoGenerationEnabled: boolean
}

export default function CurationHypothesesCard({
  spaceId,
  canEdit,
  autoGenerationEnabled,
}: CurationHypothesesCardProps) {
  const controller = useHypothesesCardController({
    spaceId,
    canEdit,
    autoGenerationEnabled,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Hypotheses</CardTitle>
        <CardDescription>
          Claim-first workflow: manual and graph-generated hypotheses are stored together as
          relation claims (`HYPOTHESIS`) and triaged through the standard claim queue.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <HypothesisComposer
          model={{
            canEdit,
            autoGenerationEnabled,
            statement: controller.statement,
            rationale: controller.rationale,
            seedInput: controller.seedInput,
            isSubmitting: controller.isSubmitting,
            isGenerating: controller.isGenerating,
            isLoading: controller.isLoading,
            lastGeneration: controller.lastGeneration,
            feedbackMessage: controller.feedbackMessage,
            feedbackTone: controller.feedbackTone,
          }}
          actions={{
            setStatementValue: controller.changeStatement,
            setRationaleValue: controller.changeRationale,
            setSeedInputValue: controller.changeSeedInput,
            submitManual: controller.submitManualHypothesis,
            runAutoGeneration: controller.runAutoGeneration,
            refreshHypotheses: controller.refreshHypotheses,
          }}
        />

        <HypothesisFilters
          availableOrigins={controller.availableOrigins}
          originFilter={controller.originFilter}
          statusFilter={controller.statusFilter}
          certaintyFilter={controller.certaintyFilter}
          setOriginFilterValue={controller.changeOriginFilter}
          setStatusFilterValue={controller.changeStatusFilter}
          setCertaintyFilterValue={controller.changeCertaintyFilter}
        />

        {controller.error ? <p className="text-sm text-destructive">{controller.error}</p> : null}

        {controller.filteredHypotheses.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hypothesis claims available in this space yet.
          </p>
        ) : (
          <HypothesisList
            hypotheses={controller.filteredHypotheses}
            canEdit={canEdit}
            pendingClaimId={controller.pendingClaimId}
            triageHypothesis={controller.triageHypothesis}
          />
        )}

        <HypothesisClaimRelations
          spaceId={spaceId}
          canEdit={canEdit}
          hypotheses={controller.hypotheses}
        />
      </CardContent>
    </Card>
  )
}
