"use client"

import type { SourceCatalogEntry, ValidationIssueDTO } from '@/types/generated'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Check, Loader2 } from 'lucide-react'
import { ValidationFeedback } from '@/components/shared/ValidationFeedback'

interface SourceCatalogProps {
  groupedEntries: Record<string, SourceCatalogEntry[]>
  selectedIds: Set<string>
  onToggle: (sourceId: string) => void
  isPending: boolean
  validationIssues: ValidationIssueDTO[]
  isValid: boolean
}

export function SourceCatalog({
  groupedEntries,
  selectedIds,
  onToggle,
  isPending,
  validationIssues,
  isValid,
}: SourceCatalogProps) {
  return (
    <div className="space-y-6">
      {!isValid && validationIssues.length > 0 && (
        <ValidationFeedback issues={validationIssues} />
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Object.entries(groupedEntries).map(([category, sources]) => (
          <Card key={category} className="border-t-4 border-t-primary/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium uppercase text-muted-foreground">
                {category}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {sources.map((source) => {
                const isSelected = selectedIds.has(source.id)
                return (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() => onToggle(source.id)}
                    className={`flex w-full items-center justify-between rounded-md border p-3 text-left transition-all ${
                      isSelected
                        ? 'border-primary bg-primary/10 shadow-sm'
                        : 'border-border bg-card hover:bg-accent'
                    }`}
                    disabled={isPending}
                  >
                    <div>
                      <div className="text-sm font-medium">{source.name}</div>
                      <div className="line-clamp-1 text-xs text-muted-foreground">
                        {source.description}
                      </div>
                    </div>
                    {isPending && isSelected ? (
                      <Loader2 className="size-4 animate-spin text-primary" />
                    ) : (
                      isSelected && <Check className="size-4 text-primary" />
                    )}
                  </button>
                )
              })}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
