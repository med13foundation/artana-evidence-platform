# Research Spaces Management System - Product Requirements Document

**Version:** 1.0
**Last Updated:** 2025-01-XX
**Status:** In Planning
**Owner:** MED13 Foundation Development Team

---

## Executive Summary

The Research Spaces Management System enables the Artana Resource Library platform to scale from a single-syndrome system (MED13) to a multi-syndrome platform supporting multiple research spaces (MED13, MED12, MED14, etc.). Each research space operates as an isolated workspace with its own data sources, team members, curation workflows, and data isolation.

**Key Objectives:**
- Enable multi-tenancy architecture for multiple research spaces
- Provide isolated workspaces per syndrome/research area
- Implement role-based access control per research space
- Create comprehensive admin UI in Next.js for space and member management
- Maintain data isolation and security between spaces

---

## Problem Statement

### Current State
The Artana Resource Library is currently designed as a single-syndrome system:
- All data sources belong to a single global context
- User roles are system-wide, not space-specific
- No isolation between different research initiatives
- Cannot scale to support multiple syndromes (MED12, MED14, etc.)

### Business Need
- **Scalability**: Support multiple research spaces without code changes
- **Isolation**: Each research space needs isolated data and team management
- **Flexibility**: Different teams working on different syndromes need independent workspaces
- **Governance**: Space-specific permissions and access control

### Success Criteria
- ✅ Users can create and manage multiple research spaces
- ✅ Each space has isolated data sources and team members
- ✅ Role-based permissions work per-space (not system-wide)
- ✅ Admin UI provides intuitive space and member management
- ✅ Existing MED13 data migrates seamlessly to MED13 research space

---

## User Stories

### Research Space Management

**US-1: Create Research Space**
- **As a** system administrator or authorized user
- **I want to** create a new research space (e.g., MED12, MED14)
- **So that** I can set up an isolated workspace for a new research initiative
- **Acceptance Criteria:**
  - User can create space with name, slug, and description
  - Slug must be unique and URL-safe (lowercase, alphanumeric, hyphens)
  - Creator automatically becomes space owner
  - Space is created in ACTIVE status

**US-2: List Research Spaces**
- **As a** user
- **I want to** see all research spaces I have access to
- **So that** I can navigate between different workspaces
- **Acceptance Criteria:**
  - User sees only spaces where they have active membership
  - Display shows space name, slug, status, member count
  - Spaces are sortable and filterable by status

**US-3: View Research Space Details**
- **As a** space member
- **I want to** view detailed information about a research space
- **So that** I can understand space configuration and settings
- **Acceptance Criteria:**
  - Shows space metadata (name, description, status, creation date)
  - Displays member count and recent activity
  - Shows space-specific settings and configuration

**US-4: Update Research Space**
- **As a** space owner or admin
- **I want to** update space information and settings
- **So that** I can keep space details current
- **Acceptance Criteria:**
  - Owner/admin can update name, description, status
  - Status changes are validated (e.g., cannot archive active space with active data sources)
  - Changes are audited and logged

**US-5: Archive Research Space**
- **As a** space owner
- **I want to** archive a research space
- **So that** I can preserve data while preventing new activity
- **Acceptance Criteria:**
  - Owner can archive space (soft delete)
  - Archived spaces are read-only
  - Data sources and memberships are preserved
  - Can be restored if needed

### Member Management

**US-6: Invite Member to Space**
- **As a** space owner or admin
- **I want to** invite users to join a research space
- **So that** I can build a team for curation and research
- **Acceptance Criteria:**
  - Can invite by user email or user ID
  - Assign role during invitation (VIEWER, RESEARCHER, CURATOR, ADMIN)
  - Invitation creates pending membership
  - User receives notification (future: email notification)

**US-7: View Space Members**
- **As a** space member
- **I want to** see all members of a research space
- **So that** I know who is working in the space
- **Acceptance Criteria:**
  - List shows all active members with roles
  - Displays member name, email, role, join date
  - Shows pending invitations
  - Filterable by role and status

**US-8: Update Member Role**
- **As a** space owner or admin
- **I want to** change a member's role
- **So that** I can adjust permissions as team needs change
- **Acceptance Criteria:**
  - Owner/admin can change roles (except owner)
  - Role changes are immediate
  - Cannot remove owner role
  - Changes are logged for audit

**US-9: Remove Member from Space**
- **As a** space owner or admin
- **I want to** remove a member from a research space
- **So that** I can manage team composition
- **Acceptance Criteria:**
  - Owner/admin can remove members (except owner)
  - Removal deactivates membership (soft delete)
  - Member loses access to space data
  - Data sources owned by member are handled (reassign or archive)

**US-10: Accept Space Invitation**
- **As a** user
- **I want to** accept an invitation to join a research space
- **So that** I can access the workspace
- **Acceptance Criteria:**
  - User can see pending invitations
  - Accepting invitation activates membership
  - User gains access based on assigned role
  - Join date is recorded

