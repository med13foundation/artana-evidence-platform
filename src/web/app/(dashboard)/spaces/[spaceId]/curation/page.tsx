import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceCurationClient from '../space-curation-client'
import {
  fetchKernelEntities,
  fetchKernelRelations,
  fetchRelationClaims,
  fetchRelationConflicts,
} from '@/lib/api/kernel'
import { fetchMyMembership } from '@/lib/api/research-spaces'
import { MembershipRole } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import type {
  KernelRelationListResponse,
  RelationClaimListResponse,
  RelationConflictListResponse,
} from '@/types/kernel'
import {
  errorMessage,
  errorStatusCode,
  firstString,
  isTimeoutLikeError,
  parseIntParam,
  parseStringList,
} from './page-helpers'

interface SpaceCurationPageProps {
  params: Promise<{
    spaceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

export default async function SpaceCurationPage({ params, searchParams }: SpaceCurationPageProps) {
  const { spaceId } = await params
  const resolvedSearchParams = searchParams ? await searchParams : undefined
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  const hypothesisGenerationEnabled = ['1', 'true', 'yes', 'on'].includes(
    (process.env.GRAPH_ENABLE_HYPOTHESIS_GENERATION ?? '0').toLowerCase(),
  )

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let relations: KernelRelationListResponse | null = null
  let claims: RelationClaimListResponse | null = null
  let relationConflicts: RelationConflictListResponse | null = null
  let relationsError: string | null = null
  let claimsError: string | null = null
  let entityLabelsById: Record<string, string> = {}

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  let effectiveRole: MembershipRole = isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER

  const tab = firstString(resolvedSearchParams?.tab) === 'claims' ? 'claims' : 'graph'
  const graphMode =
    firstString(resolvedSearchParams?.graph_mode) === 'claim_overlay'
      ? 'claim_overlay'
      : 'canonical'
  const relationType = firstString(resolvedSearchParams?.relation_type)
  const curationStatus = firstString(resolvedSearchParams?.curation_status)
  const validationState = firstString(resolvedSearchParams?.validation_state)
  const sourceDocumentId = firstString(resolvedSearchParams?.source_document_id)
  const certaintyBand = firstString(resolvedSearchParams?.certainty_band)
  const nodeQuery = firstString(resolvedSearchParams?.node_query)
  const nodeIds = parseStringList(resolvedSearchParams?.node_ids)
  const focusRelationId = firstString(resolvedSearchParams?.focus_relation_id)
  const offset = parseIntParam(firstString(resolvedSearchParams?.offset), 0)
  const limit = Math.min(parseIntParam(firstString(resolvedSearchParams?.limit), 25), 200)
  const claimStatus = firstString(resolvedSearchParams?.claim_status)
  const claimValidationState = firstString(resolvedSearchParams?.claim_validation_state)
  const claimPersistability = firstString(resolvedSearchParams?.persistability)
  const claimPolarity = firstString(resolvedSearchParams?.claim_polarity)
  const claimRelationType = firstString(resolvedSearchParams?.claim_relation_type)
  const claimSourceDocumentId = firstString(resolvedSearchParams?.claim_source_document_id)
  const claimLinkedRelationId = firstString(resolvedSearchParams?.linked_relation_id)
  const claimCertaintyBand = firstString(resolvedSearchParams?.claim_certainty_band)
  const claimOffset = parseIntParam(firstString(resolvedSearchParams?.claim_offset), 0)
  const claimLimit = Math.min(parseIntParam(firstString(resolvedSearchParams?.claim_limit), 25), 200)
  const membershipPromise = fetchMyMembership(spaceId, token)

  try {
    relations = await fetchKernelRelations(
      spaceId,
      {
        ...(relationType ? { relation_type: relationType } : {}),
        ...(curationStatus ? { curation_status: curationStatus } : {}),
        ...(validationState ? { validation_state: validationState } : {}),
        ...(sourceDocumentId ? { source_document_id: sourceDocumentId } : {}),
        ...(certaintyBand ? { certainty_band: certaintyBand as 'HIGH' | 'MEDIUM' | 'LOW' } : {}),
        ...(nodeQuery ? { node_query: nodeQuery } : {}),
        ...(nodeIds.length > 0 ? { node_ids: nodeIds } : {}),
        offset,
        limit,
      },
      token,
    )
  } catch (error) {
    const timeoutLikeError = isTimeoutLikeError(error)
    if (timeoutLikeError && limit > 20) {
      try {
        relations = await fetchKernelRelations(
          spaceId,
          {
            ...(relationType ? { relation_type: relationType } : {}),
            ...(curationStatus ? { curation_status: curationStatus } : {}),
            ...(validationState ? { validation_state: validationState } : {}),
            ...(sourceDocumentId ? { source_document_id: sourceDocumentId } : {}),
            ...(certaintyBand ? { certainty_band: certaintyBand as 'HIGH' | 'MEDIUM' | 'LOW' } : {}),
            ...(nodeQuery ? { node_query: nodeQuery } : {}),
            ...(nodeIds.length > 0 ? { node_ids: nodeIds } : {}),
            offset,
            limit: 20,
          },
          token,
        )
      } catch (retryError) {
        relationsError = errorMessage(retryError)
        console.warn(`[SpaceCurationPage] Relation lookup retry failed: ${relationsError}`)
      }
    } else {
      relationsError = errorMessage(error)
      console.warn(`[SpaceCurationPage] Relation lookup failed: ${relationsError}`)
    }
  }

  try {
    claims = await fetchRelationClaims(
      spaceId,
      {
        ...(claimStatus
          ? {
              claim_status: claimStatus as 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED',
            }
          : {}),
        ...(claimValidationState ? { validation_state: claimValidationState } : {}),
        ...(claimPersistability
          ? {
              persistability: claimPersistability as 'PERSISTABLE' | 'NON_PERSISTABLE',
            }
          : {}),
        ...(claimPolarity
          ? {
              polarity: claimPolarity as 'SUPPORT' | 'REFUTE' | 'UNCERTAIN' | 'HYPOTHESIS',
            }
          : {}),
        ...(claimSourceDocumentId
          ? { source_document_id: claimSourceDocumentId }
          : {}),
        ...(claimRelationType ? { relation_type: claimRelationType } : {}),
        ...(claimLinkedRelationId ? { linked_relation_id: claimLinkedRelationId } : {}),
        ...(claimCertaintyBand
          ? { certainty_band: claimCertaintyBand as 'HIGH' | 'MEDIUM' | 'LOW' }
          : {}),
        offset: claimOffset,
        limit: claimLimit,
      },
      token,
    )
  } catch (error) {
    claimsError = errorMessage(error)
    console.warn(`[SpaceCurationPage] Relation claims lookup failed: ${claimsError}`)
  }

  try {
    relationConflicts = await fetchRelationConflicts(
      spaceId,
      { offset: 0, limit: 200 },
      token,
    )
  } catch (error) {
    const statusCode = errorStatusCode(error)
    if (statusCode === 404 || statusCode === 405) {
      relationConflicts = {
        conflicts: [],
        total: 0,
        offset: 0,
        limit: 200,
      }
    } else {
      console.warn('[SpaceCurationPage] Relation conflicts lookup failed', error)
    }
  }

  try {
    const membership = await membershipPromise
    if (membership?.role) {
      effectiveRole = membership.role
    }
  } catch (error) {
    console.warn('[SpaceCurationPage] Membership lookup unavailable; using fallback role')
  }

  const canCurate =
    isPlatformAdmin ||
    effectiveRole === MembershipRole.OWNER ||
    effectiveRole === MembershipRole.ADMIN ||
    effectiveRole === MembershipRole.CURATOR

  const uniqueEntityIds = new Set<string>(nodeIds)
  if (relations?.relations && relations.relations.length > 0) {
    for (const relation of relations.relations) {
      uniqueEntityIds.add(relation.source_id)
      uniqueEntityIds.add(relation.target_id)
    }
  }

  if (uniqueEntityIds.size > 0) {
    const entityIds = Array.from(uniqueEntityIds).slice(0, 80)
    const labelById: Record<string, string> = {}
    for (const entityId of entityIds) {
      labelById[entityId] = `Entity ${entityId.slice(0, 8)}`
    }
    try {
      const entities = await fetchKernelEntities(
        spaceId,
        {
          ids: entityIds,
          offset: 0,
          limit: entityIds.length,
        },
        token,
      )
      for (const entity of entities.entities) {
        const resolved =
          entity.display_label && entity.display_label.trim().length > 0
            ? entity.display_label.trim()
            : entity.entity_type
        labelById[entity.id] = resolved
      }
    } catch (error) {
      console.warn('[SpaceCurationPage] Failed to fetch entity labels in bulk', error)
    }
    entityLabelsById = labelById
  }

  return (
    <SpaceCurationClient
      spaceId={spaceId}
      activeTab={tab}
      relations={relations}
      relationsError={relationsError}
      claims={claims}
      claimsError={claimsError}
      relationConflicts={relationConflicts}
      entityLabelsById={entityLabelsById}
      canCurate={canCurate}
      hypothesisGenerationEnabled={hypothesisGenerationEnabled}
      relationFilters={{
        graphMode,
        relationType: relationType ?? '',
        curationStatus: curationStatus ?? '',
        validationState: validationState ?? '',
        sourceDocumentId: sourceDocumentId ?? '',
        certaintyBand: certaintyBand ?? '',
        nodeQuery: nodeQuery ?? '',
        nodeIds,
        focusRelationId: focusRelationId ?? '',
        offset,
        limit,
      }}
      claimFilters={{
        claimStatus: claimStatus ?? '',
        validationState: claimValidationState ?? '',
        persistability: claimPersistability ?? '',
        polarity: claimPolarity ?? '',
        relationType: claimRelationType ?? '',
        sourceDocumentId: claimSourceDocumentId ?? '',
        linkedRelationId: claimLinkedRelationId ?? '',
        certaintyBand: claimCertaintyBand ?? '',
        offset: claimOffset,
        limit: claimLimit,
      }}
    />
  )
}
