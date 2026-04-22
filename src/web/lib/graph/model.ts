import type {
  ClaimEvidenceResponse,
  ClaimParticipantResponse,
  KernelEntityResponse,
  KernelGraphExportResponse,
  KernelGraphSubgraphResponse,
  KernelRelationResponse,
  RelationConflictResponse,
  RelationClaimResponse,
} from '@/types/kernel'
import type { JSONObject } from '@/types/generated'

export type GraphEdgeOrigin = 'canonical' | 'claim' | 'evidence'
export type GraphNodeOrigin = 'entity' | 'claim' | 'evidence'
export type GraphDisplayMode = 'RELATIONS_ONLY' | 'CLAIMS' | 'EVIDENCE'

export interface GraphNode {
  id: string
  entityType: string
  label: string
  aliases: string[]
  metadata: JSONObject
  createdAt: string
  updatedAt: string
  origin: GraphNodeOrigin
  claimId: string | null
  linkedRelationId: string | null
  claimStatus: RelationClaimResponse['claim_status'] | null
  claimPolarity: RelationClaimResponse['polarity'] | null
  claimText: string | null
}

export interface GraphEdge {
  id: string
  sourceId: string
  targetId: string
  relationType: string
  curationStatus: string
  confidence: number
  provenanceId: string | null
  createdAt: string
  updatedAt: string
  sourceCount: number
  highestEvidenceTier: string | null
  hasConflict: boolean
  supportClaimCount: number
  refuteClaimCount: number
  origin: GraphEdgeOrigin
  claimId: string | null
  linkedRelationId: string | null
  claimStatus: RelationClaimResponse['claim_status'] | null
  claimPolarity: RelationClaimResponse['polarity'] | null
  claimText: string | null
  claimRelationType: string | null
  claimParticipantRole: string | null
  evidenceSourceType: 'paper' | 'dataset' | null
  evidenceSourceBadge: string | null
  evidenceSentenceSource: string | null
  evidenceSentenceConfidence: string | null
  canonicalClaimCount: number
  linkedClaimIds: string[]
}

export interface GraphStats {
  nodeCount: number
  edgeCount: number
}

export interface GraphModel {
  nodes: GraphNode[]
  edges: GraphEdge[]
  nodeById: Record<string, GraphNode>
  edgeById: Record<string, GraphEdge>
  adjacency: Record<string, string[]>
  incidentEdges: Record<string, string[]>
  relationTypes: string[]
  curationStatuses: string[]
  stats: GraphStats
}

export interface GraphPruneResult {
  model: GraphModel
  preCapNodeCount: number
  preCapEdgeCount: number
  truncatedNodes: boolean
  truncatedEdges: boolean
}

export interface GraphNeighborhood {
  nodeIds: Set<string>
  edgeIds: Set<string>
}

type GraphSource = Pick<KernelGraphExportResponse, 'nodes' | 'edges'> | Pick<KernelGraphSubgraphResponse, 'nodes' | 'edges'>

const CURATION_STATUS_PRIORITY: Record<string, number> = {
  APPROVED: 5,
  UNDER_REVIEW: 4,
  DRAFT: 3,
  REJECTED: 2,
  RETRACTED: 1,
}

const CLAIM_STATUS_TO_CURATION_STATUS: Record<
  RelationClaimResponse['claim_status'],
  string | null
> = {
  OPEN: 'DRAFT',
  NEEDS_MAPPING: 'UNDER_REVIEW',
  REJECTED: 'REJECTED',
  RESOLVED: null,
}

function safeTimestamp(value: string): number {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function curationPriority(status: string): number {
  return CURATION_STATUS_PRIORITY[status.toUpperCase()] ?? 0
}

function normalizeNode(node: KernelEntityResponse): GraphNode {
  return {
    id: node.id,
    entityType: node.entity_type,
    label: node.display_label ?? node.id,
    aliases: node.aliases,
    metadata: node.metadata,
    createdAt: node.created_at,
    updatedAt: node.updated_at,
    origin: 'entity',
    claimId: null,
    linkedRelationId: null,
    claimStatus: null,
    claimPolarity: null,
    claimText: null,
  }
}

function relationConfidence(relation: KernelRelationResponse): number {
  if (typeof relation.aggregate_confidence === 'number') {
    return relation.aggregate_confidence
  }
  if (typeof relation.confidence === 'number') {
    return relation.confidence
  }
  return 0
}

function claimIdFromEdgeId(edgeId: string): string | null {
  if (!edgeId.startsWith('claim:')) {
    return null
  }
  const edgePayload = edgeId.slice('claim:'.length).trim()
  const separatorIndex = edgePayload.indexOf(':')
  const claimId = separatorIndex >= 0 ? edgePayload.slice(0, separatorIndex) : edgePayload
  return claimId.length > 0 ? claimId : null
}

function edgeOriginFromId(edgeId: string): GraphEdgeOrigin {
  if (edgeId.startsWith('claim:')) {
    return 'claim'
  }
  if (edgeId.startsWith('evidence:')) {
    return 'evidence'
  }
  return 'canonical'
}

function normalizeEdge(edge: KernelRelationResponse): GraphEdge {
  const claimId = claimIdFromEdgeId(edge.id)
  return {
    id: edge.id,
    sourceId: edge.source_id,
    targetId: edge.target_id,
    relationType: edge.relation_type,
    curationStatus: edge.curation_status,
    confidence: relationConfidence(edge),
    provenanceId: edge.provenance_id,
    createdAt: edge.created_at,
    updatedAt: edge.updated_at,
    sourceCount: edge.source_count ?? 0,
    highestEvidenceTier: edge.highest_evidence_tier ?? edge.evidence_tier ?? null,
    hasConflict: false,
    supportClaimCount: 0,
    refuteClaimCount: 0,
    origin: edgeOriginFromId(edge.id),
    claimId,
    linkedRelationId: null,
    claimStatus: null,
    claimPolarity: null,
    claimText: null,
    claimRelationType: null,
    claimParticipantRole: null,
    evidenceSourceType: null,
    evidenceSourceBadge: null,
    evidenceSentenceSource: null,
    evidenceSentenceConfidence: null,
    canonicalClaimCount: 0,
    linkedClaimIds: [],
  }
}

function sortNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort((left, right) => {
    const updatedDelta = safeTimestamp(right.updatedAt) - safeTimestamp(left.updatedAt)
    if (updatedDelta !== 0) {
      return updatedDelta
    }
    return left.id.localeCompare(right.id)
  })
}

