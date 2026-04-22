import cytoscape, {
  type Core,
  type EdgeSingular,
  type ElementDefinition,
  type EventObjectEdge,
  type EventObjectNode,
  type LayoutOptions,
} from 'cytoscape'
import type { GraphEdge, GraphModel, GraphNode } from '@/lib/graph/model'
import {
  edgeOpacityForConfidence,
  edgeColorForRelationType,
  edgeWidthForStrength,
  edgeVisualForStatus,
  nodeVisualForEntityType,
} from '@/lib/graph/style'
import type {
  GraphInteractionHandlers,
  GraphViewAdapter,
  HoverElementKind,
} from '@/lib/graph/view-adapter'

const CY_NODE_HIGHLIGHT_CLASS = 'kg-highlight'
const CY_NODE_DIM_CLASS = 'kg-dim'
const CY_EDGE_HIGHLIGHT_CLASS = 'kg-highlight'
const CY_EDGE_DIM_CLASS = 'kg-dim'
const CY_EDGE_FOCUS_LABEL_CLASS = 'kg-edge-label-focus'
const CY_EDGE_HOVER_LABEL_CLASS = 'kg-edge-label-hover'
const CY_NODE_HOVER_CLASS = 'kg-node-hover'
const CY_EDGE_HOVER_CLASS = 'kg-edge-hover'
const CY_EDGE_CONFLICT_CLASS = 'kg-edge-conflict'

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

function nodeSizeForDegree(degree: number, maxDegree: number): number {
  if (maxDegree <= 0) {
    return 28
  }
  const ratio = Math.max(0, Math.min(1, degree / maxDegree))
  return Math.round(24 + Math.sqrt(ratio) * 42)
}

function sizeForFocus(baseSize: number): number {
  return Math.round(baseSize * 1.12)
}

function nodeShapeClass(shape: string): string {
  return `kg-shape-${shape}`
}

function nodeOriginClass(node: GraphNode): string {
  if (node.origin === 'claim') {
    return 'kg-node-origin-claim'
  }
  if (node.origin === 'evidence') {
    return 'kg-node-origin-evidence'
  }
  return 'kg-node-origin-entity'
}

function nodeClaimPolarityClass(node: GraphNode): string {
  if (node.origin !== 'claim' || !node.claimPolarity) {
    return 'kg-node-claim-polarity-none'
  }
  const normalized = normalizeToken(node.claimPolarity)
  return `kg-node-claim-polarity-${normalized}`
}

function edgeStatusClass(status: string): string {
  return `kg-edge-status-${normalizeToken(status)}`
}

function edgeLineStyleClass(lineStyle: string): string {
  return `kg-edge-style-${lineStyle}`
}

function edgeOriginClass(edge: GraphEdge): string {
  if (edge.origin === 'claim') {
    return 'kg-edge-origin-claim'
  }
  if (edge.origin === 'evidence') {
    return 'kg-edge-origin-evidence'
  }
  return 'kg-edge-origin-canonical'
}

function edgeConflictClass(edge: GraphEdge): string {
  if (edge.origin === 'canonical' && edge.hasConflict) {
    return CY_EDGE_CONFLICT_CLASS
  }
  return ''
}

function canonicalEdgeLabel(edge: GraphEdge): string {
  const conflictSuffix = edge.hasConflict ? ' • CONFLICT' : ''
  if (edge.canonicalClaimCount <= 0) {
    return `${edge.relationType}${conflictSuffix}`
  }
  const suffix = edge.canonicalClaimCount === 1 ? 'claim' : 'claims'
  return `${edge.relationType} (${edge.canonicalClaimCount} ${suffix})${conflictSuffix}`
}

