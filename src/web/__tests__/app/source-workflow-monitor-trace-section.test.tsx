import { render, screen } from '@testing-library/react'

import { TraceTabSection } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-trace-section'
import type { ArtanaRunTraceResponse } from '@/types/artana'

const trace: ArtanaRunTraceResponse = {
  requested_run_id: 'pipeline-1',
  run_id: 'resolved-run-1',
  candidate_run_ids: ['resolved-run-1'],
  space_id: 'space-1',
  source_ids: ['source-1'],
  source_types: ['pubmed'],
  status: 'running',
  last_event_seq: 4,
  last_event_type: 'run_summary',
  progress_percent: 72,
  current_stage: 'extraction',
  completed_stages: ['ingestion', 'enrichment'],
  started_at: '2026-03-07T11:50:00+00:00',
  updated_at: '2026-03-07T12:00:00+00:00',
  eta_seconds: 90,
  blocked_on: null,
  failure_reason: null,
  error_category: null,
  explain: { cost_total: 0.2 },
  alerts: [
    {
      code: 'stuck_run',
      severity: 'warning',
      title: 'Run may be stuck',
      description: 'No recent updates.',
      triggered_at: '2026-03-07T12:00:00+00:00',
      metadata: {},
    },
  ],
  events: [
    {
      seq: 4,
      event_id: 'event-4',
      event_type: 'run_summary',
      timestamp: '2026-03-07T12:00:00+00:00',
      parent_step_key: null,
      step_key: 'extract',
      tool_name: null,
      tool_outcome: null,
      payload: { summary_type: 'trace::cost' },
    },
  ],
  summaries: [
    {
      summary_type: 'trace::cost',
      timestamp: '2026-03-07T12:00:00+00:00',
      step_key: 'extract',
      payload: { total_cost: 0.2, budget_usd_limit: 1.0 },
    },
  ],
  linked_records: [
    {
      record_type: 'source_document',
      record_id: 'doc-1',
      research_space_id: 'space-1',
      source_id: 'source-1',
      document_id: 'doc-1',
      source_type: 'pubmed',
      status: 'extracted',
      label: 'PMID-40214304',
      created_at: '2026-03-07T11:51:00+00:00',
      updated_at: '2026-03-07T11:59:00+00:00',
      metadata: {},
    },
  ],
  raw_tables: null,
}

describe('TraceTabSection', () => {
  it('renders an empty state when no run is selected', () => {
    render(<TraceTabSection selectedRunId={undefined} trace={null} traceError={null} />)

    expect(
      screen.getByText('Select a pipeline run to inspect Artana trace detail.'),
    ).toBeInTheDocument()
  })

  it('renders alert badges and linked record details when trace data exists', () => {
    render(
      <TraceTabSection
        selectedRunId="pipeline-1"
        trace={trace}
        traceError={null}
      />,
    )

    expect(screen.getByText('Run health')).toBeInTheDocument()
    expect(screen.getByText('Run may be stuck')).toBeInTheDocument()
    expect(screen.getByText('Recent Artana events')).toBeInTheDocument()
    expect(screen.getByText('Linked MED13 records')).toBeInTheDocument()
    expect(screen.getByText('PMID-40214304')).toBeInTheDocument()
  })
})