function sortEdges(edges: GraphEdge[]): GraphEdge[] {
  return [...edges].sort((left, right) => {
    const priorityDelta = curationPriority(right.curationStatus) - curationPriority(left.curationStatus)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    const updatedDelta = safeTimestamp(right.updatedAt) - safeTimestamp(left.updatedAt)
    if (updatedDelta !== 0) {
      return updatedDelta
    }
    return left.id.localeCompare(right.id)
  })
}

function uniqueSortedValues(values: Iterable<string>): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right))
}

function ensureNodeRecord(
  record: Record<string, string[]>,
  nodeId: string,
): string[] {
  if (!record[nodeId]) {
    record[nodeId] = []
  }
  return record[nodeId]
}

export function buildGraphModelFromNormalized(
  normalizedNodes: readonly GraphNode[],
  normalizedEdges: readonly GraphEdge[],
): GraphModel {
  const nodeById: Record<string, GraphNode> = {}
  for (const node of normalizedNodes) {
    const existing = nodeById[node.id]
    if (!existing || safeTimestamp(node.updatedAt) > safeTimestamp(existing.updatedAt)) {
      nodeById[node.id] = node
    }
  }

  const edgeById: Record<string, GraphEdge> = {}
  for (const edge of normalizedEdges) {
    if (!nodeById[edge.sourceId] || !nodeById[edge.targetId]) {
      continue
    }
    const existing = edgeById[edge.id]
    if (!existing || safeTimestamp(edge.updatedAt) > safeTimestamp(existing.updatedAt)) {
      edgeById[edge.id] = edge
    }
  }

  const nodes = sortNodes(Object.values(nodeById))
  const edges = sortEdges(Object.values(edgeById))
  const adjacency: Record<string, string[]> = {}
  const incidentEdges: Record<string, string[]> = {}

  for (const node of nodes) {
    adjacency[node.id] = []
    incidentEdges[node.id] = []
  }

  for (const edge of edges) {
    const sourceAdjacency = ensureNodeRecord(adjacency, edge.sourceId)
    const targetAdjacency = ensureNodeRecord(adjacency, edge.targetId)
    const sourceIncident = ensureNodeRecord(incidentEdges, edge.sourceId)
    const targetIncident = ensureNodeRecord(incidentEdges, edge.targetId)

    if (!sourceAdjacency.includes(edge.targetId)) {
      sourceAdjacency.push(edge.targetId)
    }
    if (!targetAdjacency.includes(edge.sourceId)) {
      targetAdjacency.push(edge.sourceId)
    }
    sourceIncident.push(edge.id)
    targetIncident.push(edge.id)
  }

  return {
    nodes,
    edges,
    nodeById,
    edgeById,
    adjacency,
    incidentEdges,
    relationTypes: uniqueSortedValues(edges.map((edge) => edge.relationType)),
    curationStatuses: uniqueSortedValues(edges.map((edge) => edge.curationStatus)),
    stats: {
      nodeCount: nodes.length,
      edgeCount: edges.length,
    },
  }
}

export function emptyGraphModel(): GraphModel {
  return {
    nodes: [],
    edges: [],
    nodeById: {},
    edgeById: {},
    adjacency: {},
    incidentEdges: {},
    relationTypes: [],
    curationStatuses: [],
    stats: {
      nodeCount: 0,
      edgeCount: 0,
    },
  }
}

export function buildGraphModel(source: GraphSource): GraphModel {
  return buildGraphModelFromNormalized(
    source.nodes.map((node) => normalizeNode(node)),
    source.edges.map((edge) => normalizeEdge(edge)),
  )
}

function nodeLookupKey(entityType: string, label: string): string {
  return `${entityType.trim().toUpperCase()}::${label.trim().toUpperCase()}`
}

function participantRoleToEntityType(
  role: string,
  claim: RelationClaimResponse,
): string {
  const normalizedRole = role.trim().toUpperCase()
  if (normalizedRole === 'SUBJECT') {
    return claim.source_type.trim().toUpperCase()
  }
  if (normalizedRole === 'OBJECT' || normalizedRole === 'OUTCOME') {
    return claim.target_type.trim().toUpperCase()
  }
  return normalizedRole
}

function participantFallbackLabel(
  role: string,
  claim: RelationClaimResponse,
): string {
  const normalizedRole = role.trim().toUpperCase()
  if (normalizedRole === 'SUBJECT') {
    return claim.source_label?.trim() || claim.source_type
  }
  if (normalizedRole === 'OBJECT' || normalizedRole === 'OUTCOME') {
    return claim.target_label?.trim() || claim.target_type
  }
  return normalizedRole
}

