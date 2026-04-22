import {
  buildGraphModelFromNormalized,
  resolveEvidenceArticleUrlFromMetadata,
  type GraphEdge,
  type GraphModel,
  type GraphNode,
} from '@/lib/graph/model'
import type {
  KernelGraphDocumentEdge,
  KernelGraphDocumentNode,
  KernelGraphDocumentResponse,
  RelationClaimResponse,
} from '@/types/kernel'
import type { JSONObject, JSONValue } from '@/types/generated'

interface ClaimContext {
  claimId: string
  claimStatus: RelationClaimResponse['claim_status'] | null
  claimPolarity: RelationClaimResponse['polarity'] | null
  claimText: string | null
  claimRelationType: string | null
  linkedRelationId: string | null
}

interface EvidenceSourceSummary {
  kind: 'paper' | 'dataset'
  badge: string | null
}

function asObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function normalizedOptionalText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
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
    const normalizedText = normalizedOptionalText(raw)
    if (normalizedText) {
      return normalizedText
    }
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return String(raw)
    }
  }
  return null
}

function metadataNumber(
  metadata: Record<string, unknown> | null,
  keys: readonly string[],
): number | null {
  if (!metadata) {
    return null
  }
  for (const key of keys) {
    const raw = metadata[key]
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return raw
    }
  }
  return null
}

function metadataBoolean(
  metadata: Record<string, unknown> | null,
  keys: readonly string[],
): boolean | null {
  if (!metadata) {
    return null
  }
  for (const key of keys) {
    const raw = metadata[key]
    if (typeof raw === 'boolean') {
      return raw
    }
  }
  return null
}

function metadataStringArray(
  metadata: Record<string, unknown> | null,
  key: string,
): string[] {
  const raw = metadata?.[key]
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
}

function flattenEvidenceMetadata(metadata: JSONObject): JSONObject {
  const flattened: JSONObject = { ...metadata }
  const metadataRecord = asObject(metadata)
  const rawMetadata = asObject(metadataRecord?.raw_metadata)
  if (!rawMetadata) {
    return flattened
  }
  for (const [key, value] of Object.entries(rawMetadata)) {
    flattened[key] = value as JSONValue
  }
  return flattened
}

function normalizeClaimStatus(
  value: string | null,
): RelationClaimResponse['claim_status'] | null {
  switch (value) {
    case 'OPEN':
    case 'NEEDS_MAPPING':
    case 'REJECTED':
    case 'RESOLVED':
      return value
    default:
      return null
  }
}

function normalizeClaimPolarity(
  value: string | null,
): RelationClaimResponse['polarity'] | null {
  switch (value) {
    case 'SUPPORT':
    case 'REFUTE':
    case 'UNCERTAIN':
    case 'HYPOTHESIS':
      return value
    default:
      return null
  }
}

function claimCurationStatus(
  claimStatus: RelationClaimResponse['claim_status'] | null,
): string {
  switch (claimStatus) {
    case 'OPEN':
      return 'DRAFT'
    case 'NEEDS_MAPPING':
      return 'UNDER_REVIEW'
    case 'REJECTED':
      return 'REJECTED'
    case 'RESOLVED':
      return 'APPROVED'
    default:
      return 'UNDER_REVIEW'
  }
}

function evidenceNodeEntityType(node: KernelGraphDocumentNode, metadata: JSONObject): string {
  const typeLabel = node.type_label.trim().toUpperCase()
  if (typeLabel.includes('DATASET')) {
    return 'DATASET'
  }
  if (typeLabel.includes('PAPER')) {
    return 'PAPER'
  }

  const metadataRecord = asObject(metadata)
  if (metadataString(metadataRecord, ['dataset_id', 'dataset_accession', 'dataset_name', 'gse_id'])) {
    return 'DATASET'
  }
  if (
    metadataString(metadataRecord, ['pmid', 'pubmed_id', 'publication_id', 'doi', 'source_url'])
    || resolveEvidenceArticleUrlFromMetadata(metadata)
  ) {
    return 'PAPER'
  }
  return 'EVIDENCE'
}

