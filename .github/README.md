# CI/CD Pipeline for MCP Git Server

This directory contains GitHub Actions workflows that validate MCP server behavior and maintain code quality.

## 🔄 Workflows

### 1. **CI Workflow** (`.github/workflows/ci.yml`)
**Triggers**: Push to main/development/feature branches, Pull Requests

**Jobs**:
- **Quality**: Code linting, formatting, type checking
- **Test**: Unit and integration tests across Python 3.10-3.12
- **MCP Validation**: Protocol compliance and behavior testing
- **Docker**: Container build validation
- **Security**: Dependency vulnerability scanning
- **Performance**: Load testing for PR/main branch changes

**Key Features**:
- ✅ **Zero-tolerance quality policy** - F,E9 lint violations fail CI
- ✅ **Cross-platform testing** - Linux, Windows, macOS
- ✅ **MCP-specific validation** - Protocol compliance checks
- ✅ **Docker integration** - Container functionality validation
- ✅ **Security scanning** - Dependency audit with safety/pip-audit

### 2. **Release Workflow** (`.github/workflows/release.yml`)
**Triggers**: Git tags (v*), Manual dispatch

**Features**:
- Full CI validation before release
- Package building and testing
- Automated GitHub releases with artifacts
- Release notes generation

### 3. **Nightly Workflow** (`.github/workflows/nightly.yml`)
**Triggers**: Daily at 2 AM UTC, Manual dispatch

**Extended Testing**:
- **Stress testing** - 1000+ notification processing
- **Memory usage validation** - Resource consumption monitoring
- **Large repository testing** - Performance with complex Git histories
- **Cross-platform validation** - All OS/Python combinations
- **Extended MCP scenarios** - Real-world usage patterns

## 🚀 MCP Behavior Validation

### **Core MCP Validations**
The CI pipeline includes comprehensive MCP server behavior testing:

1. **Protocol Compliance**
   - Server startup and shutdown
   - Notification model validation
   - Message parsing correctness

2. **Error Handling**
   - Unknown notification types
   - Malformed message recovery
   - Graceful failure modes

3. **Performance**
   - High-volume notification processing
   - Memory usage under load
   - Response time validation

4. **Integration**
   - Git operations functionality
   - Real repository interaction
   - Complex Git scenarios (merges, conflicts, branches)

### **Local Validation Script**
```bash
# Run MCP behavior validation locally
python scripts/validate_mcp_behavior.py --verbose

# With custom test repository
python scripts/validate_mcp_behavior.py --test-repo /path/to/repo

# Generate detailed report
python scripts/validate_mcp_behavior.py --report validation-report.json
```

## 🛡️ Quality Gates

### **Pre-commit Hooks** (`.pre-commit-config.yaml`)
```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks on all files
uv run pre-commit run --all-files
```

**Hook Categories**:
- **Code Quality**: ruff (linting + formatting), mypy (type checking)
- **Security**: bandit (security issues), safety (dependency vulnerabilities)
- **MCP Validation**: Custom hooks for protocol compliance
- **Git Standards**: Conventional commit messages, merge conflict detection

### **Quality Standards**
- ✅ **Zero critical lint violations** (F,E9 errors)
- ✅ **100% test pass rate** 
- ✅ **Security vulnerability checks**
- ✅ **MCP protocol compliance**
- ✅ **Type safety validation**

## 📊 CI Status Monitoring

### **Branch Protection Rules** (Recommended)
```yaml
# .github/branch-protection.yml (if using probot/settings)
branches:
  main:
    protection:
      required_status_checks:
        strict: true
        contexts:
          - "Quality & Static Analysis"
          - "Unit & Integration Tests"  
          - "MCP Server Behavior Validation"
          - "Docker Build Validation"
      enforce_admins: true
      required_pull_request_reviews:
        required_approving_review_count: 1
        dismiss_stale_reviews: true
```

### **Failure Analysis**
When CI fails, check:

1. **Quality Issues**: Review ruff/mypy output for code problems
2. **Test Failures**: Check pytest output for broken functionality  
3. **MCP Validation**: Review MCP behavior validation logs
4. **Security Issues**: Address bandit/safety vulnerability reports
5. **Docker Problems**: Check container build and runtime issues

## 🔧 Local Development Workflow

### **Before Committing**
```bash
# 1. Run tests
uv run pytest

# 2. Check code quality  
uv run ruff check --select=F,E9
uv run ruff format --check

# 3. Run MCP validation
python scripts/validate_mcp_behavior.py

# 4. Run pre-commit hooks
uv run pre-commit run --all-files
```

### **Package Manager Commands**
```bash
# Test command
uv run pytest

# Lint command (critical)
uv run ruff check --select=F,E9

# Lint command (full)
uv run ruff check

# Type checking
uv run pyright

# Format code
uv run ruff format

# Pre-commit hooks
uv run pre-commit run --all-files
```

## 🎯 Integration with MCP Inspector

The workflows are designed to integrate with [MCP Inspector](https://github.com/modelcontextprotocol/inspector) when available:

```python
# In CI scripts
pip install mcp-inspector || echo "MCP inspector not available"

# Use inspector for protocol validation
mcp-inspector validate mcp-server-git
```

**Benefits of MCP Inspector Integration**:
- ✅ **Protocol compliance verification**
- ✅ **Message format validation**
- ✅ **Performance benchmarking**
- ✅ **Interoperability testing**

## 🚨 Troubleshooting

### **Common CI Failures**

1. **Linting Failures (F,E9)**
   ```bash
   # Fix locally
   uv run ruff check --select=F,E9 --fix
   ```

2. **Test Failures**
   ```bash
   # Run specific test
   uv run pytest tests/test_specific.py -v
   ```

3. **MCP Validation Failures**
   ```bash
   # Debug locally
   python scripts/validate_mcp_behavior.py --verbose
   ```

4. **Pre-commit Hook Failures**
   ```bash
   # Fix and retry
   uv run pre-commit run --all-files
   ```

### **Performance Issues**
- **Large repositories**: CI includes performance testing
- **Memory usage**: Monitored in nightly workflow
- **Network timeouts**: Configurable timeout settings

## 📈 Monitoring and Metrics

The CI pipeline provides comprehensive metrics:

- **Test coverage** (uploaded to Codecov)
- **Performance benchmarks** (nightly validation)
- **Security scan results** (artifact uploads)
- **MCP compliance reports** (JSON format)

**GitHub Actions Insights** provide:
- ✅ Success/failure rates over time
- ⏱️ Workflow duration trends  
- 🔄 Job-level performance analysis
- 📊 Cross-platform compatibility metrics