function sortedClaimParticipants(
  participants: readonly ClaimParticipantResponse[],
): ClaimParticipantResponse[] {
  return [...participants].sort((left, right) => {
    const leftPosition = left.position ?? Number.MAX_SAFE_INTEGER
    const rightPosition = right.position ?? Number.MAX_SAFE_INTEGER
    if (leftPosition !== rightPosition) {
      return leftPosition - rightPosition
    }
    return left.id.localeCompare(right.id)
  })
}

type EvidenceSourceKind = 'paper' | 'dataset'

function asObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function metadataString(
  metadata: Record<string, unknown> | null,
  keys: readonly string[],
): string | null {
  if (!metadata) {
    return null
  }
  for (const key of keys) {
    const raw = metadata[key]
    if (typeof raw === 'string') {
      const value = raw.trim()
      if (value.length > 0) {
        return value
      }
    }
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return String(raw)
    }
  }
  return null
}

interface EvidenceSourceSummary {
  kind: EvidenceSourceKind
  label: string
  badge: string
  articleUrl: string | null
}

function normalizeHttpUrl(value: string): string | null {
  const normalized = value.trim()
  if (normalized.length === 0) {
    return null
  }
  if (!/^https?:\/\//i.test(normalized)) {
    return null
  }
  try {
    const parsed = new URL(normalized)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null
    }
    return parsed.toString()
  } catch {
    return null
  }
}

function normalizePmid(value: string | null): string | null {
  if (!value) {
    return null
  }
  const normalized = value.trim()
  if (normalized.length === 0) {
    return null
  }

  try {
    const parsed = new URL(normalized)
    const host = parsed.hostname.toLowerCase()
    if (host.includes('pubmed.ncbi.nlm.nih.gov')) {
      const pathSegments = parsed.pathname.split('/').filter((segment) => segment.trim().length > 0)
      if (pathSegments.length > 0) {
        const candidate = pathSegments[0] ?? ''
        const digits = candidate.replace(/\D/g, '')
        if (digits.length > 0) {
          return digits
        }
      }
    }
  } catch {
    // Non-URL values are handled below.
  }

  const withoutPrefix = normalized.replace(/^PMID\s*:?\s*/i, '')
  const digits = withoutPrefix.replace(/\D/g, '')
  return digits.length > 0 ? digits : null
}

function normalizeDoi(value: string | null): string | null {
  if (!value) {
    return null
  }
  const normalized = value.trim()
  if (normalized.length === 0) {
    return null
  }

  if (/^https?:\/\//i.test(normalized)) {
    try {
      const parsed = new URL(normalized)
      const host = parsed.hostname.toLowerCase()
      if (host.includes('doi.org')) {
        const doiPath = parsed.pathname.replace(/^\/+/, '').trim()
        return doiPath.length > 0 ? doiPath : null
      }
    } catch {
      return null
    }
  }

  const withoutPrefix = normalized.replace(/^doi\s*:?\s*/i, '')
  return withoutPrefix.length > 0 ? withoutPrefix : null
}

function pubmedUrlFromPmid(pmid: string): string {
  return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
}

function doiUrlFromDoi(doi: string): string {
  return `https://doi.org/${doi}`
}

function resolveEvidenceArticleUrlFromPaperLinks(
  rawPaperLinks: unknown,
): string | null {
  if (!Array.isArray(rawPaperLinks)) {
    return null
  }
  for (const link of rawPaperLinks) {
    const linkObject = asObject(link)
    if (!linkObject) {
      continue
    }
    const rawUrl = metadataString(linkObject, ['url'])
    if (!rawUrl) {
      continue
    }
    const normalized = normalizeHttpUrl(rawUrl)
    if (normalized) {
      return normalized
    }
  }
  return null
}

export function resolveEvidenceArticleUrlFromMetadata(
  metadata: JSONObject,
): string | null {
  const metadataRecord = asObject(metadata)
  const paperLinkUrl = resolveEvidenceArticleUrlFromPaperLinks(
    metadataRecord?.paper_links,
  )
  if (paperLinkUrl) {
    return paperLinkUrl
  }

  const directUrl = metadataString(metadataRecord, [
    'source_url',
    'url',
    'article_url',
    'paper_url',
    'full_text_url',
    'pubmed_url',
    'publication_url',
  ])
  const normalizedDirectUrl = directUrl ? normalizeHttpUrl(directUrl) : null
  if (normalizedDirectUrl) {
    return normalizedDirectUrl
  }

  const pmid = normalizePmid(
    metadataString(metadataRecord, ['pmid', 'pubmed_id', 'publication_id', 'external_id']),
  )
  if (pmid) {
    return pubmedUrlFromPmid(pmid)
  }

  const doi = normalizeDoi(
    metadataString(metadataRecord, ['doi', 'doi_id', 'doi_url']),
  )
  if (doi) {
    return doiUrlFromDoi(doi)
  }

  return null
}

function resolveEvidenceArticleUrl(row: ClaimEvidenceResponse): string | null {
  const fromRowPaperLinks = resolveEvidenceArticleUrlFromPaperLinks(
    row.paper_links,
  )
  if (fromRowPaperLinks) {
    return fromRowPaperLinks
  }
  return resolveEvidenceArticleUrlFromMetadata(row.metadata)
}