### Data Source Integration

**US-11: Create Data Source in Space**
- **As a** space member with appropriate permissions
- **I want to** create a data source within a research space
- **So that** I can configure data ingestion for the space
- **Acceptance Criteria:**
  - Data source is automatically associated with current space
  - Only space members can create sources
  - Source appears in space-specific data source list
  - Permissions follow space role hierarchy

**US-12: Filter Data Sources by Space**
- **As a** user
- **I want to** see data sources filtered by research space
- **So that** I can work within a specific workspace context
- **Acceptance Criteria:**
  - Data source list filters by current space context
  - Space selector allows switching contexts
  - All data source operations respect space boundaries

---

## Technical Architecture

### Architectural Alignment

This implementation follows the established Clean Architecture patterns documented in:
- **Backend**: `docs/EngineeringArchitecture.md` - Clean Architecture layers, type safety, repository patterns
- **Frontend**: `docs/frontend/EngenieeringArchitectureNext.md` - Next.js patterns, component architecture, React Query
- **Type Safety**: `docs/type_examples.md` - Typed fixtures, mock repositories, validation patterns

**Key Architectural Principles:**
1. **Layer Independence**: Domain → Application → Infrastructure → Presentation
2. **Dependency Inversion**: Domain defines interfaces, infrastructure implements
3. **Type Safety First**: 100% MyPy + TypeScript strict compliance
4. **Immutability**: Domain entities use `ConfigDict(frozen=True)`
5. **Testability**: Typed fixtures, mock repositories, comprehensive coverage

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Admin UI                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Research Spaces Management • Member Management         │ │
│  │  • Space CRUD • Role Assignment • Invitations           │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
                                 │ REST API
                                 │
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Application Layer                                        │ │
│  │  • ResearchSpaceManagementService                        │ │
│  │  • MembershipManagementService                            │ │
│  │  • SpaceAuthorizationService                              │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Domain Layer                                            │ │
│  │  • ResearchSpace • ResearchSpaceMembership               │ │
│  │  • MembershipRole • SpaceStatus                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Infrastructure Layer                                    │ │
│  │  • SQLAlchemy Repositories                               │ │
│  │  • Database Models                                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
                                 │
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  • research_spaces                                           │
│  • research_space_memberships                               │
│  • user_data_sources (with research_space_id FK)           │
└─────────────────────────────────────────────────────────────┘
```

### Domain Model

#### ResearchSpace Entity

Following Clean Architecture patterns with Pydantic models, immutability, and comprehensive validation:

```python
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

class SpaceStatus(str, Enum):
    """Research space lifecycle status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"

class ResearchSpace(BaseModel):
    """
    Domain entity representing a research space.

    Follows Clean Architecture principles:
    - Immutable (frozen=True) - changes create new instances
    - Type-safe with Pydantic validation
    - Business logic encapsulated in methods
    - No infrastructure dependencies
    """
    model_config = ConfigDict(frozen=True)  # Immutable entity

    # Identity
    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(..., min_length=2, max_length=50, description="URL-safe identifier")
    name: str = Field(..., min_length=1, max_length=200, description="Display name")

    # Metadata
    description: str = Field("", max_length=1000)
    owner_id: UUID = Field(..., description="User who created the space")
    status: SpaceStatus = Field(default=SpaceStatus.ACTIVE)

    # Configuration
    settings: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    tags: list[str] = Field(default_factory=list, max_length=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format (URL-safe, lowercase, alphanumeric + hyphens)."""
        import re
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens only")
        return v.lower()

    def update_status(self, new_status: SpaceStatus) -> "ResearchSpace":
        """Create new instance with updated status (immutability pattern)."""
        return self.model_copy(
            update={"status": new_status, "updated_at": datetime.now(UTC)}
        )

    def is_active(self) -> bool:
        """Business logic method - check if space is active."""
        return self.status == SpaceStatus.ACTIVE
```

#### ResearchSpaceMembership Entity

```python
class ResearchSpaceMembership(BaseModel):
    """
    Represents a user's membership in a research space.

    Follows Clean Architecture patterns with immutability and business logic.
    """
    model_config = ConfigDict(frozen=True)  # Immutable entity

    # Identity
    id: UUID = Field(default_factory=uuid4)
    space_id: UUID = Field(...)
    user_id: UUID = Field(...)

    # Role & Permissions
    role: MembershipRole = Field(default=MembershipRole.VIEWER)

    # Invitation Workflow
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None

    # Status
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def can_invite(self) -> bool:
        """Business logic - check if member can invite others."""
        return self.role in [MembershipRole.OWNER, MembershipRole.ADMIN] and self.is_active

    def can_manage_members(self) -> bool:
        """Business logic - check if member can manage other members."""
        return self.role in [MembershipRole.OWNER, MembershipRole.ADMIN] and self.is_active

    def update_role(self, new_role: MembershipRole) -> "ResearchSpaceMembership":
        """Create new instance with updated role (immutability pattern)."""
        return self.model_copy(update={"role": new_role})

    def activate(self) -> "ResearchSpaceMembership":
        """Activate membership (accept invitation)."""
        return self.model_copy(
            update={
                "is_active": True,
                "joined_at": datetime.now(UTC)
            }
        )