function buildLayoutOptions(model: GraphModel): LayoutOptions {
  const nodeCount = model.nodes.length
  const edgeCount = model.edges.length
  const elementCount = model.nodes.length + model.edges.length
  const shouldAnimate = elementCount <= 120
  const uniqueDegrees = new Set<number>(
    model.nodes.map((node) => model.incidentEdges[node.id]?.length ?? 0),
  )
  const hasDegreeVariance = uniqueDegrees.size > 1

  const circleLayout = {
    name: 'circle',
    fit: true,
    padding: 52,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    spacingFactor: 1.25,
    animate: shouldAnimate,
    animationDuration: 240,
  } as LayoutOptions

  if (edgeCount === 0) {
    return {
      name: 'grid',
      fit: true,
      padding: 40,
      avoidOverlap: true,
      animate: shouldAnimate,
      animationDuration: 220,
    } as LayoutOptions
  }
  if (nodeCount <= 3 || !hasDegreeVariance) {
    return circleLayout
  }
  if (nodeCount <= 14 && edgeCount <= 24) {
    return {
      name: 'concentric',
      fit: true,
      avoidOverlap: true,
      minNodeSpacing: 48,
      padding: 56,
      animate: shouldAnimate,
      animationDuration: 260,
      concentric: (node: { data: (key: string) => unknown }) => {
        const degree = node.data('degree')
        return typeof degree === 'number' ? degree : 1
      },
      levelWidth: () => 1,
      startAngle: (3 * Math.PI) / 2,
      sweep: Math.PI * 2,
      clockwise: true,
    } as LayoutOptions
  }
  return {
    name: 'cose',
    animate: shouldAnimate,
    animationDuration: 320,
    fit: true,
    padding: 34,
    nodeRepulsion: 7800,
    idealEdgeLength: 146,
    edgeElasticity: 75,
    gravity: 0.35,
    nestingFactor: 0.9,
    randomize: false,
  } as LayoutOptions
}

function buildElements(model: GraphModel): ElementDefinition[] {
  const degreeByNodeId: Record<string, number> = {}
  let maxDegree = 0
  for (const node of model.nodes) {
    const degree = model.incidentEdges[node.id]?.length ?? 0
    degreeByNodeId[node.id] = degree
    maxDegree = Math.max(maxDegree, degree)
  }

  const nodeElements: ElementDefinition[] = model.nodes.map((node) => {
    const visual = nodeVisualForEntityType(node.entityType)
    const isClaimNode = node.origin === 'claim'
    const nodeShape = isClaimNode ? 'round-rectangle' : visual.shape
    const nodeLabel = isClaimNode ? 'Claim' : node.label
    const nodeFillColor = isClaimNode ? '#e2e8f0' : visual.fillColor
    const nodeBorderColor = isClaimNode ? '#475569' : visual.borderColor
    const degree = degreeByNodeId[node.id] ?? 0
    const size = nodeSizeForDegree(degree, maxDegree)

    return {
      classes: [
        nodeShapeClass(nodeShape),
        nodeOriginClass(node),
        nodeClaimPolarityClass(node),
      ].join(' '),
      data: {
        id: node.id,
        label: nodeLabel,
        entityType: node.entityType,
        colorTop: nodeFillColor,
        borderColor: nodeBorderColor,
        size,
        sizeSelected: sizeForFocus(size),
        degree,
      },
      grabbable: true,
    }
  })

  const edgeElements: ElementDefinition[] = model.edges.map((edge) => {
    const statusVisual = edgeVisualForStatus(edge.curationStatus)
    const opacityForStatus = Math.max(0.12, statusVisual.opacity / 0.9)
    const edgeOpacity = Number(
      (edgeOpacityForConfidence(edge.confidence) * opacityForStatus).toFixed(2),
    )
    const edgeWidth = edgeWidthForStrength(edge.confidence, edge.sourceCount)

    return {
      classes: [
        edgeStatusClass(edge.curationStatus),
        edgeLineStyleClass(statusVisual.lineStyle),
        edgeOriginClass(edge),
        edgeConflictClass(edge),
      ].join(' '),
      data: {
        id: edge.id,
        source: edge.sourceId,
        target: edge.targetId,
        label:
          edge.origin === 'claim'
            ? `Claim • ${edge.claimParticipantRole ?? edge.relationType}`
            : edge.origin === 'evidence'
              ? `Evidence • ${edge.relationType}`
              : canonicalEdgeLabel(edge),
        curationStatus: edge.curationStatus,
        confidence: edge.confidence,
        color: edgeColorForRelationType(edge.relationType),
        opacity: edgeOpacity,
        width: edgeWidth,
      },
    }
  })

  return [...nodeElements, ...edgeElements]
}

function hoverCoordinatesForNode(event: EventObjectNode): { x: number; y: number } {
  return {
    x: event.renderedPosition.x,
    y: event.renderedPosition.y,
  }
}

