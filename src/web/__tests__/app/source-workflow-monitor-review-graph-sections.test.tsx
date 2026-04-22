import { render, screen } from '@testing-library/react'

import { ReviewTabSection } from '@/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-review-graph-sections'

describe('ReviewTabSection', () => {
  it('shows AI-generated evidence sentence badge and paper links', () => {
    render(
      <ReviewTabSection
        relationRows={[
          {
            evidence_id: 'e-1',
            document_id: 'doc-1',
            relation_type: 'ASSOCIATED_WITH',
            curation_status: 'DRAFT',
            source_entity_label: 'MED13',
            target_entity_label: 'Cardiomyopathy',
            evidence_summary: 'Optional relation summary.',
            evidence_sentence: 'Generated reviewer-aid sentence.',
            evidence_sentence_source: 'artana_generated',
            evidence_sentence_rationale:
              'No direct span found; inferred from extraction context.',
            paper_links: [
              {
                label: 'PubMed',
                url: 'https://pubmed.ncbi.nlm.nih.gov/40214304/',
                source: 'external_record_id',
              },
            ],
          },
        ]}
        pendingRelationRows={[]}
        reviewQueueRows={[]}
        rejectedRows={[]}
      />,
    )

    expect(
      screen.getByText('AI-generated (not verbatim span)'),
    ).toBeInTheDocument()

    const link = screen.getByRole('link', { name: 'PubMed' })
    expect(link).toHaveAttribute(
      'href',
      'https://pubmed.ncbi.nlm.nih.gov/40214304/',
    )
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('shows sentence and paper-link fallbacks when data is missing', () => {
    render(
      <ReviewTabSection
        relationRows={[
          {
            evidence_id: 'e-2',
            document_id: 'doc-2',
            relation_type: 'ASSOCIATED_WITH',
            curation_status: 'DRAFT',
            source_entity_label: 'MED13',
            target_entity_label: 'Cardiomyopathy',
            evidence_summary: 'No sentence available.',
            evidence_sentence: null,
            evidence_sentence_source: null,
            evidence_sentence_rationale: null,
            paper_links: [],
          },
        ]}
        pendingRelationRows={[]}
        reviewQueueRows={[]}
        rejectedRows={[]}
      />,
    )

    expect(screen.getByText('No source links')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(
      screen.queryByText('AI-generated (not verbatim span)'),
    ).not.toBeInTheDocument()
  })
})
