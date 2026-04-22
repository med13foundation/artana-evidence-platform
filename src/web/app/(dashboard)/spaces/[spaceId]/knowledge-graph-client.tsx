'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useState } from 'react'
import { Filter, PanelLeftClose, PanelLeftOpen, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { GraphDisplayMode } from '@/lib/graph/model'
import { cn } from '@/lib/utils'

import { KnowledgeGraphFeedbackCards } from './knowledge-graph-feedback-cards'
import { KnowledgeGraphFiltersCard } from './knowledge-graph-filters-card'
import { KnowledgeGraphQueryCard } from './knowledge-graph-query-card'
import { KnowledgeGraphSearchResultsCard } from './knowledge-graph-search-results-card'
import { KnowledgeGraphVisualization } from './knowledge-graph-visualization'
import { useKnowledgeGraphController } from './use-knowledge-graph-controller'
import type { GraphTrustPreset } from './use-knowledge-graph-controller'

interface KnowledgeGraphClientProps {
  spaceId: string
  initialQuestion?: string
  initialTopK?: number
  initialMaxDepth?: number
  initialForceAgent?: boolean
  initialTrustPreset?: GraphTrustPreset
}

export default function KnowledgeGraphClient({
  spaceId,
  initialQuestion = '',
  initialTopK = 25,
  initialMaxDepth = 2,
  initialForceAgent = false,
  initialTrustPreset = 'ALL',
}: KnowledgeGraphClientProps) {
  const router = useRouter()
  const controller = useKnowledgeGraphController({
    spaceId,
    router,
    initialQuestion,
    initialTopK,
    initialMaxDepth,
    initialForceAgent,
    initialTrustPreset,
  })
  const [showControlsPanel, setShowControlsPanel] = useState(true)
  const [activeControlsTab, setActiveControlsTab] = useState<'search' | 'filters'>('search')
  const handleCanvasTap = useCallback(() => setShowControlsPanel(false), [])
  const displayModeOptions: Array<{ value: GraphDisplayMode; label: string }> = [
    { value: 'RELATIONS_ONLY', label: 'Relations only' },
    { value: 'CLAIMS', label: 'Claims' },
    { value: 'EVIDENCE', label: 'Evidence' },
  ]

  return (
    <div className="space-y-4 px-0">
      <div className="px-3 sm:px-4 lg:px-6">
        <KnowledgeGraphFeedbackCards
          graphSearchError={controller.graphSearchError}
          graphError={controller.graphError}
          graphNotice={controller.graphNotice}
        />
      </div>

      <KnowledgeGraphVisualization
        filteredGraph={controller.filteredGraph}
        renderGraph={controller.renderGraph}
        subgraphMeta={controller.subgraphMeta}
        truncationNotice={controller.truncationNotice}
        preCapNodeCount={controller.preCapNodeCount}
        preCapEdgeCount={controller.preCapEdgeCount}
        isExpandingNodeId={controller.isExpandingNodeId}
        neighborhood={controller.neighborhood}
        selectedNodeId={controller.selectedNodeId}
        onNodeClick={controller.onNodeClick}
        onEdgeClick={controller.onEdgeClick}
        onHoverNodeChange={controller.onHoverNodeChange}
        onHoverEdgeChange={controller.onHoverEdgeChange}
        onClearSelection={controller.clearSelection}
        claimEvidenceByClaimId={controller.claimEvidenceByClaimId}
        onCanvasTap={handleCanvasTap}
        topControls={
          <div className="w-[min(96vw,460px)]">
            {showControlsPanel ? (
              <div className="overflow-hidden rounded-3xl border border-border/70 bg-background/95 shadow-brand-lg backdrop-blur supports-[backdrop-filter]:bg-background/85">
                <div className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
                  {activeControlsTab === 'search' ? (
                    <Search className="size-4 text-muted-foreground" />
                  ) : (
                    <Filter className="size-4 text-muted-foreground" />
                  )}
                  <div className="text-sm font-medium">
                    {activeControlsTab === 'search' ? 'Graph Search' : 'Local Filters'}
                  </div>
                  <div className="ml-auto inline-flex items-center rounded-full border border-border/70 bg-background p-0.5">
                    <button
                      type="button"
                      className={cn(
                        'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                        activeControlsTab === 'search'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                      onClick={() => setActiveControlsTab('search')}
                    >
                      Search
                    </button>
                    <button
                      type="button"
                      className={cn(
                        'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                        activeControlsTab === 'filters'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                      onClick={() => setActiveControlsTab('filters')}
                    >
                      Filters
                    </button>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 px-2 text-xs"
                    onClick={() => setShowControlsPanel(false)}
                  >
                    <PanelLeftClose className="mr-1 size-4" />
                    Hide
                  </Button>
                </div>

                <div className="flex flex-wrap items-center gap-2 border-b border-border/70 px-3 py-2">
                  <span className="text-xs font-medium text-muted-foreground">Show:</span>
                  {displayModeOptions.map((option) => (
                    <Button
                      key={option.value}
                      type="button"
                      size="sm"
                      variant={controller.graphDisplayMode === option.value ? 'default' : 'outline'}
                      className="h-7"
                      onClick={() => controller.setGraphDisplayMode(option.value)}
                    >
                      {option.label}
                    </Button>
                  ))}
                  {controller.graphDisplayMode === 'EVIDENCE' ? (
                    <span className="text-xs text-muted-foreground">
                      Evidence mode enabled: claim evidence expands into paper/dataset links.
                    </span>
                  ) : null}
                </div>

                {activeControlsTab === 'search' ? (
                  <KnowledgeGraphQueryCard
                    questionInput={controller.questionInput}
                    topKInput={controller.topKInput}
                    maxDepthInput={controller.maxDepthInput}
                    forceAgent={controller.forceAgent}
                    minDepth={controller.minDepth}
                    maxDepth={controller.maxDepthLimit}
                    minTopK={controller.minTopK}
                    maxTopK={controller.maxTopKLimit}
                    isLoading={controller.isLoading}
                    onQuestionInputChange={controller.setQuestionInput}
                    onTopKInputChange={controller.setTopKInput}
                    onMaxDepthInputChange={controller.setMaxDepthInput}
                    onForceAgentChange={controller.setForceAgent}
                    onSearch={controller.runSearch}
                    onLoadStarter={controller.resetToStarter}
                    onResetFilters={controller.resetFilters}
                    autoFocusQuestion={showControlsPanel && activeControlsTab === 'search'}
                    variant="menu"
                    orientation="vertical"
                    className="w-full"
                  />
                ) : (
                  <div className="max-h-[48vh] overflow-auto px-3 pb-3">
                    <KnowledgeGraphFiltersCard
                      filterOptions={{
                        relationTypes: controller.availableRelationTypes,
                        curationStatuses: controller.availableCurationStatuses,
                      }}
                      trustPreset={controller.trustPreset}
                      relationTypeFilter={controller.relationTypeFilter}
                      curationStatusFilter={controller.curationStatusFilter}
                      setTrustPreset={controller.setTrustPreset}
                      toggleRelationType={controller.toggleRelationType}
                      enableAllRelationTypes={controller.enableAllRelationTypes}
                      toggleCurationStatus={controller.toggleCurationStatus}
                      variant="embedded"
                    />
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-full border border-border/70 bg-background/95 px-3 py-2 text-left shadow-brand-md backdrop-blur supports-[backdrop-filter]:bg-background/85"
                onClick={() => setShowControlsPanel(true)}
              >
                {activeControlsTab === 'search' ? (
                  <Search className="size-4 text-muted-foreground" />
                ) : (
                  <Filter className="size-4 text-muted-foreground" />
                )}
                <span className="flex-1 truncate text-sm text-muted-foreground">
                  {activeControlsTab === 'search' ? 'Search the graph...' : 'Local filters...'}
                </span>
                <span className="inline-flex items-center rounded-full border border-border/70 px-2 py-0.5 text-xs font-medium">
                  <PanelLeftOpen className="mr-1 size-3.5" />
                  Show
                </span>
              </button>
            )}
          </div>
        }
      />

      <div className="space-y-4 px-3 sm:px-4 lg:px-6">
        <KnowledgeGraphSearchResultsCard graphSearch={controller.graphSearch} />
      </div>
    </div>
  )
}
