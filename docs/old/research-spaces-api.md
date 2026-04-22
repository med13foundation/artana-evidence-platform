# Research Spaces API Documentation

## Overview

The Research Spaces API provides endpoints for managing multi-tenant research spaces, memberships, and associated data sources. This API enables the Artana Resource Library to support multiple research spaces (e.g., MED13, MED12, MED14) with isolated data and team management.

**Base Path**: `/research-spaces`

**Authentication**: All endpoints require JWT Bearer token authentication via the `Authorization` header:
```
Authorization: Bearer <jwt_token>
```

## Response Models

### ResearchSpaceResponse

```typescript
{
  id: UUID
  slug: string
  name: string
  description: string
  owner_id: UUID
  status: "active" | "inactive" | "archived" | "suspended"
  settings: Record<string, any>
  tags: string[]
  created_at: ISO8601 datetime
  updated_at: ISO8601 datetime
}
```

### MembershipResponse

```typescript
{
  id: UUID
  space_id: UUID
  user_id: UUID
  role: "owner" | "admin" | "researcher" | "viewer"
  invited_by: UUID | null
  invited_at: ISO8601 datetime | null
  joined_at: ISO8601 datetime | null
  is_active: boolean
  created_at: ISO8601 datetime
  updated_at: ISO8601 datetime
}
```

### DataSourceResponse

```typescript
{
  id: UUID
  owner_id: UUID
  research_space_id: UUID | null
  name: string
  description: string
  source_type: "api" | "file" | "database"
  status: "active" | "inactive" | "error"
  created_at: ISO8601 datetime
  updated_at: ISO8601 datetime
}
```

## Research Space Endpoints

### Create Research Space

**POST** `/research-spaces`

Create a new research space. The authenticated user becomes the owner.

**Request Body**:
```json
{
  "name": "MED13 Research Space",
  "slug": "med13",
  "description": "Default research space for MED13 syndrome",
  "settings": {},
  "tags": ["med13", "syndrome"]
}
```

**Validation Rules**:
- `name`: Required, 1-100 characters
- `slug`: Required, 3-50 characters, lowercase alphanumeric and hyphens only, must be unique
- `description`: Optional, max 500 characters
- `settings`: Optional, JSON object
- `tags`: Optional, array of strings

**Response**: `201 Created` with `ResearchSpaceResponse`

**Error Responses**:
- `400 Bad Request`: Invalid input data or validation error
- `401 Unauthorized`: Missing or invalid authentication token
- `409 Conflict`: Slug already exists

**Example**:
```bash
curl -X POST http://localhost:8080/research-spaces \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MED13 Research Space",
    "slug": "med13",
    "description": "Default research space for MED13 syndrome"
  }'
```

---

### List Research Spaces

**GET** `/research-spaces`

Get a paginated list of research spaces. Returns all active spaces by default, or filtered by owner if specified.

**Query Parameters**:
- `skip` (optional): Number of records to skip (default: 0, min: 0)
- `limit` (optional): Maximum number of records (default: 50, min: 1, max: 100)
- `owner_id` (optional): Filter by owner UUID

**Response**: `200 OK` with:
```json
{
  "spaces": [ResearchSpaceResponse, ...],
  "total": 10,
  "skip": 0,
  "limit": 50
}
```

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces?skip=0&limit=20" \
  -H "Authorization: Bearer <token>"
```

---

### Get Research Space by ID

**GET** `/research-spaces/{space_id}`

Get detailed information about a specific research space.

**Path Parameters**:
- `space_id`: UUID of the research space

**Response**: `200 OK` with `ResearchSpaceResponse`

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Research space not found

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

---

### Get Research Space by Slug

**GET** `/research-spaces/slug/{slug}`

Get detailed information about a research space by its slug.

**Path Parameters**:
- `slug`: URL-friendly identifier (e.g., "med13")

**Response**: `200 OK` with `ResearchSpaceResponse`

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Research space with slug not found

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces/slug/med13" \
  -H "Authorization: Bearer <token>"
```

---

### Update Research Space

**PUT** `/research-spaces/{space_id}`

Update a research space. Only the owner or admins can update spaces.

