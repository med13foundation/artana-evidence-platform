import type { SourceWorkflowEventsResponse } from '@/types/kernel'

import { mergeWorkflowEvents } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-live-client'

describe('mergeWorkflowEvents', () => {
  it('preserves older server-rendered warning rows when SSE bootstrap contains only recent events', () => {
    const previous: SourceWorkflowEventsResponse = {
      source_id: 'source-1',
      run_id: 'run-1',
      generated_at: '2026-03-09T11:53:25+00:00',
      total: 3,
      has_more: false,
      events: [
        {
          event_id: 'run-1:10',
          source_id: 'source-1',
          run_id: 'run-1',
          occurred_at: '2026-03-09T11:53:24+00:00',
          category: 'run',
          stage: 'graph',
          status: 'completed',
          message: 'Run finished.',
          payload: {},
        },
        {
          event_id: 'run-1:6',
          source_id: 'source-1',
          run_id: 'run-1',
          occurred_at: '2026-03-09T11:39:58+00:00',
          category: 'run',
          event_type: 'query_resolved',
          stage: 'ingestion',
          status: 'fallback',
          level: 'warning',
          message: 'Fell back to base PubMed query configuration.',
          payload: {
            query_generation_fallback_reason: 'agent_requested_escalation',
          },
        },
        {
          event_id: 'run-1:5',
          source_id: 'source-1',
          run_id: 'run-1',
          occurred_at: '2026-03-09T11:39:12+00:00',
          category: 'run',
          event_type: 'run_started',
          stage: 'ingestion',
          status: 'running',
          message: 'Run started.',
          payload: {},
        },
      ],
    }

    const incoming: SourceWorkflowEventsResponse = {
      source_id: 'source-1',
      run_id: 'run-1',
      generated_at: '2026-03-09T11:53:26+00:00',
      total: 2,
      has_more: false,
      events: [
        {
          event_id: 'run-1:10',
          source_id: 'source-1',
          run_id: 'run-1',
          occurred_at: '2026-03-09T11:53:24+00:00',
          category: 'run',
          stage: 'graph',
          status: 'completed',
          message: 'Run finished.',
          payload: {},
        },
        {
          event_id: 'run-1:9',
          source_id: 'source-1',
          run_id: 'run-1',
          occurred_at: '2026-03-09T11:53:20+00:00',
          category: 'graph',
          event_type: 'graph_stage_finished',
          stage: 'graph',
          status: 'completed',
          message: 'Graph stage finished.',
          payload: {},
        },
      ],
    }

    const merged = mergeWorkflowEvents(previous, incoming)

    expect(merged.events.map((event) => event.event_id)).toEqual([
      'run-1:10',
      'run-1:9',
      'run-1:6',
      'run-1:5',
    ])
    expect(merged.events.some((event) => event.level === 'warning')).toBe(true)
  })
})
