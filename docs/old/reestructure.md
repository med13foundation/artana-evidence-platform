# Robust Architecture Restructuring Plan: Server-Side Orchestration

## Problem Diagnosis

The current system suffers from **Architectural Disconnect**:
1.  **Logic Duplication**: Business rules (validation, filtering) exist in both Python (Backend) and TypeScript (Frontend).
2.  **Frontend Bloat**: The frontend manages complex state derivation and orchestration, leading to massive hooks (e.g., `use-data-discovery.ts` > 400 lines).
3.  **Type Anemia**: The frontend uses generated types but lacks the rich behavioral model of the backend, leading to manual re-implementation of domain logic.
4.  **Architecture Violation**: This violates the "Clean Architecture" and "Separation of Concerns" principles outlined in `EngineeringArchitecture.md` and `AGENTS.md`.

## Architectural Strategy: Server-Side Orchestration

We will migrate from a "Smart Client" model to a **Server-Side Orchestration** model.

### Core Principles
1.  **Backend as Source of Truth**: All business rules, state derivation, and validation happen in Python Domain Services.
2.  **Next.js as Presentation Layer**: Server Components fetch "View-Ready" DTOs. Client Components are "Dumb Renderers".
3.  **Hypermedia-style State**: Interactions (clicks) trigger Server Actions that update state on the backend and refresh the view.

---

## Implementation Plan

### Phase 1: Backend Domain Enrichment (The Brain)

**Goal**: Centralize all orchestration logic in the Python Application Layer.

#### 1.1 Define Orchestration DTOs
Create rich Pydantic models in `src/routes/data_discovery/schemas.py` that represent the *complete* state needed by the UI.

*   `SourceCapabilitiesDTO`: What the current selection *can* do (supports_gene_search, etc.).
*   `ValidationIssueDTO`: Structured error (code, message, field).
*   `OrchestratedSessionState`: A unified response object containing:
    *   `session`: The raw session data.
    *   `capabilities`: Derived `SourceCapabilitiesDTO`.
    *   `validation`: `is_valid` boolean and list of `ValidationIssueDTO`.
    *   `view_context`: Pre-calculated UI hints (e.g., "3 sources selected").

#### 1.2 Implement Session Orchestration Service
Create `src/application/services/data_discovery_service/session_orchestration.py`.

*   **Class**: `SessionOrchestrationService`
*   **Methods**:
    *   `get_session_state(session_id) -> OrchestratedSessionState`:
        *   Loads session.
        *   Calculates capabilities (aggregating selected source capabilities).
        *   Runs validation rules.
    *   `update_selection(session_id, source_ids) -> OrchestratedSessionState`:
        *   Updates session repository.
        *   Triggers re-calculation of state.
        *   Returns the new state immediately.

#### 1.3 Expose Orchestration Endpoints
Update `src/routes/data_discovery/sessions.py`.

*   `GET /sessions/{id}/state`: Calls `get_session_state`.
*   `POST /sessions/{id}/selection`: Calls `update_selection`.

---

### Phase 2: Frontend Simplification (The Presenter)

**Goal**: Remove business logic from the frontend and rely on the new Backend DTOs.

#### 2.1 Generate Types
*   Run `make generate-ts-types` to get `OrchestratedSessionState` and `ValidationIssueDTO` in TypeScript.

#### 2.2 Create Server Actions
Create `src/web/app/actions/data-discovery.ts`.

*   `fetchSessionState(id)`: Server-side fetch of the new state endpoint.
*   `updateSourceSelection(id, sourceIds)`: Calls the API, checks for errors, and calls `revalidatePath` to refresh the UI.

#### 2.3 Refactor Components to "Dumb" Mode

*   **Refactor `DataDiscoveryContent.tsx`**:
    *   Convert to a Server Component (or hybrid with initial server fetch).
    *   Pass `OrchestratedSessionState` down as a prop.
*   **Refactor `SourceCatalog.tsx`**:
    *   Remove all `useState` for filtering/validation.
    *   Accept `isValid` and `validationIssues` as props.
    *   Clicking a source calls `updateSourceSelection` (Server Action) instead of local state update.
*   **Delete `use-data-discovery.ts`**:
    *   Remove the 400+ lines of client-side logic.

---

### Phase 3: Error Handling & Robustness (The Safety Net)

**Goal**: Standardize how backend validation issues are displayed.

#### 3.1 Standardize Backend Errors
*   Ensure `SessionOrchestrationService` catches domain exceptions and converts them into the `validation_issues` list in the DTO, rather than throwing HTTP 500s.

#### 3.2 Frontend Error Component
*   Create `ValidationFeedback.tsx` component.
    *   Props: `issues: ValidationIssueDTO[]`.
    *   Renders standard error alerts/toasts based on the backend response.

---

## Success Criteria

| Metric | Current State | Target State |
| :--- | :--- | :--- |
| **Frontend Logic** | > 400 lines (Hooks) | < 50 lines (Event Handlers) |
| **Validation Location** | Mixed (TS + Python) | Python Only |
| **Type Safety** | Loose (Generated) | Strict (Generated + DTOs) |
| **State Sync** | Manual (Client Calculation) | Automatic (Server Derived) |

## Execution Order

1.  **Backend**: Define DTOs (`schemas.py`).
2.  **Backend**: Implement Service (`session_orchestration.py`).
3.  **Backend**: Add Endpoints (`sessions.py`).
4.  **Tooling**: Regenerate TypeScript types.
5.  **Frontend**: Create Server Actions.
6.  **Frontend**: Refactor Components & Delete Hooks.
