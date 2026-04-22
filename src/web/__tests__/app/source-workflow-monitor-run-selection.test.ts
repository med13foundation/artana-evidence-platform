import { resolveInitialWorkflowRunId } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-run-selection'

describe('resolveInitialWorkflowRunId', () => {
  it('prefers the requested run id when it is provided', () => {
    expect(
      resolveInitialWorkflowRunId(
        'run-requested',
        {
          source_snapshot: {},
          last_run: { run_id: 'run-latest' },
          pipeline_runs: [{ run_id: 'run-fallback' }],
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
        {
          source_id: 'source-1',
          runs: [{ run_id: 'run-fallback' }],
          total: 1,
        },
      ),
    ).toBe('run-requested')
  })

  it('falls back to the latest run id from monitor payloads', () => {
    expect(
      resolveInitialWorkflowRunId(
        undefined,
        {
          source_snapshot: {},
          last_run: { run_id: 'run-latest' },
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
        null,
      ),
    ).toBe('run-latest')
  })

  it('falls back to the pipeline run list when monitor has no last run', () => {
    expect(
      resolveInitialWorkflowRunId(
        undefined,
        {
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
        {
          source_id: 'source-1',
          runs: [{ run_id: 'run-fallback' }],
          total: 1,
        },
      ),
    ).toBe('run-fallback')
  })
})
