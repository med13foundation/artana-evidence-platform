import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'
import {
  fetchSpaceConceptAliases,
  fetchSpaceConceptDecisions,
  fetchSpaceConceptMembers,
  fetchSpaceConceptPolicy,
  fetchSpaceConceptSets,
} from '@/lib/api/concepts'
import { fetchMyMembership } from '@/lib/api/research-spaces'
import { UserRole } from '@/types/auth'
import { MembershipRole } from '@/types/research-space'
import type {
  ConceptAliasListResponse,
  ConceptDecisionListResponse,
  ConceptMemberListResponse,
  ConceptPolicyResponse,
  ConceptSetListResponse,
} from '@/types/concepts'

import SpaceConceptsClient from '../space-concepts-client'

interface SpaceConceptsPageProps {
  params: Promise<{
    spaceId: string
  }>
}

function hasResearcherAccess(role: MembershipRole | null): boolean {
  return (
    role === MembershipRole.OWNER ||
    role === MembershipRole.ADMIN ||
    role === MembershipRole.CURATOR ||
    role === MembershipRole.RESEARCHER
  )
}

function hasCuratorAccess(role: MembershipRole | null): boolean {
  return (
    role === MembershipRole.OWNER ||
    role === MembershipRole.ADMIN ||
    role === MembershipRole.CURATOR
  )
}

export default async function SpaceConceptsPage({ params }: SpaceConceptsPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let sets: ConceptSetListResponse | null = null
  let members: ConceptMemberListResponse | null = null
  let aliases: ConceptAliasListResponse | null = null
  let policy: ConceptPolicyResponse | null = null
  let decisions: ConceptDecisionListResponse | null = null

  let setsError: string | null = null
  let membersError: string | null = null
  let aliasesError: string | null = null
  let policyError: string | null = null
  let decisionsError: string | null = null

  const [
    setsResult,
    membersResult,
    aliasesResult,
    policyResult,
    decisionsResult,
    membershipResult,
  ] = await Promise.allSettled([
    fetchSpaceConceptSets(spaceId, {}, token),
    fetchSpaceConceptMembers(spaceId, { limit: 200 }, token),
    fetchSpaceConceptAliases(spaceId, { limit: 200 }, token),
    fetchSpaceConceptPolicy(spaceId, token),
    fetchSpaceConceptDecisions(spaceId, { limit: 200 }, token),
    fetchMyMembership(spaceId, token),
  ])

  if (setsResult.status === 'fulfilled') {
    sets = setsResult.value
  } else {
    setsError = setsResult.reason instanceof Error ? setsResult.reason.message : 'Unable to load concept sets.'
    console.error('[SpaceConceptsPage] Failed to fetch concept sets', setsResult.reason)
  }

  if (membersResult.status === 'fulfilled') {
    members = membersResult.value
  } else {
    membersError =
      membersResult.reason instanceof Error ? membersResult.reason.message : 'Unable to load concept members.'
    console.error('[SpaceConceptsPage] Failed to fetch concept members', membersResult.reason)
  }

  if (aliasesResult.status === 'fulfilled') {
    aliases = aliasesResult.value
  } else {
    aliasesError =
      aliasesResult.reason instanceof Error ? aliasesResult.reason.message : 'Unable to load concept aliases.'
    console.error('[SpaceConceptsPage] Failed to fetch concept aliases', aliasesResult.reason)
  }

  if (policyResult.status === 'fulfilled') {
    policy = policyResult.value
  } else {
    policyError = policyResult.reason instanceof Error ? policyResult.reason.message : 'Unable to load concept policy.'
    console.error('[SpaceConceptsPage] Failed to fetch concept policy', policyResult.reason)
  }

  if (decisionsResult.status === 'fulfilled') {
    decisions = decisionsResult.value
  } else {
    decisionsError =
      decisionsResult.reason instanceof Error
        ? decisionsResult.reason.message
        : 'Unable to load concept decisions.'
    console.error('[SpaceConceptsPage] Failed to fetch concept decisions', decisionsResult.reason)
  }

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  let membershipRole: MembershipRole | null = null
  if (membershipResult.status === 'fulfilled') {
    membershipRole = membershipResult.value?.role ?? null
  }

  const canProposeDecisions = isPlatformAdmin || hasResearcherAccess(membershipRole)
  const canReviewDecisions = isPlatformAdmin || hasCuratorAccess(membershipRole)

  return (
    <SpaceConceptsClient
      spaceId={spaceId}
      canEditConcepts={canProposeDecisions}
      canReviewDecisions={canReviewDecisions}
      data={{
        sets,
        members,
        aliases,
        policy,
        decisions,
      }}
      errors={{
        sets: setsError,
        members: membersError,
        aliases: aliasesError,
        policy: policyError,
        decisions: decisionsError,
      }}
    />
  )
}
