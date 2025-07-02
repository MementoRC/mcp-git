# Domain-Specific Type System Test Specifications

## 🎯 TDD Test Specifications for MCP Git Server Type System

This directory contains comprehensive **test specifications** that define the behavioral requirements for the domain-specific type system. These tests follow strict TDD principles and serve as **immutable requirements**.

### 🔐 Test Governance

**CRITICAL**: These tests are **REQUIREMENTS**, not suggestions.
- ❌ **FORBIDDEN**: Modifying tests to match implementation
- ✅ **REQUIRED**: Implementation must satisfy these test specifications
- 🔴 **RED PHASE**: All tests currently fail (no implementation exists)
- 🟢 **GREEN PHASE**: Implementation should make tests pass
- 🔄 **REFACTOR PHASE**: Improve implementation while keeping tests green

## 📁 Test Specification Structure

### `test_git_types.py` - Git Domain Types
**Domain**: Git repository operations and version control concepts

**Types Specified**:
- `GitRepositoryPath` - Type-safe Git repository paths with validation
- `GitBranch` - Git branch names with validation rules
- `GitCommitHash` - Git commit hash validation (full/short SHA-1)
- `GitFileStatus` - Git file status enumeration
- `GitOperationResult` - Git operation result wrapper
- `GitStatusResult` - Repository status information
- `GitCommitInfo` - Complete commit information
- `GitBranchInfo` - Branch metadata
- `GitRemoteInfo` - Remote repository information

**Key Requirements**:
- Path validation and existence checks
- Git naming convention enforcement
- Repository state representation
- Error handling for invalid Git operations

### `test_github_types.py` - GitHub API Types
**Domain**: GitHub API integration and repository management

**Types Specified**:
- `GitHubRepository` - GitHub repository identification and metadata
- `GitHubUser` - GitHub user/organization representation
- `GitHubPullRequest` - Pull request data and state management
- `GitHubCheckRun` - CI/CD check run status and results
- `GitHubAPIResponse` - API response wrapper with error handling
- `GitHubPagination` - API pagination support
- `GitHubRateLimit` - Rate limiting tracking and management

**Key Requirements**:
- GitHub naming convention validation
- API response structure validation
- Rate limiting and error handling
- State management for PR and check workflows

### `test_mcp_types.py` - MCP Protocol Types
**Domain**: Model Context Protocol compliance and message handling

**Types Specified**:
- `MCPRequest` - JSON-RPC request validation
- `MCPResponse` - JSON-RPC response formatting
- `MCPNotification` - Protocol notifications
- `MCPTool` - Tool definition and schema validation
- `MCPToolInput/Output` - Tool execution data
- `MCPCapabilities` - Protocol capability negotiation
- `MCPSession` - Session state management

**Key Requirements**:
- JSON-RPC 2.0 protocol compliance
- MCP specification adherence
- Tool schema validation (JSON Schema)
- Error code standardization

### `test_validation_types.py` - Validation Infrastructure
**Domain**: Cross-cutting validation and error handling

**Types Specified**:
- `ValidationResult` - Validation outcome representation
- `ValidationError` - Structured error information
- `ValidationRule` - Reusable validation logic
- `PathValidator` - File system path validation
- `EmailValidator` - Email format validation
- `GitRefValidator` - Git reference validation
- `GitHubNameValidator` - GitHub naming validation
- `CompositeValidator` - Multi-rule validation

**Key Requirements**:
- Consistent validation patterns
- Detailed error reporting
- Extensible validation framework
- Cross-domain validation support

### `test_composite_types.py` - Integration Types
**Domain**: Cross-domain type integration and workflow orchestration

**Types Specified**:
- `GitOperationRequest/Response` - Git + MCP integration
- `GitHubOperationRequest/Response` - GitHub + MCP integration
- `RepositoryContext` - Unified Git/GitHub context
- `IntegratedOperationResult` - Multi-domain operation results
- `TypeFactory` - Type creation utilities
- `TypeRegistry` - Type resolution system
- `DomainBridge` - Cross-domain type conversion

**Key Requirements**:
- Seamless domain integration
- Type-safe conversions
- Workflow orchestration
- Unified error handling

## 🧪 Test Data and Fixtures

