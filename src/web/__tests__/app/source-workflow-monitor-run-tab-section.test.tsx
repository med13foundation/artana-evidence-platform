import { render, screen } from '@testing-library/react'

import { RunMonitorTabSection } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-run-tab-section'

describe('RunMonitorTabSection', () => {
  it('renders phase timing breakdown and startup wait metrics', () => {
    render(
      <RunMonitorTabSection
        lastRun={{
          run_id: 'run-1',
          status: 'completed',
          triggered_at: '2026-03-08T09:59:57+00:00',
          accepted_at: '2026-03-08T09:59:57+00:00',
          started_at: '2026-03-08T10:00:00+00:00',
          timing_summary: {
            total_duration_ms: 19000,
            stage_timings: {
              ingestion: {
                stage: 'ingestion',
                status: 'completed',
                started_at: '2026-03-08T10:00:00+00:00',
                completed_at: '2026-03-08T10:00:05+00:00',
                duration_ms: 5000,
              },
              enrichment: {
                stage: 'enrichment',
                status: 'completed',
                started_at: '2026-03-08T10:00:07+00:00',
                completed_at: '2026-03-08T10:00:10+00:00',
                duration_ms: 3000,
              },
              extraction: {
                stage: 'extraction',
                status: 'completed',
                started_at: '2026-03-08T10:00:11+00:00',
                completed_at: '2026-03-08T10:00:19+00:00',
                duration_ms: 8000,
                timeout_budget_ms: 300000,
              },
              graph: {
                stage: 'graph',
                status: 'completed',
                started_at: '2026-03-08T10:00:20+00:00',
                completed_at: '2026-03-08T10:00:21+00:00',
                duration_ms: 1000,
              },
            },
          },
          stage_statuses: {
            ingestion: 'completed',
            enrichment: 'completed',
            extraction: 'completed',
            graph: 'completed',
          },
          cost_summary: {
            total_cost_usd: 0,
            stage_costs_usd: {
              ingestion: 0.01,
            },
          },
          diagnostic_signals: {},
        }}
        counters={{
          extraction_extracted_count: 4,
        }}
        runRows={[]}
        documentRows={[]}
        paperCandidateRows={[]}
        queueRows={[]}
        extractionRows={[]}
        eventRows={[
          {
            event_id: 'run-1:1',
            event_type: 'run_claimed',
            queue_wait_ms: 2500,
          },
        ]}
        warnings={[]}
      />,
    )

    expect(screen.getByText('Stage Timing')).toBeInTheDocument()
    expect(screen.getByText('Slowest phase')).toBeInTheDocument()
    expect(screen.getByText('Extraction · 8.0 s')).toBeInTheDocument()
    expect(screen.getByText('Fastest phase')).toBeInTheDocument()
    expect(screen.getByText('Graph · 1.0 s')).toBeInTheDocument()
    expect(screen.getByText('Longest handoff gap')).toBeInTheDocument()
    expect(screen.getByText('Queue wait')).toBeInTheDocument()
    expect(screen.getByText('2.5 s')).toBeInTheDocument()
    expect(screen.getByText('Ingestion cost')).toBeInTheDocument()
    expect(screen.getByText('Gap From Previous')).toBeInTheDocument()
    expect(screen.getByText('Timeout Budget')).toBeInTheDocument()
    expect(screen.getByText('5m 0s')).toBeInTheDocument()
  })

  it('renders query fallback warnings with fallback labeling instead of escalation status', () => {
    render(
      <RunMonitorTabSection
        lastRun={{
          run_id: 'run-2',
          status: 'running',
          diagnostic_signals: {},
        }}
        counters={{}}
        runRows={[]}
        documentRows={[]}
        paperCandidateRows={[]}
        queueRows={[]}
        extractionRows={[]}
        eventRows={[
          {
            event_id: 'run-2:1',
            event_type: 'query_resolved',
            level: 'warning',
            stage: 'ingestion',
            status: 'fallback',
            message: 'Resolved PubMed query configuration.',
            occurred_at: '2026-03-09T10:50:49+00:00',
            payload: {
              query_generation_fallback_reason: 'agent_requested_escalation',
            },
          },
        ]}
        warnings={[]}
      />,
    )

    expect(
      screen.getByText('Fell back to base PubMed query configuration.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'ingestion · fallback: agent_requested_escalation · 2026-03-09T10:50:49+00:00',
      ),
    ).toBeInTheDocument()
  })

  it('renders fetched paper outcomes with drop reasons', () => {
    render(
      <RunMonitorTabSection
        lastRun={{
          run_id: 'run-3',
          status: 'completed',
          diagnostic_signals: {},
        }}
        counters={{}}
        runRows={[]}
        documentRows={[]}
        paperCandidateRows={[
          {
            external_record_id: 'pubmed:pubmed_id:28659948',
            paper_outcome: 'rescued_and_processed',
            paper_reason:
              'Retained by full-text rescue after semantic relevance filtering.',
            rescued_by_full_text: true,
            enrichment_status: 'enriched',
            extraction_status: 'extracted',
          },
          {
            external_record_id: 'pubmed:pubmed_id:32553196',
            paper_outcome: 'dropped',
            paper_reason:
              'Filtered out by semantic relevance; full-text rescue did not retain it.',
            rescued_by_full_text: false,
          },
        ]}
        queueRows={[]}
        extractionRows={[]}
        eventRows={[]}
        warnings={[]}
      />,
    )

    expect(screen.getByText('Fetched paper outcomes')).toBeInTheDocument()
    expect(screen.getByText('pubmed:pubmed_id:28659948')).toBeInTheDocument()
    expect(screen.getByText('rescued_and_processed')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Filtered out by semantic relevance; full-text rescue did not retain it.',
      ),
    ).toBeInTheDocument()
  })
})
