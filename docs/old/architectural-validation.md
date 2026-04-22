# Architectural Validation System

## Overview

The Artana Resource Library includes an automated architectural compliance validation system that ensures the codebase adheres to architectural standards defined in:

- `docs/EngineeringArchitecture.md` - Clean Architecture principles
- `docs/type_examples.md` - Type safety patterns
- `docs/frontend/EngenieeringArchitectureNext.md` - Frontend architecture
- `AGENTS.md` - Development guidelines

## Running Validation

### As Part of Test Suite

Architectural validation runs automatically with the test suite:

```bash
# Run all tests (includes architectural validation)
make test

# Run only architectural compliance tests
pytest tests/unit/architecture/ -v

# Run with architecture marker
pytest -m architecture -v
```

### Standalone Script

You can also run the validation script directly:

```bash
# Run validation script
python scripts/validate_architecture.py

# Or make it executable and run directly
chmod +x scripts/validate_architecture.py
./scripts/validate_architecture.py
```

## What Gets Validated

### 1. Type Safety Violations ✅

**Checks for:**
- ❌ Use of `Any` type (strictly forbidden per AGENTS.md)
- ❌ Use of `cast()` function (strictly forbidden per AGENTS.md)

**Allowed Exceptions:**
- `src/type_definitions/json_utils.py` - Explicit override in pyproject.toml
- `src/application/packaging/licenses/manager.py` - License compatibility checking
- `src/application/packaging/licenses/manifest.py` - YAML parsing

**Example Violation:**
```python
# ❌ BAD - Will fail validation
from typing import Any

def process_data(data: Any) -> Any:
    return data.get("result")

# ✅ GOOD - Passes validation
from src.type_definitions.common import JSONObject, JSONValue

def process_data(data: JSONObject) -> JSONValue:
    return data.get("result")
```

### 2. Clean Architecture Layer Violations ✅

**Checks for:**
- Domain layer importing from infrastructure
- Application layer importing from routes
- Infrastructure importing from routes

**Layer Boundaries:**
- **Domain** (`src/domain/`): Should only import from domain, type_definitions, and standard library
- **Application** (`src/application/`): Can import from domain and infrastructure repositories
- **Infrastructure** (`src/infrastructure/`): Can import from domain and application

**Example Violation:**
```python
# ❌ BAD - Domain importing from infrastructure
# In src/domain/services/gene_service.py
from src.infrastructure.repositories.gene_repository import SqlAlchemyGeneRepository

# ✅ GOOD - Domain uses interface
# In src/domain/services/gene_service.py
from src.domain.repositories.gene_repository import GeneRepository  # Interface
```

### 3. Single Responsibility Principle ✅

**Checks for:**
- Files exceeding 1200 lines (error threshold)
- Files exceeding 500 lines (warning threshold)
- Functions with cyclomatic complexity > 50
- Classes with > 30 methods

**Example Violation:**
```python
# ❌ BAD - File too large (>1200 lines)
# src/services/monolithic_service.py (1500 lines)
# Should be split into smaller, focused modules

# ✅ GOOD - Focused, single-responsibility files
# src/services/gene_service.py (200 lines)
# src/services/variant_service.py (180 lines)
```

### 4. Monolithic Code Detection ✅

**Checks for:**
- Large files that may violate SRP
- Complex functions that are hard to test
- Classes with too many responsibilities

## Validation Results

The validator produces a comprehensive report:

```
================================================================================
ARCHITECTURAL COMPLIANCE VALIDATION REPORT
================================================================================

Files checked: 330
Total lines: 61,106

Errors: 0
Warnings: 21

--------------------------------------------------------------------------------
VIOLATIONS
--------------------------------------------------------------------------------

FILE_SIZE (21 violations):
  ⚠️ src/routes/auth.py:0 - File is large (531 > 500 lines). Consider splitting into smaller modules.
  ...

================================================================================
✅ VALIDATION PASSED - No architectural errors found
================================================================================
```

## Test Coverage

The validation system includes comprehensive tests:

```bash
# Run all architectural compliance tests
pytest tests/unit/architecture/ -v

# Test coverage:
# ✅ test_no_any_types_in_codebase - Verifies no Any usage
# ✅ test_no_cast_usage_in_codebase - Verifies no cast usage
# ✅ test_clean_architecture_layer_separation - Verifies layer boundaries
# ✅ test_single_responsibility_principle - Verifies SRP compliance
# ✅ test_no_monolithic_files - Verifies file size limits
# ✅ test_architecture_validation_integration - Full integration test
```

## Integration with CI/CD

The architectural validation runs automatically in CI/CD pipelines:

1. **Pre-commit**: Can be added as a pre-commit hook
2. **Test Suite**: Runs as part of `make test`
3. **CI Pipeline**: Fails build if architectural violations detected

## Fixing Violations

### Type Safety Violations

**Replace `Any` with proper types:**
```python
# Before
from typing import Any
def process(data: Any) -> Any: ...

# After
from src.type_definitions.common import JSONObject, JSONValue
def process(data: JSONObject) -> JSONValue: ...
```

**Replace `cast` with proper type annotations:**
```python
# Before
from typing import cast
result = cast("JSONObject", data)

# After
from src.type_definitions.common import JSONObject
result: JSONObject = dict(data)
```

### Layer Violations

**Move dependencies to correct layer:**
```python
# Before: Domain importing infrastructure
# src/domain/services/gene_service.py
from src.infrastructure.repositories.gene_repository import SqlAlchemyGeneRepository

# After: Domain uses interface
# src/domain/services/gene_service.py
from src.domain.repositories.gene_repository import GeneRepository  # Interface
```

### SRP Violations

**Split large files:**
```bash
# Before: src/services/monolithic.py (1500 lines)
# After: Split into focused modules
src/services/gene_service.py (200 lines)
src/services/variant_service.py (180 lines)
src/services/phenotype_service.py (150 lines)
```

## Configuration

Validation thresholds can be adjusted in `scripts/validate_architecture.py`:

```python
# File size thresholds
MAX_FILE_SIZE = 1200  # Error threshold
WARNING_FILE_SIZE = 500  # Warning threshold

# Complexity thresholds
MAX_FUNCTION_COMPLEXITY = 50  # Cyclomatic complexity
MAX_CLASS_METHODS = 30  # Methods per class
```

## Best Practices

1. **Run validation frequently**: Run `pytest -m architecture` before committing
2. **Fix violations immediately**: Don't let architectural debt accumulate
3. **Review warnings**: Even warnings indicate potential issues
4. **Keep files focused**: Split large files proactively
5. **Use proper types**: Always use types from `src/type_definitions/`

## Troubleshooting

### Validation Script Not Found

```bash
# Ensure script is executable
chmod +x scripts/validate_architecture.py

# Run from project root
cd /path/to/resource_library
python scripts/validate_architecture.py
```

### False Positives

If you encounter a false positive:

1. **Check if it's a legitimate exception**: Some files may be allowed exceptions
2. **Review the violation**: Understand why it's flagged
3. **Fix the underlying issue**: Often the violation indicates a real problem
4. **Update allowed exceptions**: Only if absolutely necessary

## Summary

The architectural validation system ensures:

✅ **Type Safety**: No `Any` or `cast` usage
✅ **Clean Architecture**: Proper layer separation
✅ **Single Responsibility**: Focused, maintainable code
✅ **Quality Standards**: Consistent architectural patterns

**Run validation regularly to maintain architectural integrity!**
