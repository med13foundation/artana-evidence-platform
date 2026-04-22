"use client"

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  ExternalLink,
  Terminal,
  Loader2,
  FolderOpen,
  Database,
  BrainCircuit,
  ClipboardList,
  BookOpenText,
  TestTube2,
  Users,
  Network,
  Settings2,
  KeyRound,
  CheckCircle2,
  Slash,
  ChevronDown,
  ChevronUp,
  Play,
  FastForward,
} from 'lucide-react'
import type {
  AdvancedQueryParameters,
  QueryTestResult,
  SourceCatalogEntry,
  QueryParameterCapabilities,
} from '@/lib/types/data-discovery'
import {
  DEFAULT_ADVANCED_SETTINGS,
  type SourceAdvancedSettings,
} from '@/components/data-discovery/advanced-settings'
import { ParameterBar } from '@/components/data-discovery/ParameterBar'
import type { ScheduleFrequency } from '@/types/data-source'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { SpaceSelectorModal } from '@/components/research-spaces/SpaceSelectorModal'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  'Genomic Variant Databases': Database,
  'Gene Expression & Functional Genomics': BrainCircuit,
  'Model Organism Databases': TestTube2,
  'Protein / Pathway Databases': Network,
  'Electronic Health Records (EHRs)': ClipboardList,
  'Rare Disease Registries': Users,
  'Clinical Trial Databases': TestTube2,
  'Phenotype Ontologies & Databases': ClipboardList,
  'Scientific Literature': BookOpenText,
  'Knowledge Graphs / Integrated Platforms': Network,
  'AI Predictive Models': BrainCircuit,
}

const SOURCE_TYPE_LABELS: Record<SourceCatalogEntry['source_type'], string> = {
  api: 'API',
  database: 'Database',
  file_upload: 'File Upload',
  web_scraping: 'Web Scraping',
  pubmed: 'PubMed',
  clinvar: 'ClinVar',
}

const STORAGE_TARGET_SUMMARY: Record<
  SourceCatalogEntry['source_type'],
  { label: string; description: string; useCase: string }
> = {
  pubmed: {
    label: 'PDF storage backend',
    description: 'Articles are saved via the StorageUseCase.PDF configuration.',
    useCase: 'PDF',
  },
  clinvar: {
    label: 'Raw source storage',
    description: 'Variant payloads are persisted through StorageUseCase.RAW_SOURCE.',
    useCase: 'RAW_SOURCE',
  },
  api: {
    label: 'Raw source storage',
    description: 'Data exports persist through StorageUseCase.RAW_SOURCE.',
    useCase: 'RAW_SOURCE',
  },
  database: {
    label: 'Raw source storage',
    description: 'Records are captured for reproducible ingestion snapshots.',
    useCase: 'RAW_SOURCE',
  },
  file_upload: {
    label: 'Export storage',
    description: 'Uploaded artifacts are stored via StorageUseCase.EXPORT.',
    useCase: 'EXPORT',
  },
  web_scraping: {
    label: 'Raw source storage',
    description: 'Scraped payloads are routed to StorageUseCase.RAW_SOURCE.',
    useCase: 'RAW_SOURCE',
  },
}

const PARAMETER_LABELS = {
  gene: 'Gene-only',
  term: 'Phenotype-only',
  gene_and_term: 'Gene & Phenotype',
  none: 'No Parameters',
  api: 'API-Driven',
} as const

const PARAMETER_DESCRIPTIONS = {
  gene: 'Provide a valid HGNC symbol before running queries.',
  term: 'Provide a phenotype, ontology ID, or search keyword.',
  gene_and_term: 'Both the gene symbol and phenotype term are required.',
  none: 'This catalog entry cannot be queried directly from the workbench.',
  api: 'Parameters depend on the upstream API. Provide the values documented for this integration.',
} as const

type CapabilityFlag = Exclude<
  keyof QueryParameterCapabilities,
  'max_results_limit' | 'supported_storage_use_cases' | 'discovery_defaults'
>

const CAPABILITY_LABELS: Record<CapabilityFlag, string> = {
  supports_date_range: 'Date range',
  supports_publication_types: 'Publication types',
  supports_language_filter: 'Language filter',
  supports_sort_options: 'Sort options',
  supports_additional_terms: 'Additional terms',
  supports_variation_type: 'Variation types',
  supports_clinical_significance: 'Clinical significance',
  supports_review_status: 'Review status',
  supports_organism: 'Organism',
}

