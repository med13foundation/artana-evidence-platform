import type { HypothesisResponse } from '@/types/kernel'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

import {
  type HypothesisClaimStatus,
  confidenceBand,
  confidencePercent,
  humanizeToken,
  statusBadgeVariant,
} from './hypothesis-utils'

interface HypothesisListProps {
  hypotheses: HypothesisResponse[]
  canEdit: boolean
  pendingClaimId: string | null
  triageHypothesis: (
    hypothesis: HypothesisResponse,
    nextStatus: HypothesisClaimStatus,
  ) => Promise<void>
}

function HypothesisItem({
  hypothesis,
  canEdit,
  pendingClaimId,
  triageHypothesis,
}: {
  hypothesis: HypothesisResponse
  canEdit: boolean
  pendingClaimId: string | null
  triageHypothesis: (
    candidate: HypothesisResponse,
    nextStatus: HypothesisClaimStatus,
  ) => Promise<void>
}) {
  const certainty = confidenceBand(hypothesis.confidence)
  const confidence = confidencePercent(hypothesis.confidence)
  const isPending = pendingClaimId === hypothesis.claim_id
  const transferredEntityCount = hypothesis.transferred_from_entities?.length ?? 0
  const transferredClaimCount =
    hypothesis.transferred_supporting_claim_ids?.length ?? 0
  const relationView =
    `${hypothesis.source_label ?? 'Unknown source'} -> ${hypothesis.relation_type} -> ` +
    `${hypothesis.target_label ?? 'Unknown target'}`

  return (
    <Card className="border-border/70">
      <CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Hypothesis</Badge>
          <Badge variant="outline">{hypothesis.origin}</Badge>
          <Badge variant={statusBadgeVariant(hypothesis.claim_status)}>
            {humanizeToken(hypothesis.claim_status)}
          </Badge>
          <Badge variant="outline">{certainty} certainty</Badge>
          <Badge variant="outline">{confidence}%</Badge>
        </div>

        <p className="text-sm font-medium">{relationView}</p>
        {hypothesis.claim_text ? (
          <p className="text-sm text-muted-foreground">{hypothesis.claim_text}</p>
        ) : null}
        {hypothesis.reasoning_path_id ? (
          <p className="text-xs text-muted-foreground">
            Mechanism path {hypothesis.path_length ?? '?'} step
            {hypothesis.path_length === 1 ? '' : 's'} • confidence{' '}
            {confidencePercent(hypothesis.path_confidence ?? hypothesis.confidence)}%
          </p>
        ) : null}
        {transferredEntityCount > 0 ? (
          <p className="text-xs text-muted-foreground">
            Transfer-backed • {transferredEntityCount} nearby
            entit{transferredEntityCount === 1 ? 'y' : 'ies'} • {transferredClaimCount}{' '}
            transferred claim{transferredClaimCount === 1 ? '' : 's'}
          </p>
        ) : null}
        {hypothesis.explanation ? (
          <p className="text-xs text-muted-foreground">{hypothesis.explanation}</p>
        ) : null}

        <p className="font-mono text-xs text-muted-foreground">
          Claim {hypothesis.claim_id.slice(0, 8)}... • Created{' '}
          {new Date(hypothesis.created_at).toLocaleString()}
        </p>

        {canEdit ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={isPending || hypothesis.claim_status === 'OPEN'}
              onClick={() => void triageHypothesis(hypothesis, 'OPEN')}
            >
              Open
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={isPending || hypothesis.claim_status === 'NEEDS_MAPPING'}
              onClick={() => void triageHypothesis(hypothesis, 'NEEDS_MAPPING')}
            >
              Needs mapping
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={isPending || hypothesis.claim_status === 'REJECTED'}
              onClick={() => void triageHypothesis(hypothesis, 'REJECTED')}
            >
              Reject
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={isPending || hypothesis.claim_status === 'RESOLVED'}
              onClick={() => void triageHypothesis(hypothesis, 'RESOLVED')}
            >
              Resolve
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function HypothesisList({
  hypotheses,
  canEdit,
  pendingClaimId,
  triageHypothesis,
}: HypothesisListProps) {
  return (
    <div className="space-y-3">
      {hypotheses.map((hypothesis) => (
        <HypothesisItem
          key={hypothesis.claim_id}
          hypothesis={hypothesis}
          canEdit={canEdit}
          pendingClaimId={pendingClaimId}
          triageHypothesis={triageHypothesis}
        />
      ))}
    </div>
  )
}
