"use client"

import { render, screen } from '@testing-library/react'
import { SourceParameterModal } from '@/components/data-discovery/ResultsView'
import { DEFAULT_ADVANCED_SETTINGS } from '@/components/data-discovery/advanced-settings'
import type {
  AdvancedQueryParameters,
  SourceCatalogEntry,
} from '@/lib/types/data-discovery'

const baseParameters: AdvancedQueryParameters = {
  gene_symbol: 'MED13',
  search_term: 'syndrome',
  date_from: null,
  date_to: null,
  publication_types: [],
  languages: [],
  sort_by: 'relevance',
  max_results: 25,
  additional_terms: null,
}

const catalogEntry: SourceCatalogEntry = {
  id: 'pubmed-source',
  name: 'PubMed Clinical',
  description: 'Clinical PubMed interface',
  category: 'Scientific Literature',
  subcategory: 'PubMed',
  tags: ['pubmed', 'articles'],
  param_type: 'gene',
  source_type: 'pubmed',
  is_active: true,
  requires_auth: false,
  usage_count: 10,
  success_rate: 0.98,
  capabilities: {
    supports_date_range: true,
    supports_publication_types: true,
    supports_language_filter: false,
    supports_sort_options: true,
    supports_additional_terms: false,
    max_results_limit: 250,
    supported_storage_use_cases: [],
    supports_variation_type: false,
    supports_clinical_significance: false,
    supports_review_status: false,
    supports_organism: false,
  },
}

describe('SourceParameterModal', () => {
  it('shows storage target summary and capability badges', () => {
    render(
      <SourceParameterModal
        open
        entry={catalogEntry}
        parameters={baseParameters}
        advancedSettings={DEFAULT_ADVANCED_SETTINGS}
        defaultParameters={baseParameters}
        defaultAdvancedSettings={DEFAULT_ADVANCED_SETTINGS}
        onClose={jest.fn()}
        onSave={jest.fn()}
      />,
    )

    expect(screen.getByText(/Storage target/i)).toBeInTheDocument()
    expect(screen.getByText(/PDF storage backend/i)).toBeInTheDocument()
    expect(screen.getByText(/Advanced filter capabilities/i)).toBeInTheDocument()
    // Date range appears in both the collapsible section header and the label
    expect(screen.getAllByText(/Date range/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Max results limit: 250/i)).toBeInTheDocument()
  })
})