const CAPABILITY_ORDER: CapabilityFlag[] = [
  'supports_date_range',
  'supports_publication_types',
  'supports_language_filter',
  'supports_sort_options',
  'supports_additional_terms',
  'supports_variation_type',
  'supports_clinical_significance',
  'supports_review_status',
  'supports_organism',
]

interface ResultsViewProps {
  parameters: AdvancedQueryParameters
  currentSpaceId: string | null
  catalog: SourceCatalogEntry[]
  results: QueryTestResult[]
  selectedSourceIds: string[]
  sourceParameters: Record<string, AdvancedQueryParameters>
  advancedSettings: Record<string, SourceAdvancedSettings>
  defaultParameters: AdvancedQueryParameters
  defaultAdvancedSettings?: SourceAdvancedSettings
  isLoading: boolean
  onBackToSelect: () => void
  onAddToSpace: (result: QueryTestResult, spaceId: string) => Promise<void>
  onRunTest?: (catalogEntryId: string) => Promise<void>
  onUpdateSourceParameters: (sourceId: string, params: AdvancedQueryParameters) => void
  onUpdateAdvancedSettings: (sourceId: string, settings: SourceAdvancedSettings) => void
}

export function ResultsView({
  parameters,
  currentSpaceId,
  catalog,
  results,
  selectedSourceIds,
  sourceParameters,
  advancedSettings,
  defaultParameters,
  defaultAdvancedSettings = DEFAULT_ADVANCED_SETTINGS,
  isLoading,
  onBackToSelect,
  onAddToSpace,
  onRunTest,
  onUpdateSourceParameters,
  onUpdateAdvancedSettings,
}: ResultsViewProps) {
  const [spaceSelectorOpen, setSpaceSelectorOpen] = useState(false)
  const [selectedResultForSpace, setSelectedResultForSpace] = useState<QueryTestResult | null>(null)
  const [addingResultId, setAddingResultId] = useState<string | null>(null)
  const [runningResultId, setRunningResultId] = useState<string | null>(null)
  const [runningSourceId, setRunningSourceId] = useState<string | null>(null)
  const [configuringSourceId, setConfiguringSourceId] = useState<string | null>(null)
  const [isRunningAll, setIsRunningAll] = useState(false)

  const catalogById = useMemo(() => {
    const map = new Map<string, SourceCatalogEntry>()
    catalog.forEach((entry) => map.set(entry.id, entry))
    return map
  }, [catalog])

  const latestResultBySource = useMemo(() => {
    const map = new Map<string, QueryTestResult>()
    results.forEach((result) => {
      const existing = map.get(result.catalog_entry_id)
      const existingTime = existing
        ? new Date(existing.completed_at ?? existing.started_at).getTime()
        : -Infinity
      const candidateTime = new Date(result.completed_at ?? result.started_at).getTime()
      if (!existing || candidateTime >= existingTime) {
        map.set(result.catalog_entry_id, result)
      }
    })
    return map
  }, [results])

  const selectedSourcesWithMeta = useMemo(
    () =>
      selectedSourceIds
        .map((sourceId) => {
          const entry = catalogById.get(sourceId)
          if (!entry) {
            return null
          }
          return {
            entry,
            latestResult: latestResultBySource.get(sourceId) ?? null,
            parameters: sourceParameters[sourceId] ?? defaultParameters,
            advancedSettings: advancedSettings[sourceId] ?? defaultAdvancedSettings,
          }
        })
        .filter(
          (
            value,
          ): value is {
            entry: SourceCatalogEntry
            latestResult: QueryTestResult | null
            parameters: AdvancedQueryParameters
            advancedSettings: SourceAdvancedSettings
          } => value !== null,
        ),
    [
      selectedSourceIds,
      catalogById,
      latestResultBySource,
      sourceParameters,
      advancedSettings,
      defaultParameters,
      defaultAdvancedSettings,
    ],
  )

  const handleAddToSpaceRequest = async (result: QueryTestResult) => {
    if (currentSpaceId) {
      await handleAddToSpace(result, currentSpaceId)
      return
    }
    setSelectedResultForSpace(result)
    setSpaceSelectorOpen(true)
  }

  const handleAddToSpace = async (result: QueryTestResult, spaceId: string) => {
    try {
      setAddingResultId(result.id)
      await onAddToSpace(result, spaceId)
    } catch (error) {
      console.error('Failed to add source to space', error)
    } finally {
      setAddingResultId(null)
    }
  }

  const handleSpaceSelected = async (spaceId: string) => {
    if (selectedResultForSpace) {
      await handleAddToSpace(selectedResultForSpace, spaceId)
    }
    setSelectedResultForSpace(null)
    setSpaceSelectorOpen(false)
  }

  const handleRunResult = async (result: QueryTestResult) => {
    if (!onRunTest) return
    try {
      setRunningResultId(result.id)
      await onRunTest(result.catalog_entry_id)
    } finally {
      setRunningResultId(null)
    }
  }

  const handleRunSelectedSource = async (sourceId: string) => {
    if (!onRunTest) return
    try {
      setRunningSourceId(sourceId)
      await onRunTest(sourceId)
    } finally {
      setRunningSourceId(null)
    }
  }

  const handleRunAll = async () => {
    if (!onRunTest || isRunningAll) return
    setIsRunningAll(true)
    try {
      // Execute sequentially to avoid overwhelming the backend or hitting rate limits
      for (const { entry } of selectedSourcesWithMeta) {
        await onRunTest(entry.id)
      }
    } finally {
      setIsRunningAll(false)
    }
  }

  const configuringEntry = configuringSourceId ? catalogById.get(configuringSourceId) ?? null : null
  const configuringParams =
    (configuringSourceId && (sourceParameters[configuringSourceId] ?? defaultParameters)) || defaultParameters
  const configuringAdvancedSettings =
    (configuringSourceId && (advancedSettings[configuringSourceId] ?? defaultAdvancedSettings))
    || defaultAdvancedSettings

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span>Review & Run Tests</span>
              <Badge variant="secondary" className="text-xs font-normal">
                {selectedSourcesWithMeta.length} Selected
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              {onRunTest && selectedSourcesWithMeta.length > 0 && (
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleRunAll}
                  disabled={isRunningAll || isLoading}
                  className="flex items-center gap-2"
                >
                  {isRunningAll ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <FastForward className="size-4" />
                  )}
                  Run All Tests
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={onBackToSelect}>
                <ArrowLeft className="mr-2 size-4" />
                Back to Selection
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {selectedSourcesWithMeta.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <FolderOpen className="mb-4 size-12 text-muted-foreground/50" />
              <p className="text-muted-foreground">No sources selected.</p>
              <Button variant="link" onClick={onBackToSelect}>
                Go back to catalog
              </Button>
            </div>
          ) : isLoading && results.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Loader2 className="mb-4 size-8 animate-spin text-primary" />
              <p className="text-muted-foreground">Loading test results...</p>
            </div>
          ) : (
            <div className="space-y-4">
              {selectedSourcesWithMeta.map(
                ({ entry, latestResult, parameters: sourceParams, advancedSettings: sourceAdvanced }) => (
                  <UnifiedSourceCard
                    key={entry.id}
                    entry={entry}
                    latestResult={latestResult}
                    parameters={sourceParams}
                    advancedSettings={sourceAdvanced}
                    isRunning={runningSourceId === entry.id || (isRunningAll && !latestResult)}
                    onRunTest={onRunTest ? () => handleRunSelectedSource(entry.id) : undefined}
                    onConfigure={() => setConfiguringSourceId(entry.id)}
                    onAddToSpace={(result) => handleAddToSpaceRequest(result)}
                    isAddingToSpace={latestResult ? addingResultId === latestResult.id : false}
                  />
                ),
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <SpaceSelectorModal
        open={spaceSelectorOpen}
        onOpenChange={setSpaceSelectorOpen}
        onSpaceChange={(spaceId) => handleSpaceSelected(spaceId)}
      />

      <SourceParameterModal
        open={Boolean(configuringEntry)}
        entry={configuringEntry}
        parameters={configuringParams}
        advancedSettings={configuringAdvancedSettings}
        defaultParameters={defaultParameters}
        defaultAdvancedSettings={defaultAdvancedSettings}
        onClose={() => setConfiguringSourceId(null)}
        onSave={(nextParams, nextAdvancedSettings) => {
          if (configuringSourceId) {
            onUpdateSourceParameters(configuringSourceId, nextParams)
            onUpdateAdvancedSettings(configuringSourceId, nextAdvancedSettings)
          }
          setConfiguringSourceId(null)
        }}
      />
    </>
  )
}

interface UnifiedSourceCardProps {
  entry: SourceCatalogEntry
  latestResult: QueryTestResult | null
  parameters: AdvancedQueryParameters
  advancedSettings: SourceAdvancedSettings
  isRunning: boolean
  isAddingToSpace: boolean
  onRunTest?: () => Promise<void> | void
  onConfigure: () => void
  onAddToSpace: (result: QueryTestResult) => void
}

function UnifiedSourceCard({
  entry,
  latestResult,
  parameters,
  advancedSettings,
  isRunning,
  isAddingToSpace,
  onRunTest,
  onConfigure,
  onAddToSpace,
}: UnifiedSourceCardProps) {
  const IconComponent = CATEGORY_ICONS[entry.category] || Database
  const normalizedType = normalizeParamType(entry.param_type)

  // Determine card border status based on result - using MED13 brand colors
  let borderClass = 'border-border'
  if (latestResult?.status === 'success') {
    borderClass = 'border-primary/30 bg-primary/5 dark:bg-primary/10'
  } else if (latestResult?.status === 'error' || latestResult?.status === 'validation_failed') {
    borderClass = 'border-destructive/30 bg-destructive/5 dark:bg-destructive/10'
  }

  const statusBadge = latestResult ? (
    <Badge
      variant={
        latestResult.status === 'success'
          ? 'default'
          : latestResult.status === 'error' || latestResult.status === 'validation_failed'
            ? 'destructive'
            : 'secondary'
      }
      className={latestResult.status === 'success' ? 'bg-primary hover:bg-primary/90' : ''}
    >
      {latestResult.status.replace('_', ' ')}
    </Badge>
  ) : (
    <Badge variant="outline" className="border-muted-foreground/30 text-muted-foreground">
      Ready to Test
    </Badge>
  )

  const isApiResult = latestResult && !latestResult.response_url

  return (
    <Card className={`transition-all ${borderClass}`}>
      <CardContent className="flex flex-col gap-4 p-5 md:flex-row md:items-start md:justify-between">
        {/* Left Section: Source Info & Params */}
        <div className="flex items-start gap-4">
          <div
            className={`mt-1 rounded-lg p-2 ${latestResult?.status === 'success'
                ? 'bg-primary/20 text-primary-foreground dark:bg-primary/30 dark:text-primary-foreground'
                : 'bg-secondary text-secondary-foreground'
              }`}
          >
            <IconComponent className="size-5" />
          </div>

          <div className="flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-foreground">{entry.name}</h3>
              {statusBadge}
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="font-medium text-foreground">Type:</span>{' '}
                {SOURCE_TYPE_LABELS[entry.source_type]}
              </span>
              <span className="size-1 rounded-full bg-muted-foreground/30" />
              <span className="flex items-center gap-1">
                <span className="font-medium text-foreground">Gene:</span> {parameters.gene_symbol ?? '—'}
              </span>
              <span className="size-1 rounded-full bg-muted-foreground/30" />
              <span className="flex items-center gap-1">
                <span className="font-medium text-foreground">Term:</span> {parameters.search_term ?? '—'}
              </span>
            </div>

            {/* Status Message or Last Run Info */}
            <div className="text-xs text-muted-foreground">
              {latestResult ? (
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="size-3" />
                  Test completed{' '}
                  {new Date(latestResult.completed_at ?? latestResult.started_at).toLocaleTimeString()}
                  {latestResult.status === 'success' && (
                    <span className="ml-2 font-medium text-primary">
                      ✓ Data Available
                    </span>
                  )}
                </span>
              ) : (
                <span className="italic">Configure parameters and run test to verify data availability.</span>
              )}
            </div>

            {/* Schedule info - only show if configured */}
            {advancedSettings.scheduling.enabled && (
              <p className="text-xs text-muted-foreground">
                Schedule: {advancedSettings.scheduling.frequency.toUpperCase()} •{' '}
                {advancedSettings.scheduling.timezone}
              </p>
            )}
          </div>
        </div>

        {/* Right Section: Actions */}
        <div className="flex shrink-0 flex-col items-end gap-2 pt-1 md:pt-0">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onConfigure}
              className="h-8 px-2 text-muted-foreground hover:text-foreground"
            >
              <Settings2 className="mr-2 size-3.5" />
              Configure
            </Button>

            <Button
              size="sm"
              variant={latestResult?.status === 'success' ? 'secondary' : 'default'}
              onClick={onRunTest}
              disabled={!onRunTest || isRunning}
              className="h-8 min-w-[100px]"
            >
              {isRunning ? (
                <>
                  <Loader2 className="mr-2 size-3.5 animate-spin" />
                  Running
                </>
              ) : (
                <>
                  <Play className="mr-2 size-3.5" />
                  {latestResult ? 'Re-run' : 'Run Test'}
                </>
              )}
            </Button>
          </div>

          {/* Success Actions Area */}
          {latestResult?.status === 'success' && (
            <div className="mt-2 flex items-center gap-2 rounded-md bg-muted/50 p-1">
              {latestResult.response_url && (
                <Button asChild variant="ghost" size="sm" className="h-7 text-xs">
                  <a href={latestResult.response_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-2 size-3" />
                    View Data
                  </a>
                </Button>
              )}
              {latestResult.response_url && <div className="h-4 w-px bg-border" />}
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-primary hover:bg-primary/10 hover:text-primary"
                onClick={() => onAddToSpace(latestResult)}
                disabled={isAddingToSpace}
              >
                {isAddingToSpace ? (
                  <Loader2 className="mr-2 size-3 animate-spin" />
                ) : (
                  <ClipboardList className="mr-2 size-3" />
                )}
                Promote to Space
              </Button>
            </div>
          )}

          {/* Error state actions */}
          {latestResult &&
            (latestResult.status === 'error' || latestResult.status === 'validation_failed') &&
            isApiResult && (
              <Button
                size="sm"
                variant="outline"
                onClick={onRunTest}
                disabled={!onRunTest || isRunning}
                className="mt-2 h-7 text-xs"
              >
                {isRunning ? (
                  <Loader2 className="mr-2 size-3 animate-spin" />
                ) : (
                  <Terminal className="mr-2 size-3" />
                )}
                Retry API
              </Button>
            )}
        </div>
      </CardContent>
    </Card>
  )
}

interface SourceParameterModalProps {
  open: boolean
  entry: SourceCatalogEntry | null
  parameters: AdvancedQueryParameters
  advancedSettings: SourceAdvancedSettings
  defaultParameters: AdvancedQueryParameters
  defaultAdvancedSettings: SourceAdvancedSettings
  onClose: () => void
  onSave: (params: AdvancedQueryParameters, advanced: SourceAdvancedSettings) => void
}

export function SourceParameterModal({
  open,
  entry,
  parameters,
  advancedSettings,
  defaultParameters,
  defaultAdvancedSettings,
  onClose,
  onSave,
}: SourceParameterModalProps) {
  const [formValues, setFormValues] = useState<AdvancedQueryParameters>(parameters)
  const [advancedValues, setAdvancedValues] = useState<SourceAdvancedSettings>(advancedSettings)
  const [isDirty, setIsDirty] = useState(false)
  const [isSchedulingExpanded, setIsSchedulingExpanded] = useState(false)
  const previousEntryIdRef = useRef<string | null>(null)

  useEffect(() => {
    const currentEntryId = entry?.id ?? null

    if (!open) {
      previousEntryIdRef.current = currentEntryId
      setFormValues(parameters)
      setAdvancedValues(advancedSettings)
      setIsDirty(false)
      return
    }

    if (currentEntryId !== previousEntryIdRef.current) {
      previousEntryIdRef.current = currentEntryId
      setFormValues(parameters)
      setAdvancedValues(advancedSettings)
      setIsDirty(false)
      return
    }

    if (!isDirty) {
      setFormValues(parameters)
      setAdvancedValues(advancedSettings)
    }
  }, [advancedSettings, entry?.id, isDirty, open, parameters])

  if (!entry) {
    return null
  }

  const normalizedType = normalizeParamType(entry.param_type)
  const typeLabel = SOURCE_TYPE_LABELS[entry.source_type]
  const showGeneInput =
    normalizedType === 'gene' ||
    normalizedType === 'gene_and_term' ||
    normalizedType === 'api'
  const showTermInput =
    normalizedType === 'term' ||
    normalizedType === 'gene_and_term' ||
    normalizedType === 'api'
  const geneRequired = normalizedType === 'gene' || normalizedType === 'gene_and_term'
  const termRequired = normalizedType === 'term' || normalizedType === 'gene_and_term'
  const requiresParameters = normalizedType !== 'none'
  const storageSummary = STORAGE_TARGET_SUMMARY[entry.source_type] ?? STORAGE_TARGET_SUMMARY.api
  const capabilityFlags = CAPABILITY_ORDER.map((flag) => ({
    key: flag,
    label: CAPABILITY_LABELS[flag],
    enabled: Boolean(entry.capabilities[flag]),
  }))

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="flex max-h-[90vh] min-h-[80vh] w-[95vw] max-w-2xl flex-col gap-0 overflow-hidden p-4 sm:w-full md:max-w-4xl md:p-6 lg:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Configure {entry.name}</DialogTitle>
          <DialogDescription>
            Adjust the query parameters used when testing this catalog entry. Overrides apply only to the current
            session.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto pr-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-foreground">{entry.category}</p>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
                  {typeLabel}
                </Badge>
                <span>{PARAMETER_LABELS[normalizedType]}</span>
              </div>
            </div>
            {entry.requires_auth && (
              <Badge
                variant="outline"
                className="border-amber-500 text-amber-600 dark:border-amber-200 dark:text-amber-100"
              >
                <KeyRound className="mr-1 size-3" />
                Auth required
              </Badge>
            )}
          </div>

          <p className="text-sm text-muted-foreground">{PARAMETER_DESCRIPTIONS[normalizedType]}</p>

          <div className="grid gap-3 rounded-lg border border-dashed border-muted-foreground/40 bg-muted/20 p-3">
            <div className="flex flex-col gap-1 rounded-md border border-border/60 bg-background/70 p-3">
              <p className="text-xs font-semibold uppercase text-muted-foreground">Storage target</p>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">{storageSummary.label}</p>
                  <p className="text-xs text-muted-foreground">{storageSummary.description}</p>
                </div>
                <Badge variant="secondary" className="text-[11px] font-semibold uppercase tracking-wide">
                  {storageSummary.useCase}
                </Badge>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-muted-foreground">Advanced filter capabilities</p>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {capabilityFlags.map((flag) => (
                  <div
                    key={flag.key}
                    className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${flag.enabled
                        ? 'border-primary/60 text-primary dark:text-primary'
                        : 'border-border/60 text-muted-foreground'
                      }`}
                  >
                    {flag.enabled ? <CheckCircle2 className="size-3" /> : <Slash className="size-3" />}
                    <span>{flag.label}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Max results limit: {entry.capabilities.max_results_limit}
              </p>
            </div>
          </div>

          {entry.requires_auth && (
            <Alert className="border-amber-500/50 bg-amber-50 dark:bg-amber-950/30">
              <AlertTitle className="text-sm font-semibold text-amber-900 dark:text-amber-100">
                API credential required
              </AlertTitle>
              <AlertDescription className="text-xs text-amber-900/80 dark:text-amber-50">
                Configure API keys for this vendor in System Settings → Data Sources before executing queries.
              </AlertDescription>
            </Alert>
          )}

          {!requiresParameters && (
            <Alert>
              <AlertTitle className="text-sm font-semibold">No query parameters required</AlertTitle>
              <AlertDescription className="text-xs">
                This catalog entry is informational only. Activate an associated ingestion template to run data pulls.
              </AlertDescription>
            </Alert>
          )}
          {requiresParameters && entry.source_type === 'pubmed' && (
            <ParameterBar
              parameters={formValues}
              capabilities={entry.capabilities}
              onParametersChange={(newParams) => {
                setFormValues(newParams)
                setIsDirty(true)
              }}
            />
          )}
          {requiresParameters && entry.source_type !== 'pubmed' && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {showGeneInput && (
                <div>
                  <Label htmlFor={`${entry.id}-gene`} className="text-xs text-muted-foreground">
                    Gene Symbol {geneRequired ? <span className="text-destructive">*</span> : null}
                  </Label>
                  <Input
                    id={`${entry.id}-gene`}
                    placeholder="e.g., MED13L"
                    value={formValues.gene_symbol ?? ''}
                    onChange={(event) => {
                      const value = event.target.value.toUpperCase()
                      setFormValues((prev) => ({
                        ...prev,
                        gene_symbol: value.trim() === '' ? null : value.trim(),
                      }))
                      setIsDirty(true)
                    }}
                    className="mt-1 bg-background"
                  />
                </div>
              )}
              {showTermInput && (
                <div>
                  <Label htmlFor={`${entry.id}-term`} className="text-xs text-muted-foreground">
                    Phenotype / Search Term {termRequired ? <span className="text-destructive">*</span> : null}
                  </Label>
                  <Input
                    id={`${entry.id}-term`}
                    placeholder="e.g., atrial septal defect"
                    value={formValues.search_term ?? ''}
                    onChange={(event) => {
                      const value = event.target.value
                      setFormValues((prev) => ({
                        ...prev,
                        search_term: value.trim() === '' ? null : value.trim(),
                      }))
                      setIsDirty(true)
                    }}
                    className="mt-1 bg-background"
                  />
                </div>
              )}

              {/* ClinVar Specific Inputs */}
              {entry.capabilities.supports_variation_type && (
                <div>
                  <Label htmlFor={`${entry.id}-variation-types`} className="text-xs text-muted-foreground">
                    Variation Types (comma-separated)
                  </Label>
                  <Input
                    id={`${entry.id}-variation-types`}
                    placeholder="e.g., single_nucleotide_variant"
                    value={(formValues.variation_types ?? []).join(', ')}
                    onChange={(event) => {
                      const value = event.target.value
                      setFormValues((prev) => ({
                        ...prev,
                        variation_types: value
                          ? value.split(',').map((s) => s.trim())
                          : [],
                      }))
                      setIsDirty(true)
                    }}
                    className="mt-1 bg-background"
                  />
                </div>
              )}

              {entry.capabilities.supports_clinical_significance && (
                <div>
                  <Label htmlFor={`${entry.id}-clinical-sig`} className="text-xs text-muted-foreground">
                    Clinical Significance (comma-separated)
                  </Label>
                  <Input
                    id={`${entry.id}-clinical-sig`}
                    placeholder="e.g., pathogenic, benign"
                    value={(formValues.clinical_significance ?? []).join(', ')}
                    onChange={(event) => {
                      const value = event.target.value
                      setFormValues((prev) => ({
                        ...prev,
                        clinical_significance: value
                          ? value.split(',').map((s) => s.trim())
                          : [],
                      }))
                      setIsDirty(true)
                    }}
                    className="mt-1 bg-background"
                  />
                </div>
              )}

              {/* UniProt Specific Inputs */}
              {entry.capabilities.supports_organism && (
                <div>
                  <Label htmlFor={`${entry.id}-organism`} className="text-xs text-muted-foreground">
                    Organism
                  </Label>
                  <Input
                    id={`${entry.id}-organism`}
                    placeholder="e.g., Human, Mouse"
                    value={formValues.organism ?? ''}
                    onChange={(event) => {
                      const value = event.target.value
                      setFormValues((prev) => ({
                        ...prev,
                        organism: value.trim() === '' ? null : value.trim(),
                      }))
                      setIsDirty(true)
                    }}
                    className="mt-1 bg-background"
                  />
                </div>
              )}

              {entry.capabilities.supports_review_status && (
                <div>
                  <Label className="text-xs text-muted-foreground">Review Status</Label>
                  <div className="mt-1 flex gap-2">
                    <Button
                      type="button"
                      variant={formValues.is_reviewed === true ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setFormValues((prev) => ({ ...prev, is_reviewed: true }))
                        setIsDirty(true)
                      }}
                    >
                      Swiss-Prot
                    </Button>
                    <Button
                      type="button"
                      variant={formValues.is_reviewed === false ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setFormValues((prev) => ({ ...prev, is_reviewed: false }))
                        setIsDirty(true)
                      }}
                    >
                      TrEMBL
                    </Button>
                    <Button
                      type="button"
                      variant={formValues.is_reviewed === null ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setFormValues((prev) => ({ ...prev, is_reviewed: null }))
                        setIsDirty(true)
                      }}
                    >
                      All
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="mt-6 space-y-4 rounded-lg border border-border/60 bg-muted/20 p-4">
            <button
              type="button"
              onClick={() => setIsSchedulingExpanded(!isSchedulingExpanded)}
              className="flex w-full items-center justify-between rounded-md p-2 text-left transition-colors hover:bg-muted/50"
            >
              <div className="space-y-1">
                <p className="text-sm font-semibold text-foreground">Scheduling (optional)</p>
                <p className="text-xs text-muted-foreground">
                  Configure how often MED13 should ingest this source once promoted to a research space.
                </p>
              </div>
              {isSchedulingExpanded ? (
                <ChevronUp className="size-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="size-4 text-muted-foreground" />
              )}
            </button>
            {isSchedulingExpanded && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Checkbox
                      checked={advancedValues.scheduling.enabled}
                      onCheckedChange={(checked) => {
                        setAdvancedValues((prev) => ({
                          ...prev,
                          scheduling: {
                            ...prev.scheduling,
                            enabled: checked === true,
                          },
                        }))
                        setIsDirty(true)
                      }}
                    />
                    Enable
                  </label>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <Label className="text-xs text-muted-foreground">Frequency</Label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={advancedValues.scheduling.frequency}
                      disabled={!advancedValues.scheduling.enabled}
                      onChange={(event) => {
                        const value = event.target.value as ScheduleFrequency
                        setAdvancedValues((prev) => ({
                          ...prev,
                          scheduling: {
                            ...prev.scheduling,
                            frequency: value,
                          },
                        }))
                        setIsDirty(true)
                      }}
                    >
                      <option value="manual">Manual</option>
                      <option value="hourly">Hourly</option>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="cron">Cron</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Timezone</Label>
                    <Input
                      className="mt-1 bg-background"
                      placeholder="UTC"
                      value={advancedValues.scheduling.timezone}
                      disabled={!advancedValues.scheduling.enabled}
                      onChange={(event) => {
                        setAdvancedValues((prev) => ({
                          ...prev,
                          scheduling: {
                            ...prev.scheduling,
                            timezone: event.target.value || 'UTC',
                          },
                        }))
                        setIsDirty(true)
                      }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <Label className="text-xs text-muted-foreground">Start time</Label>
                    <Input
                      type="datetime-local"
                      className="mt-1 bg-background"
                      value={advancedValues.scheduling.startTime ?? ''}
                      disabled={!advancedValues.scheduling.enabled}
                      onChange={(event) => {
                        setAdvancedValues((prev) => ({
                          ...prev,
                          scheduling: {
                            ...prev.scheduling,
                            startTime: event.target.value || null,
                          },
                        }))
                        setIsDirty(true)
                      }}
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Cron expression</Label>
                    <Input
                      className="mt-1 bg-background"
                      placeholder="0 0 * * *"
                      value={advancedValues.scheduling.cronExpression ?? ''}
                      disabled={
                        !advancedValues.scheduling.enabled ||
                        advancedValues.scheduling.frequency !== 'cron'
                      }
                      onChange={(event) => {
                        setAdvancedValues((prev) => ({
                          ...prev,
                          scheduling: {
                            ...prev.scheduling,
                            cronExpression: event.target.value || null,
                          },
                        }))
                        setIsDirty(true)
                      }}
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Only used when frequency is set to cron.
                    </p>
                  </div>
                </div>

                <div>
                  <Label className="text-xs text-muted-foreground">Notes / Integration details</Label>
                  <textarea
                    className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    rows={3}
                    placeholder="Optional notes, credentials location, mapping requirements..."
                    value={advancedValues.notes}
                    onChange={(event) => {
                      setAdvancedValues((prev) => ({
                        ...prev,
                        notes: event.target.value,
                      }))
                      setIsDirty(true)
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setFormValues(defaultParameters)
              setAdvancedValues(defaultAdvancedSettings)
              setIsDirty(true)
            }}
            className="justify-start sm:justify-center"
          >
            Reset to defaults
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                onSave(formValues, advancedValues)
                setIsDirty(false)
              }}
            >
              Save Configuration
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function normalizeParamType(
  paramType: string,
): 'gene' | 'term' | 'gene_and_term' | 'none' | 'api' {
  switch (paramType) {
    case 'gene_and_term':
    case 'geneAndTerm':
      return 'gene_and_term'
    case 'gene':
    case 'term':
    case 'none':
    case 'api':
      return paramType as 'gene' | 'term' | 'none' | 'api'
    default:
      return 'gene_and_term'
  }
}
