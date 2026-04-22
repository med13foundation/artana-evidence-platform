import { render, screen } from '@testing-library/react'

import { SetupTabSection } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-setup-run-sections'

describe('SetupTabSection', () => {
  it('renders warning events from the selected run timeline', () => {
    render(
      <SetupTabSection
        sourceSnapshot={{
          status: 'active',
          query: 'MED13',
          model_id: 'gpt-5',
          open_access_only: true,
          source_type: 'pubmed',
          max_results: 4,
        }}
        schedule={{
          enabled: true,
          frequency: 'daily',
        }}
        selectedRunId="run-1"
        warnings={[]}
        eventRows={[
          {
            event_id: 'run-1:1',
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
      />,
    )

    expect(screen.getByText('Errors And Warnings')).toBeInTheDocument()
    expect(
      screen.getByText('Fell back to base PubMed query configuration.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'ingestion · fallback: agent_requested_escalation · 2026-03-09T10:50:49+00:00',
      ),
    ).toBeInTheDocument()
  })
})
