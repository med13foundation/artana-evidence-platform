"use client"

import { useState } from 'react'

import { ChevronDown, ExternalLink } from 'lucide-react'

import type { DataSource } from '@/types/data-source'
import type {
  DataSourceAiTestFinding,
  DataSourceAiTestResult,
} from '@/lib/api/data-sources'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Separator } from '@/components/ui/separator'

interface DataSourceAiTestDialogProps {
  source: DataSource | null
  result: DataSourceAiTestResult | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return 'Unknown'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

const InfoRow = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between text-sm">
    <span className="text-muted-foreground">{label}</span>
    <span className="text-right font-medium">{value}</span>
  </div>
)

const FindingCard = ({ finding }: { finding: DataSourceAiTestFinding }) => {
  const primaryLink = finding.links[0]?.url
  const secondaryLinks = finding.links.slice(1)

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          {primaryLink ? (
            <a
              href={primaryLink}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-semibold text-primary hover:underline"
            >
              {finding.title}
            </a>
          ) : (
            <p className="text-sm font-semibold">{finding.title}</p>
          )}
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {finding.journal && <span>{finding.journal}</span>}
            {finding.publication_date && <span>{finding.publication_date}</span>}
            {finding.pubmed_id && <span>PMID {finding.pubmed_id}</span>}
          </div>
        </div>
        {primaryLink && (
          <ExternalLink className="mt-1 size-4 text-muted-foreground" />
        )}
      </div>
      {secondaryLinks.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {secondaryLinks.map((link) => (
            <a
              key={`${link.label}-${link.url}`}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              {link.label}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export function DataSourceAiTestDialog({
  source,
  result,
  open,
  onOpenChange,
}: DataSourceAiTestDialogProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  if (!source || !result) {
    return null
  }

  const statusLabel = result.success ? 'Success' : 'Needs attention'
  const modelLabel = result.model || 'Not configured'
  const executedQuery = result.executed_query
  const searchTerms = Array.isArray(result.search_terms) ? result.search_terms : []
  const findings = Array.isArray(result.findings) ? result.findings : []
  const agentRunTables = Array.isArray(result.agent_run_tables) ? result.agent_run_tables : []
  const hasAgentRunTables = agentRunTables.length > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-[720px]">
        <DialogHeader className="shrink-0">
          <DialogTitle>AI test results</DialogTitle>
          <DialogDescription>
            Review the AI-generated query and sample findings for <b>{source.name}</b>.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-6 overflow-y-auto pr-2">
          <section className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={result.success ? 'secondary' : 'destructive'}>
                {statusLabel}
              </Badge>
              <span className="text-sm text-muted-foreground">{result.message}</span>
            </div>
            <div className="space-y-1 rounded-md border p-3">
              <InfoRow label="Model" value={modelLabel} />
              <InfoRow label="Checked at" value={formatTimestamp(result.checked_at)} />
              <InfoRow label="Fetched records" value={result.fetched_records.toString()} />
              <InfoRow label="Sample size" value={result.sample_size.toString()} />
            </div>
          </section>

          <Separator />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Search terms</h3>
            {searchTerms.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {searchTerms.map((term) => (
                  <Badge key={term} variant="outline" className="text-xs">
                    {term}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No search terms were extracted.
              </p>
            )}
            {executedQuery && (
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Executed query</span>
                <p className="break-all rounded bg-muted p-2 font-mono text-xs">{executedQuery}</p>
              </div>
            )}
          </section>

          <Separator />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Sample findings</h3>
            {findings.length > 0 ? (
              <div className="space-y-3">
                {findings.map((finding, index) => (
                  <FindingCard key={`${finding.title}-${index}`} finding={finding} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No findings were returned for this test run.
              </p>
            )}
          </section>

          <Separator />

          <section className="space-y-3">
            <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold">Advanced</h3>
                  <p className="text-xs text-muted-foreground">
                    Runtime state tables recorded for this AI test run.
                  </p>
                </div>
                <CollapsibleTrigger asChild>
                  <Button type="button" variant="ghost" size="sm" className="gap-2">
                    {showAdvanced ? 'Hide details' : 'Show details'}
                    <ChevronDown
                      className={`size-4 transition-transform ${
                        showAdvanced ? 'rotate-180' : ''
                      }`}
                    />
                  </Button>
                </CollapsibleTrigger>
              </div>
              <CollapsibleContent className="space-y-3">
                {result.agent_run_id ? (
                  <div className="rounded-md border p-3">
                    <InfoRow label="Agent run ID" value={result.agent_run_id} />
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No runtime run metadata was recorded for this test. Confirm Postgres
                    is active and runtime state tables are available.
                  </p>
                )}
                {hasAgentRunTables ? (
                  <div className="space-y-3">
                    {agentRunTables.map((table) => {
                      const sampleRows = Array.isArray(table.sample_rows)
                        ? table.sample_rows
                        : []
                      return (
                        <details
                          key={table.table_name}
                          className="rounded-md border p-3"
                        >
                          <summary className="flex cursor-pointer items-center justify-between text-sm font-medium">
                            <span>{table.table_name}</span>
                            <span className="text-xs text-muted-foreground">
                              {table.row_count.toString()} row(s)
                            </span>
                          </summary>
                          <div className="mt-3 space-y-3">
                            <InfoRow
                              label="Latest entry"
                              value={formatTimestamp(table.latest_created_at)}
                            />
                            {sampleRows.length > 0 ? (
                              <div className="space-y-3">
                                {sampleRows.map((row, index) => (
                                  <div key={`${table.table_name}-${index}`}>
                                    <p className="text-xs text-muted-foreground">
                                      Sample row {index + 1}
                                    </p>
                                    <pre className="mt-2 max-h-60 overflow-auto rounded-md bg-muted p-2 text-xs">
                                      {JSON.stringify(row, null, 2)}
                                    </pre>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-muted-foreground">
                                No sample rows captured for this table.
                              </p>
                            )}
                          </div>
                        </details>
                      )
                    })}
                    <p className="text-xs text-muted-foreground">
                      Sample rows show the latest runtime records for this run.
                      Long fields are truncated for readability.
                    </p>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    <p>Runtime table details are not available for this run.</p>
                    <p className="mt-1 text-xs">
                      If you expect data here, verify runtime state tables are present in
                      Postgres and the AI test executed successfully.
                    </p>
                  </div>
                )}
              </CollapsibleContent>
            </Collapsible>
          </section>
        </div>

        <DialogFooter className="shrink-0">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
