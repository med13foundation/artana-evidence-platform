# Research Spaces Component Documentation

## Overview

This document provides comprehensive documentation for React components used in the Research Spaces management UI. All components are built with Next.js, TypeScript, React Query, and shadcn/ui components.

**Location**: `src/web/components/research-spaces/`

---

## Core Components

### SpaceContextProvider

**File**: `src/web/components/space-context-provider.tsx`

Global context provider for managing the currently selected research space across the application.

#### Features

- Persists selected space ID in `localStorage`
- Automatically extracts space ID from URL routes (`/spaces/{spaceId}`)
- Falls back to first available space if no space is selected
- Provides loading state for space data fetching

#### Usage

```tsx
import { SpaceContextProvider } from '@/components/space-context-provider'

function App() {
  return (
    <SpaceContextProvider>
      {/* Your app content */}
    </SpaceContextProvider>
  )
}
```

#### Hook: `useSpaceContext()`

```tsx
import { useSpaceContext } from '@/components/space-context-provider'

function MyComponent() {
  const { currentSpaceId, setCurrentSpaceId, isLoading } = useSpaceContext()

  // currentSpaceId: string | null
  // setCurrentSpaceId: (spaceId: string | null) => void
  // isLoading: boolean
}
```

#### Context Value

```typescript
interface SpaceContextValue {
  currentSpaceId: string | null
  setCurrentSpaceId: (spaceId: string | null) => void
  isLoading: boolean
}
```

---

### SpaceSelector

**File**: `src/web/components/research-spaces/SpaceSelector.tsx`

Dropdown component for selecting the current research space. Integrates with `SpaceContextProvider` for global state management.

#### Props

```typescript
interface SpaceSelectorProps {
  currentSpaceId?: string        // Override context space ID
  onSpaceChange?: (spaceId: string) => void  // Custom change handler
}
```

#### Features

- Displays loading state while fetching spaces
- Shows space name and slug
- Automatically navigates to space detail page on selection (unless custom handler provided)
- Integrates with `SpaceContextProvider` for persistence

#### Usage

```tsx
import { SpaceSelector } from '@/components/research-spaces/SpaceSelector'

function Header() {
  return (
    <div>
      <SpaceSelector />
    </div>
  )
}
```

#### Custom Handler Example

```tsx
<SpaceSelector
  onSpaceChange={(spaceId) => {
    // Custom logic
    console.log('Space changed to:', spaceId)
  }}
/>
```

---

### ResearchSpacesList

**File**: `src/web/components/research-spaces/ResearchSpacesList.tsx`

Component for displaying a list of research spaces with cards and actions.

#### Features

- Fetches and displays all research spaces
- Shows loading and error states
- Displays "Create Space" button (always visible, even on error)
- Each space card shows name, description, status, and member count
- Clicking a card navigates to space detail page

#### Usage

```tsx
import { ResearchSpacesList } from '@/components/research-spaces/ResearchSpacesList'

function SpacesPage() {
  return (
    <div>
      <h1>Research Spaces</h1>
      <ResearchSpacesList />
    </div>
  )
}
```

#### Displayed Information

- Space name and slug
- Description
- Status badge (active/inactive/archived/suspended)
- Member count
- Created date
- Owner information

---

### ResearchSpaceCard

**File**: `src/web/components/research-spaces/ResearchSpaceCard.tsx`

Card component for displaying a single research space in a list.

#### Props

```typescript
interface ResearchSpaceCardProps {
  space: ResearchSpace
  onClick?: (spaceId: string) => void
}
```

#### Features

- Displays space name, slug, and description
- Shows status badge
- Shows member count
- Clickable card (navigates to detail page by default)
- Responsive design with hover effects

#### Usage

```tsx
import { ResearchSpaceCard } from '@/components/research-spaces/ResearchSpaceCard'

function SpacesList({ spaces }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {spaces.map(space => (
        <ResearchSpaceCard
          key={space.id}
          space={space}
          onClick={(spaceId) => router.push(`/spaces/${spaceId}`)}
        />
      ))}
    </div>
  )
}
```

---

### ResearchSpaceDetail

**File**: `src/web/components/research-spaces/ResearchSpaceDetail.tsx`

Component for displaying detailed information about a research space and managing members.

#### Props

```typescript
interface ResearchSpaceDetailProps {
  spaceId: string
}
```

#### Features

- Fetches and displays space details
- Shows space information (name, description, status, tags)
- Tabs for Overview, Members, and Settings
- Member management (invite, update roles, remove)
- Data source listing
- Permission-based UI (only owners/admins can manage members)

#### Usage

```tsx
import { ResearchSpaceDetail } from '@/components/research-spaces/ResearchSpaceDetail'

function SpaceDetailPage({ params }) {
  const { spaceId } = params
  return <ResearchSpaceDetail spaceId={spaceId} />
}
```

#### Tabs

1. **Overview**: Space information, statistics, recent activity
2. **Members**: List of members, invite dialog, role management
3. **Settings**: Space settings, tags, status management (owner/admin only)

