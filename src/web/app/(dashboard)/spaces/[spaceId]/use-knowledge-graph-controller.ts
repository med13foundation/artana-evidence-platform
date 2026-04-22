'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchKernelGraphDocumentAction,
  searchKernelGraphAction,
  type QueryActionResult,
} from '@/app/actions/kernel-graph'
import {
  buildClaimEvidencePreviewIndex,
  buildGraphModelFromDocument,
} from '@/lib/graph/document'
import {
  emptyGraphModel,
  filterGraphModel,
  getNeighborhood,
  mergeGraphModels,
  projectGraphByDisplayMode,
  pruneGraphModelForRender,
  type GraphDisplayMode,
  type GraphModel,
} from '@/lib/graph/model'
import type {
  GraphSearchResponse,
  KernelGraphDocumentMeta,
  KernelGraphDocumentRequest,
} from '@/types/kernel'

const DEFAULT_STARTER_TOP_K = 25
const DEFAULT_STARTER_DEPTH = 2
const MAX_DEPTH = 4
const MAX_TOP_K = 100
const MIN_DEPTH = 1
const MIN_TOP_K = 1
const MAX_RENDER_NODES = 180
const MAX_RENDER_EDGES = 260
const MAX_SEEDED_SEARCH_RESULTS = 5
const DEFAULT_EXPAND_TOP_K = 25
const MAX_DOCUMENT_CLAIMS = 250
const DEFAULT_EVIDENCE_LIMIT_PER_CLAIM = 3
const ALL_GRAPH_STATUSES = ['APPROVED', 'UNDER_REVIEW', 'DRAFT', 'REJECTED', 'RETRACTED'] as const

export type GraphTrustPreset = 'ALL' | 'APPROVED_ONLY' | 'PENDING_REVIEW' | 'REJECTED'
export const DEFAULT_GRAPH_DISPLAY_MODE: GraphDisplayMode = 'CLAIMS'

export type ClaimEvidencePreviewState = 'loading' | 'ready' | 'empty' | 'error'

export interface ClaimEvidencePreview {
  state: ClaimEvidencePreviewState
  sentence: string | null
  sourceLabel: string | null
}

const TRUST_PRESET_STATUS_MAP: Record<GraphTrustPreset, string[] | null> = {
  ALL: null,
  APPROVED_ONLY: ['APPROVED'],
  PENDING_REVIEW: ['DRAFT', 'UNDER_REVIEW'],
  REJECTED: ['REJECTED', 'RETRACTED'],
}

interface QueryRouter {
  replace: (href: string) => void
}

interface UseKnowledgeGraphControllerArgs {
  spaceId: string
  router: QueryRouter
  initialQuestion: string
  initialTopK: number
  initialMaxDepth: number
  initialForceAgent: boolean
  initialTrustPreset: GraphTrustPreset
}

function parseBoundedInt(
  value: string,
  fallback: number,
  minValue: number,
  maxValue: number,
): number {
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed)) {
    return fallback
  }
  return Math.min(maxValue, Math.max(minValue, parsed))
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message
  }
  return fallback
}

function unwrapQueryAction<T>(
  result: QueryActionResult<T>,
  fallback: string,
): T {
  if (result.success) {
    return result.data
  }
  const error = new Error(result.error || fallback) as Error & { status?: number }
  if (typeof result.status === 'number') {
    error.status = result.status
  }
  throw error
}

function updateQueryParams(
  router: QueryRouter,
  spaceId: string,
  question: string,
  topK: number,
  maxDepth: number,
  forceAgent: boolean,
  trustPreset: GraphTrustPreset,
): void {
  const params = new URLSearchParams()
  const trimmedQuestion = question.trim()
  if (trustPreset !== 'ALL') {
    params.set('trust', trustPreset)
  }
  if (trimmedQuestion.length > 0) {
    params.set('q', trimmedQuestion)
    params.set('top_k', String(topK))
    params.set('max_depth', String(maxDepth))
    if (forceAgent) {
      params.set('force_agent', '1')
    }
  }
  const suffix = params.toString()
  router.replace(
    suffix.length > 0
      ? `/spaces/${spaceId}/knowledge-graph?${suffix}`
      : `/spaces/${spaceId}/knowledge-graph`,
  )
}