function hoverCoordinatesForEdge(event: EventObjectEdge): { x: number; y: number } {
  if (event.renderedPosition) {
    return {
      x: event.renderedPosition.x,
      y: event.renderedPosition.y,
    }
  }
  const midpoint = event.target.midpoint()
  return {
    x: midpoint.x,
    y: midpoint.y,
  }
}

function emitHover(
  handlers: GraphInteractionHandlers,
  kind: HoverElementKind,
  id: string,
  x: number,
  y: number,
): void {
  handlers.onHoverChange?.({
    kind,
    id,
    containerX: x,
    containerY: y,
  })
}

function applyClassHighlight(
  cy: Core,
  highlightedNodeIds: ReadonlySet<string>,
  highlightedEdgeIds: ReadonlySet<string>,
): void {
  cy.nodes().removeClass(CY_NODE_HIGHLIGHT_CLASS).removeClass(CY_NODE_DIM_CLASS)
  cy.edges()
    .removeClass(CY_EDGE_HIGHLIGHT_CLASS)
    .removeClass(CY_EDGE_DIM_CLASS)
    .removeClass(CY_EDGE_FOCUS_LABEL_CLASS)

  const nodeHighlights = cy.nodes().filter((node) => highlightedNodeIds.has(node.id()))
  const edgeHighlights = cy.edges().filter((edge) => highlightedEdgeIds.has(edge.id()))
  const hasNodeHighlights = nodeHighlights.length > 0
  const hasEdgeHighlights = edgeHighlights.length > 0
  if (!hasNodeHighlights && !hasEdgeHighlights) {
    return
  }

  nodeHighlights.addClass(CY_NODE_HIGHLIGHT_CLASS)
  edgeHighlights.addClass(CY_EDGE_HIGHLIGHT_CLASS)
  edgeHighlights.addClass(CY_EDGE_FOCUS_LABEL_CLASS)
  cy.nodes().not(nodeHighlights).addClass(CY_NODE_DIM_CLASS)
  cy.edges().not(edgeHighlights).addClass(CY_EDGE_DIM_CLASS)
}

export class CytoscapeGraphViewAdapter implements GraphViewAdapter {
  private cy: Core | null = null
  private readonly handlers: GraphInteractionHandlers
  private graph: GraphModel | null = null
  private highlightSignature = ''
  private hoveredNodeId: string | null = null
  private hoveredEdgeId: string | null = null
  private suppressHoverUntil = 0
  private fallbackFitTimers: number[] = []

  public constructor(handlers: GraphInteractionHandlers) {
    this.handlers = handlers
  }