---

### CreateSpaceForm

**File**: `src/web/components/research-spaces/CreateSpaceForm.tsx`

Form component for creating a new research space.

#### Features

- Form validation using `react-hook-form` and `zod`
- Auto-generates slug from name
- Real-time slug validation
- Toast notifications for success/error
- Automatic redirect to new space on success
- Session expiration handling with redirect to login

#### Form Fields

- **Name**: Required, 1-100 characters
- **Slug**: Required, 3-50 characters, auto-generated from name
- **Description**: Optional, max 500 characters
- **Tags**: Optional, array of strings

#### Usage

```tsx
import { CreateSpaceForm } from '@/components/research-spaces/CreateSpaceForm'

function CreateSpacePage() {
  return (
    <div>
      <h1>Create Research Space</h1>
      <CreateSpaceForm />
    </div>
  )
}
```

#### Validation Schema

```typescript
const createSpaceSchema = z.object({
  name: z.string().min(1).max(100),
  slug: z.string().min(3).max(50).regex(/^[a-z0-9-]+$/),
  description: z.string().max(500).optional(),
  tags: z.array(z.string()).optional(),
})
```

#### Error Handling

- **401 Unauthorized**: Redirects to login with session expired message
- **409 Conflict**: Shows slug conflict error
- **Network Error**: Shows generic error message
- **Validation Errors**: Displays field-level errors

---

### InviteMemberDialog

**File**: `src/web/components/research-spaces/InviteMemberDialog.tsx`

Dialog component for inviting users to join a research space.

#### Props

```typescript
interface InviteMemberDialogProps {
  spaceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}
```

#### Features

- User search/selection
- Role selection (owner, admin, researcher, viewer)
- Form validation
- Toast notifications
- Closes dialog on success

#### Usage

```tsx
import { InviteMemberDialog } from '@/components/research-spaces/InviteMemberDialog'
import { useState } from 'react'

function MembersTab({ spaceId }) {
  const [dialogOpen, setDialogOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setDialogOpen(true)}>
        Invite Member
      </Button>
      <InviteMemberDialog
        spaceId={spaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSuccess={() => {
          // Refresh member list
          queryClient.invalidateQueries(['space-members', spaceId])
        }}
      />
    </>
  )
}
```

#### Form Fields

- **User**: Required, user selection (search/autocomplete)
- **Role**: Required, dropdown with options: owner, admin, researcher, viewer

---

### UpdateRoleDialog

**File**: `src/web/components/research-spaces/UpdateRoleDialog.tsx`

Dialog component for updating a member's role in a research space.

#### Props

```typescript
interface UpdateRoleDialogProps {
  membershipId: string
  spaceId: string
  currentRole: MembershipRole
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}
```

#### Features

- Role selection dropdown
- Form validation
- Toast notifications
- Permission checks (only owners/admins can update roles)

#### Usage

```tsx
import { UpdateRoleDialog } from '@/components/research-spaces/UpdateRoleDialog'
import { useState } from 'react'

function MemberRow({ membership }) {
  const [dialogOpen, setDialogOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setDialogOpen(true)}>
        Update Role
      </Button>
      <UpdateRoleDialog
        membershipId={membership.id}
        spaceId={membership.space_id}
        currentRole={membership.role}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </>
  )
}
```

---

### SpaceMembersList

**File**: `src/web/components/research-spaces/SpaceMembersList.tsx`

Component for displaying and managing members of a research space.

#### Props

```typescript
interface SpaceMembersListProps {
  spaceId: string
  canManage?: boolean  // Whether current user can manage members
}
```

#### Features

- Fetches and displays all members
- Shows member information (name, email, role, join date)
- Role badges
- Actions for updating/removing members (if `canManage` is true)
- Loading and error states

#### Usage

```tsx
import { SpaceMembersList } from '@/components/research-spaces/SpaceMembersList'

function MembersTab({ spaceId, userRole }) {
  const canManage = ['owner', 'admin'].includes(userRole)

  return (
    <div>
      <h2>Members</h2>
      <SpaceMembersList spaceId={spaceId} canManage={canManage} />
    </div>
  )
}
```

---

## Utility Functions

### role-utils.ts

**File**: `src/web/components/research-spaces/role-utils.ts`

Utility functions for working with membership roles.

#### Functions

```typescript
// Get human-readable role label
function getRoleLabel(role: MembershipRole): string

// Get role color for badges
function getRoleColor(role: MembershipRole): string

// Check if role can manage members
function canManageMembers(role: MembershipRole): boolean

// Check if role can update space settings
function canUpdateSpace(role: MembershipRole): boolean

// Check if role can delete space
function canDeleteSpace(role: MembershipRole): boolean
```

#### Usage

```tsx
import { getRoleLabel, getRoleColor, canManageMembers } from '@/components/research-spaces/role-utils'

function MemberBadge({ role }) {
  return (
    <Badge color={getRoleColor(role)}>
      {getRoleLabel(role)}
    </Badge>
  )
}

function MemberActions({ userRole }) {
  if (canManageMembers(userRole)) {
    return <Button>Manage Members</Button>
  }
  return null
}
```

