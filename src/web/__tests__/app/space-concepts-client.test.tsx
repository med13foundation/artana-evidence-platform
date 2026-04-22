import { fireEvent, render, screen } from '@testing-library/react'

import SpaceConceptsClient from '@/app/(dashboard)/spaces/[spaceId]/space-concepts-client'

const refreshMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: refreshMock,
  }),
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/concepts/concept-sets-panel', () => ({
  ConceptSetsPanel: () => <div>Sets Panel</div>,
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/concepts/concept-members-panel', () => ({
  ConceptMembersPanel: () => <div>Members Panel</div>,
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/concepts/concept-policy-panel', () => ({
  ConceptPolicyPanel: () => <div>Policy Panel</div>,
}))

jest.mock('@/app/(dashboard)/spaces/[spaceId]/concepts/concept-decisions-panel', () => ({
  ConceptDecisionsPanel: () => <div>Decisions Panel</div>,
}))

describe('SpaceConceptsClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  const baseProps = {
    spaceId: 'space-1',
    canEditConcepts: true,
    canReviewDecisions: true,
    data: {
      sets: {
        concept_sets: [
          {
            id: 'set-1',
            research_space_id: 'space-1',
            name: 'Core',
            slug: 'core',
            domain_context: 'general',
            description: null,
            review_status: 'ACTIVE' as const,
            is_active: true,
            created_by: 'manual:user',
            source_ref: null,
            created_at: '2026-03-03T00:00:00Z',
            updated_at: '2026-03-03T00:00:00Z',
          },
        ],
        total: 1,
      },
      members: {
        concept_members: [],
        total: 0,
      },
      aliases: {
        concept_aliases: [],
        total: 0,
      },
      policy: null,
      decisions: {
        concept_decisions: [],
        total: 0,
      },
    },
    errors: {
      sets: null,
      members: null,
      aliases: null,
      policy: null,
      decisions: null,
    },
  }

  it('renders concept manager heading, summary stats, and tabs', () => {
    render(<SpaceConceptsClient {...baseProps} />)

    expect(screen.getByText('Concept Manager')).toBeInTheDocument()
    expect(screen.getByText('Concept Sets')).toBeInTheDocument()
    expect(screen.getByText('Members & Aliases')).toBeInTheDocument()
    expect(screen.getByText('Policy')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Decisions' })).toBeInTheDocument()
  })

  it('shows read-only note when user cannot edit concepts', () => {
    render(
      <SpaceConceptsClient
        {...baseProps}
        canEditConcepts={false}
        canReviewDecisions={false}
      />,
    )

    expect(screen.getByText(/read-only access/i)).toBeInTheDocument()
  })

  it('refresh button calls router.refresh', () => {
    render(<SpaceConceptsClient {...baseProps} />)

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))

    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
