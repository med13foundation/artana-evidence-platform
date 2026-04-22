import { act, renderHook } from '@testing-library/react'

import { useSourceWorkflowStream } from '@/hooks/use-source-workflow-stream'
import { useSpaceWorkflowStream } from '@/hooks/use-space-workflow-stream'

interface EventSourceListenerMap {
  [event: string]: Array<(event: Event) => void>
}

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false
  private listeners: EventSourceListenerMap = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(event: string, listener: (event: Event) => void): void {
    this.listeners[event] ??= []
    this.listeners[event].push(listener)
  }

  close(): void {
    this.closed = true
  }

  emitOpen(): void {
    this.onopen?.(new Event('open'))
  }

  emitError(): void {
    this.onerror?.(new Event('error'))
  }

  emitMessage(event: string, payload: unknown): void {
    const listeners = this.listeners[event] ?? []
    const message = new MessageEvent(event, {
      data: JSON.stringify(payload),
    })
    listeners.forEach((listener) => {
      listener(message)
    })
  }
}

function buildMonitorPayload() {
  return {
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
  }
}

describe('workflow stream hooks', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    Object.defineProperty(globalThis, 'EventSource', {
      value: MockEventSource,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    jest.clearAllMocks()
    jest.useRealTimers()
  })

  it('handles space stream events and exposes parsed error details', () => {
    const onBootstrap = jest.fn()
    const onSourceCardStatus = jest.fn()
    const { result, unmount } = renderHook(() =>
      useSpaceWorkflowStream({
        spaceId: 'space-1',
        sourceIds: ['source-1'],
        enabled: true,
        onBootstrap,
        onSourceCardStatus,
      }),
    )

    const stream = MockEventSource.instances[0]
    act(() => {
      stream.emitOpen()
    })
    expect(result.current.isConnected).toBe(true)

    act(() => {
      stream.emitMessage('bootstrap', {
        sources: [
          {
            source_id: 'source-1',
            workflow_status: {
              last_pipeline_status: 'running',
              last_failed_stage: null,
              pending_paper_count: 2,
              pending_relation_review_count: 1,
              extraction_extracted_count: 1,
              extraction_failed_count: 1,
              extraction_skipped_count: 0,
            extraction_timeout_failed_count: 0,
              graph_edges_delta_last_run: 3,
              graph_edges_total: 10,
            },
            events: [],
            generated_at: '2026-01-01T00:00:00+00:00',
          },
        ],
        generated_at: '2026-01-01T00:00:00+00:00',
      })
      stream.emitMessage('source_card_status', {
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
          graph_edges_total: 11,
        },
        events: [],
        generated_at: '2026-01-01T00:00:01+00:00',
      })
      stream.emitMessage('error', { message: 'stream-failed' })
    })

    expect(onBootstrap).toHaveBeenCalledTimes(1)
    expect(onSourceCardStatus).toHaveBeenCalledTimes(1)
    expect(result.current.lastError).toBe('stream-failed')

    unmount()
  })

  it('activates fallback after repeated stream failures', () => {
    jest.useFakeTimers()
    jest.spyOn(Math, 'random').mockReturnValue(0)
    const { result, unmount } = renderHook(() =>
      useSpaceWorkflowStream({
        spaceId: 'space-1',
        sourceIds: ['source-1'],
        enabled: true,
      }),
    )

    for (let i = 0; i < 3; i += 1) {
      const stream = MockEventSource.instances[MockEventSource.instances.length - 1]
      act(() => {
        stream.emitError()
      })
      act(() => {
        jest.advanceTimersByTime(20_000)
      })
    }

    expect(result.current.isFallbackActive).toBe(true)
    expect(MockEventSource.instances.length).toBeGreaterThan(1)

    unmount()
  })

  it('dispatches source bootstrap, snapshot, and workflow events', () => {
    const onBootstrap = jest.fn()
    const onSnapshot = jest.fn()
    const onEvents = jest.fn()
    renderHook(() =>
      useSourceWorkflowStream({
        spaceId: 'space-1',
        sourceId: 'source-1',
        runId: 'run-1',
        enabled: true,
        onBootstrap,
        onSnapshot,
        onEvents,
      }),
    )

    const stream = MockEventSource.instances[0]
    act(() => {
      stream.emitOpen()
      stream.emitMessage('bootstrap', {
        monitor: buildMonitorPayload(),
        events: [],
        generated_at: '2026-01-01T00:00:00+00:00',
        run_id: 'run-1',
      })
      stream.emitMessage('snapshot', {
        monitor: buildMonitorPayload(),
        generated_at: '2026-01-01T00:00:01+00:00',
        run_id: 'run-1',
      })
      stream.emitMessage('workflow_events', {
        events: [
          {
            event_id: 'event-1',
            source_id: 'source-1',
            run_id: 'run-1',
            occurred_at: '2026-01-01T00:00:01+00:00',
            category: 'run',
            stage: null,
            status: 'running',
            message: 'running',
            payload: {},
          },
        ],
        generated_at: '2026-01-01T00:00:02+00:00',
        run_id: 'run-1',
      })
    })

    expect(onBootstrap).toHaveBeenCalledTimes(1)
    expect(onSnapshot).toHaveBeenCalledTimes(1)
    expect(onEvents).toHaveBeenCalledTimes(1)
  })
})