---

## React Query Hooks

### useResearchSpaces

**File**: `src/web/lib/queries/research-spaces.ts`

Hook for fetching the list of research spaces.

```typescript
const { data, isLoading, error } = useResearchSpaces()
```

**Returns**:
- `data`: `{ spaces: ResearchSpace[], total: number }`
- `isLoading`: boolean
- `error`: Error | null

---

### useResearchSpace

**File**: `src/web/lib/queries/research-spaces.ts`

Hook for fetching a single research space by ID.

```typescript
const { data, isLoading, error } = useResearchSpace(spaceId)
```

**Returns**:
- `data`: `ResearchSpace | undefined`
- `isLoading`: boolean
- `error`: Error | null

---

### useCreateResearchSpace

**File**: `src/web/lib/queries/research-spaces.ts`

Hook for creating a new research space.

```typescript
const createMutation = useCreateResearchSpace()

createMutation.mutate({
  name: "MED13",
  slug: "med13",
  description: "..."
})
```

**Returns**: React Query mutation object with `mutate`, `mutateAsync`, `isLoading`, `error`, etc.

---

### useSpaceMembers

**File**: `src/web/lib/queries/research-spaces.ts`

Hook for fetching members of a research space.

```typescript
const { data, isLoading, error } = useSpaceMembers(spaceId)
```

**Returns**:
- `data`: `{ memberships: Membership[], total: number }`
- `isLoading`: boolean
- `error`: Error | null

---

## Type Definitions

### ResearchSpace

```typescript
interface ResearchSpace {
  id: string
  slug: string
  name: string
  description: string
  owner_id: string
  status: 'active' | 'inactive' | 'archived' | 'suspended'
  settings: Record<string, any>
  tags: string[]
  created_at: string
  updated_at: string
}
```

### MembershipRole

```typescript
type MembershipRole = 'owner' | 'admin' | 'researcher' | 'viewer'
```

### ResearchSpaceMembership

```typescript
interface ResearchSpaceMembership {
  id: string
  space_id: string
  user_id: string
  role: MembershipRole
  invited_by: string | null
  invited_at: string | null
  joined_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}
```

---

## Best Practices

### 1. Always Use SpaceContextProvider

Wrap your app with `SpaceContextProvider` to enable global space state management:

```tsx
// app/layout.tsx
import { SpaceContextProvider } from '@/components/space-context-provider'

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <SpaceContextProvider>
          {children}
        </SpaceContextProvider>
      </body>
    </html>
  )
}
```

### 2. Use React Query Hooks

Always use the provided React Query hooks instead of direct API calls:

```tsx
// ✅ Good
const { data } = useResearchSpaces()

// ❌ Bad
const [spaces, setSpaces] = useState([])
useEffect(() => {
  fetch('/api/research-spaces').then(...)
}, [])
```

### 3. Handle Loading and Error States

Always handle loading and error states in your components:

```tsx
function MyComponent() {
  const { data, isLoading, error } = useResearchSpace(spaceId)

  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage error={error} />
  if (!data) return <NotFound />

  return <SpaceContent space={data} />
}
```

### 4. Use Toast Notifications

Use `sonner` toast notifications for user feedback:

```tsx
import { toast } from 'sonner'

function MyComponent() {
  const mutation = useCreateResearchSpace()

  const handleSubmit = async (data) => {
    try {
      await mutation.mutateAsync(data)
      toast.success('Space created successfully!')
    } catch (error) {
      toast.error('Failed to create space')
    }
  }
}
```

### 5. Check Permissions

Always check user permissions before showing actions:

```tsx
function SpaceActions({ space, userRole }) {
  const canUpdate = ['owner', 'admin'].includes(userRole)
  const canDelete = userRole === 'owner'

  return (
    <div>
      {canUpdate && <Button>Update</Button>}
      {canDelete && <Button variant="destructive">Delete</Button>}
    </div>
  )
}
```

---

## Testing

### Component Testing

Components can be tested using React Testing Library:

```tsx
import { render, screen } from '@testing-library/react'
import { SpaceSelector } from '@/components/research-spaces/SpaceSelector'

test('renders space selector', () => {
  render(<SpaceSelector />)
  expect(screen.getByLabelText('Space:')).toBeInTheDocument()
})
```

### Mocking React Query

Mock React Query hooks in tests:

```tsx
jest.mock('@/lib/queries/research-spaces', () => ({
  useResearchSpaces: () => ({
    data: { spaces: [mockSpace] },
    isLoading: false,
    error: null,
  }),
}))
```

---

## Accessibility

All components follow accessibility best practices:

- Proper ARIA labels
- Keyboard navigation support
- Focus management
- Screen reader support
- Semantic HTML elements

---

## Performance Considerations

- Components use React Query for efficient data fetching and caching
- Space context uses `localStorage` for persistence (client-side only)
- Lazy loading for large lists
- Memoization for expensive computations
- Optimistic updates for better UX
