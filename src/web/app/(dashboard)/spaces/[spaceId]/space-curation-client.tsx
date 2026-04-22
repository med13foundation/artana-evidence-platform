'use client'

import { type UIEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { ChevronDown } from 'lucide-react'

import {
  searchKernelRelationNodesAction,
  updateKernelRelationStatusAction,
  updateRelationClaimStatusAction,
  type NodeSearchOption,
} from '@/app/actions/kernel-relations'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { DashboardSection } from '@/components/ui/composition-patterns'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  KernelRelationListResponse,
  KernelRelationResponse,
  RelationConflictListResponse,
  RelationClaimListResponse,
  RelationClaimResponse,
} from '@/types/kernel'
import CurationHypothesesCard from './curation/curation-hypotheses-card'
import ClaimOverlayGraphPanel from './curation/claim-overlay-graph-panel'

interface SpaceCurationClientProps {
  spaceId: string
  activeTab: 'graph' | 'claims'
  relations: KernelRelationListResponse | null
  relationsError?: string | null
  claims: RelationClaimListResponse | null
  claimsError?: string | null
  relationConflicts: RelationConflictListResponse | null
  entityLabelsById: Record<string, string>
  canCurate: boolean
  hypothesisGenerationEnabled: boolean
  relationFilters: {
    graphMode: 'canonical' | 'claim_overlay'
    relationType: string
    curationStatus: string
    validationState: string
    sourceDocumentId: string
    certaintyBand: string
    nodeQuery: string
    nodeIds: string[]
    focusRelationId: string
    offset: number
    limit: number
  }
  claimFilters: {
    claimStatus: string
    validationState: string
    persistability: string
    polarity: string
    relationType: string
    sourceDocumentId: string
    linkedRelationId: string
    certaintyBand: string
    offset: number
    limit: number
  }
}

const ALL_VALUE = '__all__'
const NODE_SEARCH_MIN_CHARS = 2
const NODE_SEARCH_LIMIT = 40

const GRAPH_STATUSES = ['DRAFT', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RETRACTED'] as const
const CLAIM_STATUSES = ['OPEN', 'NEEDS_MAPPING', 'REJECTED', 'RESOLVED'] as const
const CLAIM_POLARITIES = ['SUPPORT', 'REFUTE', 'UNCERTAIN', 'HYPOTHESIS'] as const
const VALIDATION_STATES = [
  'ALLOWED',
  'FORBIDDEN',
  'UNDEFINED',
  'INVALID_COMPONENTS',
  'ENDPOINT_UNRESOLVED',
  'SELF_LOOP',
] as const
const PERSISTABILITY = ['PERSISTABLE', 'NON_PERSISTABLE'] as const
const CERTAINTY_BANDS = ['HIGH', 'MEDIUM', 'LOW'] as const

type CertaintyLevel = 'High' | 'Medium' | 'Low' | 'Unscored'

function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

function humanizeToken(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

function confidencePercent(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null
  }
  if (value <= 1) {
    return Math.max(0, Math.min(100, Math.round(value * 100)))
  }
  return Math.max(0, Math.min(100, Math.round(value)))
}

function confidenceCertaintyLevel(value: number | null): CertaintyLevel {
  if (value === null) return 'Unscored'
  if (value >= 80) return 'High'
  if (value >= 60) return 'Medium'
  return 'Low'
}

function certaintyBadgeVariant(level: CertaintyLevel): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (level === 'High') return 'default'
  if (level === 'Medium') return 'secondary'
  if (level === 'Low') return 'destructive'
  return 'outline'
}

function statusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'APPROVED' || status === 'RESOLVED') return 'default'
  if (status === 'REJECTED' || status === 'RETRACTED') return 'destructive'
  if (status === 'UNDER_REVIEW' || status === 'NEEDS_MAPPING') return 'secondary'
  return 'outline'
}

function polarityBadgeVariant(
  polarity: RelationClaimResponse['polarity'],
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (polarity === 'SUPPORT') return 'default'
  if (polarity === 'REFUTE') return 'destructive'
  if (polarity === 'HYPOTHESIS') return 'secondary'
  return 'outline'
}

function relationConnectorPhrase(relationType: string): string {
  const normalized = relationType.trim().toUpperCase()
  const predefined: Record<string, string> = {
    ASSOCIATED_WITH: 'is associated with',
    CAUSES: 'causes',
    RESULTS_IN: 'results in',
    PROTECTIVE_EFFECT: 'protects against',
    TREATS: 'treats',
    CONTRAINDICATED_FOR: 'is contraindicated for',
    LOSS_OF_FUNCTION_INCREASES_PHENOTYPE_SEVERITY: 'causes',
  }
  const mapped = predefined[normalized]
  if (mapped) {
    return mapped
  }
  return humanizeToken(relationType).toLowerCase()
}

function mergeNodeOptions(
  current: NodeSearchOption[],
  incoming: NodeSearchOption[],
): NodeSearchOption[] {
  const merged = [...current]
  const seenIds = new Set(current.map((option) => option.id))
  for (const option of incoming) {
    if (seenIds.has(option.id)) {
      continue
    }
    seenIds.add(option.id)
    merged.push(option)
  }
  return merged
}

function buildPaginationLabel(total: number, offset: number, limit: number): string {
  if (total <= 0) {
    return 'No records'
  }
  const start = Math.min(total, offset + 1)
  const end = Math.min(total, offset + limit)
  return `${start}-${end} of ${total}`
}

function appendIfValue(params: URLSearchParams, key: string, value: string): void {
  const trimmed = value.trim()
  if (trimmed.length > 0) {
    params.set(key, trimmed)
  }
}

