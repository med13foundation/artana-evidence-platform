# Type Examples Pattern Validation

This document describes the automated validation system that ensures code follows the patterns documented in `docs/type_examples.md`.

## Overview

The Artana Resource Library now includes comprehensive automated validation to ensure adherence to type safety patterns. These validations run as part of the architectural compliance checks and are integrated into the CI/CD pipeline.

## Validation Checks

### 1. JSON Type Usage Validator ✅

**What it checks:**
- Detects usage of `dict[str, Any]` or `Dict[str, Any]` in type annotations
- Suggests using `JSONObject` or `JSONValue` from `src.type_definitions.common`

**Severity:** Error

**Example violation:**
```python
# ❌ BAD - Will fail validation
def process_data(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("result")

# ✅ GOOD - Passes validation
from src.type_definitions.common import JSONObject, JSONValue

def process_data(data: JSONObject) -> JSONValue:
    return data.get("result")
```

**Location:** `scripts/validate_architecture.py::_check_json_type_usage()`

### 2. Update Type Usage Validator ✅

**What it checks:**
- Detects update operations that use plain `dict` instead of TypedDict classes
- Suggests using `GeneUpdate`, `VariantUpdate`, `PhenotypeUpdate`, etc.

**Severity:** Warning

**Example violation:**
```python
# ❌ BAD - Will generate warning
def update_gene(gene_id: str, updates: dict[str, Any]) -> Gene:
    ...

# ✅ GOOD - Passes validation
from src.type_definitions.common import GeneUpdate

def update_gene(gene_id: str, updates: GeneUpdate) -> Gene:
    ...
```

**Location:** `scripts/validate_architecture.py::_check_update_type_usage()`

### 3. Test Fixture Usage Validator ✅

**What it checks:**
- Validates that test files use typed fixtures from `tests.test_types.fixtures` and `tests.test_types.mocks`
- Detects plain dictionary usage in test data creation

**Severity:** Warning

**Example violation:**
```python
# ❌ BAD - Will generate warning
def test_gene_operations():
    gene = {"gene_id": "TEST", "symbol": "TEST"}
    ...

# ✅ GOOD - Passes validation
from tests.test_types.fixtures import create_test_gene

def test_gene_operations():
    gene = create_test_gene(gene_id="TEST", symbol="TEST")
    ...
```

**Location:** `scripts/validate_architecture.py::_check_test_fixture_usage()`

### 4. API Response Type Validator ✅

**What it checks:**
- Validates that route endpoints return `ApiResponse` or `PaginatedResponse` types
- Checks route files in `src/routes/` directory

**Severity:** Warning

**Example violation:**
```python
# ❌ BAD - Will generate warning
@router.get("/genes")
def get_genes() -> list[Gene]:
    ...

# ✅ GOOD - Passes validation
from src.type_definitions.common import PaginatedResponse

@router.get("/genes")
def get_genes() -> PaginatedResponse[GeneResponse]:
    ...
```

**Location:** `scripts/validate_architecture.py::_check_api_response_types()`

## Running Validations

### Standalone Script

```bash
# Run architectural validation (includes type_examples.md pattern checks)
python scripts/validate_architecture.py

# Or via Makefile
make validate-architecture
```

### As Part of Test Suite

```bash
# Run architectural compliance tests via Makefile
make test-architecture

# Or run directly with pytest
pytest tests/unit/architecture/test_architectural_compliance.py -v -m architecture

# Run specific validation test
pytest tests/unit/architecture/test_architectural_compliance.py::TestArchitecturalCompliance::test_json_type_usage_compliance -v
```

### Pre-commit Hook

The validations run automatically via pre-commit hooks configured in `.pre-commit-config.yaml`:

```yaml
- id: validate-architecture
  name: Validate Architecture
  entry: python scripts/validate_architecture.py
  language: system
  pass_filenames: false
  always_run: true
  stages: [pre-commit]
```

### CI/CD Pipeline

The validations are part of the full quality gate:

```bash
make all  # Includes validate-architecture and test-architecture
```

The `make all` command explicitly runs:
- `validate-architecture` - Runs the validation script
- `test-architecture` - Runs the architectural compliance tests

This ensures both the validation script and the test suite verify type_examples.md pattern compliance.

## Test Coverage

All new validators have corresponding tests in `tests/unit/architecture/test_architectural_compliance.py`:

- `test_json_type_usage_compliance()` - Tests JSON type usage validation
- `test_update_type_usage_compliance()` - Tests update type usage validation
- `test_test_fixture_usage_compliance()` - Tests test fixture usage validation
- `test_api_response_type_compliance()` - Tests API response type validation

## Integration with Existing Validations

The new validators are integrated into the existing architectural validation system:

1. **Type Safety Violations** (existing): Checks for `Any` and `cast()` usage
2. **JSON Type Usage** (new): Checks for `dict[str, Any]` patterns
3. **Update Type Usage** (new): Checks for TypedDict usage in updates
4. **Test Fixture Usage** (new): Checks for typed fixture usage in tests
5. **API Response Types** (new): Checks for proper API response types
6. **Layer Violations** (existing): Checks Clean Architecture boundaries
7. **SRP Violations** (existing): Checks Single Responsibility Principle

## Exceptions

Some files are explicitly allowed to use `Any` types (documented in `ALLOWED_ANY_USAGE`):

- `src/type_definitions/json_utils.py` - Explicit override in pyproject.toml
- `src/application/packaging/licenses/manager.py` - License compatibility checking
- `src/application/packaging/licenses/manifest.py` - YAML parsing

These exceptions are also respected by the new JSON type usage validator.

## Best Practices

1. **Always use typed fixtures in tests**: Import from `tests.test_types.fixtures` and `tests.test_types.mocks`
2. **Use JSON types for JSON data**: Use `JSONObject`, `JSONValue`, `JSONArray` instead of `dict[str, Any]`
3. **Use TypedDict for updates**: Use `GeneUpdate`, `VariantUpdate`, etc. for update operations
4. **Use ApiResponse for routes**: Return `ApiResponse<T>` or `PaginatedResponse<T>` from route endpoints

## References

- **Pattern Examples**: `docs/type_examples.md` - Complete type safety patterns and examples
- **Type Definitions**: `src/type_definitions/` - All existing TypedDict, Protocol, and union types
- **Test Types**: `tests/test_types/` - Typed test fixtures, mocks, and test data patterns
- **Validation Script**: `scripts/validate_architecture.py` - Implementation of all validators

## Future Enhancements

Potential future improvements to the validation system:

1. **External API Validation**: Check that external API responses are validated using `APIResponseValidator`
2. **Property-Based Testing**: Validate that property-based tests use Hypothesis generators
3. **Type Guard Usage**: Check that type guards are used instead of `cast()`
4. **Protocol Compliance**: Validate that interfaces use Protocol classes

---

**This validation system ensures that the patterns documented in `docs/type_examples.md` are consistently followed throughout the codebase, maintaining type safety and code quality.** 🛡️✨
