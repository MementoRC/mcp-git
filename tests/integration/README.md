# Integration Tests

Tests for component interaction and service layer functionality.

## Coverage Target: 85%+

Integration tests should cover:
- Service layer interactions
- Component communication
- Data flow between layers
- Configuration and dependency injection

## Structure

- `services/` - Service layer integration tests
- `applications/` - Application layer integration tests

## Guidelines

- Test component boundaries
- Use real implementations where possible
- Mock only external services (GitHub API, file system)
- Moderate execution time (< 1 second per test)