  public mount(container: HTMLElement): void {
    if (this.cy) {
      return
    }

    this.cy = cytoscape({
      container,
      elements: [],
      autoungrabify: false,
      boxSelectionEnabled: false,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(colorTop)',
            'background-opacity': 0.98,
            label: 'data(label)',
            color: '#0f172a',
            'font-size': '11px',
            'font-weight': 700,
            'text-wrap': 'wrap',
            'text-max-width': '125px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 7,
            width: 'data(size)',
            height: 'data(size)',
            'border-color': 'data(borderColor)',
            'border-width': 2.6,
            'text-background-color': '#f8fafc',
            'text-background-opacity': 0.84,
            'text-background-padding': '2.5px',
            'text-outline-color': '#f8fafc',
            'text-outline-opacity': 1,
            'text-outline-width': 1.3,
            'overlay-opacity': 0,
          },
        },
        {
          selector: 'node.kg-shape-ellipse',
          style: {
            shape: 'ellipse',
          },
        },
        {
          selector: 'node.kg-shape-round-rectangle',
          style: {
            shape: 'round-rectangle',
          },
        },
        {
          selector: 'node.kg-node-origin-claim',
          style: {
            'background-color': '#e2e8f0',
            'background-opacity': 0.96,
            color: '#0f172a',
            'font-size': '10px',
            'font-weight': 800,
            'text-wrap': 'none',
            'text-background-color': '#cbd5e1',
            'text-background-opacity': 0.92,
            'text-outline-color': '#e2e8f0',
            'text-outline-width': 1,
            'text-margin-y': 5,
            'border-width': 3.8,
          },
        },
        {
          selector: 'node.kg-node-origin-evidence',
          style: {
            'background-color': '#e2e8f0',
            'background-opacity': 0.96,
            color: '#0f172a',
            'font-size': '10px',
            'font-weight': 700,
            'text-wrap': 'wrap',
            'text-max-width': '150px',
            'text-background-color': '#cbd5e1',
            'text-background-opacity': 0.9,
            'text-outline-color': '#e2e8f0',
            'text-outline-width': 1,
            'border-color': '#64748b',
            'border-width': 3.2,
          },
        },
        {
          selector: 'node.kg-node-claim-polarity-support',
          style: {
            'border-color': '#15803d',
          },
        },
        {
          selector: 'node.kg-node-claim-polarity-refute',
          style: {
            'border-color': '#dc2626',
          },
        },
        {
          selector: 'node.kg-node-claim-polarity-hypothesis',
          style: {
            'border-color': '#ca8a04',
          },
        },
        {
          selector: 'node.kg-node-claim-polarity-uncertain',
          style: {
            'border-color': '#64748b',
          },
        },
        {
          selector: 'node.kg-shape-diamond',
          style: {
            shape: 'diamond',
          },
        },
        {
          selector: 'node.kg-shape-hexagon',
          style: {
            shape: 'hexagon',
          },
        },
        {
          selector: 'node.kg-shape-triangle',
          style: {
            shape: 'triangle',
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'line-color': 'data(color)',
            width: 'data(width)',
            opacity: (edge: EdgeSingular) => {
              const value = edge.data('opacity')
              return typeof value === 'number' ? value : 0.9
            },
            'line-style': 'solid',
            'target-arrow-color': 'data(color)',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.9,
            label: '',
            color: '#1f2937',
            'font-size': '9px',
            'font-weight': 600,
            'text-background-color': '#f8fafc',
            'text-background-opacity': 0,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate',
            'text-events': 'no',
            'overlay-opacity': 0,
          },
        },
        {
          selector: 'edge.kg-edge-style-dashed',
          style: {
            'line-style': 'dashed',
          },
        },
        {
          selector: 'edge.kg-edge-style-dotted',
          style: {
            'line-style': 'dotted',
          },
        },
        {
          selector: 'edge.kg-edge-origin-claim',
          style: {
            'line-style': 'dashed',
            'line-dash-pattern': [8, 4],
            'target-arrow-shape': 'vee',
            'arrow-scale': 0.8,
            opacity: 0.9,
          },
        },
        {
          selector: 'edge.kg-edge-origin-evidence',
          style: {
            'line-style': 'dotted',
            'line-dash-pattern': [4, 3],
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.72,
            opacity: 0.9,
          },
        },
        {
          selector: `edge.${CY_EDGE_CONFLICT_CLASS}`,
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            width: 5.4,
            opacity: 0.98,
          },
        },
        {
          selector: `edge.${CY_EDGE_FOCUS_LABEL_CLASS}, edge.${CY_EDGE_HOVER_LABEL_CLASS}, edge:selected`,
          style: {
            label: 'data(label)',
            'text-background-opacity': 0.94,
            'font-weight': 700,
          },
        },
        {
          selector: `node.${CY_NODE_HOVER_CLASS}`,
          style: {
            'border-width': 4,
            'underlay-color': '#0f172a',
            'underlay-opacity': 0.14,
            'underlay-padding': 3,
          },
        },
        {
          selector: `edge.${CY_EDGE_HOVER_CLASS}`,
          style: {
            opacity: 0.94,
            'z-index': 24,
          },
        },
        {
          selector: `node.${CY_NODE_HIGHLIGHT_CLASS}`,
          style: {
            'border-color': '#0f766e',
            'border-width': 4.2,
            opacity: 1,
            'underlay-color': '#0f766e',
            'underlay-opacity': 0.16,
            'underlay-padding': 4,
            'z-index': 26,
          },
        },
        {
          selector: `edge.${CY_EDGE_HIGHLIGHT_CLASS}`,
          style: {
            width: 6.4,
            opacity: 1,
            'z-index': 20,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#0f766e',
            'border-width': 5,
            width: 'data(sizeSelected)',
            height: 'data(sizeSelected)',
            opacity: 1,
            'underlay-color': '#0f766e',
            'underlay-opacity': 0.2,
            'underlay-padding': 5,
            'z-index': 28,
          },
        },
        {
          selector: `node.${CY_NODE_DIM_CLASS}`,
          style: {
            opacity: 0.32,
            'text-opacity': 0.45,
          },
        },
        {
          selector: `edge.${CY_EDGE_DIM_CLASS}`,
          style: {
            opacity: 0.24,
            'text-opacity': 0,
          },
        },
        {
          selector: `node.${CY_NODE_DIM_CLASS}.${CY_NODE_HOVER_CLASS}`,
          style: {
            opacity: 0.9,
            'text-opacity': 1,
          },
        },
        {
          selector: `edge.${CY_EDGE_DIM_CLASS}.${CY_EDGE_HOVER_CLASS}`,
          style: {
            opacity: 0.92,
          },
        },
      ],
      layout: { name: 'grid', fit: true, padding: 20 },
      minZoom: 0.1,
      maxZoom: 4,
    })

    const suppressHoverFor = (durationMs: number): void => {
      this.suppressHoverUntil = Date.now() + durationMs
      this.handlers.onHoverChange?.(null)
    }

    this.cy.on('pan zoom dragpan', () => {
      suppressHoverFor(90)
    })
    this.cy.on('boxstart', () => {
      suppressHoverFor(90)
    })

    this.cy.on('tap', () => {
      this.handlers.onCanvasTap?.()
    })
    this.cy.on('tap', 'node', (event: EventObjectNode) => {
      this.handlers.onNodeClick?.(event.target.id())
    })
    this.cy.on('tap', 'edge', (event: EventObjectEdge) => {
      this.handlers.onEdgeClick?.(event.target.id())
      const neighborhood = event.target.connectedNodes().add(event.target)
      this.cy?.stop()
      this.cy?.animate({
        fit: {
          eles: neighborhood,
          padding: 92,
        },
        duration: 320,
        easing: 'ease-out-cubic',
      })
    })
    this.cy.on('mouseover', 'node', (event: EventObjectNode) => {
      if (Date.now() < this.suppressHoverUntil) {
        return
      }
      const nodeId = event.target.id()
      const coordinates = hoverCoordinatesForNode(event)
      if (this.hoveredNodeId && this.hoveredNodeId !== nodeId) {
        this.cy?.getElementById(this.hoveredNodeId).removeClass(CY_NODE_HOVER_CLASS)
      }
      this.hoveredNodeId = nodeId
      event.target.addClass(CY_NODE_HOVER_CLASS)
      event.target.connectedEdges().addClass(CY_EDGE_HOVER_LABEL_CLASS)
      event.target.connectedEdges().addClass(CY_EDGE_HOVER_CLASS)
      emitHover(this.handlers, 'node', nodeId, coordinates.x, coordinates.y)
    })
    this.cy.on('mouseout', 'node', (event: EventObjectNode) => {
      if (Date.now() < this.suppressHoverUntil) {
        return
      }
      event.target.removeClass(CY_NODE_HOVER_CLASS)
      event.target.connectedEdges().removeClass(CY_EDGE_HOVER_LABEL_CLASS)
      event.target.connectedEdges().removeClass(CY_EDGE_HOVER_CLASS)
      if (this.hoveredNodeId === event.target.id()) {
        this.hoveredNodeId = null
      }
      this.handlers.onHoverChange?.(null)
    })
    this.cy.on('mouseover', 'edge', (event: EventObjectEdge) => {
      if (Date.now() < this.suppressHoverUntil) {
        return
      }
      const edgeId = event.target.id()
      const coordinates = hoverCoordinatesForEdge(event)
      if (this.hoveredEdgeId && this.hoveredEdgeId !== edgeId) {
        this.cy?.getElementById(this.hoveredEdgeId).removeClass(CY_EDGE_HOVER_CLASS)
        this.cy?.getElementById(this.hoveredEdgeId).removeClass(CY_EDGE_HOVER_LABEL_CLASS)
      }
      this.hoveredEdgeId = edgeId
      event.target.addClass(CY_EDGE_HOVER_LABEL_CLASS)
      event.target.addClass(CY_EDGE_HOVER_CLASS)
      emitHover(this.handlers, 'edge', edgeId, coordinates.x, coordinates.y)
    })
    this.cy.on('mouseout', 'edge', (event: EventObjectEdge) => {
      if (Date.now() < this.suppressHoverUntil) {
        return
      }
      event.target.removeClass(CY_EDGE_HOVER_LABEL_CLASS)
      event.target.removeClass(CY_EDGE_HOVER_CLASS)
      if (this.hoveredEdgeId === event.target.id()) {
        this.hoveredEdgeId = null
      }
      this.handlers.onHoverChange?.(null)
    })
  }

  public unmount(): void {
    this.clearFallbackFitTasks()
    this.handlers.onHoverChange?.(null)
    this.cy?.destroy()
    this.cy = null
    this.highlightSignature = ''
    this.hoveredNodeId = null
    this.hoveredEdgeId = null
    this.suppressHoverUntil = 0
  }

  public setGraph(model: GraphModel): void {
    this.graph = model
    this.highlightSignature = ''
    this.hoveredNodeId = null
    this.hoveredEdgeId = null
    this.suppressHoverUntil = Date.now() + 120
    this.handlers.onHoverChange?.(null)
    if (!this.cy) {
      return
    }

    const elements = buildElements(model)
    this.cy.batch(() => {
      this.cy?.elements().remove()
      this.cy?.add(elements)
    })

    this.clearFallbackFitTasks()
    this.cy.resize()
    const layout = this.cy.layout(buildLayoutOptions(model))
    layout.on('layoutstop', () => {
      this.cy?.fit(undefined, 36)
    })
    layout.run()
    this.scheduleFallbackFitPasses()
  }

  public setHighlight(
    highlightedNodeIds: ReadonlySet<string>,
    highlightedEdgeIds: ReadonlySet<string>,
  ): void {
    if (!this.cy) {
      return
    }
    const nextSignature = `${[...highlightedNodeIds].sort().join('|')}::${[...highlightedEdgeIds]
      .sort()
      .join('|')}`
    if (nextSignature === this.highlightSignature) {
      return
    }
    this.highlightSignature = nextSignature
    applyClassHighlight(this.cy, highlightedNodeIds, highlightedEdgeIds)
  }

  public focusNode(nodeId: string): void {
    if (!this.cy) {
      return
    }
    const node = this.cy.getElementById(nodeId)
    if (!node.nonempty()) {
      return
    }
    node.select()
    const neighborhood = node.closedNeighborhood()
    this.cy.stop()
    this.cy.animate({
      fit: {
        eles: neighborhood,
        padding: 84,
      },
      duration: 380,
      easing: 'ease-out-cubic',
    })
  }

  public fit(): void {
    if (!this.cy || !this.graph || this.graph.edges.length + this.graph.nodes.length === 0) {
      return
    }
    this.cy.fit(undefined, 32)
  }

  public zoomIn(): void {
    this.zoomBy(1.18)
  }

  public zoomOut(): void {
    this.zoomBy(1 / 1.18)
  }

  private clearFallbackFitTasks(): void {
    if (this.fallbackFitTimers.length === 0) {
      return
    }
    for (const timerId of this.fallbackFitTimers) {
      window.clearTimeout(timerId)
    }
    this.fallbackFitTimers = []
  }

  private scheduleFallbackFitPasses(): void {
    if (!this.cy || !this.graph || this.graph.stats.nodeCount === 0) {
      return
    }

    const runFitPass = (): void => {
      if (!this.cy || !this.graph || this.graph.stats.nodeCount === 0) {
        return
      }
      this.cy.resize()
      this.cy.fit(undefined, 36)
    }

    window.requestAnimationFrame(runFitPass)
    this.fallbackFitTimers.push(window.setTimeout(runFitPass, 140))
    this.fallbackFitTimers.push(window.setTimeout(runFitPass, 340))
  }

  private zoomBy(scaleFactor: number): void {
    if (!this.cy || !this.graph || this.graph.stats.nodeCount === 0) {
      return
    }

    const currentZoom = this.cy.zoom()
    const nextZoom = Math.max(
      this.cy.minZoom(),
      Math.min(this.cy.maxZoom(), currentZoom * scaleFactor),
    )
    if (Math.abs(nextZoom - currentZoom) < 0.001) {
      return
    }

    this.cy.zoom({
      level: nextZoom,
      renderedPosition: {
        x: this.cy.width() / 2,
        y: this.cy.height() / 2,
      },
    })
  }
}

export function relationDetails(edge: GraphEdge): string {
  const confidencePct = (edge.confidence * 100).toFixed(1)
  return `${edge.relationType} (${edge.curationStatus}, ${confidencePct}%)`
}
