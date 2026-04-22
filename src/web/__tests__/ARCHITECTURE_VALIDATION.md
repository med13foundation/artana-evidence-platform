# Architecture Validation Test Suite

This document describes the comprehensive test suite that validates Server-Side Orchestration patterns and frontend-backend integration.

## Overview

The MED13 Next.js admin interface follows a **Server-Side Orchestration** pattern where:
- **Backend** (Python) is the source of truth for all business logic
- **Server Components** fetch "View-Ready" DTOs from the backend
- **Client Components** are "dumb renderers" that receive props
- **Server Actions** handle all mutations and trigger UI refreshes via `revalidatePath`

## Test Structure

```
__tests__/
├── architecture/
│   ├── server-side-orchestration.test.tsx  # Pattern validation
│   ├── helpers.ts                          # Test utilities
│   └── README.md                           # Architecture test docs
└── integration/
    ├── backend-endpoints.test.ts           # Endpoint integration
    ├── type-synchronization.test.ts        # Type sync validation
    └── README.md                           # Integration test docs
```

## Test Coverage

### 1. Server-Side Orchestration Pattern Tests
**File**: `architecture/server-side-orchestration.test.tsx`

**Validates**:
- ✅ Server Actions are used for mutations (not client-side `fetch`)
- ✅ `revalidatePath` is called after successful mutations
- ✅ Components receive `OrchestratedSessionState` as props
- ✅ No client-side data fetching in components
- ✅ Business logic stays in Python Domain Services

**Key Tests**:
- Server Action functions are exported
- `fetchSessionState` calls correct backend endpoint
- `updateSourceSelection` calls backend and calls `revalidatePath`
- Error handling doesn't call `revalidatePath`
- Component pattern validation

### 2. Frontend-Backend Endpoint Integration Tests
**File**: `integration/backend-endpoints.test.ts`

**Validates**:
- ✅ Frontend calls correct backend endpoints
- ✅ Request payloads match backend schemas
- ✅ Response handling is correct
- ✅ Error handling is consistent
- ✅ Authentication headers are included

**Endpoints Tested**:
- `GET /data-discovery/sessions/{session_id}/state`
- `POST /data-discovery/sessions/{session_id}/selection`

**Error Scenarios**:
- 404 (Not Found)
- 422 (Validation Errors)
- 500 (Server Errors)
- Network Errors

### 3. Type Synchronization Tests
**File**: `integration/type-synchronization.test.ts`

**Validates**:
- ✅ TypeScript types match Pydantic models
- ✅ `OrchestratedSessionState` structure is correct
- ✅ Request/response types are synchronized
- ✅ Optional fields are properly typed

**Types Validated**:
- `OrchestratedSessionState`
- `UpdateSelectionRequest`
- `DataDiscoverySessionResponse`
- `SourceCapabilitiesDTO`
- `ValidationResultDTO`
- `ViewContextDTO`

## Running the Tests

```bash
# Run all architecture validation tests
npm test -- __tests__/architecture

# Run all integration tests
npm test -- __tests__/integration

# Run specific test file
npm test -- server-side-orchestration.test.tsx
npm test -- backend-endpoints.test.ts
npm test -- type-synchronization.test.ts

# Run with coverage
npm test -- --coverage __tests__/architecture
```

## Test Results

All tests are currently **passing**:
- ✅ 11 tests in `server-side-orchestration.test.tsx`
- ✅ 11 tests in `backend-endpoints.test.ts`
- ✅ 11 tests in `type-synchronization.test.ts`

**Total**: 33 tests validating architectural patterns and integration

## Architectural Rules Enforced

### 1. Server Actions First
All mutations must use Server Actions, not client-side `fetch`:
```typescript
// ✅ Correct
export async function updateSourceSelection(...) {
  await apiClient.post(...)
  revalidatePath(path)
}

// ❌ Wrong
useEffect(() => {
  fetch('/api/endpoint').then(...)
}, [])
```

### 2. Dumb Components
Components receive data as props, don't fetch data:
```typescript
// ✅ Correct
function Component({ orchestratedState }: { orchestratedState: OrchestratedSessionState }) {
  return <div>{orchestratedState.view_context.selected_count}</div>
}

// ❌ Wrong
function Component() {
  const [data, setData] = useState()
  useEffect(() => { fetch(...) }, [])
}
```

### 3. Backend as Source of Truth
All business logic in Python Domain Services:
```python
# ✅ Correct - Backend calculates everything
class SessionOrchestrationService:
    def get_orchestrated_state(self, session_id: UUID) -> OrchestratedSessionState:
        # Calculate capabilities, validation, view context
        return OrchestratedSessionState(...)
```

### 4. Type Safety
Full type synchronization between frontend and backend:
```typescript
// ✅ Types generated from Pydantic models
import { OrchestratedSessionState } from '@/types/generated'
```

## Adding New Tests

When adding new features:

1. **Server Actions**: Add tests in `server-side-orchestration.test.tsx`
   - Verify Server Action calls backend
   - Verify `revalidatePath` is called
   - Verify error handling

2. **Endpoints**: Add tests in `backend-endpoints.test.ts`
   - Test endpoint URL
   - Test request payload
   - Test response handling
   - Test error scenarios

3. **Types**: Add tests in `type-synchronization.test.ts`
   - Validate type structure
   - Validate optional fields
   - Validate nested types

## Continuous Validation

These tests should be run:
- ✅ Before every commit (pre-commit hook)
- ✅ In CI/CD pipeline
- ✅ When adding new Server Actions
- ✅ When adding new backend endpoints
- ✅ When updating Pydantic models (regenerate types first)

## Future Enhancements

Potential additions to the test suite:
- AST-based analysis to detect business logic in components
- Automated detection of client-side data fetching
- Visual regression tests for Server-Side Orchestration compliance
- Performance tests for Server Actions
- End-to-end tests validating complete workflows

---

**These tests ensure the MED13 Next.js admin interface maintains architectural integrity and follows Server-Side Orchestration patterns consistently.**