function canonicalClaimIds(model: GraphModel, canonicalEdgeId: string): string[] {
  const linkedClaimIds = model.edgeById[canonicalEdgeId]?.linkedClaimIds ?? []
  if (linkedClaimIds.length > 0) {
    return linkedClaimIds
  }

  const claimIds = new Set<string>()
  for (const edge of model.edges) {
    if (edge.origin !== 'claim' || !edge.claimId || edge.linkedRelationId !== canonicalEdgeId) {
      continue
    }
    claimIds.add(edge.claimId)
  }
  return [...claimIds]
}

export interface KnowledgeGraphController {
  questionInput: string
  topKInput: string
  maxDepthInput: string
  forceAgent: boolean
  trustPreset: GraphTrustPreset
  graphDisplayMode: GraphDisplayMode
  setQuestionInput: (value: string) => void
  setTopKInput: (value: string) => void
  setMaxDepthInput: (value: string) => void
  setForceAgent: (value: boolean) => void
  setTrustPreset: (value: GraphTrustPreset) => void
  setGraphDisplayMode: (mode: GraphDisplayMode) => void
  topK: number
  maxDepth: number
  minDepth: number
  maxDepthLimit: number
  minTopK: number
  maxTopKLimit: number
  graphSearch: GraphSearchResponse | null
  graphSearchResults: GraphSearchResponse['results']
  graphSearchError: string | null
  graphError: string | null
  graphNotice: string | null
  isLoading: boolean
  isExpandingNodeId: string | null
  filteredGraph: GraphModel
  renderGraph: GraphModel
  neighborhood: {
    nodeIds: Set<string>
    edgeIds: Set<string>
  }
  selectedNodeId: string | null
  subgraphMeta: KernelGraphDocumentMeta | null
  truncationNotice: boolean | undefined
  preCapNodeCount: number
  preCapEdgeCount: number
  availableRelationTypes: string[]
  availableCurationStatuses: string[]
  relationTypeFilter: Set<string>
  curationStatusFilter: Set<string>
  onNodeClick: (nodeId: string) => void
  onEdgeClick: (edgeId: string) => void
  onHoverNodeChange: (nodeId: string | null) => void
  onHoverEdgeChange: (edgeId: string | null) => void
  clearSelection: () => void
  claimEvidenceByClaimId: Readonly<Record<string, ClaimEvidencePreview>>
  runSearch: (syncUrl?: boolean) => Promise<void>
  resetToStarter: () => void
  resetFilters: () => void
  enableAllRelationTypes: () => void
  toggleRelationType: (relationType: string, checked: boolean) => void
  toggleCurationStatus: (status: string, checked: boolean) => void
}