function normalizeDocumentNode(node: KernelGraphDocumentNode): GraphNode {
  const metadata = node.kind === 'EVIDENCE' ? flattenEvidenceMetadata(node.metadata) : node.metadata
  const metadataRecord = asObject(metadata)
  const claimId = node.kind === 'CLAIM'
    ? node.resource_id
    : node.kind === 'EVIDENCE'
      ? metadataString(metadataRecord, ['claim_id'])
      : null

  return {
    id: node.id,
    entityType:
      node.kind === 'ENTITY'
        ? node.type_label
        : node.kind === 'CLAIM'
          ? 'CLAIM'
          : evidenceNodeEntityType(node, metadata),
    label: node.label,
    aliases: metadataStringArray(metadataRecord, 'aliases'),
    metadata,
    createdAt: node.created_at,
    updatedAt: node.updated_at,
    origin:
      node.kind === 'ENTITY'
        ? 'entity'
        : node.kind === 'CLAIM'
          ? 'claim'
          : 'evidence',
    claimId,
    linkedRelationId: node.canonical_relation_id,
    claimStatus: normalizeClaimStatus(node.claim_status),
    claimPolarity: normalizeClaimPolarity(node.polarity),
    claimText:
      node.kind === 'CLAIM'
        ? metadataString(metadataRecord, ['claim_text']) ?? normalizedOptionalText(node.label)
        : null,
  }
}

function claimContextIndex(nodes: readonly GraphNode[]): Map<string, ClaimContext> {
  const byClaimId = new Map<string, ClaimContext>()
  for (const node of nodes) {
    if (node.origin !== 'claim' || !node.claimId) {
      continue
    }
    const metadata = asObject(node.metadata)
    byClaimId.set(node.claimId, {
      claimId: node.claimId,
      claimStatus: node.claimStatus,
      claimPolarity: node.claimPolarity,
      claimText: node.claimText,
      claimRelationType: metadataString(metadata, ['relation_type']),
      linkedRelationId: node.linkedRelationId,
    })
  }
  return byClaimId
}

function evidenceSourceSummary(node: GraphNode): EvidenceSourceSummary {
  const metadata = asObject(node.metadata)
  const datasetId = metadataString(metadata, [
    'dataset_id',
    'dataset_accession',
    'dataset_name',
    'geo_accession',
    'gse_id',
  ])
  if (node.entityType === 'DATASET' || datasetId) {
    return {
      kind: 'dataset',
      badge: datasetId ? `Dataset: ${datasetId}` : normalizedOptionalText(node.label),
    }
  }

  const pmid = metadataString(metadata, ['pmid', 'pubmed_id', 'publication_id', 'external_id'])
  if (pmid) {
    return {
      kind: 'paper',
      badge: `PMID: ${pmid}`,
    }
  }

  const paperLinks = metadata?.paper_links
  if (Array.isArray(paperLinks)) {
    for (const link of paperLinks) {
      const label = metadataString(asObject(link), ['label'])
      if (label) {
        return {
          kind: 'paper',
          badge: label,
        }
      }
    }
  }

  const sourceDocumentId = metadataString(metadata, ['source_document_id'])
  if (sourceDocumentId) {
    return {
      kind: 'paper',
      badge: `Source doc: ${sourceDocumentId.slice(0, 8)}...`,
    }
  }

  return {
    kind: 'paper',
    badge: normalizedOptionalText(node.label),
  }
}