function summarizeEvidenceSource(row: ClaimEvidenceResponse): EvidenceSourceSummary {
  const metadata = asObject(row.metadata)
  const datasetId = metadataString(metadata, [
    'dataset_id',
    'dataset_accession',
    'dataset',
    'accession',
    'geo_accession',
    'gse_id',
    'dbgap_id',
  ])
  const datasetName = metadataString(metadata, ['dataset_name', 'dataset_title'])
  if (datasetId || datasetName) {
    const label = datasetName ?? `Dataset ${datasetId ?? row.id.slice(0, 8)}`
    const badgeValue = datasetId ?? datasetName ?? row.id.slice(0, 8)
    return {
      kind: 'dataset',
      label,
      badge: `Dataset: ${badgeValue}`,
      articleUrl: null,
    }
  }

  const pmid = normalizePmid(
    metadataString(metadata, ['pmid', 'pubmed_id', 'publication_id', 'external_id']),
  )
  const articleUrl = resolveEvidenceArticleUrl(row)
  if (pmid) {
    return {
      kind: 'paper',
      label: `PMID ${pmid}`,
      badge: `PMID: ${pmid}`,
      articleUrl,
    }
  }

  const sourceDocumentId = row.source_document_id?.trim()
  if (sourceDocumentId) {
    const compact = sourceDocumentId.slice(0, 8)
    return {
      kind: 'paper',
      label: `Paper ${compact}`,
      badge: `Source doc: ${compact}`,
      articleUrl,
    }
  }

  return {
    kind: 'paper',
    label: `Evidence ${row.id.slice(0, 8)}`,
    badge: `Evidence: ${row.id.slice(0, 8)}`,
    articleUrl,
  }
}

function graphNodesToKernelNodes(nodes: GraphNode[]): KernelEntityResponse[] {
  return nodes.map((node) => ({
    id: node.id,
    research_space_id: '',
    entity_type: node.entityType,
    display_label: node.label,
    aliases: node.aliases,
    metadata: node.metadata,
    created_at: node.createdAt,
    updated_at: node.updatedAt,
  }))
}

function graphEdgesToKernelEdges(edges: GraphEdge[]): KernelRelationResponse[] {
  return edges.map((edge) => ({
    id: edge.id,
    research_space_id: '',
    source_id: edge.sourceId,
    relation_type: edge.relationType,
    target_id: edge.targetId,
    curation_status: edge.curationStatus,
    aggregate_confidence: edge.confidence,
    source_count: edge.sourceCount,
    highest_evidence_tier: edge.highestEvidenceTier,
    confidence: edge.confidence,
    evidence_summary: null,
    evidence_tier: edge.highestEvidenceTier,
    provenance_id: edge.provenanceId,
    reviewed_by: null,
    reviewed_at: null,
    created_at: edge.createdAt,
    updated_at: edge.updatedAt,
  }))
}

export function annotateGraphModelWithConflicts(
  base: GraphModel,
  conflicts: ReadonlyArray<RelationConflictResponse>,
): GraphModel {
  if (conflicts.length === 0 || base.edges.length === 0) {
    return base
  }
  const conflictByRelationId = new Map<
    string,
    { supportCount: number; refuteCount: number }
  >()
  for (const conflict of conflicts) {
    conflictByRelationId.set(conflict.relation_id, {
      supportCount: conflict.support_count,
      refuteCount: conflict.refute_count,
    })
  }
  const edges = base.edges.map((edge) => {
    const conflict = conflictByRelationId.get(edge.id)
    if (!conflict) {
      return edge
    }
    return {
      ...edge,
      hasConflict: true,
      supportClaimCount: conflict.supportCount,
      refuteClaimCount: conflict.refuteCount,
    }
  })
  const edgeById: Record<string, GraphEdge> = {}
  for (const edge of edges) {
    edgeById[edge.id] = edge
  }
  return {
    ...base,
    edges,
    edgeById,
  }
}

export function annotateGraphModelWithRelationClaimContext(
  base: GraphModel,
  claims: ReadonlyArray<RelationClaimResponse>,
): GraphModel {
  if (base.edges.length === 0 || claims.length === 0) {
    return base
  }

  const claimById = new Map<string, RelationClaimResponse>()
  for (const claim of claims) {
    claimById.set(claim.id, claim)
  }

  let changed = false
  const nodes = base.nodes.map((node) => {
    if (!node.id.startsWith('claim-node:')) {
      return node
    }
    const claimId = node.id.slice('claim-node:'.length).trim()
    if (claimId.length === 0) {
      return node
    }
    const claim = claimById.get(claimId)
    if (!claim) {
      if (node.origin !== 'claim') {
        changed = true
        return {
          ...node,
          origin: 'claim' as const,
          claimId,
        }
      }
      return node
    }
    changed = true
    return {
      ...node,
      origin: 'claim' as const,
      claimId: claim.id,
      linkedRelationId: claim.linked_relation_id ?? null,
      claimStatus: claim.claim_status,
      claimPolarity: claim.polarity,
      claimText: claim.claim_text ?? null,
    }
  })

  const edges = base.edges.map((edge) => {
    const claimId = claimIdFromEdgeId(edge.id)
    if (!claimId) {
      return edge
    }
    const claim = claimById.get(claimId)
    if (!claim) {
      if (edge.origin !== 'claim') {
        changed = true
        return {
          ...edge,
          origin: 'claim' as const,
          claimId,
        }
      }
      return edge
    }
    changed = true
    return {
      ...edge,
      origin: 'claim' as const,
      claimId: claim.id,
      linkedRelationId: claim.linked_relation_id ?? null,
      claimStatus: claim.claim_status,
      claimPolarity: claim.polarity,
      claimText: claim.claim_text ?? null,
      claimRelationType: claim.relation_type,
      claimParticipantRole: edge.relationType,
    }
  })

  if (!changed) {
    return base
  }

  const edgeById: Record<string, GraphEdge> = {}
  for (const edge of edges) {
    edgeById[edge.id] = edge
  }
  const nodeById: Record<string, GraphNode> = {}
  for (const node of nodes) {
    nodeById[node.id] = node
  }

  return {
    ...base,
    nodes,
    nodeById,
    edges,
    edgeById,
  }
}