**Path Parameters**:
- `space_id`: UUID of the research space

**Request Body**:
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "status": "active",
  "settings": {},
  "tags": ["updated", "tags"]
}
```

**Validation Rules**:
- All fields are optional
- `name`: 1-100 characters if provided
- `description`: max 500 characters if provided
- `status`: Must be one of: "active", "inactive", "archived", "suspended"

**Response**: `200 OK` with `ResearchSpaceResponse`

**Error Responses**:
- `400 Bad Request`: Invalid input data
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not owner or admin
- `404 Not Found`: Research space not found

**Example**:
```bash
curl -X PUT "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "description": "Updated description"
  }'
```

---

### Delete Research Space

**DELETE** `/research-spaces/{space_id}`

Delete a research space. Only the owner can delete spaces.

**Path Parameters**:
- `space_id`: UUID of the research space

**Response**: `204 No Content`

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not the owner
- `404 Not Found`: Research space not found

**Example**:
```bash
curl -X DELETE "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

---

## Membership Endpoints

### Invite Member

**POST** `/research-spaces/{space_id}/members`

Invite a user to join a research space. Only owners and admins can invite members.

**Path Parameters**:
- `space_id`: UUID of the research space

**Request Body**:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "role": "researcher"
}
```

**Validation Rules**:
- `user_id`: Required, valid UUID
- `role`: Required, must be one of: "owner", "admin", "researcher", "viewer"

**Response**: `201 Created` with `MembershipResponse`

**Error Responses**:
- `400 Bad Request`: Invalid input data or invalid role
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not owner or admin
- `404 Not Found`: Research space or user not found

**Example**:
```bash
curl -X POST "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/members" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "456e7890-e89b-12d3-a456-426614174000",
    "role": "researcher"
  }'
```

---

### List Space Members

**GET** `/research-spaces/{space_id}/members`

Get all members of a research space. User must be a member of the space.

**Path Parameters**:
- `space_id`: UUID of the research space

**Query Parameters**:
- `skip` (optional): Number of records to skip (default: 0, min: 0)
- `limit` (optional): Maximum number of records (default: 50, min: 1, max: 100)

**Response**: `200 OK` with:
```json
{
  "memberships": [MembershipResponse, ...],
  "total": 5,
  "skip": 0,
  "limit": 50
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not a member of the space

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/members" \
  -H "Authorization: Bearer <token>"
```

---

### Update Member Role

**PUT** `/research-spaces/{space_id}/members/{membership_id}/role`

Update a member's role in a research space. Only owners and admins can update roles.

**Path Parameters**:
- `space_id`: UUID of the research space
- `membership_id`: UUID of the membership record

**Request Body**:
```json
{
  "role": "admin"
}
```

**Validation Rules**:
- `role`: Required, must be one of: "owner", "admin", "researcher", "viewer"

**Response**: `200 OK` with `MembershipResponse`

**Error Responses**:
- `400 Bad Request`: Invalid role
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not owner or admin
- `404 Not Found`: Membership not found

**Example**:
```bash
curl -X PUT "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/members/789e0123-e89b-12d3-a456-426614174000/role" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "admin"
  }'
```

---

### Remove Member

**DELETE** `/research-spaces/{space_id}/members/{membership_id}`

Remove a member from a research space. Only owners and admins can remove members.

**Path Parameters**:
- `space_id`: UUID of the research space
- `membership_id`: UUID of the membership record

**Response**: `204 No Content`

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not owner or admin
- `404 Not Found`: Membership not found

**Example**:
```bash
curl -X DELETE "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/members/789e0123-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

---

### Accept Invitation

**POST** `/research-spaces/memberships/{membership_id}/accept`

Accept a pending invitation to join a research space.

**Path Parameters**:
- `membership_id`: UUID of the membership record

**Response**: `200 OK` with `MembershipResponse`

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Invitation not found or already accepted

**Example**:
```bash
curl -X POST "http://localhost:8080/research-spaces/memberships/789e0123-e89b-12d3-a456-426614174000/accept" \
  -H "Authorization: Bearer <token>"
```

---

### Get Pending Invitations