function normalizeDocumentEdge(
  edge: KernelGraphDocumentEdge,
  nodeById: Readonly<Record<string, GraphNode>>,
  claimContextById: ReadonlyMap<string, ClaimContext>,
): GraphEdge {
  const metadata = asObject(edge.metadata)
  const claimId = edge.claim_id
  const claimContext = claimId ? claimContextById.get(claimId) ?? null : null
  const evidenceNode = edge.kind === 'CLAIM_EVIDENCE' ? nodeById[edge.target_id] : undefined
  const evidenceSummary = evidenceNode ? evidenceSourceSummary(evidenceNode) : null
  const curationStatus =
    edge.kind === 'CANONICAL_RELATION'
      ? edge.curation_status ?? 'UNDER_REVIEW'
      : claimCurationStatus(claimContext?.claimStatus ?? null)

  return {
    id: edge.id,
    sourceId: edge.source_id,
    targetId: edge.target_id,
    relationType:
      edge.kind === 'CLAIM_EVIDENCE'
        ? evidenceSummary?.kind === 'dataset'
          ? 'DERIVED_FROM'
          : 'SUPPORTED_BY'
        : edge.type_label,
    curationStatus,
    confidence: edge.confidence ?? 0,
    provenanceId:
      edge.kind === 'CLAIM_EVIDENCE'
        ? metadataString(asObject(evidenceNode?.metadata), ['source_document_id'])
        : null,
    createdAt: edge.created_at,
    updatedAt: edge.updated_at,
    sourceCount:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataNumber(metadata, ['source_count']) ?? 0
        : 1,
    highestEvidenceTier:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataString(metadata, ['highest_evidence_tier'])
        : metadataString(asObject(evidenceNode?.metadata), ['sentence_confidence']),
    hasConflict:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataBoolean(metadata, ['has_conflict']) ?? false
        : false,
    supportClaimCount:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataNumber(metadata, ['support_claim_count']) ?? 0
        : 0,
    refuteClaimCount:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataNumber(metadata, ['refute_claim_count']) ?? 0
        : 0,
    origin:
      edge.kind === 'CANONICAL_RELATION'
        ? 'canonical'
        : edge.kind === 'CLAIM_PARTICIPANT'
          ? 'claim'
          : 'evidence',
    claimId,
    linkedRelationId: edge.kind === 'CANONICAL_RELATION' ? null : edge.canonical_relation_id,
    claimStatus: claimContext?.claimStatus ?? null,
    claimPolarity: claimContext?.claimPolarity ?? null,
    claimText: claimContext?.claimText ?? null,
    claimRelationType: claimContext?.claimRelationType ?? null,
    claimParticipantRole: edge.kind === 'CLAIM_PARTICIPANT' ? edge.type_label : null,
    evidenceSourceType: evidenceSummary?.kind ?? null,
    evidenceSourceBadge: evidenceSummary?.badge ?? null,
    evidenceSentenceSource:
      edge.kind === 'CLAIM_EVIDENCE'
        ? metadataString(asObject(evidenceNode?.metadata), ['sentence_source'])
        : null,
    evidenceSentenceConfidence:
      edge.kind === 'CLAIM_EVIDENCE'
        ? metadataString(asObject(evidenceNode?.metadata), ['sentence_confidence'])
        : null,
    canonicalClaimCount:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataStringArray(metadata, 'linked_claim_ids').length
        : 0,
    linkedClaimIds:
      edge.kind === 'CANONICAL_RELATION'
        ? metadataStringArray(metadata, 'linked_claim_ids')
        : [],
  }
}

export function buildGraphModelFromDocument(source: KernelGraphDocumentResponse): GraphModel {
  const normalizedNodes = source.nodes.map((node) => normalizeDocumentNode(node))
  const nodeById: Record<string, GraphNode> = {}
  for (const node of normalizedNodes) {
    nodeById[node.id] = node
  }
  const claimContextById = claimContextIndex(normalizedNodes)
  const normalizedEdges = source.edges.map((edge) =>
    normalizeDocumentEdge(edge, nodeById, claimContextById),
  )
  return buildGraphModelFromNormalized(normalizedNodes, normalizedEdges)
}

export function buildClaimEvidencePreviewIndex(
  model: GraphModel,
): Record<string, { state: 'ready' | 'empty'; sentence: string | null; sourceLabel: string | null }> {
  const grouped: Record<string, Array<{ edge: GraphEdge; node: GraphNode }>> = {}

  for (const edge of model.edges) {
    if (edge.origin !== 'evidence' || !edge.claimId) {
      continue
    }
    const node = model.nodeById[edge.targetId]
    if (!node || node.origin !== 'evidence') {
      continue
    }
    grouped[edge.claimId] = [...(grouped[edge.claimId] ?? []), { edge, node }]
  }

  const previews: Record<string, { state: 'ready' | 'empty'; sentence: string | null; sourceLabel: string | null }> = {}
  for (const [claimId, entries] of Object.entries(grouped)) {
    const ranked = [...entries].sort((left, right) => {
      const leftHasSentence = normalizedOptionalText(asObject(left.node.metadata)?.sentence) ? 1 : 0
      const rightHasSentence = normalizedOptionalText(asObject(right.node.metadata)?.sentence) ? 1 : 0
      if (leftHasSentence !== rightHasSentence) {
        return rightHasSentence - leftHasSentence
      }
      const confidenceDelta = right.edge.confidence - left.edge.confidence
      if (confidenceDelta !== 0) {
        return confidenceDelta
      }
      return Date.parse(right.node.updatedAt) - Date.parse(left.node.updatedAt)
    })

    const topEntry = ranked[0]
    if (!topEntry) {
      continue
    }
    const sentence = normalizedOptionalText(asObject(topEntry.node.metadata)?.sentence)
    previews[claimId] = {
      state: sentence ? 'ready' : 'empty',
      sentence,
      sourceLabel: evidenceSourceSummary(topEntry.node).badge,
    }
  }

  return previews
}