export function annotateGraphModelWithCanonicalClaimCounts(
  base: GraphModel,
  claims: ReadonlyArray<RelationClaimResponse>,
): GraphModel {
  if (base.edges.length === 0 || claims.length === 0) {
    return base
  }

  const claimIdsByRelationId = new Map<string, string[]>()
  for (const claim of claims) {
    const linkedRelationId = claim.linked_relation_id?.trim()
    if (!linkedRelationId) {
      continue
    }
    const relationClaimIds = claimIdsByRelationId.get(linkedRelationId) ?? []
    relationClaimIds.push(claim.id)
    claimIdsByRelationId.set(linkedRelationId, relationClaimIds)
  }

  if (claimIdsByRelationId.size === 0) {
    return base
  }

  let changed = false
  const edges = base.edges.map((edge) => {
    if (edge.origin !== 'canonical') {
      return edge
    }
    const linkedClaimIds = claimIdsByRelationId.get(edge.id)
    if (!linkedClaimIds || linkedClaimIds.length === 0) {
      return edge
    }
    changed = true
    return {
      ...edge,
      canonicalClaimCount: linkedClaimIds.length,
      linkedClaimIds,
    }
  })

  if (!changed) {
    return base
  }

  const edgeById: Record<string, GraphEdge> = {}
  for (const edge of edges) {
    edgeById[edge.id] = edge
  }

  return {
    ...base,
    edges,
    edgeById,
  }
}

export function mergeGraphModelWithRelationClaims(
  base: GraphModel,
  claims: ReadonlyArray<RelationClaimResponse>,
  claimParticipantsByClaimId: Readonly<Record<string, readonly ClaimParticipantResponse[]>> = {},
): GraphModel {
  if (claims.length === 0) {
    return base
  }

  const nodes = graphNodesToKernelNodes(base.nodes)
  const edges = graphEdgesToKernelEdges(base.edges)
  const knownNodeIds = new Set<string>(nodes.map((node) => node.id))
  const nodeIdByTypeAndLabel = new Map<string, string>()

  for (const node of base.nodes) {
    const key = nodeLookupKey(node.entityType, node.label)
    if (!nodeIdByTypeAndLabel.has(key)) {
      nodeIdByTypeAndLabel.set(key, node.id)
    }
  }

  for (const claim of claims) {
    const mappedStatus = CLAIM_STATUS_TO_CURATION_STATUS[claim.claim_status]
    if (mappedStatus === null) {
      continue
    }

    const sourceLabel = claim.source_label?.trim() || claim.source_type
    const targetLabel = claim.target_label?.trim() || claim.target_type
    const sourceType = claim.source_type.trim().toUpperCase()
    const targetType = claim.target_type.trim().toUpperCase()

    const sourceLookupKey = nodeLookupKey(sourceType, sourceLabel)
    const targetLookupKey = nodeLookupKey(targetType, targetLabel)

    let sourceNodeId = nodeIdByTypeAndLabel.get(sourceLookupKey)
    if (!sourceNodeId) {
      sourceNodeId = `claim:${claim.id}:source`
      nodeIdByTypeAndLabel.set(sourceLookupKey, sourceNodeId)
      if (!knownNodeIds.has(sourceNodeId)) {
        nodes.push({
          id: sourceNodeId,
          research_space_id: claim.research_space_id,
          entity_type: sourceType,
          display_label: sourceLabel,
          aliases: [],
          metadata: {},
          created_at: claim.created_at,
          updated_at: claim.updated_at,
        })
        knownNodeIds.add(sourceNodeId)
      }
    }

    let targetNodeId = nodeIdByTypeAndLabel.get(targetLookupKey)
    if (!targetNodeId) {
      targetNodeId = `claim:${claim.id}:target`
      nodeIdByTypeAndLabel.set(targetLookupKey, targetNodeId)
      if (!knownNodeIds.has(targetNodeId)) {
        nodes.push({
          id: targetNodeId,
          research_space_id: claim.research_space_id,
          entity_type: targetType,
          display_label: targetLabel,
          aliases: [],
          metadata: {},
          created_at: claim.created_at,
          updated_at: claim.updated_at,
        })
        knownNodeIds.add(targetNodeId)
      }
    }

    const claimNodeId = `claim-node:${claim.id}`
    if (!knownNodeIds.has(claimNodeId)) {
      nodes.push({
        id: claimNodeId,
        research_space_id: claim.research_space_id,
        entity_type: 'CLAIM',
        display_label: 'Claim',
        aliases: [],
        metadata: {
          claim_id: claim.id,
          claim_status: claim.claim_status,
          claim_polarity: claim.polarity,
          linked_relation_id: claim.linked_relation_id,
        },
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })
      knownNodeIds.add(claimNodeId)
    }

    const participants = sortedClaimParticipants(
      claimParticipantsByClaimId[claim.id] ?? [],
    )
    if (participants.length === 0) {
      edges.push({
        id: `claim:${claim.id}:subject`,
        research_space_id: claim.research_space_id,
        source_id: sourceNodeId,
        relation_type: 'SUBJECT',
        target_id: claimNodeId,
        curation_status: mappedStatus,
        aggregate_confidence: claim.confidence,
        source_count: 1,
        highest_evidence_tier: null,
        confidence: claim.confidence,
        evidence_summary: claim.validation_reason,
        evidence_tier: null,
        provenance_id: null,
        reviewed_by: claim.triaged_by,
        reviewed_at: claim.triaged_at,
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })

      edges.push({
        id: `claim:${claim.id}:object`,
        research_space_id: claim.research_space_id,
        source_id: targetNodeId,
        relation_type: 'OBJECT',
        target_id: claimNodeId,
        curation_status: mappedStatus,
        aggregate_confidence: claim.confidence,
        source_count: 1,
        highest_evidence_tier: null,
        confidence: claim.confidence,
        evidence_summary: claim.validation_reason,
        evidence_tier: null,
        provenance_id: null,
        reviewed_by: claim.triaged_by,
        reviewed_at: claim.triaged_at,
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })
      continue
    }

    for (const participant of participants) {
      const role = participant.role.trim().toUpperCase()
      const entityType = participantRoleToEntityType(role, claim)
      const fallbackLabel = participantFallbackLabel(role, claim)
      const label = participant.label?.trim() || fallbackLabel
      const lookupKey = nodeLookupKey(entityType, label)

      let participantNodeId = participant.entity_id?.trim() || null
      if (!participantNodeId) {
        participantNodeId = nodeIdByTypeAndLabel.get(lookupKey) ?? null
      }
      if (!participantNodeId) {
        participantNodeId = `claim:${claim.id}:participant:${participant.id}`
      }

      if (!knownNodeIds.has(participantNodeId)) {
        nodes.push({
          id: participantNodeId,
          research_space_id: claim.research_space_id,
          entity_type: entityType,
          display_label: label,
          aliases: [],
          metadata: {},
          created_at: claim.created_at,
          updated_at: claim.updated_at,
        })
        knownNodeIds.add(participantNodeId)
      }
      if (!nodeIdByTypeAndLabel.has(lookupKey)) {
        nodeIdByTypeAndLabel.set(lookupKey, participantNodeId)
      }

      edges.push({
        id: `claim:${claim.id}:participant:${participant.id}`,
        research_space_id: claim.research_space_id,
        source_id: participantNodeId,
        relation_type: role,
        target_id: claimNodeId,
        curation_status: mappedStatus,
        aggregate_confidence: claim.confidence,
        source_count: 1,
        highest_evidence_tier: null,
        confidence: claim.confidence,
        evidence_summary: claim.validation_reason,
        evidence_tier: null,
        provenance_id: null,
        reviewed_by: claim.triaged_by,
        reviewed_at: claim.triaged_at,
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })
    }
  }

  return annotateGraphModelWithCanonicalClaimCounts(
    annotateGraphModelWithRelationClaimContext(
      buildGraphModel({ nodes, edges }),
      claims,
    ),
    claims,
  )
}

