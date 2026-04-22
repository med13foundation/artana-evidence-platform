import type { ReactNode } from 'react'
import { useCallback, useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import KnowledgeGraphCanvas from '@/components/knowledge-graph/KnowledgeGraphCanvas'
import {
  resolveEvidenceArticleUrlFromMetadata,
  type GraphEdge,
  type GraphModel,
} from '@/lib/graph/model'
import {
  edgeColorForRelationType,
  edgeVisualForStatus,
  nodeVisualForEntityType,
} from '@/lib/graph/style'
import { cn } from '@/lib/utils'
import type { KernelGraphDocumentMeta } from '@/types/kernel'
import type { ClaimEvidencePreview } from './use-knowledge-graph-controller'

interface KnowledgeGraphVisualizationProps {
  filteredGraph: GraphModel
  renderGraph: GraphModel
  subgraphMeta: KernelGraphDocumentMeta | null
  truncationNotice: boolean | undefined
  preCapNodeCount: number
  preCapEdgeCount: number
  isExpandingNodeId: string | null
  neighborhood: {
    nodeIds: Set<string>
    edgeIds: Set<string>
  }
  selectedNodeId: string | null
  onNodeClick: (nodeId: string) => void
  onEdgeClick: (edgeId: string) => void
  onHoverNodeChange: (nodeId: string | null) => void
  onHoverEdgeChange: (edgeId: string | null) => void
  onClearSelection: () => void
  claimEvidenceByClaimId: Readonly<Record<string, ClaimEvidencePreview>>
  /** Called when the user taps anywhere on the canvas (background, node, or edge). Use e.g. to collapse the controls panel. */
  onCanvasTap?: () => void
  topControls?: ReactNode
}

interface FocusInspectorProps {
  selectedNode: GraphModel['nodes'][number] | null
  selectedEdges: GraphEdge[]
  neighborhoodNodeCount: number
  onClearSelection: () => void
  className?: string
}

function confidenceValue(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`
}

function isGraphEdge(value: GraphEdge | undefined): value is GraphEdge {
  return Boolean(value)
}

const EVIDENCE_STRENGTH_LEGEND = [
  { label: 'High', width: 5, opacity: 0.95 },
  { label: 'Medium', width: 3.5, opacity: 0.72 },
  { label: 'Low', width: 2.2, opacity: 0.45 },
] as const

function FocusInspector({
  selectedNode,
  selectedEdges,
  neighborhoodNodeCount,
  onClearSelection,
  className,
}: FocusInspectorProps) {
  const selectedEvidenceCount = selectedEdges.reduce((sum, edge) => sum + edge.sourceCount, 0)
  const claimOverlayEdgeCount = selectedEdges.filter((edge) => edge.origin === 'claim').length
  const canonicalEdgeCount = selectedEdges.length - claimOverlayEdgeCount
  const curatedEdgeCount = selectedEdges.filter(
    (edge) => edge.curationStatus === 'APPROVED' || edge.curationStatus === 'UNDER_REVIEW',
  ).length
  const averageConfidence = selectedEdges.length
    ? selectedEdges.reduce((sum, edge) => sum + edge.confidence, 0) / selectedEdges.length
    : 0

  const relationBreakdown = useMemo(() => {
    const counts = new Map<string, number>()
    for (const edge of selectedEdges) {
      counts.set(edge.relationType, (counts.get(edge.relationType) ?? 0) + 1)
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 4)
  }, [selectedEdges])
  const selectedNodeType = selectedNode?.entityType.trim().toUpperCase() ?? null
  const selectedPaperArticleUrl =
    selectedNode && selectedNodeType === 'PAPER'
      ? resolveEvidenceArticleUrlFromMetadata(selectedNode.metadata)
      : null

  return (
    <div className={cn('rounded-xl border border-border/70 bg-background/85 p-4 backdrop-blur', className)}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Relation Inspect</div>
          <div className="text-sm font-semibold">Focus Mode</div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!selectedNode}
          onClick={onClearSelection}
        >
          Clear
        </Button>
      </div>
      {!selectedNode ? (
        <div className="rounded-lg border border-dashed border-border/70 bg-muted/35 p-3 text-xs text-muted-foreground">
          Select a node to isolate neighborhood evidence.
        </div>
      ) : (
        <div className="space-y-3 text-xs">
          <div>
            <div className="text-muted-foreground">{selectedNode.entityType}</div>
            <div className="text-sm font-semibold text-foreground">{selectedNode.label}</div>
            {selectedNodeType === 'PAPER' ? (
              selectedPaperArticleUrl ? (
                <a
                  href={selectedPaperArticleUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-1 inline-flex text-xs font-medium text-sky-400 underline-offset-2 hover:text-sky-300 hover:underline"
                >
                  Open article
                </a>
              ) : (
                <div className="mt-1 text-[11px] text-muted-foreground">
                  Article link unavailable in evidence metadata.
                </div>
              )
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/70 bg-muted/30 p-2">
            <div className="text-muted-foreground">Degree</div>
            <div className="text-right font-semibold">{selectedEdges.length}</div>
            <div className="text-muted-foreground">Evidence Sources</div>
            <div className="text-right font-semibold">{selectedEvidenceCount}</div>
            <div className="text-muted-foreground">Avg Confidence</div>
            <div className="text-right font-semibold">{confidenceValue(averageConfidence)}</div>
            <div className="text-muted-foreground">Curated Links</div>
            <div className="text-right font-semibold">{curatedEdgeCount}</div>
            <div className="text-muted-foreground">Claim Overlay Links</div>
            <div className="text-right font-semibold">
              {claimOverlayEdgeCount} / {canonicalEdgeCount} canonical
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={curatedEdgeCount > 0 ? 'default' : 'secondary'}>
              {curatedEdgeCount > 0 ? 'Curated Evidence Present' : 'Inferred / Draft Heavy'}
            </Badge>
            {claimOverlayEdgeCount > 0 ? (
              <Badge variant="secondary">Claim Overlay Present</Badge>
            ) : null}
            <Badge variant="outline">Neighborhood: {neighborhoodNodeCount} nodes</Badge>
          </div>
          <div className="space-y-1.5">
            <div className="font-medium text-foreground">Top Relation Types</div>
            {relationBreakdown.length === 0 ? (
              <div className="text-muted-foreground">No incident relations in view.</div>
            ) : (
              relationBreakdown.map(([relationType, count]) => (
                <div
                  key={relationType}
                  className="flex items-center justify-between rounded-md border border-border/60 px-2 py-1"
                >
                  <span className="truncate font-mono">{relationType}</span>
                  <span className="font-semibold">{count}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function KnowledgeGraphVisualization({
  filteredGraph,
  renderGraph,
  subgraphMeta,
  truncationNotice,
  preCapNodeCount,
  preCapEdgeCount,
  isExpandingNodeId,
  neighborhood,
  selectedNodeId,
  onNodeClick,
  onEdgeClick,
  onHoverNodeChange,
  onHoverEdgeChange,
  onClearSelection,
  claimEvidenceByClaimId,
  onCanvasTap,
  topControls,
}: KnowledgeGraphVisualizationProps) {
  const nodeLegend = useMemo(
    () =>
      [...new Set(renderGraph.nodes.map((node) => node.entityType))]
        .slice(0, 7)
        .map((entityType) => ({
          label: entityType,
          visual: nodeVisualForEntityType(entityType),
        })),
    [renderGraph.nodes],
  )

  const statusLegend = useMemo(
    () =>
      [...new Set(filteredGraph.edges.map((edge) => edge.curationStatus))]
        .slice(0, 5)
        .map((status) => ({
          label: status,
          visual: edgeVisualForStatus(status),
        })),
    [filteredGraph.edges],
  )

  const relationLegend = useMemo(
    () =>
      [...new Set(filteredGraph.edges.map((edge) => edge.relationType))]
        .slice(0, 5)
        .map((relationType) => ({
          label: relationType,
          color: edgeColorForRelationType(relationType),
        })),
    [filteredGraph.edges],
  )

  const selectedNode = selectedNodeId ? renderGraph.nodeById[selectedNodeId] ?? null : null
  const expandingNodeLabel = isExpandingNodeId
    ? (renderGraph.nodeById[isExpandingNodeId]?.label ?? 'selected node')
    : null
  const canonicalEdgeCount = filteredGraph.edges.filter((edge) => edge.origin === 'canonical').length
  const claimOverlayEdgeCount = filteredGraph.edges.filter((edge) => edge.origin === 'claim').length
  const evidenceOverlayEdgeCount = filteredGraph.edges.filter((edge) => edge.origin === 'evidence').length

  const selectedEdges = useMemo(
    () =>
      selectedNodeId
        ? [...neighborhood.edgeIds]
            .map((edgeId) => renderGraph.edgeById[edgeId])
            .filter(isGraphEdge)
        : [],
    [neighborhood.edgeIds, renderGraph.edgeById, selectedNodeId],
  )
  const handleCanvasHoverChange = useCallback(
    (hover: { nodeId: string | null; edgeId: string | null }) => {
      onHoverNodeChange(hover.nodeId)
      onHoverEdgeChange(hover.edgeId)
    },
    [onHoverEdgeChange, onHoverNodeChange],
  )

  return (
    <>
      <div className="relative overflow-hidden border-y border-border/70 bg-background/80">
        <KnowledgeGraphCanvas
          graph={renderGraph}
          highlightedNodeIds={neighborhood.nodeIds}
          highlightedEdgeIds={neighborhood.edgeIds}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onHoverChange={handleCanvasHoverChange}
          claimEvidenceByClaimId={claimEvidenceByClaimId}
          onCanvasTap={onCanvasTap}
          chrome="minimal"
          className="h-[calc(100svh-72px)] min-h-[620px] rounded-none border-0 bg-transparent"
        />

        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 p-3 sm:p-4">
          <div className="mr-auto w-full max-w-[1700px] space-y-3">
            <div className="pointer-events-none flex flex-col gap-2 lg:flex-row lg:items-start">
              {topControls ? (
                <div className="pointer-events-auto shrink-0">{topControls}</div>
              ) : null}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-center gap-2 overflow-x-auto pb-1 text-xs">
                  <Badge
                    variant="outline"
                    className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                  >
                    Entities: {filteredGraph.stats.nodeCount}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                  >
                    Relations: {filteredGraph.stats.edgeCount}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                  >
                    Canonical: {canonicalEdgeCount}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                  >
                    Claim Overlay: {claimOverlayEdgeCount}
                  </Badge>
                  {evidenceOverlayEdgeCount > 0 ? (
                    <Badge
                      variant="outline"
                      className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                    >
                      Evidence Overlay: {evidenceOverlayEdgeCount}
                    </Badge>
                  ) : null}
                  <Badge
                    variant="outline"
                    className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                  >
                    Rendered: {renderGraph.stats.nodeCount} nodes / {renderGraph.stats.edgeCount} edges
                  </Badge>
                  {subgraphMeta ? (
                    <Badge
                      variant="outline"
                      className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                    >
                      Mode: {subgraphMeta.mode} • Depth {subgraphMeta.requested_depth} • Top K{' '}
                      {subgraphMeta.requested_top_k}
                    </Badge>
                  ) : null}
                  {truncationNotice ? (
                    <Badge
                      variant="secondary"
                      className="shrink-0 rounded-full bg-accent/90 shadow-brand-sm"
                    >
                      Truncated (pre-cap: {preCapNodeCount} nodes / {preCapEdgeCount} edges)
                    </Badge>
                  ) : null}
                  {isExpandingNodeId ? (
                    <Badge
                      variant="outline"
                      className="shrink-0 rounded-full bg-background/95 shadow-brand-sm"
                    >
                      Expanding {expandingNodeLabel}
                    </Badge>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 hidden p-3 sm:block lg:p-4">
          <div className="mx-auto w-full max-w-[1700px]">
            <div className="pointer-events-auto max-w-4xl rounded-xl border border-border/70 bg-background/85 px-3 py-2 text-xs text-muted-foreground backdrop-blur">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium text-foreground">Legend</span>
                {nodeLegend.map((item) => (
                  <span key={item.label} className="inline-flex items-center gap-1.5">
                    <span
                      className="size-2.5 rounded-full border border-black/10"
                      style={{ backgroundColor: item.visual.fillColor }}
                    />
                    <span>{item.label}</span>
                  </span>
                ))}
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2.5 w-3.5 rounded-sm border-2"
                    style={{
                      backgroundColor: '#e2e8f0',
                      borderColor: '#ca8a04',
                    }}
                  />
                  <span>Claim node (rounded rectangle, border = polarity)</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-0 w-4 border-t-2"
                    style={{
                      borderTopColor: '#475569',
                      borderTopStyle: 'dashed',
                    }}
                  />
                  <span>Claim edge (participant role → claim)</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-0 w-4 border-t-[3px]"
                    style={{
                      borderTopColor: '#f59e0b',
                      borderTopStyle: 'solid',
                    }}
                  />
                  <span>Conflict edge (support + refute)</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-0 w-4 border-t-2"
                    style={{
                      borderTopColor: '#0ea5e9',
                      borderTopStyle: 'dotted',
                    }}
                  />
                  <span>Evidence edge (SUPPORTED_BY / DERIVED_FROM)</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-foreground">Confidence strength:</span>
                  {EVIDENCE_STRENGTH_LEGEND.map((item) => (
                    <span key={item.label} className="inline-flex items-center gap-1">
                      <span
                        className="h-0 w-4 border-t"
                        style={{
                          borderTopWidth: item.width,
                          borderTopColor: '#475569',
                          opacity: item.opacity,
                        }}
                      />
                      <span>{item.label}</span>
                    </span>
                  ))}
                </span>
                {statusLegend.map((item) => (
                  <span key={item.label} className="inline-flex items-center gap-1.5">
                    <span
                      className="h-0 w-4 border-t-2"
                      style={{
                        borderTopColor: '#475569',
                        borderTopStyle: item.visual.lineStyle,
                        opacity: item.visual.opacity,
                      }}
                    />
                    <span>{item.label}</span>
                  </span>
                ))}
                {relationLegend.map((item) => (
                  <span key={item.label} className="inline-flex items-center gap-1.5">
                    <span
                      className="h-0 w-4 border-t-2"
                      style={{
                        borderTopColor: item.color,
                        borderTopStyle: 'solid',
                      }}
                    />
                    <span>{item.label}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="pointer-events-none absolute bottom-0 right-0 z-30 hidden p-3 lg:block lg:p-4">
          <FocusInspector
            selectedNode={selectedNode}
            selectedEdges={selectedEdges}
            neighborhoodNodeCount={neighborhood.nodeIds.size}
            onClearSelection={onClearSelection}
            className="pointer-events-auto w-[350px]"
          />
        </div>
      </div>

      <div className="p-3 sm:hidden">
        <FocusInspector
          selectedNode={selectedNode}
          selectedEdges={selectedEdges}
          neighborhoodNodeCount={neighborhood.nodeIds.size}
          onClearSelection={onClearSelection}
        />
      </div>
    </>
  )
}
