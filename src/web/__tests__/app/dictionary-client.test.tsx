import { fireEvent, render, screen } from '@testing-library/react'

import DictionaryClient from '@/app/(dashboard)/admin/dictionary/dictionary-client'

const refreshMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: refreshMock,
  }),
}))

jest.mock('@/app/(dashboard)/admin/dictionary/variable-create-card', () => ({
  CreateVariableCard: () => <div>Create Variable Card</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/variables-table-card', () => ({
  VariablesTableCard: () => <div>Variables Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/transforms-table-card', () => ({
  TransformsTableCard: () => <div>Transforms Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/policies-table-card', () => ({
  PoliciesTableCard: () => <div>Policies Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/constraints-table-card', () => ({
  ConstraintsTableCard: () => <div>Constraints Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/entity-types-table-card', () => ({
  EntityTypesTableCard: () => <div>Entity Types Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/relation-types-table-card', () => ({
  RelationTypesTableCard: () => <div>Relation Types Table</div>,
}))

jest.mock('@/app/(dashboard)/admin/dictionary/dictionary-curation-card', () => ({
  DictionaryCurationCard: () => <div>Dictionary Curation Card</div>,
}))

describe('DictionaryClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  const baseProps = {
    data: {
      variables: { variables: [], total: 0 },
      transforms: { transforms: [], total: 0 },
      policies: { policies: [], total: 0 },
      constraints: { constraints: [], total: 0, offset: 0, limit: 100 },
      entityTypes: { entity_types: [], total: 0, offset: 0, limit: 100 },
      relationTypes: { relation_types: [], total: 0, offset: 0, limit: 100 },
    },
    errors: {},
  }

  it('renders dictionary tabs for deterministic governance views', () => {
    render(<DictionaryClient {...baseProps} />)

    expect(screen.getByText('Dictionary')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Curation' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Transforms' })).toBeInTheDocument()
  })

  it('refresh button calls router.refresh', () => {
    render(<DictionaryClient {...baseProps} />)

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))
    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
