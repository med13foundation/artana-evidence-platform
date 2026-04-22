# ADR-0002: Strict Type Safety - No Any Policy

**Status**: Accepted
**Date**: 2025-01-09
**Deciders**: MED13 Development Team

## Context

Healthcare software requires the highest level of type safety to prevent data corruption and runtime errors. The use of `Any` types undermines type safety and can lead to subtle bugs that are difficult to catch.

## Decision

We will enforce a strict "no Any" policy across the codebase:
- No `Any` types allowed (except in explicitly documented exceptions)
- No `cast()` usage allowed
- All types must be properly defined using `src/type_definitions/`
- MyPy strict mode must pass for all code

## Consequences

### Positive
- Prevents type-related bugs
- Improves IDE autocomplete and refactoring
- Makes code self-documenting
- Enables confident refactoring
- Critical for healthcare data integrity

### Negative
- Requires more upfront type definition work
- May slow initial development slightly
- Requires discipline to maintain

## Implementation

- Automated validation via `scripts/validate_architecture.py`
- Pre-commit hooks enforce the policy
- CI/CD pipeline blocks violations
- Exceptions documented in `ALLOWED_ANY_USAGE` constant

## References

- `AGENTS.md` - Type Safety Excellence section
- `docs/type_examples.md` - Type safety patterns
- `scripts/validate_architecture.py` - Validation implementation
