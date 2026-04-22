'use client'

import type {
  ConceptAliasResponse,
  ConceptMemberResponse,
  ConceptSetResponse,
} from '@/types/concepts'

import { ConceptAliasCreateCard } from './concept-alias-create-card'
import { ConceptAliasesTableCard } from './concept-aliases-table-card'
import { ConceptMemberCreateCard } from './concept-member-create-card'
import { ConceptMembersTableCard } from './concept-members-table-card'

interface ConceptMembersPanelProps {
  spaceId: string
  canEdit: boolean
  conceptSets: ConceptSetResponse[]
  conceptMembers: ConceptMemberResponse[]
  conceptAliases: ConceptAliasResponse[]
  errors: {
    members?: string | null
    aliases?: string | null
  }
}

export function ConceptMembersPanel({
  spaceId,
  canEdit,
  conceptSets,
  conceptMembers,
  conceptAliases,
  errors,
}: ConceptMembersPanelProps) {
  return (
    <div className="space-y-4">
      <ConceptMemberCreateCard
        spaceId={spaceId}
        canEdit={canEdit}
        conceptSets={conceptSets}
      />
      <ConceptAliasCreateCard
        spaceId={spaceId}
        canEdit={canEdit}
        conceptMembers={conceptMembers}
      />
      <ConceptMembersTableCard
        conceptMembers={conceptMembers}
        conceptSets={conceptSets}
        error={errors.members}
      />
      <ConceptAliasesTableCard
        conceptAliases={conceptAliases}
        conceptMembers={conceptMembers}
        error={errors.aliases}
      />
    </div>
  )
}
