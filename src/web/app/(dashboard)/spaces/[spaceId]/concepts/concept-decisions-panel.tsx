'use client'

import type {
  ConceptDecisionResponse,
  ConceptMemberResponse,
  ConceptSetResponse,
} from '@/types/concepts'

import { ConceptDecisionsLedgerCard } from './concept-decisions-ledger-card'
import { ConceptDecisionProposeCard } from './concept-decision-propose-card'

interface ConceptDecisionsPanelProps {
  spaceId: string
  canPropose: boolean
  canReview: boolean
  conceptSets: ConceptSetResponse[]
  conceptMembers: ConceptMemberResponse[]
  conceptDecisions: ConceptDecisionResponse[]
  error?: string | null
}

export function ConceptDecisionsPanel({
  spaceId,
  canPropose,
  canReview,
  conceptSets,
  conceptMembers,
  conceptDecisions,
  error,
}: ConceptDecisionsPanelProps) {
  return (
    <div className="space-y-4">
      <ConceptDecisionProposeCard
        spaceId={spaceId}
        canPropose={canPropose}
        conceptSets={conceptSets}
        conceptMembers={conceptMembers}
      />
      <ConceptDecisionsLedgerCard
        spaceId={spaceId}
        canReview={canReview}
        conceptSets={conceptSets}
        conceptMembers={conceptMembers}
        conceptDecisions={conceptDecisions}
        error={error}
      />
    </div>
  )
}