```

#### MembershipRole Enum

```python
class MembershipRole(str, Enum):
    OWNER = "owner"        # Full control, cannot be removed
    ADMIN = "admin"        # Manage space settings and members
    CURATOR = "curator"    # Curation permissions
    RESEARCHER = "researcher"  # Read + limited write
    VIEWER = "viewer"      # Read-only access
```

#### SpaceStatus Enum

```python
class SpaceStatus(str, Enum):
    ACTIVE = "active"      # Fully operational
    INACTIVE = "inactive"  # Temporarily disabled
    ARCHIVED = "archived"  # Read-only, preserved
    SUSPENDED = "suspended"  # Disabled by admin
```

### Repository Interfaces

Following the established repository pattern from `src/domain/repositories/base.py`:

```python
from abc import ABC, abstractmethod
from uuid import UUID
from src.domain.entities.research_space import ResearchSpace
from src.domain.repositories.base import Repository

class ResearchSpaceRepository(Repository[ResearchSpace, UUID], ABC):
    """
    Repository interface for research space persistence.

    Extends base Repository pattern with space-specific queries.
    """

    @abstractmethod
    async def get_by_slug(self, slug: str) -> ResearchSpace | None:
        """Get research space by slug."""

    @abstractmethod
    async def get_by_owner(self, owner_id: UUID) -> list[ResearchSpace]:
        """Get all spaces owned by a user."""

    @abstractmethod
    async def get_by_ids(self, space_ids: list[UUID]) -> list[ResearchSpace]:
        """Get multiple spaces by IDs."""

class ResearchSpaceMembershipRepository(Repository[ResearchSpaceMembership, UUID], ABC):
    """
    Repository interface for membership persistence.

    Extends base Repository pattern with membership-specific queries.
    """

    @abstractmethod
    async def get_by_space_and_user(
        self, space_id: UUID, user_id: UUID
    ) -> ResearchSpaceMembership | None:
        """Get membership for user in space."""

    @abstractmethod
    async def get_by_user(self, user_id: UUID) -> list[ResearchSpaceMembership]:
        """Get all memberships for a user."""

    @abstractmethod
    async def get_by_space(
        self, space_id: UUID, active_only: bool = True
    ) -> list[ResearchSpaceMembership]:
        """Get all memberships for a space."""
```

### Domain Services

Following the domain service pattern from `src/domain/services/base.py`:

```python
from src.domain.services.base import DomainService
from src.domain.entities.research_space import ResearchSpace, SpaceStatus

class ResearchSpaceDomainService(DomainService):
    """
    Domain service for research space business logic.

    Contains pure business logic without infrastructure dependencies.
    """

    def validate_space_creation(
        self, name: str, slug: str, owner_id: UUID
    ) -> list[str]:
        """Validate business rules for space creation."""
        errors = []
        if not name.strip():
            errors.append("Space name cannot be empty")
        if not slug.strip():
            errors.append("Space slug cannot be empty")
        # Additional business rules...
        return errors

    def can_archive_space(self, space: ResearchSpace) -> bool:
        """Business rule: Can archive space if no active data sources."""
        # This would check domain rules, not database
        return space.status == SpaceStatus.ACTIVE
```

### Application Service Pattern

Following the application service pattern from `src/application/services/source_management_service.py`:

```python
from dataclasses import dataclass
from uuid import UUID
from src.domain.entities.research_space import ResearchSpace
from src.domain.repositories.research_space_repository import ResearchSpaceRepository
from src.domain.repositories.research_space_membership_repository import ResearchSpaceMembershipRepository
from src.domain.services.research_space_domain_service import ResearchSpaceDomainService

@dataclass
class CreateSpaceRequest:
    """Request DTO for creating a research space."""
    name: str
    slug: str
    description: str = ""
    tags: list[str] | None = None

