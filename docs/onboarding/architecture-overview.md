# Architecture Overview for New Developers

## Quick Start

Welcome to the Artana Resource Library! This guide will help you understand the architecture and start contributing effectively.

## Core Principles

### 1. Clean Architecture
- **Domain Layer**: Pure business logic, no external dependencies
- **Application Layer**: Use cases and orchestration
- **Infrastructure Layer**: External adapters (database, APIs, file system)
- **Presentation Layer**: API endpoints and UI

**Rule**: Dependencies flow inward (Domain ← Application ← Infrastructure ← Presentation)

### 2. Type Safety First
- **Never use `Any`**: Use proper types from `src/type_definitions/`
- **Never use `cast`**: Fix the underlying type issue instead
- **100% MyPy compliance**: All code must pass strict type checking

### 3. Single Responsibility Principle
- Files should be focused (<1200 lines)
- Functions should have low complexity (<50)
- Classes should have reasonable method count (<30)

### 4. FastAPI Concurrency Rule
- **Sync SQLAlchemy path uses `def`**: If a route or dependency uses the synchronous SQLAlchemy `Session` or sync application services, declare it with normal `def`.
- **`async def` means real awaited work**: Reserve `async def` for handlers that actually `await`, return streaming/SSE responses, or wrap sync work in a dedicated offload boundary.
- **Do not do sync DB work in async hot paths**: Async middleware and SSE generators must not call sync DB/service methods directly on the event loop.
- **Preserve boundaries**: Fix fake-async handlers by changing their signature to `def`, not by sprinkling threadpool helpers inside ordinary CRUD routes.

## Development Workflow

### Before You Start Coding

1. **Read the Architecture Docs**:
   - `docs/EngineeringArchitecture.md` - Overall architecture
   - `docs/type_examples.md` - Type safety patterns
   - `AGENTS.md` - Development guidelines

2. **Understand the Layer Structure**:
   ```
   src/
   ├── domain/          # Business logic (no infrastructure deps)
   ├── application/     # Use cases
   ├── infrastructure/  # External adapters
   └── routes/          # API endpoints
   ```

### When Adding New Features

1. **Choose the Right Layer**:
   - Business rules → `src/domain/`
   - Use cases → `src/application/`
   - Database/API access → `src/infrastructure/`
   - API endpoints → `src/routes/`

2. **Follow Existing Patterns**:
   - Use repository interfaces (not implementations)
   - Use existing type definitions
   - Follow naming conventions

3. **Write Tests**:
   - Unit tests for domain logic
   - Integration tests for services
   - Architectural tests run automatically

### Before Committing

1. **Run Quality Checks**:
   ```bash
   make all  # Runs all checks including architectural validation
   ```

2. **Verify Architectural Compliance**:
   ```bash
   pytest -m architecture  # Run architectural tests
   python scripts/validate_architecture.py  # Full validation
   python scripts/validate_dependencies.py  # Dependency check
   ```

3. **Check Pre-commit Hooks**:
   - Pre-commit hooks run automatically
   - Fix any issues before committing

## Common Patterns

### Adding a New Domain Entity

```python
# src/domain/entities/my_entity.py
from pydantic import BaseModel, Field
from uuid import UUID

class MyEntity(BaseModel):
    """Domain entity with business logic."""
    id: UUID
    name: str = Field(..., min_length=1)

    def business_method(self) -> str:
        """Business logic here."""
        return f"Processed: {self.name}"
```

### Adding a Repository Interface

```python
# src/domain/repositories/my_repository.py
from abc import ABC, abstractmethod
from src.domain.entities.my_entity import MyEntity

class MyRepository(ABC):
    """Repository interface - domain layer."""

    @abstractmethod
    def find_by_id(self, id: UUID) -> MyEntity | None:
        """Find entity by ID."""
        ...
```

### Adding a Repository Implementation

```python
# src/infrastructure/repositories/my_repository.py
from src.domain.repositories.my_repository import MyRepository
from src.domain.entities.my_entity import MyEntity

class SqlAlchemyMyRepository(MyRepository):
    """Repository implementation - infrastructure layer."""

    def find_by_id(self, id: UUID) -> MyEntity | None:
        # Implementation using SQLAlchemy
        ...
```

### Adding an Application Service

```python
# src/application/services/my_service.py
from src.domain.repositories.my_repository import MyRepository
from src.domain.entities.my_entity import MyEntity

class MyApplicationService:
    """Application service - orchestrates use cases."""

    def __init__(self, repository: MyRepository):
        self._repository = repository

    def get_entity(self, id: UUID) -> MyEntity | None:
        """Use case: Get entity by ID."""
        return self._repository.find_by_id(id)
```

## Type Safety Patterns

### Using JSON Types

```python
from src.type_definitions.common import JSONObject, JSONValue

def process_data(data: JSONObject) -> JSONValue:
    return data.get("result")
```

### Using API Response Types

```python
from src.type_definitions.common import ApiResponse

def get_users() -> ApiResponse[list[User]]:
    return {
        "success": True,
        "data": users,
        "meta": {"timestamp": "...", "requestId": "..."}
    }
```

### Using Update Types

```python
from src.type_definitions.common import GeneUpdate

updates: GeneUpdate = {
    "name": "Updated name",
    "description": "New description"
}
```

## Testing Patterns

### Using Typed Fixtures

```python
from tests.test_types.fixtures import create_test_gene
from tests.test_types.mocks import create_mock_gene_service

def test_my_feature():
    test_gene = create_test_gene(symbol="TEST")
    service = create_mock_gene_service([test_gene])
    # Test logic here
```

## Common Mistakes to Avoid

### ❌ Don't Do This

```python
# Wrong: Using Any
from typing import Any
def process(data: Any) -> Any: ...

# Wrong: Using cast
from typing import cast
result = cast("MyType", data)

# Wrong: Domain importing infrastructure
# In src/domain/services/my_service.py
from src.infrastructure.repositories.my_repo import SqlAlchemyMyRepo  # ❌

# Wrong: Large monolithic files
# 2000+ line files violate SRP
```

### ✅ Do This Instead

```python
# Correct: Use proper types
from src.type_definitions.common import JSONObject
def process(data: JSONObject) -> JSONValue: ...

# Correct: Fix the type issue
result: MyType = dict(data)  # Proper type annotation

# Correct: Domain uses interface
# In src/domain/services/my_service.py
from src.domain.repositories.my_repo import MyRepo  # ✅ Interface

# Correct: Focused, single-responsibility files
# Keep files <1200 lines, split if needed
```

## Resources

- **Architecture Docs**: `docs/EngineeringArchitecture.md`
- **Type Examples**: `docs/type_examples.md`
- **Development Guide**: `AGENTS.md`
- **Architectural Validation**: `docs/architectural-validation.md`
- **Growth Safeguards**: `docs/architectural-growth-safeguards.md`

## Getting Help

- Check existing code for patterns
- Review ADRs in `docs/adr/`
- Run `make all` to see validation errors
- Ask team members for guidance

## Next Steps

1. Set up your development environment (`make setup-dev`)
2. Run the test suite (`make test`)
3. Read the architecture documentation
4. Start with a small feature to learn the patterns
5. Run `make all` before every commit

Welcome to the team! 🚀