function claimCurationStatusIndex(base: GraphModel): Map<string, string> {
  const byClaimId = new Map<string, string>()
  for (const edge of base.edges) {
    if (edge.origin !== 'claim' || !edge.claimId) {
      continue
    }
    const existing = byClaimId.get(edge.claimId)
    if (!existing || curationPriority(edge.curationStatus) > curationPriority(existing)) {
      byClaimId.set(edge.claimId, edge.curationStatus)
    }
  }
  return byClaimId
}

interface ClaimContextSummary {
  linkedRelationId: string | null
  claimStatus: RelationClaimResponse['claim_status'] | null
  claimPolarity: RelationClaimResponse['polarity'] | null
  claimText: string | null
  claimRelationType: string | null
}

function claimContextIndex(base: GraphModel): Map<string, ClaimContextSummary> {
  const byClaimId = new Map<string, ClaimContextSummary>()
  for (const node of base.nodes) {
    if (node.origin !== 'claim' || !node.claimId) {
      continue
    }
    byClaimId.set(node.claimId, {
      linkedRelationId: node.linkedRelationId,
      claimStatus: node.claimStatus,
      claimPolarity: node.claimPolarity,
      claimText: node.claimText,
      claimRelationType: null,
    })
  }
  for (const edge of base.edges) {
    if (edge.origin !== 'claim' || !edge.claimId) {
      continue
    }
    const existing = byClaimId.get(edge.claimId)
    byClaimId.set(edge.claimId, {
      linkedRelationId: existing?.linkedRelationId ?? edge.linkedRelationId,
      claimStatus: existing?.claimStatus ?? edge.claimStatus,
      claimPolarity: existing?.claimPolarity ?? edge.claimPolarity,
      claimText: existing?.claimText ?? edge.claimText,
      claimRelationType: existing?.claimRelationType ?? edge.claimRelationType,
    })
  }
  return byClaimId
}