**GET** `/research-spaces/memberships/pending`

Get all pending invitations for the current user.

**Query Parameters**:
- `skip` (optional): Number of records to skip (default: 0, min: 0)
- `limit` (optional): Maximum number of records (default: 50, min: 1, max: 100)

**Response**: `200 OK` with:
```json
{
  "memberships": [MembershipResponse, ...],
  "total": 2,
  "skip": 0,
  "limit": 50
}
```

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces/memberships/pending" \
  -H "Authorization: Bearer <token>"
```

---

## Data Source Integration Endpoints

### List Data Sources in Space

**GET** `/research-spaces/{space_id}/data-sources`

Get all data sources associated with a research space. User must be a member of the space.

**Path Parameters**:
- `space_id`: UUID of the research space

**Query Parameters**:
- `skip` (optional): Number of records to skip (default: 0, min: 0)
- `limit` (optional): Maximum number of records (default: 50, min: 1, max: 100)

**Response**: `200 OK` with:
```json
{
  "data_sources": [DataSourceResponse, ...],
  "total": 5,
  "skip": 0,
  "limit": 50
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not a member of the space

**Example**:
```bash
curl -X GET "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/data-sources" \
  -H "Authorization: Bearer <token>"
```

---

### Create Data Source in Space

**POST** `/research-spaces/{space_id}/data-sources`

Create a new data source within a research space. User must be a member of the space.

**Path Parameters**:
- `space_id`: UUID of the research space

**Request Body**:
```json
{
  "name": "ClinVar API Source",
  "description": "ClinVar variant data source",
  "source_type": "api",
  "config": {
    "api_url": "https://api.clinvar.org",
    "api_key": "..."
  },
  "tags": ["clinvar", "variants"]
}
```

**Validation Rules**:
- `name`: Required, string
- `description`: Optional, string
- `source_type`: Required, must be one of: "api", "file", "database"
- `config`: Optional, JSON object with source-specific configuration
- `tags`: Optional, array of strings

**Response**: `201 Created` with `DataSourceResponse`

**Error Responses**:
- `400 Bad Request`: Invalid input data
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User is not a member of the space
- `500 Internal Server Error`: Failed to create data source

**Example**:
```bash
curl -X POST "http://localhost:8080/research-spaces/123e4567-e89b-12d3-a456-426614174000/data-sources" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ClinVar API Source",
    "description": "ClinVar variant data source",
    "source_type": "api",
    "config": {}
  }'
```

---

## Role-Based Access Control

### Membership Roles

- **owner**: Full control, can delete space, manage all members
- **admin**: Can manage members (except owner), update space settings
- **researcher**: Can create and manage data sources, view all data
- **viewer**: Read-only access to space data

### Permission Matrix

| Action | Owner | Admin | Researcher | Viewer |
|--------|-------|-------|------------|--------|
| View space | ✅ | ✅ | ✅ | ✅ |
| Update space | ✅ | ✅ | ❌ | ❌ |
| Delete space | ✅ | ❌ | ❌ | ❌ |
| Invite members | ✅ | ✅ | ❌ | ❌ |
| Update member roles | ✅ | ✅ | ❌ | ❌ |
| Remove members | ✅ | ✅ | ❌ | ❌ |
| Create data sources | ✅ | ✅ | ✅ | ❌ |
| View data sources | ✅ | ✅ | ✅ | ✅ |
| Update data sources | ✅ | ✅ | ✅ | ❌ |

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error message describing the validation issue"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "User is not a member of this research space"
}
```

### 404 Not Found
```json
{
  "detail": "Research space {space_id} not found"
}
```

### 409 Conflict
```json
{
  "detail": "Slug already exists"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "slug"],
      "msg": "string does not match regex",
      "type": "value_error.str.regex"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to process request: {error_message}"
}
```

---

## Rate Limiting

All endpoints are subject to rate limiting based on client IP address. Rate limit headers are included in responses:

- `X-RateLimit-Limit`: Maximum number of requests per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the rate limit resets

---

## OpenAPI Documentation

Interactive API documentation is available at:
- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`

The OpenAPI schema includes full request/response models, validation rules, and example requests.
