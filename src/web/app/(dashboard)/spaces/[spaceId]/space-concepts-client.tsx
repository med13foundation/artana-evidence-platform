'use client'

import { useRouter } from 'next/navigation'
import { RefreshCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { StatCard } from '@/components/ui/composition-patterns'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  ConceptAliasListResponse,
  ConceptDecisionListResponse,
  ConceptMemberListResponse,
  ConceptPolicyResponse,
  ConceptSetListResponse,
} from '@/types/concepts'

import { ConceptDecisionsPanel } from './concepts/concept-decisions-panel'
import { ConceptMembersPanel } from './concepts/concept-members-panel'
import { ConceptPolicyPanel } from './concepts/concept-policy-panel'
import { ConceptSetsPanel } from './concepts/concept-sets-panel'

interface SpaceConceptsClientProps {
  spaceId: string
  canEditConcepts: boolean
  canReviewDecisions: boolean
  data: {
    sets: ConceptSetListResponse | null
    members: ConceptMemberListResponse | null
    aliases: ConceptAliasListResponse | null
    policy: ConceptPolicyResponse | null
    decisions: ConceptDecisionListResponse | null
  }
  errors: {
    sets?: string | null
    members?: string | null
    aliases?: string | null
    policy?: string | null
    decisions?: string | null
  }
}

export default function SpaceConceptsClient({
  spaceId,
  canEditConcepts,
  canReviewDecisions,
  data,
  errors,
}: SpaceConceptsClientProps) {
  const router = useRouter()

  const setCount = data.sets?.total ?? 0
  const memberCount = data.members?.total ?? 0
  const aliasCount = data.aliases?.total ?? 0
  const decisionCount = data.decisions?.total ?? 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">Concept Manager</h1>
          <p className="text-sm text-muted-foreground">
            Govern concept sets, aliases, policy profile, and harness-backed decisions for this research space.
          </p>
        </div>
        <Button variant="outline" onClick={() => router.refresh()} className="w-full sm:w-auto">
          <RefreshCcw className="mr-2 size-4" />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Concept Sets" value={setCount} description="Scoped taxonomy groups" />
        <StatCard title="Members" value={memberCount} description="Canonical + provisional concepts" />
        <StatCard title="Aliases" value={aliasCount} description="Normalized synonym surface" />
        <StatCard title="Decisions" value={decisionCount} description="Governance ledger entries" />
      </div>

      {!canEditConcepts ? (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">
            You have read-only access. Researcher role or higher is required to create concept records.
          </CardContent>
        </Card>
      ) : null}

      <Tabs defaultValue="sets">
        <TabsList>
          <TabsTrigger value="sets">Sets</TabsTrigger>
          <TabsTrigger value="members">Members & Aliases</TabsTrigger>
          <TabsTrigger value="policy">Policy</TabsTrigger>
          <TabsTrigger value="decisions">Decisions</TabsTrigger>
        </TabsList>

        <TabsContent value="sets" className="mt-4">
          <ConceptSetsPanel
            spaceId={spaceId}
            canEdit={canEditConcepts}
            conceptSets={data.sets?.concept_sets ?? []}
            error={errors.sets}
          />
        </TabsContent>

        <TabsContent value="members" className="mt-4">
          <ConceptMembersPanel
            spaceId={spaceId}
            canEdit={canEditConcepts}
            conceptSets={data.sets?.concept_sets ?? []}
            conceptMembers={data.members?.concept_members ?? []}
            conceptAliases={data.aliases?.concept_aliases ?? []}
            errors={{ members: errors.members, aliases: errors.aliases }}
          />
        </TabsContent>

        <TabsContent value="policy" className="mt-4">
          <ConceptPolicyPanel
            spaceId={spaceId}
            canEdit={canEditConcepts}
            policy={data.policy}
            error={errors.policy}
          />
        </TabsContent>

        <TabsContent value="decisions" className="mt-4">
          <ConceptDecisionsPanel
            spaceId={spaceId}
            canPropose={canEditConcepts}
            canReview={canReviewDecisions}
            conceptSets={data.sets?.concept_sets ?? []}
            conceptMembers={data.members?.concept_members ?? []}
            conceptDecisions={data.decisions?.concept_decisions ?? []}
            error={errors.decisions}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
