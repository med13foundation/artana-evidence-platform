# Frontend-Backend Integration Tests

This directory contains integration tests that validate the connection between the Next.js frontend and the FastAPI backend.

## Test Files

### `backend-endpoints.test.ts`
Validates that frontend Server Actions correctly call backend endpoints:
- ✅ Correct endpoint URLs are used
- ✅ Request payloads match backend schemas
- ✅ Response handling is correct
- ✅ Error handling is consistent with backend responses
- ✅ Authentication headers are properly included

### `type-synchronization.test.ts`
Validates type synchronization between frontend and backend:
- ✅ TypeScript types match Pydantic models
- ✅ `OrchestratedSessionState` structure is correct
- ✅ Request/response types are synchronized
- ✅ Optional fields are properly typed

## Running the Tests

```bash
# Run all integration tests
npm test -- __tests__/integration

# Run specific test file
npm test -- backend-endpoints.test.ts
npm test -- type-synchronization.test.ts

# Run with coverage
npm test -- --coverage __tests__/integration
```

## Test Coverage

### Backend Endpoints Tested
- `GET /data-discovery/sessions/{session_id}/state` - Fetch orchestrated state
- `POST /data-discovery/sessions/{session_id}/selection` - Update source selection

### Type Validation
- `OrchestratedSessionState` - Complete session state DTO
- `UpdateSelectionRequest` - Source selection request
- `DataDiscoverySessionResponse` - Session response
- `SourceCapabilitiesDTO` - Capabilities response
- `ValidationResultDTO` - Validation response
- `ViewContextDTO` - View context response

## Integration with Architecture Tests

These tests work together with the architectural validation tests in `../architecture/`:
- Architecture tests validate the **pattern** (how components should work)
- Integration tests validate the **implementation** (that it actually works)

## Adding New Tests

When adding new backend endpoints:
1. Add endpoint test in `backend-endpoints.test.ts`
2. Add type validation in `type-synchronization.test.ts`
3. Ensure Server Actions are tested in `../architecture/server-side-orchestration.test.tsx`