### Shared Test Fixtures
Located in `/tests/fixtures/`:
- `git_repos.py` - Git repository test fixtures
- `github_responses.py` - Mock GitHub API responses
- `mcp_messages.py` - MCP protocol message fixtures

### Test Data Patterns

#### Valid Data Examples
```python
# Git domain
valid_repo_paths = ["/tmp/repo", "~/projects/app", "/var/git/service"]
valid_branches = ["main", "feature/auth", "bugfix-123", "release/v1.0"]
valid_commits = ["a1b2c3d", "abc123def456", "full-40-char-sha1-hash"]

# GitHub domain  
valid_github_repos = [("owner", "repo"), ("org-name", "project-2023")]
valid_usernames = ["user", "user-name", "user123", "123user"]

# MCP protocol
valid_methods = ["initialize", "tools/list", "tools/call", "resources/read"]
valid_error_codes = [-32700, -32600, -32601, -32602, -32603]
```

#### Invalid Data Examples
```python
# Git domain
invalid_branches = ["", "feature..double", "~invalid", "branch:name"]
invalid_commits = ["", "123", "invalid-chars", "too-long-hash"]

# GitHub domain
invalid_repos = [("", "repo"), ("owner", ""), ("owner with spaces", "repo")]
invalid_usernames = ["", "user name", "user@name", "-user", "user-"]

# MCP protocol
invalid_methods = ["", "invalid-method", "custom/method"]
```

## 🔍 Test Execution and Validation

### Running Type Tests
```bash
# All type tests
uv run pytest tests/unit/types/ -v

# Specific domain
uv run pytest tests/unit/types/test_git_types.py -v
uv run pytest tests/unit/types/test_github_types.py -v
uv run pytest tests/unit/types/test_mcp_types.py -v

# TDD workflow - should fail initially
uv run python scripts/test_runner.py tdd -k "GitRepositoryPath"
```

### Expected Test States

#### RED Phase (Current State)
- ✅ All tests **FAIL** with clear error messages
- ✅ Error messages indicate missing implementation
- ✅ Tests define exact API requirements

#### GREEN Phase (Implementation Goal)
- 🎯 Minimal implementation to pass tests
- 🎯 No additional features beyond test requirements
- 🎯 All validation rules enforced

#### REFACTOR Phase (Quality Improvement)
- 🎯 Improve code quality while tests stay green
- 🎯 Performance optimization
- 🎯 Documentation enhancement

## 📋 Implementation Checklist

### Phase 1: Core Type Definitions
- [ ] `src/mcp_server_git/types/` directory structure
- [ ] `git_types.py` - Git domain types
- [ ] `github_types.py` - GitHub API types  
- [ ] `mcp_types.py` - MCP protocol types
- [ ] `validation_types.py` - Validation infrastructure

### Phase 2: Validation Framework
- [ ] Base validation classes
- [ ] Domain-specific validators
- [ ] Error handling hierarchy
- [ ] Validation rule composition

### Phase 3: Integration Layer
- [ ] `composite_types.py` - Cross-domain integration
- [ ] Type factory and registry
- [ ] Domain bridge utilities
- [ ] Workflow orchestration types

### Phase 4: Quality Assurance
- [ ] All tests pass (GREEN phase)
- [ ] Coverage >= 95% for type system
- [ ] Performance benchmarks
- [ ] Integration testing

## 🎯 Success Criteria

### Type System Requirements Met
1. **Type Safety**: All domain concepts properly typed
2. **Validation**: Comprehensive input validation
3. **Error Handling**: Structured error reporting
4. **Integration**: Seamless cross-domain operations
5. **Extensibility**: Easy to add new types and validation rules

### TDD Process Followed
1. **RED**: All tests fail initially ✅
2. **GREEN**: Implementation makes tests pass
3. **REFACTOR**: Code quality improvements
4. **IMMUTABLE**: No test modifications during implementation

### Quality Standards Met
1. **Coverage**: ≥95% test coverage for type system
2. **Performance**: Type operations complete in <1ms
3. **Documentation**: All public APIs documented
4. **Compliance**: Full MCP protocol adherence

---

**Remember**: These tests are **executable specifications** that define exactly what the type system must do. Implementation success is measured by making these tests pass, not by modifying the tests to match implementation preferences.