'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { GraphModel } from '@/lib/graph/model'
import { CytoscapeGraphViewAdapter } from '@/lib/graph/cytoscape-adapter'
import type { GraphHoverEvent } from '@/lib/graph/view-adapter'
import {
  buildGraphCanvasTooltip,
  type ClaimEvidencePreview,
  MAP_GRID_STYLE,
} from './knowledge-graph-canvas-tooltips'

interface KnowledgeGraphCanvasHover {
  nodeId: string | null
  edgeId: string | null
}

interface KnowledgeGraphCanvasProps {
  graph: GraphModel
  highlightedNodeIds: ReadonlySet<string>
  highlightedEdgeIds: ReadonlySet<string>
  onNodeClick: (nodeId: string) => void
  onEdgeClick?: (edgeId: string) => void
  onHoverChange?: (hover: KnowledgeGraphCanvasHover) => void
  claimEvidenceByClaimId?: Readonly<Record<string, ClaimEvidencePreview>>
  /** Called on any tap on the canvas (background, node, or edge). Use e.g. to collapse overlays. */
  onCanvasTap?: () => void
  chrome?: 'full' | 'minimal' | 'none'
  className?: string
}

export default function KnowledgeGraphCanvas({
  graph,
  highlightedNodeIds,
  highlightedEdgeIds,
  onNodeClick,
  onEdgeClick,
  onHoverChange,
  claimEvidenceByClaimId = {},
  onCanvasTap,
  chrome = 'full',
  className,
}: KnowledgeGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const adapterRef = useRef<CytoscapeGraphViewAdapter | null>(null)
  const [hoverEvent, setHoverEvent] = useState<GraphHoverEvent | null>(null)
  const hoverKeyRef = useRef<string>('none')
  const hoverStateRef = useRef<KnowledgeGraphCanvasHover>({
    nodeId: null,
    edgeId: null,
  })

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return undefined
    }

    const adapter = new CytoscapeGraphViewAdapter({
      onNodeClick: (nodeId) => {
        onNodeClick(nodeId)
        adapterRef.current?.focusNode(nodeId)
      },
      onEdgeClick,
      onCanvasTap,
      onHoverChange: (event: GraphHoverEvent | null) => {
        const nextHoverKey = event ? `${event.kind}:${event.id}` : 'none'
        if (nextHoverKey !== hoverKeyRef.current) {
          hoverKeyRef.current = nextHoverKey
          setHoverEvent(event)
        }
        const nextHoverState: KnowledgeGraphCanvasHover = {
          nodeId: !event || event.kind !== 'node' ? null : event.id,
          edgeId: !event || event.kind !== 'edge' ? null : event.id,
        }
        if (
          nextHoverState.nodeId !== hoverStateRef.current.nodeId ||
          nextHoverState.edgeId !== hoverStateRef.current.edgeId
        ) {
          hoverStateRef.current = nextHoverState
          onHoverChange?.(nextHoverState)
        }
      },
    })
    adapter.mount(container)
    adapterRef.current = adapter

    return () => {
      adapter.unmount()
      adapterRef.current = null
      hoverKeyRef.current = 'none'
      hoverStateRef.current = { nodeId: null, edgeId: null }
    }
  }, [onCanvasTap, onEdgeClick, onHoverChange, onNodeClick])

  useEffect(() => {
    adapterRef.current?.setGraph(graph)
  }, [graph])

  useEffect(() => {
    adapterRef.current?.setHighlight(highlightedNodeIds, highlightedEdgeIds)
  }, [highlightedEdgeIds, highlightedNodeIds])

  const hasRenderableGraph = graph.stats.nodeCount > 0

  const tooltip = useMemo(() => {
    const container = containerRef.current
    if (!container) {
      return null
    }
    const rect = container.getBoundingClientRect()
    return buildGraphCanvasTooltip({
      hoverEvent,
      containerWidth: rect.width,
      containerHeight: rect.height,
      graph,
      claimEvidenceByClaimId,
    })
  }, [claimEvidenceByClaimId, graph, hoverEvent])

  const isMinimalChrome = chrome === 'minimal'

  return (
    <div
      className={cn(
        'relative h-[560px] w-full overflow-hidden rounded-xl border border-border/80 bg-[linear-gradient(168deg,#f8fbfc_0%,#eef4f6_100%)] shadow-brand-sm',
        isMinimalChrome && 'shadow-none',
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 opacity-55" style={MAP_GRID_STYLE} />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_16%_14%,rgba(20,184,166,0.1),transparent_48%),radial-gradient(circle_at_84%_84%,rgba(59,130,246,0.06),transparent_44%)]" />
      {!isMinimalChrome && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-background/55 to-transparent" />
      )}
      <div ref={containerRef} className="relative z-10 size-full" />

      {chrome === 'full' ? (
        <div className="absolute left-3 top-3 z-20 flex items-center gap-2">
          <Badge variant="outline" className="bg-background/85 backdrop-blur">
            Interactive Graph
          </Badge>
          <div className="hidden text-xs text-muted-foreground md:block">
            Click a node to focus and expand. Edge labels appear on hover and focus.
          </div>
        </div>
      ) : null}
      {chrome === 'full' || chrome === 'minimal' ? (
        <div className="absolute right-3 top-3 z-20 flex flex-col items-end gap-2">
          <div className="inline-flex flex-col overflow-hidden rounded-lg border border-border/70 bg-background/90 shadow-brand-sm backdrop-blur">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Zoom in"
              disabled={!hasRenderableGraph}
              className="size-8 rounded-none p-0"
              onClick={() => adapterRef.current?.zoomIn()}
            >
              <Plus className="size-4" />
            </Button>
            <div className="h-px bg-border/70" />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Zoom out"
              disabled={!hasRenderableGraph}
              className="size-8 rounded-none p-0"
              onClick={() => adapterRef.current?.zoomOut()}
            >
              <Minus className="size-4" />
            </Button>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!hasRenderableGraph}
            className="h-8 bg-background/90 backdrop-blur"
            onClick={() => adapterRef.current?.fit()}
          >
            Fit View
          </Button>
        </div>
      ) : null}

      {!hasRenderableGraph ? (
        <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center p-8">
          <div className="max-w-sm rounded-xl border border-border/70 bg-background/90 px-6 py-4 text-center shadow-brand-sm backdrop-blur">
            <div className="text-sm font-semibold text-foreground">
              No graph elements in the current view
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Run a graph search, load the starter subgraph, or relax local filters.
            </div>
          </div>
        </div>
      ) : null}

      {tooltip && (
        <div
          className="pointer-events-none absolute z-30 w-[280px] rounded-lg border border-border/70 bg-background/95 p-3 shadow-brand-sm backdrop-blur"
          style={{
            left: `${tooltip.position.left}px`,
            top: `${tooltip.position.top}px`,
          }}
        >
          {tooltip.content}
        </div>
      )}
    </div>
  )
}