class ResearchSpaceManagementService:
    """
    Application service for research space management.

    Orchestrates domain services and repositories following Clean Architecture.
    """

    def __init__(
        self,
        space_repository: ResearchSpaceRepository,
        membership_repository: ResearchSpaceMembershipRepository,
        domain_service: ResearchSpaceDomainService,
    ):
        self.space_repository = space_repository
        self.membership_repository = membership_repository
        self.domain_service = domain_service

    async def create_space(
        self, request: CreateSpaceRequest, owner_id: UUID
    ) -> ResearchSpace:
        """Create a new research space with validation."""
        # Validate business rules
        errors = self.domain_service.validate_space_creation(
            request.name, request.slug, owner_id
        )
        if errors:
            raise ValueError(f"Validation failed: {', '.join(errors)}")

        # Check slug uniqueness
        existing = await self.space_repository.get_by_slug(request.slug)
        if existing:
            raise ValueError(f"Space with slug '{request.slug}' already exists")

        # Create domain entity
        space = ResearchSpace(
            name=request.name,
            slug=request.slug,
            description=request.description,
            owner_id=owner_id,
            tags=request.tags or [],
        )

        # Persist via repository
        return await self.space_repository.create(space)
```

### Database Schema

#### research_spaces Table

```sql
CREATE TABLE research_spaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id UUID NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    settings JSONB NOT NULL DEFAULT '{}',
    tags JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_slug CHECK (slug ~ '^[a-z0-9-]+$')
);

CREATE INDEX idx_research_spaces_slug ON research_spaces(slug);
CREATE INDEX idx_research_spaces_owner ON research_spaces(owner_id);
CREATE INDEX idx_research_spaces_status ON research_spaces(status);
```

#### research_space_memberships Table

```sql
CREATE TABLE research_space_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id UUID NOT NULL REFERENCES research_spaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    invited_by UUID REFERENCES users(id),
    invited_at TIMESTAMP WITH TIME ZONE,
    joined_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_active_membership UNIQUE (space_id, user_id, is_active)
        WHERE is_active = TRUE
);

CREATE INDEX idx_memberships_space ON research_space_memberships(space_id);
CREATE INDEX idx_memberships_user ON research_space_memberships(user_id);
CREATE INDEX idx_memberships_active ON research_space_memberships(space_id, is_active)
    WHERE is_active = TRUE;
```

#### user_data_sources Table Update

```sql
-- Add research_space_id foreign key
ALTER TABLE user_data_sources
    ADD COLUMN research_space_id UUID REFERENCES research_spaces(id);

-- Make it required after migration
ALTER TABLE user_data_sources
    ALTER COLUMN research_space_id SET NOT NULL;

CREATE INDEX idx_data_sources_space ON user_data_sources(research_space_id);
```

---

## API Specifications

### Base Path
All research space endpoints are under `/api/spaces`

### Authentication
All endpoints require JWT authentication via Bearer token in Authorization header.

### Endpoints

#### Research Spaces CRUD

**GET /api/spaces**
- **Description**: List all research spaces the user has access to
- **Authentication**: Required
- **Query Parameters**:
  - `status` (optional): Filter by status (active, inactive, archived, suspended)
  - `page` (optional): Page number (default: 1)
  - `limit` (optional): Items per page (default: 20, max: 100)
- **Response**: `{ items: ResearchSpace[], total: number, page: number, limit: number }`
- **Status Codes**: 200 OK, 401 Unauthorized

**GET /api/spaces/{space_id}**
- **Description**: Get detailed information about a specific research space
- **Authentication**: Required
- **Authorization**: User must be a member of the space
- **Response**: `ResearchSpace`
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

**POST /api/spaces**
- **Description**: Create a new research space
- **Authentication**: Required
- **Authorization**: User must have permission to create spaces (system admin or feature flag)
- **Request Body**: `{ name: string, slug: string, description?: string, tags?: string[] }`
- **Response**: `ResearchSpace`
- **Status Codes**: 201 Created, 400 Bad Request, 401 Unauthorized, 409 Conflict (slug exists)

**PATCH /api/spaces/{space_id}**
- **Description**: Update research space information
- **Authentication**: Required
- **Authorization**: User must be space owner or admin
- **Request Body**: `{ name?: string, description?: string, status?: SpaceStatus, tags?: string[] }`
- **Response**: `ResearchSpace`
- **Status Codes**: 200 OK, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found

**DELETE /api/spaces/{space_id}**
- **Description**: Archive a research space (soft delete)
- **Authentication**: Required
- **Authorization**: User must be space owner
- **Response**: `{ message: string }`
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

#### Membership Management

**GET /api/spaces/{space_id}/members**
- **Description**: List all members of a research space
- **Authentication**: Required
- **Authorization**: User must be a member of the space
- **Query Parameters**:
  - `role` (optional): Filter by role
  - `is_active` (optional): Filter by active status (default: true)
- **Response**: `{ items: ResearchSpaceMembership[], total: number }`
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

**POST /api/spaces/{space_id}/members**
- **Description**: Invite a user to join the research space
- **Authentication**: Required
- **Authorization**: User must be space owner or admin
- **Request Body**: `{ user_id: string, role: MembershipRole }`
- **Response**: `ResearchSpaceMembership`
- **Status Codes**: 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict (already member)

**PATCH /api/spaces/{space_id}/members/{membership_id}**
- **Description**: Update a member's role
- **Authentication**: Required
- **Authorization**: User must be space owner or admin
- **Request Body**: `{ role: MembershipRole }`
- **Response**: `ResearchSpaceMembership`
- **Status Codes**: 200 OK, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found

**DELETE /api/spaces/{space_id}/members/{membership_id}**
- **Description**: Remove a member from the research space
- **Authentication**: Required
- **Authorization**: User must be space owner or admin (cannot remove owner)
- **Response**: `{ message: string }`
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

**POST /api/spaces/{space_id}/members/{membership_id}/accept**
- **Description**: Accept a pending space invitation
- **Authentication**: Required
- **Authorization**: User must be the invited user
- **Response**: `ResearchSpaceMembership`
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

#### Data Source Integration

**GET /api/spaces/{space_id}/data-sources**
- **Description**: List data sources for a specific research space
- **Authentication**: Required
- **Authorization**: User must be a member of the space
- **Query Parameters**: Same as existing data sources list endpoint
- **Response**: Same as existing data sources list response
- **Status Codes**: 200 OK, 401 Unauthorized, 403 Forbidden, 404 Not Found

**POST /api/spaces/{space_id}/data-sources**
- **Description**: Create a data source in a research space
- **Authentication**: Required
- **Authorization**: User must be space member with appropriate role
- **Request Body**: Same as existing create data source request
- **Response**: Same as existing data source response
- **Status Codes**: 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found

### Request/Response Models

#### CreateSpaceRequest
```typescript
interface CreateSpaceRequest {
  name: string          // 1-200 characters
  slug: string          // 2-50 characters, lowercase alphanumeric + hyphens
  description?: string  // Max 1000 characters
  tags?: string[]       // Max 10 tags, 50 chars each
}
```

#### UpdateSpaceRequest
```typescript
interface UpdateSpaceRequest {
  name?: string
  description?: string
  status?: SpaceStatus
  tags?: string[]
}
```

#### InviteMemberRequest
```typescript
interface InviteMemberRequest {
  user_id: string       // UUID of user to invite
  role: MembershipRole  // Role to assign
}
```

#### UpdateMemberRoleRequest
```typescript
interface UpdateMemberRoleRequest {
  role: MembershipRole
}
```

---

## UI/UX Requirements

### Next.js Admin Interface Structure

```
/app
  /spaces
    page.tsx                    # Research spaces list
    new
      page.tsx                  # Create new space
    [spaceId]
      page.tsx                  # Space detail & management
      /members
        page.tsx                # Member management (tab)
      /settings
        page.tsx                # Space settings (tab)
