import { Badge } from '@/components/ui/badge'

import { TableCard } from './source-workflow-monitor-primitives'
import type { RunMonitorTabSectionProps } from './source-workflow-monitor-run-tab-types'
import { formatDuration, toNumber } from './source-workflow-monitor-run-tab-utils'
import { asRecord, displayValue } from './source-workflow-monitor-utils'

type RunMonitorTablesProps = Omit<RunMonitorTabSectionProps, 'warnings' | 'lastRun' | 'counters'>

export function RunMonitorTables({
  runRows,
  documentRows,
  paperCandidateRows,
  queueRows,
  extractionRows,
  eventRows,
}: RunMonitorTablesProps) {
  const agentDecisionRows = eventRows.filter((row) => {
    return (
      String(row.event_type ?? '') === 'query_generated' ||
      typeof row.agent_kind === 'string' ||
      String(row.event_type ?? '') === 'document_finished'
    )
  })
  const changeRows = eventRows.filter((row) => {
    const scopeKind = String(row.scope_kind ?? '')
    if (
      scopeKind === 'dictionary' ||
      scopeKind === 'concept' ||
      scopeKind === 'relation' ||
      scopeKind === 'graph'
    ) {
      return true
    }
    const payload = asRecord(row.payload)
    return (
      toNumber(payload.persisted_relations_count) > 0 ||
      toNumber(payload.concept_members_created_count) > 0 ||
      toNumber(payload.concept_aliases_created_count) > 0 ||
      toNumber(payload.concept_decisions_proposed_count) > 0 ||
      toNumber(payload.dictionary_variables_created) > 0 ||
      toNumber(payload.dictionary_synonyms_created) > 0 ||
      toNumber(payload.dictionary_entity_types_created) > 0
    )
  })

  return (
    <>
      <TableCard
        title="Timeline"
        rows={eventRows}
        emptyText="No persisted workflow events found."
        limit={40}
        rowKey={(row, index) => `${displayValue(row.event_id)}-${index}`}
        columns={[
          { header: 'When', render: (row) => displayValue(row.occurred_at) },
          { header: 'Stage', render: (row) => <Badge variant="outline">{displayValue(row.stage)}</Badge> },
          { header: 'Type', className: 'font-mono text-xs', render: (row) => displayValue(row.event_type) },
          { header: 'Status', render: (row) => displayValue(row.status) },
          { header: 'Duration', render: (row) => formatDuration(row.duration_ms) },
          { header: 'Message', className: 'max-w-[520px] truncate', render: (row) => displayValue(row.message) },
        ]}
      />

      <TableCard
        title="Pipeline runs"
        rows={runRows}
        emptyText="No pipeline runs found."
        limit={50}
        rowKey={(row, index) => `${displayValue(row.run_id)}-${index}`}
        columns={[
          { header: 'Run', className: 'font-mono text-xs', render: (row) => displayValue(row.run_id) },
          { header: 'Status', render: (row) => <Badge variant="outline">{displayValue(row.status)}</Badge> },
          { header: 'Started', render: (row) => displayValue(row.started_at) },
          { header: 'Completed', render: (row) => displayValue(row.completed_at) },
          { header: 'Executed query', className: 'max-w-[500px] truncate font-mono text-xs', render: (row) => displayValue(row.executed_query) },
        ]}
      />

      <TableCard
        title="Agent Decisions"
        rows={agentDecisionRows}
        emptyText="No agent decisions recorded yet."
        limit={25}
        rowKey={(row, index) => `${displayValue(row.event_id)}-${index}`}
        columns={[
          { header: 'When', render: (row) => displayValue(row.occurred_at) },
          { header: 'Agent', render: (row) => displayValue(row.agent_kind ?? row.event_type) },
          { header: 'Document', render: (row) => displayValue(row.scope_id) },
          { header: 'Status', render: (row) => displayValue(row.status) },
          { header: 'Reason', className: 'max-w-[520px] truncate', render: (row) => displayValue(asRecord(row.payload).reason ?? row.message) },
        ]}
      />

      <TableCard
        title="Changes"
        rows={changeRows}
        emptyText="No dictionary, concept, relation, or graph deltas recorded yet."
        limit={25}
        rowKey={(row, index) => `${displayValue(row.event_id)}-${index}`}
        columns={[
          { header: 'When', render: (row) => displayValue(row.occurred_at) },
          { header: 'Kind', render: (row) => displayValue(row.scope_kind) },
          { header: 'Document', render: (row) => displayValue(row.scope_id) },
          { header: 'Delta', className: 'max-w-[520px] truncate', render: (row) => displayValue(row.payload) },
        ]}
      />

      <TableCard
        title="Fetched paper outcomes"
        rows={paperCandidateRows}
        emptyText="No fetched-paper outcomes recorded yet."
        rowKey={(row, index) => `${displayValue(row.external_record_id)}-${index}`}
        columns={[
          {
            header: 'External Record',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.external_record_id),
          },
          {
            header: 'Outcome',
            render: (row) => <Badge variant="outline">{displayValue(row.paper_outcome)}</Badge>,
          },
          {
            header: 'Reason',
            className: 'max-w-[520px] truncate',
            render: (row) => displayValue(row.paper_reason),
          },
          {
            header: 'Rescued',
            render: (row) => (row.rescued_by_full_text ? 'yes' : 'no'),
          },
          {
            header: 'Processing',
            render: (row) => {
              const enrichment = displayValue(row.enrichment_status)
              const extraction = displayValue(row.extraction_status)
              if (enrichment === '—' && extraction === '—') {
                return '—'
              }
              return `${enrichment} / ${extraction}`
            },
          },
        ]}
      />

      <TableCard
        title="Recent papers (source_documents)"
        rows={documentRows}
        emptyText="No document rows found."
        rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
        columns={[
          { header: 'Document ID', className: 'font-mono text-xs', render: (row) => displayValue(row.id) },
          { header: 'External Record', className: 'font-mono text-xs', render: (row) => displayValue(row.external_record_id) },
          { header: 'Enrichment', render: (row) => displayValue(row.enrichment_status) },
          { header: 'Extraction', render: (row) => displayValue(row.extraction_status) },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <TableCard
          title="Extraction queue rows"
          rows={queueRows}
          emptyText="No queue rows found."
          rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
          columns={[
            { header: 'Queue ID', className: 'font-mono text-xs', render: (row) => displayValue(row.id) },
            { header: 'Record', className: 'font-mono text-xs', render: (row) => displayValue(row.source_record_id) },
            { header: 'Status', render: (row) => displayValue(row.status) },
            { header: 'Attempts', render: (row) => displayValue(row.attempts) },
          ]}
        />
        <TableCard
          title="Publication extraction rows"
          rows={extractionRows}
          emptyText="No extraction rows found."
          rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
          columns={[
            { header: 'Extraction ID', className: 'font-mono text-xs', render: (row) => displayValue(row.id) },
            { header: 'Status', render: (row) => displayValue(row.status) },
            { header: 'Text source', render: (row) => displayValue(row.text_source) },
            { header: 'Facts', render: (row) => displayValue(row.facts_count) },
          ]}
        />
      </div>
    </>
  )
}