export default function SpaceCurationClient({
  spaceId,
  activeTab,
  relations,
  relationsError,
  claims,
  claimsError,
  relationConflicts,
  entityLabelsById,
  canCurate,
  hypothesisGenerationEnabled,
  relationFilters,
  claimFilters,
}: SpaceCurationClientProps) {
  const router = useRouter()

  const [relationType, setRelationType] = useState(relationFilters.relationType)
  const [graphMode, setGraphMode] = useState<'canonical' | 'claim_overlay'>(
    relationFilters.graphMode,
  )
  const [curationStatus, setCurationStatus] = useState(relationFilters.curationStatus || ALL_VALUE)
  const [validationState, setValidationState] = useState(relationFilters.validationState || ALL_VALUE)
  const [sourceDocumentId, setSourceDocumentId] = useState(relationFilters.sourceDocumentId)
  const [certaintyBand, setCertaintyBand] = useState(relationFilters.certaintyBand || ALL_VALUE)
  const [nodeQuery, setNodeQuery] = useState(relationFilters.nodeQuery)
  const [selectedNodeIds, setSelectedNodeIds] = useState(relationFilters.nodeIds)
  const [focusRelationId, setFocusRelationId] = useState(relationFilters.focusRelationId)

  const [claimStatus, setClaimStatus] = useState(claimFilters.claimStatus || ALL_VALUE)
  const [claimValidationState, setClaimValidationState] = useState(
    claimFilters.validationState || ALL_VALUE,
  )
  const [claimPersistability, setClaimPersistability] = useState(
    claimFilters.persistability || ALL_VALUE,
  )
  const [claimPolarity, setClaimPolarity] = useState(claimFilters.polarity || ALL_VALUE)
  const [claimRelationType, setClaimRelationType] = useState(claimFilters.relationType)
  const [claimSourceDocumentId, setClaimSourceDocumentId] = useState(claimFilters.sourceDocumentId)
  const [claimLinkedRelationId, setClaimLinkedRelationId] = useState(claimFilters.linkedRelationId)
  const [claimCertaintyBand, setClaimCertaintyBand] = useState(claimFilters.certaintyBand || ALL_VALUE)

  const [nodeSearchInput, setNodeSearchInput] = useState('')
  const [nodeSearchOptions, setNodeSearchOptions] = useState<NodeSearchOption[]>([])
  const [nodeSearchHasMore, setNodeSearchHasMore] = useState(false)
  const [nodeSearchOffset, setNodeSearchOffset] = useState(0)
  const [nodeSearchLoading, setNodeSearchLoading] = useState(false)
  const nodeSearchRequestIdRef = useRef(0)

  const [pendingRelationId, setPendingRelationId] = useState<string | null>(null)
  const [pendingClaimId, setPendingClaimId] = useState<string | null>(null)

  const [nodeLabelsById, setNodeLabelsById] = useState<Record<string, string>>(() => {
    const seeded: Record<string, string> = {}
    for (const [entityId, label] of Object.entries(entityLabelsById)) {
      const trimmedLabel = label.trim()
      if (trimmedLabel.length > 0) {
        seeded[entityId] = trimmedLabel
      }
    }
    for (const nodeId of relationFilters.nodeIds) {
      if (!seeded[nodeId]) {
        seeded[nodeId] = `Entity ${compactId(nodeId)}`
      }
    }
    return seeded
  })

  useEffect(() => {
    setGraphMode(relationFilters.graphMode)
    setRelationType(relationFilters.relationType)
    setCurationStatus(relationFilters.curationStatus || ALL_VALUE)
    setValidationState(relationFilters.validationState || ALL_VALUE)
    setSourceDocumentId(relationFilters.sourceDocumentId)
    setCertaintyBand(relationFilters.certaintyBand || ALL_VALUE)
    setNodeQuery(relationFilters.nodeQuery)
    setSelectedNodeIds(relationFilters.nodeIds)
    setFocusRelationId(relationFilters.focusRelationId)
  }, [relationFilters])

  useEffect(() => {
    setClaimStatus(claimFilters.claimStatus || ALL_VALUE)
    setClaimValidationState(claimFilters.validationState || ALL_VALUE)
    setClaimPersistability(claimFilters.persistability || ALL_VALUE)
    setClaimPolarity(claimFilters.polarity || ALL_VALUE)
    setClaimRelationType(claimFilters.relationType)
    setClaimSourceDocumentId(claimFilters.sourceDocumentId)
    setClaimLinkedRelationId(claimFilters.linkedRelationId)
    setClaimCertaintyBand(claimFilters.certaintyBand || ALL_VALUE)
  }, [claimFilters])

  useEffect(() => {
    setNodeLabelsById((current) => {
      const merged = { ...current }
      for (const [entityId, label] of Object.entries(entityLabelsById)) {
        const trimmed = label.trim()
        if (trimmed.length > 0) {
          merged[entityId] = trimmed
        }
      }
      return merged
    })
  }, [entityLabelsById])

  const selectedNodeIdSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])
  const relationRows = relations?.relations ?? []
  const claimRows = claims?.claims ?? []
  const conflictByRelationId = useMemo(() => {
    const index = new Map<string, { supportCount: number; refuteCount: number }>()
    const conflicts = relationConflicts?.conflicts ?? []
    for (const conflict of conflicts) {
      index.set(conflict.relation_id, {
        supportCount: conflict.support_count,
        refuteCount: conflict.refute_count,
      })
    }
    return index
  }, [relationConflicts])

  function resolveEntityLabel(entityId: string): string {
    const existing = nodeLabelsById[entityId]
    if (typeof existing === 'string' && existing.trim().length > 0) {
      return existing.trim()
    }
    return `Entity ${compactId(entityId)}`
  }

  const rememberNodeLabels = useCallback((options: NodeSearchOption[]) => {
    if (options.length === 0) {
      return
    }
    setNodeLabelsById((current) => {
      const merged = { ...current }
      for (const option of options) {
        merged[option.id] = option.label
      }
      return merged
    })
  }, [])

  const fetchNodeOptions = useCallback(
    async (query: string, requestedOffset: number, append: boolean): Promise<void> => {
      const normalized = query.trim()
      if (normalized.length < NODE_SEARCH_MIN_CHARS) {
        setNodeSearchOptions([])
        setNodeSearchHasMore(false)
        setNodeSearchOffset(0)
        setNodeSearchLoading(false)
        return
      }

      const requestId = nodeSearchRequestIdRef.current + 1
      nodeSearchRequestIdRef.current = requestId
      setNodeSearchLoading(true)

      const result = await searchKernelRelationNodesAction(
        spaceId,
        normalized,
        requestedOffset,
        NODE_SEARCH_LIMIT,
      )
      if (requestId !== nodeSearchRequestIdRef.current) {
        return
      }

      setNodeSearchLoading(false)
      if (!result.success) {
        if (!append) {
          setNodeSearchOptions([])
        }
        setNodeSearchHasMore(false)
        toast.error(result.error)
        return
      }

      rememberNodeLabels(result.data.options)
      setNodeSearchOptions((current) =>
        append ? mergeNodeOptions(current, result.data.options) : result.data.options,
      )
      setNodeSearchHasMore(result.data.hasMore)
      setNodeSearchOffset(result.data.nextOffset)
    },
    [rememberNodeLabels, spaceId],
  )

  useEffect(() => {
    const normalizedQuery = nodeSearchInput.trim()
    if (normalizedQuery.length < NODE_SEARCH_MIN_CHARS) {
      nodeSearchRequestIdRef.current += 1
      setNodeSearchOptions([])
      setNodeSearchHasMore(false)
      setNodeSearchOffset(0)
      setNodeSearchLoading(false)
      return
    }

    const timeoutId = window.setTimeout(() => {
      void fetchNodeOptions(normalizedQuery, 0, false)
    }, 180)

    return () => window.clearTimeout(timeoutId)
  }, [fetchNodeOptions, nodeSearchInput])

  const onNodeOptionToggle = useCallback(
    (option: NodeSearchOption, checked: boolean) => {
      rememberNodeLabels([option])
      setSelectedNodeIds((current) => {
        const exists = current.includes(option.id)
        if (checked) {
          return exists ? current : [...current, option.id]
        }
        if (!exists) {
          return current
        }
        return current.filter((id) => id !== option.id)
      })
    },
    [rememberNodeLabels],
  )

  const onNodeOptionsScroll = useCallback(
    (event: UIEvent<HTMLDivElement>): void => {
      if (nodeSearchLoading || !nodeSearchHasMore) {
        return
      }
      const element = event.currentTarget
      if (element.scrollTop + element.clientHeight < element.scrollHeight - 24) {
        return
      }
      void fetchNodeOptions(nodeSearchInput, nodeSearchOffset, true)
    },
    [fetchNodeOptions, nodeSearchHasMore, nodeSearchInput, nodeSearchLoading, nodeSearchOffset],
  )

  function removeSelectedNode(nodeId: string): void {
    setSelectedNodeIds((current) => current.filter((id) => id !== nodeId))
  }

  function buildGraphParams(
    offset: number,
    limit: number,
    mode: 'canonical' | 'claim_overlay' = graphMode,
    focusRelationIdOverride: string | null = null,
  ): URLSearchParams {
    const params = new URLSearchParams()
    params.set('tab', 'graph')
    if (mode === 'claim_overlay') {
      params.set('graph_mode', 'claim_overlay')
    }
    appendIfValue(params, 'relation_type', relationType)
    appendIfValue(params, 'node_query', nodeQuery)
    appendIfValue(params, 'source_document_id', sourceDocumentId)
    if (curationStatus !== ALL_VALUE) {
      appendIfValue(params, 'curation_status', curationStatus)
    }
    if (validationState !== ALL_VALUE) {
      appendIfValue(params, 'validation_state', validationState)
    }
    if (certaintyBand !== ALL_VALUE) {
      appendIfValue(params, 'certainty_band', certaintyBand)
    }
    const normalizedNodeIds = Array.from(
      new Set(selectedNodeIds.map((value) => value.trim()).filter((value) => value.length > 0)),
    )
    if (normalizedNodeIds.length > 0) {
      params.set('node_ids', normalizedNodeIds.join(','))
    }
    const resolvedFocusRelationId = (
      focusRelationIdOverride !== null
        ? focusRelationIdOverride
        : focusRelationId
    ).trim()
    if (mode === 'canonical' && resolvedFocusRelationId.length > 0) {
      params.set('focus_relation_id', resolvedFocusRelationId)
    }
    params.set('offset', String(Math.max(0, offset)))
    params.set('limit', String(Math.max(1, limit)))
    return params
  }

  function buildClaimParams(
    offset: number,
    limit: number,
    linkedRelationIdOverride: string | null = null,
  ): URLSearchParams {
    const params = new URLSearchParams()
    params.set('tab', 'claims')
    if (claimStatus !== ALL_VALUE) {
      appendIfValue(params, 'claim_status', claimStatus)
    }
    if (claimValidationState !== ALL_VALUE) {
      appendIfValue(params, 'claim_validation_state', claimValidationState)
    }
    if (claimPersistability !== ALL_VALUE) {
      appendIfValue(params, 'persistability', claimPersistability)
    }
    if (claimPolarity !== ALL_VALUE) {
      appendIfValue(params, 'claim_polarity', claimPolarity)
    }
    appendIfValue(params, 'claim_relation_type', claimRelationType)
    appendIfValue(params, 'claim_source_document_id', claimSourceDocumentId)
    appendIfValue(
      params,
      'linked_relation_id',
      linkedRelationIdOverride !== null ? linkedRelationIdOverride : claimLinkedRelationId,
    )
    if (claimCertaintyBand !== ALL_VALUE) {
      appendIfValue(params, 'claim_certainty_band', claimCertaintyBand)
    }
    params.set('claim_offset', String(Math.max(0, offset)))
    params.set('claim_limit', String(Math.max(1, limit)))
    return params
  }

  function switchTab(tab: 'graph' | 'claims'): void {
    if (tab === 'graph') {
      router.push(`/spaces/${spaceId}/curation?${buildGraphParams(0, relationFilters.limit).toString()}`)
      return
    }
    router.push(`/spaces/${spaceId}/curation?${buildClaimParams(0, claimFilters.limit).toString()}`)
  }

  async function updateRelationStatus(relation: KernelRelationResponse, status: string): Promise<void> {
    setPendingRelationId(relation.id)
    const result = await updateKernelRelationStatusAction(spaceId, relation.id, status)
    setPendingRelationId(null)

    if (!result.success) {
      toast.error(result.error)
      return
    }
    toast.success(`Relation marked ${status}`)
    router.refresh()
  }

  async function updateClaimStatus(claim: RelationClaimResponse, status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'): Promise<void> {
    if (claim.claim_status === status) {
      toast.info(`Claim is already ${humanizeToken(status)}.`)
      return
    }
    setPendingClaimId(claim.id)
    const result = await updateRelationClaimStatusAction(spaceId, claim.id, status)
    setPendingClaimId(null)

    if (!result.success) {
      toast.error(result.error)
      return
    }
    if (status === 'RESOLVED') {
      const linkedRelationId = result.data.linked_relation_id
      if (linkedRelationId) {
        toast.success(`Resolved and linked to relation ${compactId(linkedRelationId)}`)
      } else {
        toast.success('Claim resolved')
      }
    } else {
      toast.success(`Claim marked ${status}`)
    }
    router.refresh()
  }

  function openDictionaryForClaim(claim: RelationClaimResponse): void {
    const params = new URLSearchParams()
    params.set('relation_type', claim.relation_type)
    params.set('source_type', claim.source_type)
    params.set('target_type', claim.target_type)
    router.push(`/admin/dictionary?${params.toString()}`)
  }

  function openClaimsForLinkedRelation(relationId: string): void {
    setClaimLinkedRelationId(relationId)
    router.push(
      `/spaces/${spaceId}/curation?${buildClaimParams(
        0,
        claimFilters.limit,
        relationId,
      ).toString()}`,
    )
  }

  function openGraphForLinkedRelation(relationId: string): void {
    setGraphMode('canonical')
    setFocusRelationId(relationId)
    router.push(
      `/spaces/${spaceId}/curation?${buildGraphParams(
        0,
        relationFilters.limit,
        'canonical',
        relationId,
      ).toString()}`,
    )
  }

  function claimResolveBlockedReason(claim: RelationClaimResponse): string | null {
    if (claim.linked_relation_id) {
      return null
    }
    if (claim.persistability !== 'PERSISTABLE') {
      return 'Resolve blocked: claim is NON_PERSISTABLE. Use Needs Mapping or Reject.'
    }
    const sourceEntityId = typeof claim.metadata?.source_entity_id === 'string'
      ? claim.metadata.source_entity_id.trim()
      : ''
    const targetEntityId = typeof claim.metadata?.target_entity_id === 'string'
      ? claim.metadata.target_entity_id.trim()
      : ''
    if (!sourceEntityId || !targetEntityId) {
      return 'Resolve blocked: source/target entity mapping is missing. Use Needs Mapping.'
    }
    return null
  }

  function applyClaimQueuePreset(
    preset: 'ALL' | 'READY_TO_RESOLVE' | 'NEEDS_MAPPING' | 'REJECTED',
  ): void {
    const params = new URLSearchParams()
    params.set('tab', 'claims')
    params.set('claim_offset', '0')
    params.set('claim_limit', String(claimFilters.limit))

    if (preset === 'READY_TO_RESOLVE') {
      params.set('claim_status', 'OPEN')
      params.set('claim_validation_state', 'ALLOWED')
      params.set('persistability', 'PERSISTABLE')
    } else if (preset === 'NEEDS_MAPPING') {
      params.set('claim_validation_state', 'UNDEFINED')
    } else if (preset === 'REJECTED') {
      params.set('claim_status', 'REJECTED')
    }

    router.push(`/spaces/${spaceId}/curation?${params.toString()}`)
  }

  const graphTotal = relations?.total ?? 0
  const graphOffset = relationFilters.offset
  const graphLimit = relationFilters.limit
  const graphHasPrev = graphOffset > 0
  const graphHasNext = graphOffset + graphLimit < graphTotal

  const claimTotal = claims?.total ?? 0
  const claimOffset = claimFilters.offset
  const claimLimit = claimFilters.limit
  const claimHasPrev = claimOffset > 0
  const claimHasNext = claimOffset + claimLimit < claimTotal

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Data Curation"
        description="Review canonical graph relations and extraction claims with certainty and validation context."
      >
        <div className="space-y-4">
          <div className="inline-flex items-center rounded-md border border-border/80 bg-background p-1">
            <Button
              variant={activeTab === 'graph' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => switchTab('graph')}
            >
              Graph Relations
            </Button>
            <Button
              variant={activeTab === 'claims' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => switchTab('claims')}
            >
              Extraction Claims
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {activeTab === 'graph'
              ? graphMode === 'canonical'
                ? 'Graph Relations: curate canonical edges (DRAFT, UNDER_REVIEW, APPROVED, REJECTED).'
                : 'Claim Overlay: inspect claim-to-claim links and participant context without canonical graph writes.'
              : 'Extraction Claims: triage candidate edges. Resolve promotes/links into canonical graph when allowed.'}
          </p>

          {activeTab === 'graph' ? (
            <>
              <Card className="border-border/80 bg-card">
                <CardContent className="py-4">
                  <div className="flex items-center gap-3">
                    <Label className="font-semibold text-foreground">Graph Mode</Label>
                    <Select
                      value={graphMode}
                      onValueChange={(value) => {
                        const nextMode = value as 'canonical' | 'claim_overlay'
                        setGraphMode(nextMode)
                        if (nextMode !== 'canonical') {
                          setFocusRelationId('')
                        }
                        router.push(
                          `/spaces/${spaceId}/curation?${buildGraphParams(
                            0,
                            relationFilters.limit,
                            nextMode,
                            nextMode === 'canonical' ? null : '',
                          ).toString()}`,
                        )
                      }}
                    >
                      <SelectTrigger className="w-64">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="canonical">Canonical Graph</SelectItem>
                        <SelectItem value="claim_overlay">Claim Overlay</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>

              {graphMode === 'canonical' ? (
                <>
                <Card className="border-border/80 bg-card">
                <CardContent className="grid gap-4 py-6 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="relation_type" className="font-semibold text-foreground">
                      Relation Type
                    </Label>
                    <Input
                      id="relation_type"
                      value={relationType}
                      onChange={(event) => setRelationType(event.target.value)}
                      placeholder="e.g. ASSOCIATED_WITH"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="node_query" className="font-semibold text-foreground">
                      Node Context
                    </Label>
                    <Input
                      id="node_query"
                      value={nodeQuery}
                      onChange={(event) => setNodeQuery(event.target.value)}
                      placeholder="Search node label/type/id"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="source_document_id" className="font-semibold text-foreground">
                      Source Document ID
                    </Label>
                    <Input
                      id="source_document_id"
                      value={sourceDocumentId}
                      onChange={(event) => setSourceDocumentId(event.target.value)}
                      placeholder="UUID"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Status</Label>
                    <Select value={curationStatus} onValueChange={setCurationStatus}>
                      <SelectTrigger>
                        <SelectValue placeholder="All statuses" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {GRAPH_STATUSES.map((status) => (
                          <SelectItem key={status} value={status}>
                            {humanizeToken(status)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Validation State</Label>
                    <Select value={validationState} onValueChange={setValidationState}>
                      <SelectTrigger>
                        <SelectValue placeholder="All validation states" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {VALIDATION_STATES.map((state) => (
                          <SelectItem key={state} value={state}>
                            {humanizeToken(state)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">AI Certainty</Label>
                    <Select value={certaintyBand} onValueChange={setCertaintyBand}>
                      <SelectTrigger>
                        <SelectValue placeholder="All certainty bands" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {CERTAINTY_BANDS.map((band) => (
                          <SelectItem key={band} value={band}>
                            {humanizeToken(band)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
                <CardContent className="space-y-3 border-t border-border/70 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="node_filter" className="font-semibold text-foreground">
                      Node IDs (optional)
                    </Label>
                    <div className="space-y-2 rounded-md border border-border/70 bg-background/55 p-2">
                      <div className="flex min-h-11 flex-wrap items-center gap-2 rounded-md border border-input bg-background px-2 py-1">
                        {selectedNodeIds.map((nodeId) => (
                          <span
                            key={nodeId}
                            className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/35 bg-primary/10 px-2 py-0.5 text-xs"
                          >
                            <span className="truncate">{resolveEntityLabel(nodeId)}</span>
                            <button
                              type="button"
                              className="rounded px-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                              onClick={() => removeSelectedNode(nodeId)}
                              aria-label={`Remove ${resolveEntityLabel(nodeId)}`}
                            >
                              x
                            </button>
                          </span>
                        ))}
                        <Input
                          id="node_filter"
                          value={nodeSearchInput}
                          onChange={(event) => setNodeSearchInput(event.target.value)}
                          placeholder="Type to search nodes"
                          className="h-7 min-w-48 flex-1 border-0 bg-transparent px-1 py-0 text-sm shadow-none focus-visible:ring-0"
                        />
                      </div>

                      <div
                        className="max-h-44 space-y-2 overflow-auto rounded-md border border-border/70 bg-background/70 p-2"
                        onScroll={onNodeOptionsScroll}
                      >
                        {nodeSearchInput.trim().length < NODE_SEARCH_MIN_CHARS ? (
                          <div className="text-xs text-muted-foreground">
                            Type at least {NODE_SEARCH_MIN_CHARS} characters to search nodes.
                          </div>
                        ) : nodeSearchOptions.length === 0 && !nodeSearchLoading ? (
                          <div className="text-xs text-muted-foreground">No nodes match this query.</div>
                        ) : (
                          nodeSearchOptions.map((option) => {
                            const isSelected = selectedNodeIdSet.has(option.id)
                            return (
                              <div
                                key={option.id}
                                className="flex items-start gap-2 rounded-md border border-transparent px-2 py-1 transition-colors hover:border-border hover:bg-muted/55"
                              >
                                <Checkbox
                                  id={`node-option-${option.id}`}
                                  checked={isSelected}
                                  onCheckedChange={(checked) =>
                                    onNodeOptionToggle(option, checked === true)
                                  }
                                />
                                <Label htmlFor={`node-option-${option.id}`} className="min-w-0 flex-1 cursor-pointer">
                                  <span className="block truncate text-xs font-medium text-foreground">
                                    {option.label} ({option.entityType})
                                  </span>
                                  <span className="font-mono text-[10px] text-muted-foreground">
                                    {compactId(option.id)}
                                  </span>
                                </Label>
                              </div>
                            )
                          })
                        )}
                        {nodeSearchLoading ? (
                          <div className="px-1 text-xs text-muted-foreground">Loading node options...</div>
                        ) : null}
                        {nodeSearchHasMore && !nodeSearchLoading ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-7 w-full text-xs"
                            onClick={() => {
                              void fetchNodeOptions(nodeSearchInput, nodeSearchOffset, true)
                            }}
                          >
                            Load more nodes
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      onClick={() => {
                        router.push(
                          `/spaces/${spaceId}/curation?${buildGraphParams(0, relationFilters.limit).toString()}`,
                        )
                      }}
                    >
                      Apply
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setRelationType('')
                        setCurationStatus(ALL_VALUE)
                        setValidationState(ALL_VALUE)
                        setSourceDocumentId('')
                        setCertaintyBand(ALL_VALUE)
                        setNodeQuery('')
                        setSelectedNodeIds([])
                        setNodeSearchInput('')
                        setNodeSearchOptions([])
                        setNodeSearchHasMore(false)
                        setNodeSearchOffset(0)
                        setFocusRelationId('')
                        router.push(`/spaces/${spaceId}/curation?tab=graph`)
                      }}
                    >
                      Clear
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      {buildPaginationLabel(graphTotal, graphOffset, graphLimit)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {relationsError ? (
                <Card>
                  <CardContent className="py-8 text-center text-destructive">{relationsError}</CardContent>
                </Card>
              ) : relationRows.length === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-muted-foreground">No graph relations found.</CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {relationRows.map((relation) => {
                    const sourceLabel = resolveEntityLabel(relation.source_id)
                    const targetLabel = resolveEntityLabel(relation.target_id)
                    const conflictSummary = conflictByRelationId.get(relation.id)
                    const confidence = confidencePercent(relation.confidence)
                    const certaintyLevel = confidenceCertaintyLevel(confidence)
                    const evidenceSummary = relation.evidence_summary?.trim() ?? ''
                    const evidenceSentence = relation.evidence_sentence?.trim() ?? ''
                    const paperLinks =
                      relation.paper_links?.filter(
                        (link) =>
                          typeof link.url === 'string' &&
                          link.url.trim().length > 0 &&
                          typeof link.label === 'string' &&
                          link.label.trim().length > 0,
                      ) ?? []
                    const showsAiGeneratedBadge =
                      relation.evidence_sentence_source === 'artana_generated' &&
                      evidenceSentence.length > 0
                    const linkedClaims = claimRows.filter(
                      (claim) => claim.linked_relation_id === relation.id,
                    )
                    const isFocusedRelation =
                      focusRelationId.trim().length > 0 &&
                      focusRelationId.trim() === relation.id

                    return (
                      <Card
                        key={relation.id}
                        className={
                          isFocusedRelation
                            ? 'border-primary/70 bg-card shadow-sm ring-1 ring-primary/35'
                            : 'border-border bg-card shadow-sm'
                        }
                      >
                        <CardContent className="space-y-4 p-5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={statusBadgeVariant(relation.curation_status)}>
                                {humanizeToken(relation.curation_status)}
                              </Badge>
                              {conflictSummary ? (
                                <Badge variant="destructive">
                                  Conflict {conflictSummary.supportCount}/{conflictSummary.refuteCount}
                                </Badge>
                              ) : null}
                              {isFocusedRelation ? (
                                <Badge variant="secondary">Focused from claim queue</Badge>
                              ) : null}
                              <span className="font-mono text-xs text-muted-foreground">
                                Relation {compactId(relation.id)}
                              </span>
                            </div>
                            <span className="text-xs text-muted-foreground">
                              Updated {formatTimestamp(relation.updated_at)}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 md:gap-3">
                            <span className="rounded-lg border border-primary/35 bg-primary/10 px-3 py-1 text-base font-semibold text-foreground md:text-xl">
                              {sourceLabel}
                            </span>
                            <span className="font-serif text-lg italic text-foreground/80 md:text-2xl">
                              {relationConnectorPhrase(relation.relation_type)}
                            </span>
                            <span className="rounded-lg border border-secondary/40 bg-secondary/15 px-3 py-1 text-base font-semibold text-foreground md:text-xl">
                              {targetLabel}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <Badge variant="outline">{relation.relation_type}</Badge>
                            <Badge variant={certaintyBadgeVariant(certaintyLevel)}>
                              AI {certaintyLevel} certainty
                            </Badge>
                          </div>

                          <div className="space-y-2">
                            {evidenceSentence.length > 0 ? (
                              <p className="text-sm text-foreground/80">{evidenceSentence}</p>
                            ) : null}
                            {showsAiGeneratedBadge ? (
                              <Badge variant="secondary">AI-generated (not verbatim span)</Badge>
                            ) : null}
                            {evidenceSummary.length > 0 && evidenceSummary !== evidenceSentence ? (
                              <p className="text-sm text-muted-foreground">{evidenceSummary}</p>
                            ) : null}
                            {evidenceSentence.length === 0 && evidenceSummary.length === 0 ? (
                              <p className="text-sm text-muted-foreground">No evidence summary available.</p>
                            ) : null}

                            <div className="text-xs text-muted-foreground">
                              {paperLinks.length > 0 ? (
                                <span className="inline-flex flex-wrap items-center gap-2">
                                  <span>Paper(s):</span>
                                  {paperLinks.map((link) => (
                                    <a
                                      key={`${link.url}-${link.source}`}
                                      href={link.url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="underline decoration-dotted underline-offset-2 hover:text-foreground"
                                    >
                                      {link.label}
                                    </a>
                                  ))}
                                </span>
                              ) : (
                                'No source links'
                              )}
                            </div>
                          </div>

                          <div className="space-y-2 rounded-md border border-border/70 bg-muted/20 p-3">
                            <p className="text-xs font-semibold uppercase text-muted-foreground">
                              Linked Claims
                            </p>
                            {linkedClaims.length > 0 ? (
                              <div className="space-y-1">
                                {linkedClaims.slice(0, 3).map((claim) => (
                                  <p key={claim.id} className="text-xs text-foreground/85">
                                    {compactId(claim.id)}: {claim.source_label || claim.source_type} {'->'}{' '}
                                    {claim.relation_type} {'->'} {claim.target_label || claim.target_type}
                                  </p>
                                ))}
                                {linkedClaims.length > 3 ? (
                                  <p className="text-xs text-muted-foreground">
                                    +{linkedClaims.length - 3} more linked claims in queue
                                  </p>
                                ) : null}
                              </div>
                            ) : (
                              <p className="text-xs text-muted-foreground">
                                No linked claims in the current queue view.
                              </p>
                            )}
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => openClaimsForLinkedRelation(relation.id)}
                            >
                              Open linked claims
                            </Button>
                          </div>

                          {canCurate ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={pendingRelationId === relation.id}
                                onClick={() => updateRelationStatus(relation, 'UNDER_REVIEW')}
                              >
                                Under Review
                              </Button>
                              <Button
                                size="sm"
                                disabled={pendingRelationId === relation.id}
                                onClick={() => updateRelationStatus(relation, 'APPROVED')}
                              >
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={pendingRelationId === relation.id}
                                onClick={() => updateRelationStatus(relation, 'REJECTED')}
                              >
                                Reject
                              </Button>
                            </div>
                          ) : null}
                        </CardContent>
                      </Card>
                    )
                  })}
                </div>
              )}

              <div className="flex items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={!graphHasPrev}
                  onClick={() => {
                    const nextOffset = Math.max(0, graphOffset - graphLimit)
                    router.push(`/spaces/${spaceId}/curation?${buildGraphParams(nextOffset, graphLimit).toString()}`)
                  }}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground">
                  {buildPaginationLabel(graphTotal, graphOffset, graphLimit)}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!graphHasNext}
                  onClick={() => {
                    const nextOffset = graphOffset + graphLimit
                    router.push(`/spaces/${spaceId}/curation?${buildGraphParams(nextOffset, graphLimit).toString()}`)
                  }}
                >
                  Next
                </Button>
              </div>
                </>
              ) : (
                <ClaimOverlayGraphPanel
                  spaceId={spaceId}
                  canCurate={canCurate}
                  openClaimsTab={() => switchTab('claims')}
                  openCanonicalGraphRelation={(relationId) => openGraphForLinkedRelation(relationId)}
                />
              )}
            </>
          ) : (
            <>
              <CurationHypothesesCard
                spaceId={spaceId}
                canEdit={canCurate}
                autoGenerationEnabled={hypothesisGenerationEnabled}
              />

              <Card className="border-border/80 bg-card">
                <CardContent className="border-b border-border/70 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase text-muted-foreground">Queue Presets</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => applyClaimQueuePreset('ALL')}
                    >
                      All
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => applyClaimQueuePreset('READY_TO_RESOLVE')}
                    >
                      Ready to resolve
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => applyClaimQueuePreset('NEEDS_MAPPING')}
                    >
                      Needs mapping
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => applyClaimQueuePreset('REJECTED')}
                    >
                      Rejected
                    </Button>
                  </div>
                </CardContent>
                <CardContent className="grid gap-4 py-6 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Claim Status</Label>
                    <Select value={claimStatus} onValueChange={setClaimStatus}>
                      <SelectTrigger>
                        <SelectValue placeholder="All claim statuses" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {CLAIM_STATUSES.map((status) => (
                          <SelectItem key={status} value={status}>
                            {humanizeToken(status)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Validation State</Label>
                    <Select value={claimValidationState} onValueChange={setClaimValidationState}>
                      <SelectTrigger>
                        <SelectValue placeholder="All validation states" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {VALIDATION_STATES.map((state) => (
                          <SelectItem key={state} value={state}>
                            {humanizeToken(state)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Persistability</Label>
                    <Select value={claimPersistability} onValueChange={setClaimPersistability}>
                      <SelectTrigger>
                        <SelectValue placeholder="All persistability states" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {PERSISTABILITY.map((value) => (
                          <SelectItem key={value} value={value}>
                            {humanizeToken(value)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold text-foreground">Polarity</Label>
                    <Select value={claimPolarity} onValueChange={setClaimPolarity}>
                      <SelectTrigger>
                        <SelectValue placeholder="All polarities" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {CLAIM_POLARITIES.map((polarity) => (
                          <SelectItem key={polarity} value={polarity}>
                            {humanizeToken(polarity)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claim_relation_type" className="font-semibold text-foreground">
                      Relation Type
                    </Label>
                    <Input
                      id="claim_relation_type"
                      value={claimRelationType}
                      onChange={(event) => setClaimRelationType(event.target.value)}
                      placeholder="e.g. ASSOCIATED_WITH"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claim_source_document_id" className="font-semibold text-foreground">
                      Source Document ID
                    </Label>
                    <Input
                      id="claim_source_document_id"
                      value={claimSourceDocumentId}
                      onChange={(event) => setClaimSourceDocumentId(event.target.value)}
                      placeholder="UUID"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claim_linked_relation_id" className="font-semibold text-foreground">
                      Linked Relation ID
                    </Label>
                    <Input
                      id="claim_linked_relation_id"
                      value={claimLinkedRelationId}
                      onChange={(event) => setClaimLinkedRelationId(event.target.value)}
                      placeholder="UUID"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-3">
                    <Label className="font-semibold text-foreground">AI Certainty</Label>
                    <Select value={claimCertaintyBand} onValueChange={setClaimCertaintyBand}>
                      <SelectTrigger>
                        <SelectValue placeholder="All certainty bands" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_VALUE}>All</SelectItem>
                        {CERTAINTY_BANDS.map((band) => (
                          <SelectItem key={band} value={band}>
                            {humanizeToken(band)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
                <CardContent className="border-t border-border/70 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      onClick={() => {
                        router.push(
                          `/spaces/${spaceId}/curation?${buildClaimParams(0, claimFilters.limit).toString()}`,
                        )
                      }}
                    >
                      Apply
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setClaimStatus(ALL_VALUE)
                        setClaimValidationState(ALL_VALUE)
                        setClaimPersistability(ALL_VALUE)
                        setClaimPolarity(ALL_VALUE)
                        setClaimRelationType('')
                        setClaimSourceDocumentId('')
                        setClaimLinkedRelationId('')
                        setClaimCertaintyBand(ALL_VALUE)
                        router.push(`/spaces/${spaceId}/curation?tab=claims`)
                      }}
                    >
                      Clear
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      {buildPaginationLabel(claimTotal, claimOffset, claimLimit)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {claimsError ? (
                <Card>
                  <CardContent className="py-8 text-center text-destructive">{claimsError}</CardContent>
                </Card>
              ) : claimRows.length === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-muted-foreground">No extraction claims found.</CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {claimRows.map((claim) => {
                    const confidence = confidencePercent(claim.confidence)
                    const certaintyLevel = confidenceCertaintyLevel(confidence)
                    const resolveBlockedReason = claimResolveBlockedReason(claim)
                    const canResolveClaim = resolveBlockedReason === null
                    const isPendingClaimAction = pendingClaimId === claim.id
                    const linkedConflictSummary =
                      claim.linked_relation_id
                        ? conflictByRelationId.get(claim.linked_relation_id)
                        : undefined
                    return (
                      <Card key={claim.id} className="border-border bg-card shadow-sm">
                        <CardContent className="space-y-4 p-5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={statusBadgeVariant(claim.claim_status)}>
                                {humanizeToken(claim.claim_status)}
                              </Badge>
                              <Badge variant="outline">{humanizeToken(claim.validation_state)}</Badge>
                              <Badge variant="outline">{humanizeToken(claim.persistability)}</Badge>
                              <Badge variant={polarityBadgeVariant(claim.polarity)}>
                                {humanizeToken(claim.polarity)}
                              </Badge>
                              {linkedConflictSummary ? (
                                <Badge variant="destructive">
                                  Conflict {linkedConflictSummary.supportCount}/
                                  {linkedConflictSummary.refuteCount}
                                </Badge>
                              ) : null}
                            </div>
                            <span className="text-xs text-muted-foreground">
                              Created {formatTimestamp(claim.created_at)}
                            </span>
                          </div>

                          <div className="space-y-1">
                            <p className="text-sm text-foreground">
                              <span className="font-semibold">{claim.source_label || claim.source_type}</span>
                              {' -> '}
                              <span className="font-mono">{claim.relation_type}</span>
                              {' -> '}
                              <span className="font-semibold">{claim.target_label || claim.target_type}</span>
                            </p>
                            <p className="font-mono text-xs text-muted-foreground">
                              Claim {compactId(claim.id)}
                              {claim.linked_relation_id ? ` | Linked relation ${compactId(claim.linked_relation_id)}` : ''}
                            </p>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span>Source type: {claim.source_type}</span>
                              <span>Target type: {claim.target_type}</span>
                              {claim.source_document_id ? <span>Doc: {compactId(claim.source_document_id)}</span> : null}
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={certaintyBadgeVariant(certaintyLevel)}>
                              AI {certaintyLevel} certainty
                            </Badge>
                            {claim.validation_reason ? (
                              <span className="text-xs text-muted-foreground">{claim.validation_reason}</span>
                            ) : null}
                          </div>
                          {claim.claim_text ? (
                            <p className="text-sm text-foreground/85">{claim.claim_text}</p>
                          ) : null}
                          {claim.claim_section ? (
                            <p className="text-xs text-muted-foreground">
                              Section: {humanizeToken(claim.claim_section)}
                            </p>
                          ) : null}
                          {claim.linked_relation_id ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                if (!claim.linked_relation_id) {
                                  return;
                                }
                                openGraphForLinkedRelation(claim.linked_relation_id);
                              }}
                            >
                              Highlight linked relation
                            </Button>
                          ) : null}

                          {canCurate ? (
                            <div className="flex flex-wrap items-center gap-2">
                              {canResolveClaim ? (
                                <Button
                                  size="sm"
                                  disabled={isPendingClaimAction}
                                  onClick={() => updateClaimStatus(claim, 'RESOLVED')}
                                >
                                  Resolve to graph draft
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  disabled={isPendingClaimAction}
                                  onClick={() => updateClaimStatus(claim, 'NEEDS_MAPPING')}
                                >
                                  Send to mapping queue
                                </Button>
                              )}
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={isPendingClaimAction}
                                  >
                                    Actions
                                    <ChevronDown className="ml-1 size-4" />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="start">
                                  <DropdownMenuItem
                                    disabled={!canResolveClaim}
                                    onClick={() => updateClaimStatus(claim, 'RESOLVED')}
                                  >
                                    Resolve to graph draft
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => updateClaimStatus(claim, 'NEEDS_MAPPING')}
                                  >
                                    Mark Needs Mapping
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => openDictionaryForClaim(claim)}
                                  >
                                    Open dictionary constraints
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    onClick={() => updateClaimStatus(claim, 'OPEN')}
                                  >
                                    Mark Open
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    className="text-destructive focus:text-destructive"
                                    onClick={() => updateClaimStatus(claim, 'REJECTED')}
                                  >
                                    Reject claim
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          ) : null}
                          {canCurate && !canResolveClaim ? (
                            <p className="text-xs text-muted-foreground">
                              {resolveBlockedReason} Next step: mark Needs Mapping, then open dictionary constraints.
                            </p>
                          ) : null}
                        </CardContent>
                      </Card>
                    )
                  })}
                </div>
              )}

              <div className="flex items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={!claimHasPrev}
                  onClick={() => {
                    const nextOffset = Math.max(0, claimOffset - claimLimit)
                    router.push(`/spaces/${spaceId}/curation?${buildClaimParams(nextOffset, claimLimit).toString()}`)
                  }}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground">
                  {buildPaginationLabel(claimTotal, claimOffset, claimLimit)}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!claimHasNext}
                  onClick={() => {
                    const nextOffset = claimOffset + claimLimit
                    router.push(`/spaces/${spaceId}/curation?${buildClaimParams(nextOffset, claimLimit).toString()}`)
                  }}
                >
                  Next
                </Button>
              </div>
            </>
          )}
        </div>
      </DashboardSection>
    </div>
  )
}
