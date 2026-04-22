# ADR-0003: Clean Architecture Layer Separation

**Status**: Accepted
**Date**: 2025-01-09
**Deciders**: MED13 Development Team

## Context

We need to maintain clear separation between architectural layers to ensure:
- Testability
- Maintainability
- Flexibility to change implementations
- Independence of business logic from technical concerns

## Decision

We will strictly enforce Clean Architecture layer separation:
- **Domain Layer** (`src/domain/`): Pure business logic, no infrastructure dependencies
- **Application Layer** (`src/application/`): Use cases, orchestrates domain and infrastructure
- **Infrastructure Layer** (`src/infrastructure/`): External concerns, implements domain interfaces
- **Presentation Layer** (`src/routes/`, `src/web/`): API endpoints and UI

Dependency direction: Domain ← Application ← Infrastructure ← Presentation

## Consequences

### Positive
- Business logic independent of technical details
- Easy to test in isolation
- Can swap implementations (database, UI framework)
- Maintainable and evolvable

### Negative
- Requires more upfront design
- May seem like over-engineering for simple features
- Requires discipline to maintain boundaries

## Implementation

- Automated validation via `scripts/validate_architecture.py` and `scripts/validate_dependencies.py`
- Pre-commit hooks enforce layer boundaries
- CI/CD pipeline blocks violations
- Repository pattern ensures dependency inversion

## References

- `docs/EngineeringArchitecture.md` - Architecture foundation
- `AGENTS.md` - Clean Architecture principles
- `scripts/validate_dependencies.py` - Dependency validation