export function useKnowledgeGraphController({
  spaceId,
  router,
  initialQuestion,
  initialTopK,
  initialMaxDepth,
  initialForceAgent,
  initialTrustPreset,
}: UseKnowledgeGraphControllerArgs): KnowledgeGraphController {
  const bootstrapRef = useRef(false)

  const [questionInput, setQuestionInput] = useState(initialQuestion)
  const [topKInput, setTopKInput] = useState(String(initialTopK))
  const [maxDepthInput, setMaxDepthInput] = useState(String(initialMaxDepth))
  const [forceAgent, setForceAgent] = useState(initialForceAgent)
  const [trustPreset, setTrustPresetState] = useState<GraphTrustPreset>(initialTrustPreset)
  const [graphDisplayMode, setGraphDisplayModeState] = useState<GraphDisplayMode>(
    DEFAULT_GRAPH_DISPLAY_MODE,
  )

  const [rawGraph, setRawGraph] = useState<GraphModel>(emptyGraphModel())
  const [subgraphMeta, setSubgraphMeta] = useState<KernelGraphDocumentMeta | null>(null)
  const [graphSearch, setGraphSearch] = useState<GraphSearchResponse | null>(null)

  const [graphError, setGraphError] = useState<string | null>(null)
  const [graphNotice, setGraphNotice] = useState<string | null>(null)
  const [graphSearchError, setGraphSearchError] = useState<string | null>(null)
  const [isLoadingGraph, setIsLoadingGraph] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [isExpandingNodeId, setIsExpandingNodeId] = useState<string | null>(null)

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)

  const [relationTypeFilter, setRelationTypeFilter] = useState<Set<string>>(new Set())
  const [curationStatusFilter, setCurationStatusFilter] = useState<Set<string>>(
    () => new Set(TRUST_PRESET_STATUS_MAP[initialTrustPreset] ?? []),
  )
  const trustPresetSyncRef = useRef<GraphTrustPreset>(initialTrustPreset)

  const activeCurationStatuses = useMemo(
    () => TRUST_PRESET_STATUS_MAP[trustPreset],
    [trustPreset],
  )

  const topK = useMemo(
    () => parseBoundedInt(topKInput, initialTopK, MIN_TOP_K, MAX_TOP_K),
    [initialTopK, topKInput],
  )
  const maxDepth = useMemo(
    () => parseBoundedInt(maxDepthInput, initialMaxDepth, MIN_DEPTH, MAX_DEPTH),
    [initialMaxDepth, maxDepthInput],
  )

  const requestGraphDocument = useCallback(
    async (
      payload: KernelGraphDocumentRequest,
    ): Promise<{ model: GraphModel; meta: KernelGraphDocumentMeta }> => {
      const response = unwrapQueryAction(
        await fetchKernelGraphDocumentAction(spaceId, {
          ...payload,
          include_claims: true,
          include_evidence: true,
          max_claims: MAX_DOCUMENT_CLAIMS,
          evidence_limit_per_claim: DEFAULT_EVIDENCE_LIMIT_PER_CLAIM,
        }),
        'Unable to load graph document for this research space.',
      )
      return {
        model: buildGraphModelFromDocument(response),
        meta: response.meta,
      }
    },
    [spaceId],
  )

  const fetchSubgraph = useCallback(
    async (payload: KernelGraphDocumentRequest): Promise<void> => {
      setIsLoadingGraph(true)
      setGraphError(null)
      setGraphNotice(null)

      try {
        const response = await requestGraphDocument(payload)
        setRawGraph(response.model)
        setSubgraphMeta(response.meta)
      } catch (error) {
        setGraphError(
          toErrorMessage(
            error,
            'Unable to load graph document for this research space.',
          ),
        )
      } finally {
        setIsLoadingGraph(false)
      }
    },
    [requestGraphDocument],
  )

  const loadStarterSubgraph = useCallback(async (): Promise<void> => {
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
    setHoveredNodeId(null)
    setHoveredEdgeId(null)
    await fetchSubgraph({
      mode: 'starter',
      seed_entity_ids: [],
      depth: DEFAULT_STARTER_DEPTH,
      top_k: DEFAULT_STARTER_TOP_K,
      curation_statuses: activeCurationStatuses,
      max_nodes: MAX_RENDER_NODES,
      max_edges: MAX_RENDER_EDGES,
    })
  }, [activeCurationStatuses, fetchSubgraph])

  const runQuery = useCallback(
    async ({
      question,
      topK,
      maxDepth,
      forceAgent,
      syncUrl,
    }: {
      question: string
      topK: number
      maxDepth: number
      forceAgent: boolean
      syncUrl: boolean
    }): Promise<void> => {
      const normalizedQuestion = question.trim()
      if (normalizedQuestion.length === 0) {
        setGraphSearch(null)
        setGraphSearchError(null)
        if (syncUrl) {
          updateQueryParams(
            router,
            spaceId,
            '',
            topK,
            maxDepth,
            forceAgent,
            trustPreset,
          )
        }
        await loadStarterSubgraph()
        return
      }

      setIsSearching(true)
      setGraphSearchError(null)
      setGraphError(null)
      setGraphNotice(null)
      setSelectedNodeId(null)
      setSelectedEdgeId(null)
      setHoveredNodeId(null)
      setHoveredEdgeId(null)

      try {
        const searchResponse = unwrapQueryAction(
          await searchKernelGraphAction(spaceId, {
            question: normalizedQuestion,
            top_k: topK,
            max_depth: maxDepth,
            curation_statuses: activeCurationStatuses,
            include_evidence_chains: true,
            force_agent: forceAgent,
          }),
          'Unable to execute graph search for this space.',
        )
        setGraphSearch(searchResponse)

        const seedEntityIds = searchResponse.results
          .slice(0, MAX_SEEDED_SEARCH_RESULTS)
          .map((result) => result.entity_id)

        if (seedEntityIds.length === 0) {
          setRawGraph(emptyGraphModel())
          setSubgraphMeta(null)
        } else {
          await fetchSubgraph({
            mode: 'seeded',
            seed_entity_ids: seedEntityIds,
            depth: maxDepth,
            top_k: topK,
            curation_statuses: activeCurationStatuses,
            max_nodes: MAX_RENDER_NODES,
            max_edges: MAX_RENDER_EDGES,
          })
        }

        if (syncUrl) {
          updateQueryParams(
            router,
            spaceId,
            normalizedQuestion,
            topK,
            maxDepth,
            forceAgent,
            trustPreset,
          )
        }
      } catch (error) {
        setGraphSearchError(
          toErrorMessage(error, 'Unable to execute graph search for this space.'),
        )
      } finally {
        setIsSearching(false)
      }
    },
    [activeCurationStatuses, fetchSubgraph, loadStarterSubgraph, router, spaceId, trustPreset],
  )

  useEffect(() => {
    if (bootstrapRef.current) {
      return
    }
    bootstrapRef.current = true

    if (initialQuestion.trim().length > 0) {
      void runQuery({
        question: initialQuestion,
        topK: initialTopK,
        maxDepth: initialMaxDepth,
        forceAgent: initialForceAgent,
        syncUrl: false,
      })
      return
    }

    void loadStarterSubgraph()
  }, [
    initialForceAgent,
    initialMaxDepth,
    initialQuestion,
    initialTopK,
    loadStarterSubgraph,
    runQuery,
  ])

  useEffect(() => {
    if (!bootstrapRef.current) {
      return
    }
    if (trustPresetSyncRef.current === trustPreset) {
      return
    }
    trustPresetSyncRef.current = trustPreset

    if (questionInput.trim().length > 0) {
      void runQuery({
        question: questionInput,
        topK,
        maxDepth,
        forceAgent,
        syncUrl: true,
      })
      return
    }

    updateQueryParams(
      router,
      spaceId,
      '',
      topK,
      maxDepth,
      forceAgent,
      trustPreset,
    )
    void loadStarterSubgraph()
  }, [
    forceAgent,
    loadStarterSubgraph,
    maxDepth,
    questionInput,
    router,
    runQuery,
    spaceId,
    topK,
    trustPreset,
  ])

  const expandFromNode = useCallback(
    async (nodeId: string): Promise<void> => {
      setIsExpandingNodeId(nodeId)
      setGraphError(null)
      setGraphNotice(null)
      try {
        const response = await requestGraphDocument({
          mode: 'seeded',
          seed_entity_ids: [nodeId],
          depth: 1,
          top_k: Math.min(topK, DEFAULT_EXPAND_TOP_K),
          curation_statuses: activeCurationStatuses,
          max_nodes: MAX_RENDER_NODES,
          max_edges: MAX_RENDER_EDGES,
        })
        setRawGraph((current) => mergeGraphModels(current, response.model))
        setSubgraphMeta(response.meta)
      } catch (error) {
        setGraphError(
          toErrorMessage(
            error,
            'Unable to expand neighborhood for selected node.',
          ),
        )
      } finally {
        setIsExpandingNodeId(null)
      }
    },
    [activeCurationStatuses, requestGraphDocument, topK],
  )

  const onNodeClick = useCallback(
    (nodeId: string): void => {
      setSelectedNodeId(nodeId)
      setSelectedEdgeId(null)
      const selectedNode = rawGraph.nodeById[nodeId]
      if (!selectedNode || selectedNode.origin !== 'entity') {
        return
      }
      void expandFromNode(nodeId)
    },
    [expandFromNode, rawGraph],
  )

  const onEdgeClick = useCallback((edgeId: string): void => {
    setSelectedNodeId(null)
    setSelectedEdgeId(edgeId)
  }, [])

  const claimEvidenceByClaimId = useMemo(
    () => buildClaimEvidencePreviewIndex(rawGraph),
    [rawGraph],
  )

  const modeProjectedGraph = useMemo(
    () => projectGraphByDisplayMode(rawGraph, graphDisplayMode),
    [graphDisplayMode, rawGraph],
  )

  const availableRelationTypes = modeProjectedGraph.relationTypes
  const availableCurationStatuses = useMemo(() => {
    const merged = new Set<string>(ALL_GRAPH_STATUSES)
    for (const status of modeProjectedGraph.curationStatuses) {
      merged.add(status)
    }
    return [...merged]
  }, [modeProjectedGraph.curationStatuses])

  const filteredGraph = useMemo(
    () => filterGraphModel(modeProjectedGraph, relationTypeFilter, curationStatusFilter),
    [curationStatusFilter, modeProjectedGraph, relationTypeFilter],
  )

  const prunedGraph = useMemo(
    () =>
      pruneGraphModelForRender(
        filteredGraph,
        MAX_RENDER_NODES,
        MAX_RENDER_EDGES,
        selectedNodeId ? [selectedNodeId] : [],
      ),
    [filteredGraph, selectedNodeId],
  )

  const renderGraph = prunedGraph.model
  const claimNodeIdByClaimId = useMemo(() => {
    const index = new Map<string, string>()
    for (const node of renderGraph.nodes) {
      if (node.origin === 'claim' && node.claimId) {
        index.set(node.claimId, node.id)
      }
    }
    return index
  }, [renderGraph.nodes])

  const neighborhood = useMemo(() => {
    if (selectedEdgeId) {
      const selectedEdge = renderGraph.edgeById[selectedEdgeId]
      if (!selectedEdge) {
        return {
          nodeIds: new Set<string>(),
          edgeIds: new Set<string>(),
        }
      }

      const nodeIds = new Set<string>([selectedEdge.sourceId, selectedEdge.targetId])
      const edgeIds = new Set<string>([selectedEdge.id])

      if (selectedEdge.origin === 'canonical') {
        for (const claimId of canonicalClaimIds(renderGraph, selectedEdge.id)) {
          const claimNodeId = claimNodeIdByClaimId.get(claimId)
          if (claimNodeId) {
            nodeIds.add(claimNodeId)
          }
          for (const edge of renderGraph.edges) {
            if (!edge.claimId || edge.claimId !== claimId) {
              continue
            }
            if (edge.origin !== 'claim' && edge.origin !== 'evidence') {
              continue
            }
            edgeIds.add(edge.id)
            nodeIds.add(edge.sourceId)
            nodeIds.add(edge.targetId)
          }
        }
      }

      return { nodeIds, edgeIds }
    }

    const activeNeighborhoodNode = selectedNodeId ?? hoveredNodeId
    if (!activeNeighborhoodNode) {
      return {
        nodeIds: new Set<string>(),
        edgeIds: new Set<string>(),
      }
    }
    return getNeighborhood(renderGraph, activeNeighborhoodNode)
  }, [claimNodeIdByClaimId, hoveredNodeId, renderGraph, selectedEdgeId, selectedNodeId])

  const runSearch = useCallback(
    async (syncUrl = true): Promise<void> => {
      await runQuery({
        question: questionInput,
        topK,
        maxDepth,
        forceAgent,
        syncUrl,
      })
    },
    [forceAgent, maxDepth, questionInput, runQuery, topK],
  )

  const resetToStarter = useCallback((): void => {
    setQuestionInput('')
    setTopKInput(String(initialTopK))
    setMaxDepthInput(String(initialMaxDepth))
    setForceAgent(false)
    setGraphSearch(null)
    setGraphSearchError(null)
    updateQueryParams(
      router,
      spaceId,
      '',
      topK,
      maxDepth,
      false,
      trustPreset,
    )
    void loadStarterSubgraph()
  }, [
    initialMaxDepth,
    initialTopK,
    loadStarterSubgraph,
    maxDepth,
    router,
    spaceId,
    topK,
    trustPreset,
  ])

  const clearSelection = useCallback((): void => {
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
    setHoveredNodeId(null)
    setHoveredEdgeId(null)
  }, [])

  const onHoverNodeChange = useCallback(
    (nodeId: string | null): void => {
      if (selectedNodeId || selectedEdgeId) {
        return
      }
      setHoveredNodeId(nodeId)
    },
    [selectedEdgeId, selectedNodeId],
  )

  const onHoverEdgeChange = useCallback((edgeId: string | null): void => {
    setHoveredEdgeId(edgeId)
  }, [])

  const resetFilters = useCallback((): void => {
    setRelationTypeFilter(new Set())
    setCurationStatusFilter(new Set())
  }, [])

  const enableAllRelationTypes = useCallback((): void => {
    setRelationTypeFilter(new Set())
  }, [])

  const toggleRelationType = useCallback((relationType: string, checked: boolean): void => {
    setRelationTypeFilter((current) => {
      const hasExplicitFilter = current.size > 0
      const nextEnabled = hasExplicitFilter
        ? new Set(current)
        : new Set(availableRelationTypes)

      if (checked) {
        nextEnabled.add(relationType)
      } else {
        nextEnabled.delete(relationType)
      }

      if (
        nextEnabled.size === 0 ||
        nextEnabled.size >= availableRelationTypes.length
      ) {
        return new Set()
      }

      return nextEnabled
    })
  }, [availableRelationTypes])

  const toggleCurationStatus = useCallback((status: string, checked: boolean): void => {
    setCurationStatusFilter((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(status)
      } else {
        next.delete(status)
      }
      return next
    })
  }, [])

  const setTrustPreset = useCallback((preset: GraphTrustPreset): void => {
    setTrustPresetState(preset)
    const mappedStatuses = TRUST_PRESET_STATUS_MAP[preset]
    setCurationStatusFilter(new Set(mappedStatuses ?? []))
  }, [])

  const setGraphDisplayMode = useCallback((mode: GraphDisplayMode): void => {
    setGraphDisplayModeState(mode)
    setRelationTypeFilter(new Set())
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
    setHoveredNodeId(null)
    setHoveredEdgeId(null)
  }, [])

  const graphSearchResults = graphSearch?.results ?? []
  const isLoading = isLoadingGraph || isSearching
  const truncationNotice =
    prunedGraph.truncatedEdges ||
    prunedGraph.truncatedNodes ||
    subgraphMeta?.truncated_canonical_edges ||
    subgraphMeta?.truncated_entity_nodes

  return {
    questionInput,
    topKInput,
    maxDepthInput,
    forceAgent,
    trustPreset,
    graphDisplayMode,
    setQuestionInput,
    setTopKInput,
    setMaxDepthInput,
    setForceAgent,
    setTrustPreset,
    setGraphDisplayMode,
    topK,
    maxDepth,
    minDepth: MIN_DEPTH,
    maxDepthLimit: MAX_DEPTH,
    minTopK: MIN_TOP_K,
    maxTopKLimit: MAX_TOP_K,
    graphSearch,
    graphSearchResults,
    graphSearchError,
    graphError,
    graphNotice,
    isLoading,
    isExpandingNodeId,
    filteredGraph,
    renderGraph,
    neighborhood,
    selectedNodeId,
    subgraphMeta,
    truncationNotice,
    preCapNodeCount: Math.max(
      prunedGraph.preCapNodeCount,
      subgraphMeta?.pre_cap_entity_node_count ?? 0,
    ),
    preCapEdgeCount: Math.max(
      prunedGraph.preCapEdgeCount,
      subgraphMeta?.pre_cap_canonical_edge_count ?? 0,
    ),
    availableRelationTypes,
    availableCurationStatuses,
    relationTypeFilter,
    curationStatusFilter,
    onNodeClick,
    onEdgeClick,
    onHoverNodeChange,
    onHoverEdgeChange,
    clearSelection,
    claimEvidenceByClaimId,
    runSearch,
    resetToStarter,
    resetFilters,
    enableAllRelationTypes,
    toggleRelationType,
    toggleCurationStatus,
  }
}
