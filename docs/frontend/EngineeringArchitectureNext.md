# Artana Next.js Admin - Frontend Architecture Foundation & Growth Strategy

## Current Architectural State (Successfully Implemented)

### ✅ **Next.js 14 App Router Foundation - COMPLETE**
The Artana Next.js admin interface implements a modern, scalable frontend architecture with a **Server-Side Orchestration** pattern optimized for admin applications:

```
┌─────────────────────────────────────────────────────────────┐
│              Server-Side Orchestration                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Server Components (Orchestrator) → Client Components   │ │
│  │  • Fetch "View-Ready" DTOs from Backend                 │ │
│  │  • Pass derived state & validation to Client            │ │
│  │  • "Dumb" Client Components for rendering only          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│              Server Component Layer                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  • Page components act as Presentation Orchestrators    │ │
│  │  • Fetch `OrchestratedSessionState` from Python         │ │
│  │  • Handle authentication & initial data loading         │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│              Client Component Layer                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  • Receive immutable state props (No complex logic)     │ │
│  │  • Trigger Server Actions for user interactions         │ │
│  │  • Display standardized ValidationFeedback              │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                 Component Architecture                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         UI Components • Theme System • Server Actions   │ │
│  │         • shadcn/ui • Tailwind CSS • Sonner Toasts      │ │
│  │         • "Dumb" components strictly typed via DTOs     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Server-Side Orchestration Strategy:**
- **Backend as Source of Truth**: All business rules, validation, and state derivation happen in Python Domain Services.
- **Next.js as Presentation Layer**: Server Components fetch "View-Ready" DTOs (`OrchestratedSessionState`). Client Components are "Dumb Renderers".
- **Hypermedia-style State**: Interactions (clicks) trigger **Server Actions** that update state on the backend and refresh the view via `revalidatePath`.

### ✅ **Data Discovery Module - RESTRUCTURED**
**Server-Side Orchestration Implementation:**
- **Backend**: `SessionOrchestrationService` centralizes logic for capabilities, validation, and view context.
- **Frontend**: `DataDiscoveryContent` and `SourceCatalog` refactored to be "dumb" components receiving `OrchestratedSessionState`.
- **Actions**: `updateSourceSelection` Server Action handles updates and UI refreshes without client-side logic.
- **Type Safety**: Full Pydantic <-> TypeScript synchronization for Orchestration DTOs.

### ✅ **Design System Implementation - ACHIEVED**
- **MED13 Foundation Colors**: Warm Science + Family Hope palette (Soft Teal, Coral-Peach, Sunlight Yellow)
- **Typography System**: Nunito Sans (headings), Inter (body), Playfair Display (quotes)
- **Component Library**: shadcn/ui with full variant system and accessibility
- **Theme System**: Class-based dark mode with next-themes integration
- **Responsive Design**: Mobile-first approach with Tailwind CSS

### ✅ **Quality Assurance Pipeline - OPERATIONAL**
```bash
# Next.js quality gate suite
npm run build              # Production build verification
npm run lint              # ESLint with Next.js rules
npm run type-check        # TypeScript strict checking
npm test                  # Jest with React Testing Library
npm run visual-test       # Percy-powered visual regression suite
```

## Evolutionary Growth Strategy

Our solid Next.js foundation enables **organic, sustainable growth** across multiple frontend dimensions. Rather than rigid phases, we focus on **architectural leverage points** that enable natural expansion.

### 🚀 **Architecture Leverage Points**

#### **Server Actions for Mutations**
```typescript
// src/web/app/actions/data-discovery.ts
// Centralized mutation logic that calls Backend API
// Handles error mapping and UI revalidation
export async function updateSourceSelection(...) {
  // ... API call ...
  revalidatePath(path)
}
```

#### **Orchestration DTOs**
```python
# src/routes/data_discovery/schemas.py
class OrchestratedSessionState(BaseModel):
    """ViewModel for the frontend."""
    session: DataDiscoverySessionResponse
    capabilities: SourceCapabilitiesDTO
    validation: ValidationResultDTO
    view_context: ViewContextDTO
```

### 📈 **Growth Principles**

**Sustainable Frontend Expansion Guidelines:**

1.  **🚫 No Business Logic on Client**: If it involves a rule (e.g., "can I search?"), calculate it on the Backend.
2.  **🔌 Server Actions First**: Use Server Actions for mutations instead of `useEffect`/`fetch` in components.
3.  **📦 Dumb Components**: Components should take data as props and emit events (or call actions). They should not calculate state.
4.  **🛡️ Strict Types**: Always regenerate types after Backend changes. Never use `any`.

### 🤖 **AI Agent Integration Pattern**

The frontend interacts with AI agents through the same Server-Side Orchestration pattern:

```
┌─────────────────────────────────────────────────────────────┐
│              Frontend (Next.js)                             │
│  • Server Action triggers AI query generation               │
│  • Receives QueryGenerationContract from backend            │
│  • Displays confidence scores and evidence                  │
└─────────────────────────────────────────────────────────────┘
                                 │
                         Server Action
                                 │
┌─────────────────────────────────────────────────────────────┐
│              Backend (FastAPI)                              │
│  • QueryAgentService orchestrates agent                     │
│  • ArtanaQueryAgentAdapter executes pipeline                 │
│  • Returns typed QueryGenerationContract                    │
└─────────────────────────────────────────────────────────────┘
```

**Frontend Responsibilities:**
- Display AI-generated queries with confidence indicators
- Show evidence and rationale for transparency
- Handle escalation states (when agent routes for human review)
- Never duplicate AI logic - backend is source of truth

**Contract Response Handling:**
```typescript
// Example: Displaying AI query results
interface QueryGenerationContract {
  decision: "generated" | "fallback" | "escalate";
  confidence_score: number;  // 0.0-1.0
  rationale: string;
  evidence: EvidenceItem[];
  query: string;
  source_type: string;
}

// Display based on decision
if (contract.decision === "escalate") {
  showReviewRequired(contract.rationale);
} else if (contract.confidence_score < 0.5) {
  showLowConfidenceWarning(contract.confidence_score);
}
```

## Conclusion

The Artana Next.js admin interface stands on a **solid, modern frontend foundation** that enables **confident, sustainable growth**. Our **Server-Side Orchestration architecture** combines the best of backend domain logic and modern frontend rendering:

- **Server Components** act as the "BFF" (Backend for Frontend) layer.
- **Python Domain Services** remain the single source of truth for business rules.
- **AI Agents** are accessed through the same pattern - backend handles all AI logic.
- **Zero Logic Duplication** ensures robustness and maintainability.

The foundation is built. The growth strategy is clear. The admin interface is architecturally sound with a production-ready Server-Side Orchestration implementation. 🚀

---

*This architecture document serves as the foundation for all Next.js frontend development in the Artana Resource Library. Regular updates and expansions should maintain the principles outlined above.*
