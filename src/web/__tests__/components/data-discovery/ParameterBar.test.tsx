"use client"

import { render, screen } from '@testing-library/react'
import { useState } from 'react'
import userEvent from '@testing-library/user-event'
import { ParameterBar } from '@/components/data-discovery/ParameterBar'
import type {
  AdvancedQueryParameters,
  QueryParameterCapabilities,
} from '@/lib/types/data-discovery'

const BASE_PARAMETERS: AdvancedQueryParameters = {
  gene_symbol: null,
  search_term: null,
  date_from: null,
  date_to: null,
  publication_types: [],
  languages: [],
  sort_by: 'relevance',
  max_results: 100,
  additional_terms: null,
}

const FULL_CAPABILITIES: QueryParameterCapabilities = {
  supports_date_range: true,
  supports_publication_types: true,
  supports_language_filter: true,
  supports_sort_options: true,
  supports_additional_terms: true,
  max_results_limit: 500,
  supported_storage_use_cases: [],
  supports_variation_type: false,
  supports_clinical_significance: false,
  supports_review_status: false,
  supports_organism: false,
}

describe('ParameterBar', () => {
  it('updates query preview when inputs change', async () => {
    const user = userEvent.setup()

    function ControlledParameterBar() {
      const [parameters, setParameters] = useState(BASE_PARAMETERS)
      return (
        <ParameterBar
          parameters={parameters}
          capabilities={FULL_CAPABILITIES}
          onParametersChange={setParameters}
        />
      )
    }

    render(<ControlledParameterBar />)

    await user.type(screen.getByLabelText(/Gene Symbol/i), 'tp53')

    expect(screen.getByText(/TP53\[Title\/Abstract]/i)).toBeInTheDocument()
  })

  it('shows capability hint when filters disabled', () => {
    render(
      <ParameterBar
        parameters={BASE_PARAMETERS}
        capabilities={{
          ...FULL_CAPABILITIES,
          supports_date_range: false,
        }}
        onParametersChange={jest.fn()}
      />,
    )

    expect(
      screen.getByText(/Current sources do not support date filtering/i),
    ).toBeInTheDocument()
  })
})
