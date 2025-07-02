# Test-Driven Development (TDD) Test Suite

This test suite follows strict TDD principles to ensure requirements drive implementation.

## 🔐 TDD Governance Rules

**CRITICAL**: Tests define requirements and are **IMMUTABLE** once marked complete.

### Test Modification Policy
- ✅ **ALLOWED**: New tests for new requirements
- ✅ **ALLOWED**: Test fixes for genuine bugs in test logic (with approval)
- ❌ **FORBIDDEN**: Modifying tests to match implementation
- ❌ **FORBIDDEN**: Removing tests that fail due to implementation issues

### Approval Process for Test Changes
1. Create GitHub issue explaining why test needs modification
2. Get approval from project maintainer
3. Document the requirement change that necessitates test change
4. Update tests with clear commit message referencing issue

## 📁 Test Structure (5-Layer Architecture)

```
tests/
├── unit/                    # Layer 1-2: Primitives & Operations
│   ├── primitives/         # Atomic Git/GitHub operations
│   ├── operations/         # Composed operations  
│   ├── types/             # Type system validation
│   ├── constants/         # Constants validation
│   └── protocols/         # Protocol definitions
├── integration/            # Layer 3: Services
│   ├── services/          # Service layer integration
│   └── applications/      # Application integration
├── system/                # Layer 4-5: Applications & Frameworks
│   ├── mcp_protocol/      # MCP protocol compliance
│   └── server_lifecycle/  # Full server testing
└── fixtures/              # Shared test data
    ├── git_repos/         # Git repository fixtures
    ├── github_responses/  # GitHub API response mocks
    └── mcp_messages/      # MCP protocol message fixtures
```

## 🏷️ Test Markers

Use pytest markers to categorize tests:

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests (moderate speed)  
- `@pytest.mark.system` - End-to-end tests (slower)
- `@pytest.mark.slow` - Tests taking >1 second
- `@pytest.mark.requires_git` - Needs git repository setup
- `@pytest.mark.requires_github` - Needs GitHub API access

## 🚀 Running Tests

```bash
# All tests
uv run pytest

# Unit tests only (fast feedback)
uv run pytest -m unit

# With coverage
uv run pytest --cov=src --cov-report=html

# Specific layer
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/system/

# Parallel execution
uv run pytest -n auto
```

## 📊 Coverage Requirements

- **Minimum**: 80% overall coverage (enforced by CI)
- **Target**: 90%+ coverage for critical paths
- **Primitives/Operations**: 95%+ coverage (foundational code)
- **Services**: 85%+ coverage
- **Applications**: 80%+ coverage

## 🎯 TDD Workflow

### Red-Green-Refactor Cycle

1. **RED**: Write failing test that defines requirement
2. **GREEN**: Write minimal code to make test pass
3. **REFACTOR**: Improve code while keeping tests passing

### Test-First Development

```python
# 1. FIRST: Write the test (should fail)
def test_git_status_returns_clean_repo():
    repo = GitRepository("/tmp/test-repo")
    status = repo.get_status()
    assert status.is_clean is True
    assert status.modified_files == []

# 2. THEN: Implement to make test pass
class GitRepository:
    def get_status(self) -> GitStatus:
        # Minimal implementation to pass test
        pass
```

## 🛡️ Quality Gates

Before any code commit:

1. ✅ All tests pass
2. ✅ Coverage >= 80%
3. ✅ No test modifications without approval
4. ✅ New functionality has corresponding tests
5. ✅ Tests follow naming conventions

## 📚 Test Writing Guidelines

### Test Naming Convention
```python
def test_[component]_[action]_[expected_result]():
    # Example: test_git_status_returns_clean_repo()
```

### Test Structure (AAA Pattern)
```python
def test_example():
    # ARRANGE: Set up test data
    repo = create_test_repository()
    
    # ACT: Execute the functionality
    result = repo.get_status()
    
    # ASSERT: Verify expectations
    assert result.is_clean is True
```

### Mock External Dependencies
```python
@pytest.mark.unit
def test_github_api_call(mocker):
    # Mock external GitHub API
    mock_response = mocker.patch('requests.get')
    mock_response.return_value.json.return_value = {'status': 'success'}
    
    # Test internal logic without external dependency
    result = github_service.get_user('test')
    assert result['status'] == 'success'
```

## 🔄 Continuous Integration

Tests run automatically on:
- Every commit to feature branches
- Pull request creation/updates  
- Merge to main branch

CI will **fail** if:
- Any test fails
- Coverage drops below 80%
- Test modifications detected without proper approval

## 🚨 Emergency Procedures

If tests are blocking critical fixes:

1. **NEVER** modify tests to make them pass
2. Create emergency branch with minimal fix
3. Document why tests need updating
4. Get approval for test modifications
5. Update tests in separate commit with clear reasoning

Remember: **Tests are requirements, not obstacles!**