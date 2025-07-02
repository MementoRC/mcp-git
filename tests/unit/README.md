# Unit Tests

Tests for individual components in isolation.

## Coverage Target: 95%+

Unit tests should cover:
- Individual functions and methods
- Edge cases and error conditions
- Type validation and constraints
- Business logic in isolation

## Structure

- `primitives/` - Atomic Git/GitHub operations
- `operations/` - Composed operations built on primitives
- `types/` - Type system validation and contracts
- `constants/` - Constants validation and organization
- `protocols/` - Protocol definitions and interfaces

## Guidelines

- Mock all external dependencies
- Test one thing at a time
- Fast execution (< 100ms per test)
- No I/O operations (file system, network)