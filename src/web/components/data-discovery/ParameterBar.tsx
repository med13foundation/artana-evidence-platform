"use client"

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import type {
  AdvancedQueryParameters,
  PubmedSortOption,
  QueryParameterCapabilities,
} from '@/lib/types/data-discovery'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui/separator'

interface ParameterBarProps {
  parameters: AdvancedQueryParameters
  capabilities: QueryParameterCapabilities
  onParametersChange: (parameters: AdvancedQueryParameters) => void
}

const PUBLICATION_TYPE_OPTIONS = [
  'Clinical Trial',
  'Meta-Analysis',
  'Randomized Controlled Trial',
  'Review',
  'Case Report',
]

const LANGUAGE_OPTIONS = [
  { code: 'eng', label: 'English' },
  { code: 'spa', label: 'Spanish' },
  { code: 'fra', label: 'French' },
  { code: 'deu', label: 'German' },
  { code: 'ita', label: 'Italian' },
]

const SORT_OPTIONS: { value: PubmedSortOption; label: string }[] = [
  { value: 'relevance', label: 'Best Match' },
  { value: 'publication_date', label: 'Publication Date' },
  { value: 'author', label: 'First Author' },
  { value: 'journal', label: 'Journal' },
  { value: 'title', label: 'Title' },
]

