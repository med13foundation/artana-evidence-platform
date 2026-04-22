"use client"

import type {
  AdvancedQueryParameters,
  SourceCatalogEntry,
} from '@/lib/types/data-discovery'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { KeyRound, Layers3 } from 'lucide-react'

interface SourceParameterConfiguratorProps {
  catalog: SourceCatalogEntry[]
  selectedSourceIds: string[]
  sourceParameters: Record<string, AdvancedQueryParameters>
  defaultParameters: AdvancedQueryParameters
  onChange: (sourceId: string, parameters: AdvancedQueryParameters) => void
}

const PARAMETER_LABELS: Record<SourceCatalogEntry['param_type'], string> = {
  gene: 'Gene-only',
  term: 'Phenotype-only',
  gene_and_term: 'Gene & Phenotype',
  none: 'No Parameters',
  api: 'API-Driven',
}

const PARAMETER_DESCRIPTIONS: Record<SourceCatalogEntry['param_type'], string> = {
  gene: 'Provide a valid HGNC symbol before running queries.',
  term: 'Provide a phenotype, ontology ID, or search keyword.',
  gene_and_term: 'Both the gene symbol and phenotype term are required.',
  none: 'This catalog entry cannot be queried directly from the workbench.',
  api: 'Parameters depend on the upstream API. Provide the values documented for this integration.',
}

export function SourceParameterConfigurator({
  catalog,
  selectedSourceIds,
  sourceParameters,
  defaultParameters,
  onChange,
}: SourceParameterConfiguratorProps) {
  if (selectedSourceIds.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-muted-foreground/50 bg-muted/30 p-4 text-sm text-muted-foreground">
        Select one or more catalog entries to configure their query parameters.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {selectedSourceIds.map((sourceId) => {
        const entry = catalog.find((item) => item.id === sourceId)
        if (!entry) {
          return (
            <div
              key={sourceId}
              className="rounded-lg border border-dashed border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive"
            >
              Unable to load metadata for source <span className="font-medium">{sourceId}</span>.
            </div>
          )
        }
        const params = sourceParameters[sourceId] ?? defaultParameters
        const showGeneInput =
          entry.param_type === 'gene' ||
          entry.param_type === 'gene_and_term' ||
          entry.param_type === 'api'
        const showTermInput =
          entry.param_type === 'term' ||
          entry.param_type === 'gene_and_term' ||
          entry.param_type === 'api'
        const geneRequired =
          entry.param_type === 'gene' || entry.param_type === 'gene_and_term'
        const termRequired =
          entry.param_type === 'term' || entry.param_type === 'gene_and_term'
        const requiresParameters = entry.param_type !== 'none'

        return (
          <div key={entry.id} className="rounded-lg border border-border bg-card/40 p-4 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-foreground">{entry.name}</p>
                <p className="text-xs text-muted-foreground">{entry.category}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{PARAMETER_LABELS[entry.param_type]}</Badge>
                {entry.requires_auth && (
                  <Badge
                    variant="outline"
                    className="border-amber-500 text-amber-600 dark:border-amber-200 dark:text-amber-200"
                  >
                    <KeyRound className="mr-1 size-3" />
                    Auth required
                  </Badge>
                )}
              </div>
            </div>

            <p className="mb-3 text-sm text-muted-foreground">{PARAMETER_DESCRIPTIONS[entry.param_type]}</p>

            {entry.requires_auth && (
              <Alert className="mb-3 border-amber-500/50 bg-amber-50 dark:bg-amber-950/30">
                <AlertTitle className="flex items-center text-sm font-semibold text-amber-900 dark:text-amber-100">
                  <KeyRound className="mr-2 size-4" />
                  API credential required
                </AlertTitle>
                <AlertDescription className="text-xs text-amber-900/80 dark:text-amber-50">
                  Configure API keys for this vendor in System Settings → Data Sources before executing queries.
                </AlertDescription>
              </Alert>
            )}

            {entry.param_type === 'none' && (
              <Alert className="border-dashed">
                <AlertTitle className="text-sm font-semibold">No query parameters used</AlertTitle>
                <AlertDescription className="text-xs">
                  This catalog entry is informational only. Activate an associated ingestion template to run data pulls.
                </AlertDescription>
              </Alert>
            )}

            {requiresParameters && (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {showGeneInput && (
                  <div>
                    <Label htmlFor={`${entry.id}-gene`} className="text-xs text-muted-foreground">
                      Gene Symbol {geneRequired ? <span className="text-destructive">*</span> : null}
                    </Label>
                    <Input
                      id={`${entry.id}-gene`}
                      placeholder="e.g., MED13L"
                      value={params.gene_symbol ?? ''}
                      onChange={(event) => {
                        const value = event.target.value.trim().toUpperCase()
                        const nextValue = value === '' ? null : value
                        onChange(entry.id, {
                          ...params,
                          gene_symbol: nextValue,
                        })
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
                      value={params.search_term ?? ''}
                      onChange={(event) => {
                        const value = event.target.value.trim()
                        onChange(entry.id, {
                          ...params,
                          search_term: value === '' ? null : value,
                        })
                      }}
                      className="mt-1 bg-background"
                    />
                  </div>
                )}
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Layers3 className="size-3" />
                <span>Overrides persist for this session only.</span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  onChange(entry.id, {
                    ...defaultParameters,
                  })
                }
              >
                Reset to defaults
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
