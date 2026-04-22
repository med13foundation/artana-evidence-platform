import {
  parseSourceWorkflowBootstrapEvent,
  parseSourceWorkflowEventsEvent,
  parseSourceWorkflowSnapshotEvent,
  parseSpaceWorkflowBootstrapEvent,
  parseSpaceWorkflowSourceCardEvent,
  parseWorkflowStreamErrorEvent,
} from '@/hooks/workflow-stream-parser'

describe('workflow stream parser', () => {
  it('parses source bootstrap payload', () => {
    const payload = parseSourceWorkflowBootstrapEvent(JSON.stringify({
      monitor: {
        source_snapshot: {},
        last_run: null,
        pipeline_runs: [],
        documents: [],
        document_status_counts: {},
        extraction_queue: [],
        extraction_queue_status_counts: {},
        publication_extractions: [],
        publication_extraction_status_counts: {},
        relation_review: {},
        graph_summary: null,
        operational_counters: {},
        warnings: [],
      },
      events: [],
      generated_at: '2026-01-01T00:00:00+00:00',
      run_id: 'run-1',
    }))

    expect(payload).not.toBeNull()
    expect(payload?.run_id).toBe('run-1')
    expect(payload?.events).toEqual([])
  })

  it('parses source snapshot and events payloads', () => {
    const snapshot = parseSourceWorkflowSnapshotEvent(JSON.stringify({
      monitor: {
        source_snapshot: {},
        last_run: null,
        pipeline_runs: [],
        documents: [],
        document_status_counts: {},
        extraction_queue: [],
        extraction_queue_status_counts: {},
        publication_extractions: [],
        publication_extraction_status_counts: {},
        relation_review: {},
        graph_summary: null,
        operational_counters: {},
        warnings: [],
      },
      generated_at: '2026-01-01T00:00:00+00:00',
      run_id: null,
    }))
    const events = parseSourceWorkflowEventsEvent(JSON.stringify({
      events: [
        {
          event_id: 'event-1',
          source_id: 'source-1',
          run_id: null,
          occurred_at: '2026-01-01T00:00:00+00:00',
          category: 'run',
          stage: null,
          status: 'running',
          message: 'Running',
          payload: {},
        },
      ],
      generated_at: '2026-01-01T00:00:00+00:00',
      run_id: null,
    }))

    expect(snapshot?.generated_at).toContain('2026-01-01')
    expect(events?.events).toHaveLength(1)
  })

  it('parses space bootstrap and card payloads', () => {
    const bootstrap = parseSpaceWorkflowBootstrapEvent(JSON.stringify({
      sources: [
        {
          source_id: 'source-1',
          workflow_status: {
            active_pipeline_run_id: 'run-1',
            last_pipeline_status: 'running',
            last_failed_stage: null,
            pending_paper_count: 2,
            pending_relation_review_count: 1,
            extraction_extracted_count: 1,
            extraction_failed_count: 1,
            extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
            graph_edges_delta_last_run: 3,
            graph_edges_total: 8,
          },
          events: [
            {
              event_id: 'event-1',
              occurred_at: '2026-01-01T00:00:00+00:00',
              category: 'run',
              stage: null,
              status: 'running',
              message: 'Pipeline running',
            },
          ],
          generated_at: '2026-01-01T00:00:00+00:00',
        },
      ],
      generated_at: '2026-01-01T00:00:00+00:00',
    }))
    const card = parseSpaceWorkflowSourceCardEvent(JSON.stringify({
      source_id: 'source-1',
      workflow_status: {
        last_pipeline_status: 'completed',
        last_failed_stage: null,
        pending_paper_count: 0,
        pending_relation_review_count: 0,
        extraction_extracted_count: 2,
        extraction_failed_count: 0,
        extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
        graph_edges_delta_last_run: 1,
        graph_edges_total: 9,
      },
      events: [],
      generated_at: '2026-01-01T00:00:00+00:00',
    }))

    expect(bootstrap?.sources).toHaveLength(1)
    expect(bootstrap?.sources[0]?.workflow_status.active_pipeline_run_id).toBe('run-1')
    expect(card?.workflow_status.graph_edges_total).toBe(9)
  })

  it('extracts error message and rejects invalid payloads', () => {
    expect(parseWorkflowStreamErrorEvent(JSON.stringify({ message: 'failure' }))).toBe(
      'failure',
    )
    expect(parseSourceWorkflowBootstrapEvent('not-json')).toBeNull()
    expect(parseSpaceWorkflowSourceCardEvent(JSON.stringify({ source_id: 'x' }))).toBeNull()
  })
})
