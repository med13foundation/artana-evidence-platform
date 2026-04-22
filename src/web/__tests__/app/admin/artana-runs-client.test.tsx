import { render, screen } from '@testing-library/react'

import AdminArtanaRunsClient from '@/app/(dashboard)/admin/artana/runs/admin-artana-runs-client'
import type { ArtanaRunListResponse, ArtanaRunTraceResponse } from '@/types/artana'

const runs: ArtanaRunListResponse = {
  runs: [
    {
      run_id: 'run-1',
      space_id: 'space-1',
      source_ids: ['source-1'],
      source_type: 'pubmed',
      status: 'running',
      current_stage: 'extraction',
      updated_at: '2026-03-07T12:00:00+00:00',
      started_at: '2026-03-07T11:50:00+00:00',
      last_event_type: 'run_summary',
      alert_count: 1,
      alert_codes: ['stuck_run'],
    },
  ],
  total: 1,
  page: 1,
  per_page: 25,
  counters: {
    running: 1,
    failed: 0,
    stuck: 1,
    drift_detected: 0,
    budget_warning: 0,
    tool_unknown_outcome: 0,
  },
}

const trace: ArtanaRunTraceResponse = {
  requested_run_id: 'run-1',
  run_id: 'run-1',
  candidate_run_ids: ['run-1'],
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
  events: [],
  summaries: [],
  linked_records: [],
  raw_tables: [
    {
      table_name: 'runs',
      row_count: 1,
      latest_created_at: '2026-03-07T12:00:00+00:00',
      sample_rows: [],
    },
  ],
}

describe('AdminArtanaRunsClient', () => {
  it('renders filters, run rows, and detail panel content', () => {
    render(
      <AdminArtanaRunsClient
        filters={{ q: 'run-1', page: 1, per_page: 25 }}
        selectedRunId="run-1"
        runs={runs}
        runsError={null}
        trace={trace}
        traceError={null}
      />,
    )

    expect(screen.getByDisplayValue('run-1')).toBeInTheDocument()
    expect(screen.getByText('Artana Runs')).toBeInTheDocument()
    expect(screen.getAllByText('run-1').length).toBeGreaterThan(0)
    expect(screen.getByText('Run detail')).toBeInTheDocument()
    expect(screen.getByText('Legacy Artana tables')).toBeInTheDocument()
    expect(screen.getByText('runs')).toBeInTheDocument()
  })
})