export function ParameterBar({
  parameters,
  capabilities,
  onParametersChange,
}: ParameterBarProps) {
  const maxResultsLimit = capabilities.max_results_limit ?? 1000

  const updateParameters = (next: Partial<AdvancedQueryParameters>) => {
    onParametersChange({
      ...parameters,
      ...next,
    })
  }

  const toggleArrayValue = (
    field: 'publication_types' | 'languages',
    value: string,
  ) => {
    const current = parameters[field] ?? []
    const nextArray = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]
    updateParameters({ [field]: nextArray })
  }

  const queryPreview = useMemo(() => buildQueryPreview(parameters), [parameters])

  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    basics: true,
    filters: true,
    sourceSpecific: true,
    output: true,
  })

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }))
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card/60 p-3 sm:space-y-6 sm:p-4">
      <CollapsibleSection
        title="Basics"
        description="Core terms to seed your PubMed search."
        isExpanded={expandedSections.basics}
        onToggle={() => toggleSection('basics')}
      >
      <div className="grid gap-4 lg:grid-cols-2">
        <LabeledInput
          id="geneSymbol"
          label="Gene Symbol"
          value={parameters.gene_symbol ?? ''}
          placeholder="e.g., MED13L"
          onChange={(value) =>
            updateParameters({ gene_symbol: value.toUpperCase() || null })
          }
        />
        <LabeledInput
          id="searchTerm"
          label="Phenotype / Search Term"
          value={parameters.search_term ?? ''}
          placeholder="e.g., atrial septal defect"
          onChange={(value) => updateParameters({ search_term: value || null })}
        />
      </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Filters"
        description="Control time ranges, publication types, languages, and additional PubMed syntax."
        isExpanded={expandedSections.filters}
        onToggle={() => toggleSection('filters')}
      >

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <Label className="mb-1 block text-sm text-foreground">Date Range</Label>
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              type="date"
              value={parameters.date_from ?? ''}
              onChange={(event) =>
                updateParameters({
                  date_from: event.target.value ? event.target.value : null,
                })
              }
              disabled={!capabilities.supports_date_range}
            />
            <Input
              type="date"
              value={parameters.date_to ?? ''}
              onChange={(event) =>
                updateParameters({
                  date_to: event.target.value ? event.target.value : null,
                })
              }
              disabled={!capabilities.supports_date_range}
            />
          </div>
          {!capabilities.supports_date_range && (
            <CapabilityHint message="Current sources do not support date filtering." />
          )}
        </div>

        <div>
          <Label className="mb-1 block text-sm text-foreground">Publication Types</Label>
          <div className="flex flex-wrap gap-2">
            {PUBLICATION_TYPE_OPTIONS.map((type) => {
              const selected = parameters.publication_types?.includes(type)
              return (
                <button
                  key={type}
                  type="button"
                  disabled={!capabilities.supports_publication_types}
                  onClick={() => toggleArrayValue('publication_types', type)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors',
                    selected
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80',
                    !capabilities.supports_publication_types && 'opacity-60',
                  )}
                >
                  {type}
                </button>
              )
            })}
          </div>
          {!capabilities.supports_publication_types && (
            <CapabilityHint message="Publication type filters unavailable for selected sources." />
          )}
        </div>

        <div>
          <Label className="mb-1 block text-sm text-foreground">Languages</Label>
          <div className="flex flex-wrap gap-2">
            {LANGUAGE_OPTIONS.map((language) => {
              const selected = parameters.languages?.includes(language.code)
              return (
                <Badge
                  key={language.code}
                  variant={selected ? 'default' : 'secondary'}
                  className={cn(
                    'cursor-pointer select-none',
                    !capabilities.supports_language_filter && 'opacity-60',
                  )}
                  onClick={() =>
                    capabilities.supports_language_filter &&
                    toggleArrayValue('languages', language.code)
                  }
                >
                  {language.label}
                </Badge>
              )
            })}
          </div>
          {!capabilities.supports_language_filter && (
            <CapabilityHint message="Language filters disabled for selected sources." />
          )}
        </div>

        <div>
          <Label className="mb-1 block text-sm text-foreground">Additional Terms</Label>
          <Textarea
            value={parameters.additional_terms ?? ''}
            placeholder="Boolean expressions, MeSH terms, etc."
            onChange={(event) =>
              updateParameters({
                additional_terms: event.target.value ? event.target.value : null,
              })
            }
            disabled={!capabilities.supports_additional_terms}
          />
          {!capabilities.supports_additional_terms && (
            <CapabilityHint message="Additional syntax not supported by the selected sources." />
          )}
        </div>
      </div>
      </CollapsibleSection>

      {(capabilities.supports_variation_type ||
        capabilities.supports_clinical_significance ||
        capabilities.supports_review_status ||
        capabilities.supports_organism) && (
        <CollapsibleSection
          title="Source Specific"
          description="Filters for specialized sources like ClinVar and UniProt."
          isExpanded={expandedSections.sourceSpecific}
          onToggle={() => toggleSection('sourceSpecific')}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            {capabilities.supports_variation_type && (
              <LabeledInput
                id="variationTypes"
                label="Variation Types (ClinVar)"
                value={(parameters.variation_types ?? []).join(', ')}
                placeholder="e.g., single_nucleotide_variant"
                onChange={(value) =>
                  updateParameters({
                    variation_types: value
                      ? value.split(',').map((s) => s.trim())
                      : [],
                  })
                }
              />
            )}
            {capabilities.supports_clinical_significance && (
              <LabeledInput
                id="clinicalSignificance"
                label="Clinical Significance (ClinVar)"
                value={(parameters.clinical_significance ?? []).join(', ')}
                placeholder="e.g., pathogenic, benign"
                onChange={(value) =>
                  updateParameters({
                    clinical_significance: value
                      ? value.split(',').map((s) => s.trim())
                      : [],
                  })
                }
              />
            )}
            {capabilities.supports_organism && (
              <LabeledInput
                id="organism"
                label="Organism (UniProt)"
                value={parameters.organism ?? ''}
                placeholder="e.g., Human, Mouse"
                onChange={(value) => updateParameters({ organism: value || null })}
              />
            )}
            {capabilities.supports_review_status && (
              <div>
                <Label className="mb-1 block text-sm text-foreground">
                  Review Status (UniProt)
                </Label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => updateParameters({ is_reviewed: true })}
                    className={cn(
                      'rounded-md border px-3 py-1 text-sm transition-colors',
                      parameters.is_reviewed === true
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80',
                    )}
                  >
                    Swiss-Prot (Reviewed)
                  </button>
                  <button
                    type="button"
                    onClick={() => updateParameters({ is_reviewed: false })}
                    className={cn(
                      'rounded-md border px-3 py-1 text-sm transition-colors',
                      parameters.is_reviewed === false
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80',
                    )}
                  >
                    TrEMBL (Unreviewed)
                  </button>
                  <button
                    type="button"
                    onClick={() => updateParameters({ is_reviewed: null })}
                    className={cn(
                      'rounded-md border px-3 py-1 text-sm transition-colors',
                      parameters.is_reviewed === null
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80',
                    )}
                  >
                    All
                  </button>
                </div>
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      <CollapsibleSection
        title="Output"
        description="Control sort order and result limits for the query."
        isExpanded={expandedSections.output}
        onToggle={() => toggleSection('output')}
      >
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <Label className="mb-1 block text-sm text-foreground">Sort Order</Label>
          <div className="flex flex-wrap gap-2">
            {SORT_OPTIONS.map((option) => {
              const selected = (parameters.sort_by ?? 'relevance') === option.value
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={!capabilities.supports_sort_options}
                  onClick={() =>
                    capabilities.supports_sort_options &&
                    updateParameters({ sort_by: option.value })
                  }
                  className={cn(
                    'rounded-md border px-3 py-1 text-sm transition-colors',
                    selected
                      ? 'bg-primary text-primary-foreground shadow'
                      : 'bg-muted text-muted-foreground hover:bg-muted/70',
                    !capabilities.supports_sort_options && 'opacity-60',
                  )}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
          {!capabilities.supports_sort_options && (
            <CapabilityHint message="Sort options unavailable for selected sources." />
          )}
        </div>

        <div>
          <Label className="mb-1 block text-sm text-foreground">Max Results</Label>
          <Input
            type="number"
            min={1}
            max={maxResultsLimit}
            value={parameters.max_results ?? 100}
            onChange={(event) =>
              updateParameters({
                max_results: Math.max(
                  1,
                  Math.min(maxResultsLimit, Number(event.target.value) || 1),
                ),
              })
            }
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Up to {maxResultsLimit.toLocaleString()} results per search.
          </p>
        </div>
      </div>
      </CollapsibleSection>

      <Separator />

      <div>
        <Label className="mb-2 block text-sm font-medium text-foreground">
          Query Preview
        </Label>
        <div className="rounded-md border border-dashed border-muted-foreground/40 bg-muted/40 p-3 text-sm text-muted-foreground">
          {queryPreview}
        </div>
      </div>
    </div>
  )
}

function CollapsibleSection({
  title,
  description,
  isExpanded,
  onToggle,
  children,
}: {
  title: string
  description: string
  isExpanded: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between rounded-md p-2 text-left transition-colors hover:bg-muted/50"
      >
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        {isExpanded ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>
      {isExpanded && <div className="space-y-4">{children}</div>}
    </div>
  )
}

function LabeledInput({
  id,
  label,
  value,
  placeholder,
  onChange,
}: {
  id: string
  label: string
  value: string
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <div>
      <Label htmlFor={id} className="mb-1 block text-sm text-foreground">
        {label}
      </Label>
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}

function SectionHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function CapabilityHint({ message }: { message: string }) {
  return <p className="mt-1 text-xs text-muted-foreground">{message}</p>
}

function buildQueryPreview(parameters: AdvancedQueryParameters): string {
  const tokens: string[] = []
  if (parameters.gene_symbol) {
    tokens.push(`${parameters.gene_symbol}[Title/Abstract]`)
  }
  if (parameters.search_term) {
    tokens.push(parameters.search_term)
  }
  ;(parameters.publication_types ?? []).forEach((type) =>
    tokens.push(`${type}[Publication Type]`),
  )
  ;(parameters.languages ?? []).forEach((language) =>
    tokens.push(`${language}[Language]`),
  )
  if (parameters.date_from || parameters.date_to) {
    const from = parameters.date_from ?? '1800'
    const to = parameters.date_to ?? '3000'
    tokens.push(`${from}:${to}[Publication Date]`)
  }
  if (parameters.additional_terms) {
    tokens.push(parameters.additional_terms)
  }
  if (tokens.length === 0) {
    return 'ALL[All Fields]'
  }
  return tokens.join(' AND ')
}