export function augmentGraphModelWithClaimEvidence(
  base: GraphModel,
  claimEvidenceByClaimId: Readonly<Record<string, readonly ClaimEvidenceResponse[]>>,
): GraphModel {
  if (Object.keys(claimEvidenceByClaimId).length === 0) {
    return base
  }

  const claimStatusByClaimId = claimCurationStatusIndex(base)
  const claimContextById = claimContextIndex(base)
  const nodes = [...base.nodes]
  const edges = [...base.edges]
  const knownNodeIds = new Set<string>(nodes.map((node) => node.id))
  const knownEdgeIds = new Set<string>(edges.map((edge) => edge.id))

  for (const [claimId, evidenceRows] of Object.entries(claimEvidenceByClaimId)) {
    if (evidenceRows.length === 0) {
      continue
    }
    const claimNodeId = `claim-node:${claimId}`
    if (!knownNodeIds.has(claimNodeId)) {
      continue
    }
    const claimContext = claimContextById.get(claimId)
    const curationStatus = claimStatusByClaimId.get(claimId) ?? 'UNDER_REVIEW'

    for (const row of evidenceRows) {
      const sourceSummary = summarizeEvidenceSource(row)
      const evidenceNodeId = `evidence-node:${row.id}`
      if (!knownNodeIds.has(evidenceNodeId)) {
        const serializedPaperLinks: JSONObject[] = Array.isArray(row.paper_links)
          ? row.paper_links.map((paperLink) => ({
            label: paperLink.label,
            url: paperLink.url,
            source: paperLink.source,
          }))
          : []
        const evidenceMetadata: JSONObject = {
          ...row.metadata,
          evidence_id: row.id,
          claim_id: claimId,
          source_document_id: row.source_document_id,
          paper_links: serializedPaperLinks,
          sentence_source: row.sentence_source,
          sentence_confidence: row.sentence_confidence,
          sentence: row.sentence,
        }
        if (sourceSummary.articleUrl && !('source_url' in evidenceMetadata)) {
          evidenceMetadata.source_url = sourceSummary.articleUrl
        }
        nodes.push({
          id: evidenceNodeId,
          entityType: sourceSummary.kind === 'dataset' ? 'DATASET' : 'PAPER',
          label: sourceSummary.label,
          aliases: [],
          metadata: evidenceMetadata,
          createdAt: row.created_at,
          updatedAt: row.created_at,
          origin: 'evidence',
          claimId,
          linkedRelationId: claimContext?.linkedRelationId ?? null,
          claimStatus: claimContext?.claimStatus ?? null,
          claimPolarity: claimContext?.claimPolarity ?? null,
          claimText: claimContext?.claimText ?? null,
        })
        knownNodeIds.add(evidenceNodeId)
      }

      const evidenceEdgeId = `evidence:${claimId}:${row.id}`
      if (knownEdgeIds.has(evidenceEdgeId)) {
        continue
      }
      const relationType = sourceSummary.kind === 'dataset' ? 'DERIVED_FROM' : 'SUPPORTED_BY'
      edges.push({
        id: evidenceEdgeId,
        sourceId: claimNodeId,
        targetId: evidenceNodeId,
        relationType,
        curationStatus,
        confidence: row.confidence,
        provenanceId: row.source_document_id,
        createdAt: row.created_at,
        updatedAt: row.created_at,
        sourceCount: 1,
        highestEvidenceTier: row.sentence_confidence?.toUpperCase() ?? null,
        hasConflict: false,
        supportClaimCount: 0,
        refuteClaimCount: 0,
        origin: 'evidence',
        claimId,
        linkedRelationId: claimContext?.linkedRelationId ?? null,
        claimStatus: claimContext?.claimStatus ?? null,
        claimPolarity: claimContext?.claimPolarity ?? null,
        claimText: claimContext?.claimText ?? null,
        claimRelationType: claimContext?.claimRelationType ?? null,
        claimParticipantRole: null,
        evidenceSourceType: sourceSummary.kind,
        evidenceSourceBadge: sourceSummary.badge,
        evidenceSentenceSource: row.sentence_source,
        evidenceSentenceConfidence: row.sentence_confidence,
        canonicalClaimCount: 0,
        linkedClaimIds: [],
      })
      knownEdgeIds.add(evidenceEdgeId)
    }
  }

  if (nodes.length === base.nodes.length && edges.length === base.edges.length) {
    return base
  }
  return buildGraphModelFromNormalized(nodes, edges)
}

function mergeNodeMaps(
  left: Record<string, GraphNode>,
  right: Record<string, GraphNode>,
): Record<string, GraphNode> {
  const merged: Record<string, GraphNode> = { ...left }
  for (const node of Object.values(right)) {
    const existing = merged[node.id]
    if (!existing || safeTimestamp(node.updatedAt) > safeTimestamp(existing.updatedAt)) {
      merged[node.id] = node
    }
  }
  return merged
}

function mergeEdgeMaps(
  left: Record<string, GraphEdge>,
  right: Record<string, GraphEdge>,
): Record<string, GraphEdge> {
  const merged: Record<string, GraphEdge> = { ...left }
  for (const edge of Object.values(right)) {
    const existing = merged[edge.id]
    if (!existing || safeTimestamp(edge.updatedAt) > safeTimestamp(existing.updatedAt)) {
      merged[edge.id] = edge
    }
  }
  return merged
}

export function mergeGraphModels(base: GraphModel, incoming: GraphModel): GraphModel {
  const nodes = mergeNodeMaps(base.nodeById, incoming.nodeById)
  const edges = mergeEdgeMaps(base.edgeById, incoming.edgeById)
  return buildGraphModelFromNormalized(Object.values(nodes), Object.values(edges))
}

