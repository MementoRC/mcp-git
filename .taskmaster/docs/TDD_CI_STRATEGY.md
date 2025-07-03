# TDD CI Strategy for Type System Implementation

## Overview

This document explains the CI configuration strategy for Test-Driven Development (TDD) of the type system in this project.

## Problem

During TDD red phase, we write tests first and implementations second. This creates legitimate linting violations:
- **F821**: Undefined names (tests reference unimplemented types)
- **F401**: Unused imports (test files import types not yet fully used)
- **F841**: Unused variables (test setup for incomplete scenarios)

## Solution: File-Specific Linting Rules

Instead of relaxing CI standards project-wide, we use **surgical precision**:

### Configuration

**`pyproject.toml`**:
```toml
[tool.ruff.lint.per-file-ignores]
# TDD type tests: Allow TDD-related violations during red phase
"tests/unit/types/*.py" = ["F821", "F401", "F841"]
# Production code: Maintain strict standards
"src/mcp_server_git/types/*.py" = []
```

**CI Workflow** (`.github/workflows/ci.yml`):
- Uses per-file-ignores from pyproject.toml
- Maintains strict linting for all production code
- Only relaxes rules for type test files

### Benefits

1. **Surgical Precision**: Only affects TDD test files where needed
2. **Quality Preservation**: Production code maintains full quality standards
3. **Clear Boundaries**: Easy to understand which code has which standards
4. **Future-Proof**: When types are implemented, strict linting automatically applies
5. **Contributor-Friendly**: Clear rules about expectations

### File Structure

```
tests/unit/types/          # Relaxed TDD rules (F821, F401, F841 ignored)
├── test_git_types.py      # ✅ Can reference unimplemented GitBranch
├── test_mcp_types.py      # ✅ Can import unused MCPRequest
└── test_validation_types.py

src/mcp_server_git/types/  # Strict production rules
├── git_types.py           # ❌ Must implement all referenced types
├── mcp_types.py           # ❌ Must use all imports
└── validation_types.py    # ❌ Must use all variables
```

## TDD Workflow

### Red Phase (Tests First)
1. Write tests in `tests/unit/types/` - **relaxed linting**
2. Reference unimplemented types freely
3. Import types speculatively for test setup
4. CI passes with TDD-compatible rules

### Green Phase (Minimal Implementation)
1. Implement types in `src/mcp_server_git/types/` - **strict linting**
2. Must satisfy all imports and references
3. Production code maintains quality standards
4. CI enforces strict rules for implementations

### Refactor Phase (Improve Design)
1. Both test and implementation code must pass their respective standards
2. Clean up unused imports in tests if desired
3. Maintain quality boundaries

## Graduation Strategy

When TDD phase completes:

1. **Keep Configuration**: Per-file rules remain beneficial for future TDD
2. **Document Completion**: Update this file to mark TDD phase complete
3. **Review Test Quality**: Optionally clean up test imports for consistency
4. **Monitor**: Production code automatically maintains strict standards

## Quality Assurance

- **Critical Errors**: Always caught (E9 syntax errors, other F violations)
- **Production Code**: Full strict linting always applied
- **Test Code**: TDD-compatible but still catches real issues
- **Documentation**: Clear boundaries and expectations

This approach balances TDD workflow needs with long-term code quality and maintainability.