```

### Component Architecture

#### Core Components

**ResearchSpacesList** (`/components/research-spaces/ResearchSpacesList.tsx`)
- Displays grid/list of research spaces
- Shows space name, slug, status, member count
- Filterable by status
- Searchable by name/slug
- Click to navigate to space detail

**ResearchSpaceCard** (`/components/research-spaces/ResearchSpaceCard.tsx`)
- Individual space card component
- Displays key information
- Status badge with color coding
- Quick actions (manage, settings)

**ResearchSpaceDetail** (`/components/research-spaces/ResearchSpaceDetail.tsx`)
- Main detail view component
- Tabbed interface: Overview, Members, Settings
- Space information display
- Member management integration
- Settings management

**CreateSpaceForm** (`/components/research-spaces/CreateSpaceForm.tsx`)
- Form for creating new research space
- Validation: name, slug format, uniqueness
- Real-time slug generation from name
- Error handling and success feedback

**SpaceMembersList** (`/components/research-spaces/SpaceMembersList.tsx`)
- Table/list of space members
- Shows user info, role, join date
- Role badges with color coding
- Actions: change role, remove member

**InviteMemberDialog** (`/components/research-spaces/InviteMemberDialog.tsx`)
- Dialog for inviting users
- User search/select
- Role selection dropdown
- Invitation confirmation

**UpdateRoleDialog** (`/components/research-spaces/UpdateRoleDialog.tsx`)
- Dialog for changing member role
- Role selection
- Confirmation and validation

**SpaceSelector** (`/components/research-spaces/SpaceSelector.tsx`)
- Dropdown/selector for switching active space
- Shows current space context
- Quick access to space list
- Used in navigation/header

### Design Specifications

#### Color Coding

**Space Status:**
- Active: Green (`bg-green-500`)
- Inactive: Gray (`bg-gray-500`)
- Archived: Yellow (`bg-yellow-500`)
- Suspended: Red (`bg-red-500`)

**Member Roles:**
- Owner: Purple (`bg-purple-500`)
- Admin: Blue (`bg-blue-500`)
- Curator: Green (`bg-green-500`)
- Researcher: Yellow (`bg-yellow-500`)
- Viewer: Gray (`bg-gray-500`)

#### Layout Requirements

- **Responsive Design**: Mobile-first, works on all screen sizes
- **Accessibility**: WCAG AA compliance, keyboard navigation, screen reader support
- **Loading States**: Skeleton loaders for async data
- **Error Handling**: Clear error messages, retry mechanisms
- **Empty States**: Helpful messages when no data exists

#### User Experience Flow

1. **User logs in** → Sees dashboard with space selector
2. **User clicks "Research Spaces"** → Sees list of accessible spaces
3. **User clicks "Create Space"** → Fills form, creates space
4. **User clicks on space** → Views space detail
5. **User navigates to Members tab** → Sees member list
6. **User clicks "Invite Member"** → Opens dialog, invites user
7. **User changes member role** → Opens dialog, updates role
8. **User removes member** → Confirms, removes member

---

## Security & Permissions

### Permission Model

#### Space-Level Permissions

**OWNER:**
- Full control over space
- Can update space settings
- Can manage all members (add, remove, change roles)
- Cannot be removed from space
- Can archive space

**ADMIN:**
- Can update space settings (except owner transfer)
- Can manage members (add, remove, change roles except owner)
- Cannot archive space
- Can be removed by owner

**CURATOR:**
- Can create/edit data sources
- Can manage curation workflows
- Cannot manage space settings or members
- Can view all space data

**RESEARCHER:**
- Can create data sources
- Can view space data
- Limited write permissions
- Cannot manage space settings or members

**VIEWER:**
- Read-only access to space data
- Cannot create data sources
- Cannot manage space settings or members

### Authorization Checks

All API endpoints implement authorization checks:
1. **JWT Authentication**: Valid token required
2. **Space Membership**: User must be active member of space
3. **Role Verification**: User role must have required permissions
4. **Resource Ownership**: Special checks for owner-only operations

### Data Isolation

- **Database Level**: Foreign key constraints ensure data integrity
- **Application Level**: All queries filter by `research_space_id`
- **API Level**: Space context extracted from URL/header, validated
- **UI Level**: Space selector ensures user works in correct context

---

## Implementation Phases

### Phase 1: Backend Foundation (Week 1-2)

**Domain Layer:**
- [x] Create `ResearchSpace` domain entity with Pydantic BaseModel, `ConfigDict(frozen=True)`
- [x] Create `ResearchSpaceMembership` domain entity with immutability pattern
- [x] Create `MembershipRole` and `SpaceStatus` enums (str, Enum)
- [x] Add field validators and business logic methods
- [x] Create repository interfaces extending `Repository[Entity, UUID]` pattern
- [x] Create domain services for business logic (e.g., `ResearchSpaceDomainService`)
- [x] Ensure 100% MyPy strict compliance

**Infrastructure Layer:**
- [x] Create `ResearchSpaceModel` SQLAlchemy model (extends Base, proper typing)
- [x] Create `ResearchSpaceMembershipModel` SQLAlchemy model
- [x] Implement `SqlAlchemyResearchSpaceRepository` implementing `ResearchSpaceRepository` interface
- [x] Implement `SqlAlchemyResearchSpaceMembershipRepository` implementing `ResearchSpaceMembershipRepository` interface
- [x] Create entity-to-model mappers (domain ↔ infrastructure)
- [x] Create Alembic migration for new tables
- [x] Update `UserDataSourceModel` to include `research_space_id` foreign key
- [x] Create migration to add `research_space_id` to `user_data_sources`
- [x] Add proper database indexes for performance

**Application Layer:**
- [x] Create `ResearchSpaceManagementService` with dependency injection
- [x] Create `MembershipManagementService` with dependency injection
- [x] Create `SpaceAuthorizationService` for permission checks
- [x] Create Request DTOs (`CreateSpaceRequest`, `UpdateSpaceRequest`, etc.) following existing patterns
- [x] Create Response DTOs for API contracts
- [x] Add dependency injection configuration in `infrastructure/dependency_injection/container.py`
- [x] Implement proper error handling with domain exceptions
- [x] Follow existing service patterns (see `SourceManagementService` for reference)

**API Layer:**
- [x] Create `/api/spaces` route module
- [x] Implement CRUD endpoints for research spaces
- [x] Implement membership management endpoints
- [x] Add space context middleware
- [x] Update data source endpoints to require space context
- [x] Add OpenAPI documentation

**Testing:**
- [x] Unit tests for domain entities with typed test fixtures (following `type_examples.md` patterns)
- [x] Unit tests for application services with mock repositories
- [x] Integration tests for API endpoints
- [x] Repository tests with type-safe mocks
- [x] Authorization tests with permission scenarios
- [x] Use `create_test_research_space()` fixture pattern
- [x] Use `MockResearchSpaceRepository` pattern for service tests
- [x] Achieve >85% test coverage for new code
- [x] All tests must pass MyPy strict type checking

### Phase 2: Data Migration (Week 2)

**Migration Tasks:**
- [ ] Create default MED13 research space
- [ ] Migrate existing data sources to MED13 space
- [ ] Create memberships for existing users
- [ ] Verify data integrity
- [ ] Rollback plan documentation

### Phase 3: Frontend Foundation (Week 3-4)

**Type Definitions:**
- [x] Create TypeScript types for research spaces (`src/web/types/research-space.ts`)
- [x] Create TypeScript types for memberships
- [x] Add Zod schemas for runtime validation (following existing patterns)
- [x] Export types from shared types module
- [x] Ensure 100% TypeScript coverage, no `any` types

**API Client:**
- [x] Create `research-spaces.ts` API client module
- [x] Implement all API functions
- [x] Add error handling
- [x] Add request/response types

**React Query Hooks:**
- [x] Create query hooks for research spaces (`useResearchSpaces`, `useResearchSpace`)
- [x] Create mutation hooks for CRUD operations (`useCreateResearchSpace`, etc.)
- [x] Create membership management hooks (`useSpaceMembers`, `useInviteMember`, etc.)
- [x] Add query key factories following existing patterns (`researchSpaceKeys`)
- [x] Add optimistic updates for better UX
- [x] Implement proper error handling and loading states
- [x] Follow existing hook patterns (see `lib/queries/dashboard.ts` for reference)

**Core Components:**
- [x] Create `ResearchSpacesList` component (uses shadcn/ui, React Query)
- [x] Create `ResearchSpaceCard` component (composable, accessible)
- [x] Create `CreateSpaceForm` component (React Hook Form + Zod validation)
- [x] Create `ResearchSpaceDetail` component (tabbed interface, server/client components)
- [x] Create `SpaceMembersList` component (shadcn/ui Table component)
- [x] Create `InviteMemberDialog` component (shadcn/ui Dialog)
- [x] Create `UpdateRoleDialog` component (form validation)
- [x] Create `SpaceSelector` component (dropdown, context-aware)
- [x] All components must be WCAG AA compliant
- [x] All components must have TypeScript types
- [x] Follow component composition patterns from `EngenieeringArchitectureNext.md`

**Pages:**
- [x] Create `/spaces` list page
- [x] Create `/spaces/new` create page
- [x] Create `/spaces/[spaceId]` detail page
- [x] Add navigation links

**Testing:**
- [ ] Component unit tests with React Testing Library
- [ ] Integration tests for forms (form validation, submission)
- [ ] API integration tests (mock API responses)
- [ ] E2E tests for critical flows (Playwright ready)
- [ ] Test coverage >75% for new components
- [ ] All tests follow existing patterns from `__tests__/` directory

### Phase 4: Integration & Polish (Week 4-5)

**Data Source Integration:**
- [x] Update data source list to filter by space
- [x] Update data source create to require space
- [x] Add space context to all data source operations
- [x] Update data source UI components

**Navigation & UX:**
- [x] Add space selector to header/navigation
- [x] Update dashboard to show space context
- [x] Add breadcrumbs
- [x] Improve loading states
- [x] Add error boundaries
- [x] Add success/error toast notifications

**Documentation:**
- [x] API documentation updates (endpoints documented in code)
- [ ] Component documentation (JSDoc comments added)
- [ ] User guide for space management
- [ ] Admin guide for member management

**Quality Assurance:**
- [ ] End-to-end testing
- [ ] Performance testing
- [ ] Accessibility audit
- [ ] Security review
- [ ] User acceptance testing

### Phase 5: Deployment & Monitoring (Week 5)

**Deployment:**
- [ ] Database migration execution plan
- [ ] Backend deployment
- [ ] Frontend deployment
- [ ] Environment configuration
- [ ] Rollback procedures

**Monitoring:**
- [ ] Add logging for space operations
- [ ] Add metrics for space usage
- [ ] Set up alerts for errors
- [ ] Monitor performance

---

## Success Criteria

### Functional Requirements
- ✅ Users can create research spaces with unique slugs
- ✅ Users can view all spaces they have access to
- ✅ Space owners can invite members and assign roles
- ✅ Space admins can manage members and roles
- ✅ Data sources are isolated per research space
- ✅ All API endpoints enforce space-level authorization
- ✅ Existing MED13 data migrates successfully

### Performance Requirements
- ✅ Space list loads in < 500ms
- ✅ Member list loads in < 500ms
- ✅ Space creation completes in < 2s
- ✅ Member invitation completes in < 1s
- ✅ All operations maintain < 100ms database query time

### Quality Requirements
- ✅ 100% TypeScript type coverage (no `any` types)
- ✅ 100% MyPy strict compliance for Python code
- ✅ > 85% test coverage for backend code (domain + application layers)
- ✅ > 75% test coverage for frontend components
- ✅ All components pass accessibility audit (WCAG AA)
- ✅ Zero critical security vulnerabilities
- ✅ API documentation complete and accurate (OpenAPI)
- ✅ All code follows existing architectural patterns
- ✅ Typed test fixtures used throughout (following `type_examples.md`)

### User Experience Requirements
- ✅ Intuitive space management interface
- ✅ Clear role and permission indicators
- ✅ Helpful error messages
- ✅ Responsive design works on mobile
- ✅ Loading states for all async operations

---

## Future Enhancements

### Phase 2 Features (Post-MVP)

**Advanced Space Features:**
- Space templates for quick setup
- Space cloning/duplication
- Space-level data export
- Space analytics and reporting
- Custom space settings and configurations

**Enhanced Member Management:**
- Email invitation notifications
- Bulk member import/export
- Member activity tracking
- Permission inheritance rules
- Custom role definitions

**Integration Enhancements:**
- Space-level API keys
- Space-specific webhooks
- Space-level audit logs
- Space resource quotas
- Space billing/usage tracking

**UI Enhancements:**
- Space dashboard customization
- Advanced filtering and search
- Bulk operations
- Space comparison view
- Activity feed per space

---

## Risk Mitigation

### Technical Risks

**Risk: Data Migration Complexity**
- **Mitigation**: Comprehensive migration script with rollback capability
- **Testing**: Test migration on staging environment first
- **Backup**: Full database backup before migration

**Risk: Performance Impact**
- **Mitigation**: Add database indexes, query optimization
- **Monitoring**: Performance testing before deployment
- **Scaling**: Plan for database scaling if needed

**Risk: Authorization Bugs**
- **Mitigation**: Comprehensive authorization tests
- **Review**: Security code review
- **Audit**: Regular security audits

### Business Risks

**Risk: User Confusion**
- **Mitigation**: Clear UI/UX, user documentation, training
- **Support**: Help documentation and support channels
- **Feedback**: User feedback collection and iteration

**Risk: Adoption Resistance**
- **Mitigation**: Seamless migration, clear benefits communication
- **Training**: User training sessions
- **Support**: Dedicated support during transition

---

## Appendix

### Related Documents
- [Engineering Architecture](./EngineeringArchitecture.md)
- [Next.js Frontend Architecture](./frontend/EngenieeringArchitectureNext.md)
- [Data Sources Plan](./data_sources_plan.md)
- [Authentication PRD](./Auth_PRD_FSD.md)
- [Research Spaces API Documentation](./research-spaces-api.md)
- [Research Spaces Component Documentation](./research-spaces-components.md)

### Glossary

- **Research Space**: An isolated workspace for a research initiative (e.g., MED13, MED12)
- **Membership**: A user's association with a research space, including role
- **Space Owner**: The user who created the space, has full control
- **Space Admin**: User with administrative permissions in a space
- **Data Isolation**: Ensuring data from one space is not accessible from another

### Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-01-XX | Initial PRD creation with architectural alignment | Development Team |

---

## Architectural Alignment Summary

This PRD has been designed to align with the established architectural patterns:

### ✅ Backend Architecture (`EngineeringArchitecture.md`)
- **Clean Architecture Layers**: Domain → Application → Infrastructure → Presentation
- **Repository Pattern**: Interfaces in domain, implementations in infrastructure
- **Domain Services**: Pure business logic without infrastructure dependencies
- **Application Services**: Orchestration with Request/Response DTOs
- **Type Safety**: 100% MyPy strict compliance, Pydantic models with `ConfigDict(frozen=True)`
- **Immutability**: Domain entities use immutability pattern (`model_copy` for updates)

### ✅ Frontend Architecture (`EngenieeringArchitectureNext.md`)
- **Next.js App Router**: Server + Client components pattern
- **Component Architecture**: shadcn/ui components, composition patterns
- **State Management**: React Query for server state, hooks for client state
- **Type Safety**: 100% TypeScript coverage, Zod schemas for validation
- **Testing**: React Testing Library, >75% coverage target
- **Accessibility**: WCAG AA compliance required

### ✅ Type Safety Patterns (`type_examples.md`)
- **Typed Test Fixtures**: `create_test_research_space()` pattern
- **Mock Repositories**: `MockResearchSpaceRepository` for service testing
- **API Validation**: Runtime validation with Pydantic/Zod
- **Type Guards**: Proper type narrowing and validation

### Key Architectural Decisions
1. **Domain Entities**: Immutable Pydantic models with business logic methods
2. **Repositories**: Extend `Repository[Entity, UUID]` generic interface
3. **Services**: Application services orchestrate, domain services contain business rules
4. **Testing**: Typed fixtures and mocks following established patterns
5. **Frontend**: React Query hooks with query key factories, Zod validation

**All implementation must follow these patterns to maintain architectural consistency.**

---

**Document Status**: ✅ Ready for Implementation
**Next Review Date**: After Phase 1 Completion
**Stakeholder Approval**: Pending