export function filterGraphModel(
  model: GraphModel,
  relationTypes: ReadonlySet<string>,
  curationStatuses: ReadonlySet<string>,
): GraphModel {
  const hasRelationTypeFilter = relationTypes.size > 0
  const hasStatusFilter = curationStatuses.size > 0

  const filteredEdges = model.edges.filter((edge) => {
    if (hasRelationTypeFilter && !relationTypes.has(edge.relationType)) {
      return false
    }
    if (hasStatusFilter && !curationStatuses.has(edge.curationStatus)) {
      return false
    }
    return true
  })

  if (filteredEdges.length === 0) {
    return buildGraphModelFromNormalized(model.nodes, [])
  }

  const referencedNodeIds = new Set<string>()
  for (const edge of filteredEdges) {
    referencedNodeIds.add(edge.sourceId)
    referencedNodeIds.add(edge.targetId)
  }

  const filteredNodes = model.nodes.filter((node) => referencedNodeIds.has(node.id))
  return buildGraphModelFromNormalized(filteredNodes, filteredEdges)
}

export function projectGraphByDisplayMode(
  model: GraphModel,
  mode: GraphDisplayMode,
): GraphModel {
  if (mode === 'EVIDENCE') {
    return model
  }

  const visibleEdges = model.edges.filter((edge) => {
    if (mode === 'RELATIONS_ONLY') {
      return edge.origin === 'canonical'
    }
    return edge.origin === 'canonical' || edge.origin === 'claim'
  })

  if (visibleEdges.length === 0) {
    return buildGraphModelFromNormalized([], [])
  }

  const referencedNodeIds = new Set<string>()
  for (const edge of visibleEdges) {
    referencedNodeIds.add(edge.sourceId)
    referencedNodeIds.add(edge.targetId)
  }

  const visibleNodes = model.nodes.filter((node) => referencedNodeIds.has(node.id))
  return buildGraphModelFromNormalized(visibleNodes, visibleEdges)
}

export function pruneGraphModelForRender(
  model: GraphModel,
  maxNodes: number,
  maxEdges: number,
  prioritizedNodeIds: readonly string[] = [],
): GraphPruneResult {
  const preCapNodeCount = model.stats.nodeCount
  const preCapEdgeCount = model.stats.edgeCount
  if (preCapNodeCount <= maxNodes && preCapEdgeCount <= maxEdges) {
    return {
      model,
      preCapNodeCount,
      preCapEdgeCount,
      truncatedNodes: false,
      truncatedEdges: false,
    }
  }

  let prunedEdges = sortEdges(model.edges).slice(0, Math.max(maxEdges, 0))
  const referencedNodeIds = new Set<string>()
  for (const edge of prunedEdges) {
    referencedNodeIds.add(edge.sourceId)
    referencedNodeIds.add(edge.targetId)
  }

  if (prunedEdges.length === 0) {
    const prunedNodes = sortNodes(model.nodes).slice(0, Math.max(maxNodes, 0))
    return {
      model: buildGraphModelFromNormalized(prunedNodes, []),
      preCapNodeCount,
      preCapEdgeCount,
      truncatedNodes: preCapNodeCount > prunedNodes.length,
      truncatedEdges: preCapEdgeCount > 0,
    }
  }

  let allowedNodeIds = [...referencedNodeIds]
  if (allowedNodeIds.length > maxNodes) {
    const priorityIds: string[] = []
    const seenPriority = new Set<string>()
    for (const prioritizedNodeId of prioritizedNodeIds) {
      if (!referencedNodeIds.has(prioritizedNodeId) || seenPriority.has(prioritizedNodeId)) {
        continue
      }
      seenPriority.add(prioritizedNodeId)
      priorityIds.push(prioritizedNodeId)
    }

    const remainingNodes = sortNodes(
      model.nodes.filter((node) => referencedNodeIds.has(node.id) && !seenPriority.has(node.id)),
    )
    allowedNodeIds = [
      ...priorityIds,
      ...remainingNodes.map((node) => node.id),
    ].slice(0, Math.max(maxNodes, 0))
    const allowedNodeSet = new Set<string>(allowedNodeIds)
    prunedEdges = prunedEdges.filter(
      (edge) => allowedNodeSet.has(edge.sourceId) && allowedNodeSet.has(edge.targetId),
    )
  }

  const allowedNodeSet = new Set<string>(allowedNodeIds)
  const prunedNodes = sortNodes(
    model.nodes.filter((node) => allowedNodeSet.has(node.id)),
  )

  const prunedModel = buildGraphModelFromNormalized(prunedNodes, prunedEdges)

  return {
    model: prunedModel,
    preCapNodeCount,
    preCapEdgeCount,
    truncatedNodes: preCapNodeCount > prunedModel.stats.nodeCount,
    truncatedEdges: preCapEdgeCount > prunedModel.stats.edgeCount,
  }
}

export function getNeighborhood(model: GraphModel, nodeId: string): GraphNeighborhood {
  const node = model.nodeById[nodeId]
  if (!node) {
    return {
      nodeIds: new Set(),
      edgeIds: new Set(),
    }
  }

  const nodeIds = new Set<string>([node.id])
  const edgeIds = new Set<string>()
  for (const edgeId of model.incidentEdges[node.id] ?? []) {
    const edge = model.edgeById[edgeId]
    if (!edge) {
      continue
    }
    edgeIds.add(edge.id)
    nodeIds.add(edge.sourceId)
    nodeIds.add(edge.targetId)
  }

  return {
    nodeIds,
    edgeIds,
  }
}
