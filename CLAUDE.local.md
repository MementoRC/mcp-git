# Claude Development Framework Instructions

This document provides a reusable framework for managing complex software development projects using AI-assisted development tools and systematic project management.

## Framework Overview

This framework combines AI-assisted development with systematic project management using TaskMaster AI for tracking progress, maintaining quality standards, and ensuring systematic completion of complex software projects.

## Project Management with TaskMaster AI

### 🎯 **Task Management Strategy**

**Primary Tool**: Use the `taskmaster-ai` MCP tool for all project planning and tracking instead of manual markdown files.

**Core Commands**:
- `mcp__taskmaster-ai__initialize_project` - Set up project structure
- `mcp__taskmaster-ai__parse_prd` - Generate tasks from requirements document
- `mcp__taskmaster-ai__get_tasks` - View current project status
- `mcp__taskmaster-ai__next_task` - Get next prioritized task
- `mcp__taskmaster-ai__set_task_status` - Update task progress
- `mcp__taskmaster-ai__get_health_status` - Monitor project health

### Project Initialization Workflow

1. **Initialize TaskMaster Project**
   ```
   mcp__taskmaster-ai__initialize_project(projectRoot="/path/to/project")
   ```

2. **Create Requirements Document**
   - Place project requirements in `scripts/prd.txt`
   - Include technical specifications, objectives, and acceptance criteria

3. **Generate Task Structure**
   ```
   mcp__taskmaster-ai__parse_prd(input="scripts/prd.txt", numTasks="15")
   ```

4. **Monitor Progress**
   ```
   mcp__taskmaster-ai__get_tasks(withSubtasks=true)
   mcp__taskmaster-ai__next_task()
   ```

### Task Lifecycle Management

**Task Status Progression**:
- `pending` → `in-progress` → `done`
- Alternative: `pending` → `in-progress` → `review` → `done`
- Exception: `cancelled` or `deferred`

**Status Updates**:
```
mcp__taskmaster-ai__set_task_status(id="5", status="in-progress")
mcp__taskmaster-ai__set_task_status(id="5", status="done")
```

## Development Workflow Process

### 🎯 **SYSTEMATIC DEVELOPMENT WORKFLOW**

### Phase-Based Development

1. **Planning Phase**
   - Use TaskMaster AI to break down requirements into manageable tasks
   - Create dependency chains between tasks
   - Prioritize tasks based on complexity and dependencies
   - Set up quality gates and acceptance criteria

2. **Implementation Phase**
   - Follow task dependencies using `mcp__taskmaster-ai__next_task`
   - Update task status in real-time during development
   - Maintain quality standards with each task completion
   - Document progress through task updates

3. **Quality Assurance Phase**
   - Run quality checks after each task completion
   - Update task status only after quality validation
   - Use TaskMaster complexity analysis for risk assessment
   - Monitor project health through TaskMaster metrics

4. **Integration Phase**
   - Complete integration tasks using TaskMaster coordination
   - Validate end-to-end functionality
   - Update final task statuses
   - Generate project completion reports

### Quality Standards Integration

**🚨 CRITICAL: ZERO-TOLERANCE QUALITY POLICY**

**ABSOLUTE REQUIREMENTS - NO EXCEPTIONS:**

### 🛑 **STOP-GATE QUALITY CHECKS**
**BEFORE PROCEEDING TO NEXT TASK OR COMMIT:**

1. **MANDATORY Unit tests**: 100% pass rate - **ZERO FAILURES ALLOWED**
2. **MANDATORY Critical lint checks**: **ZERO F,E9 violations ALLOWED**
3. **MANDATORY Pre-commit validation**: **MUST PASS ALL HOOKS**
4. **MANDATORY CI Status**: **ALL CHECKS MUST BE GREEN**
5. **MANDATORY TaskMaster update**: Update status ONLY after quality validation

**⚠️ QUALITY FAILURE PROTOCOL:**
- **IF ANY CHECK FAILS**: STOP all development immediately
- **INVESTIGATE ROOT CAUSE**: Never proceed with "quick fixes"
- **FIX SYSTEMATICALLY**: Address underlying issues, not symptoms
- **RE-RUN ALL CHECKS**: Verify complete resolution before proceeding
- **ESCALATE IF STUCK**: Ask for help rather than compromising quality

### 🔍 **MANDATORY QUALITY SEQUENCE**
**Execute in EXACT order after each task:**

```bash
# STEP 1: Core Quality Validation (MUST PASS)
hatch -e dev run pytest                    # All tests pass
hatch -e dev run ruff check --select=F,E9 # Zero critical violations

# STEP 2: Comprehensive Quality Validation (MUST PASS)
hatch -e dev run pre-commit run --all-files # All hooks pass

# STEP 3: Git Status Verification (MUST BE CLEAN)
git status                                 # Clean working tree

# STEP 4: CI Validation (IF APPLICABLE)
gh pr checks                              # All CI checks passing
```

**🚨 CONTAMINATION PREVENTION:**
- **FILE INTEGRITY**: Verify no unrelated files in project
- **DEPENDENCY INTEGRITY**: Check no foreign dependencies introduced
- **TEST ISOLATION**: Ensure tests don't interfere with each other
- **ASYNC CLEANUP**: Verify no hanging tasks or resources

## Git Workflow Integration

### Branch Strategy
- **Main development branch**: `feature/project-name` or `main`
- **Task branches**: `feature/task-X-description` (for complex tasks)
- **Quality branches**: `quality/fixes-batch-X` (for quality improvements)

### Commit Strategy
Each task completion gets a commit following this pattern:
```
feat: implement Task X - [Task Title]

- [Key implementation detail 1]
- [Key implementation detail 2]
- [Integration points or dependencies resolved]

✅ Quality: [Quality check results]
✅ Tests: [Test status]
📋 TaskMaster: [Task status update]
🎯 Next: [Next task or dependency]

🤖 Generated with [Claude Code](https://claude.ai/code)
Co-Authored-By: Claude <noreply@anthropic.com>
```

## PR Management Best Practices

**🚨 IMPORTANT: UPDATE PR DESCRIPTION, NOT COMMENTS**

- **DO**: Use `gh pr edit <PR_NUMBER> --body` to update PR summary with TaskMaster progress
- **DON'T**: Post individual comments for each task (clutters discussion)
- **Reason**: PR description serves as authoritative progress summary

**PR Description Template**:
```markdown
# [Project Title] - [Current Phase]

## Progress Summary
- **X/Y tasks completed** ✅
- **Current Phase:** [Phase description from TaskMaster]
- **Quality Status:** [Test count] passing, zero critical violations

## Recent Milestones (from TaskMaster)
- ✅ Task X: [Description] - [Key achievement]
- ✅ Task Y: [Description] - [Key achievement]

## Next Steps (from TaskMaster)
- [Next prioritized tasks from taskmaster-ai__next_task]

## Quality Verification
- All CI checks passing
- TaskMaster project health: [status]
```

## Development Tools Integration

### Primary Development Tools
- **Task Management**: `taskmaster-ai` MCP tool (primary)
- **Code Implementation**: `aider` or other AI coding tools
- **Problem Analysis**: `sequentialthinking` for complex decisions
- **Alternative Solutions**: Additional AI models for consultation
- **Quality Assurance**: Project-specific linting and testing tools

### TaskMaster AI Commands Reference

**Core Task Management**:
- `get_tasks()` - View all tasks and current status
- `get_task(id="X")` - Get detailed task information
- `next_task()` - Get next prioritized task to work on
- `set_task_status(id="X", status="done")` - Update task completion

**Advanced Features**:
- `analyze_project_complexity()` - Assess project complexity
- `expand_task(id="X")` - Break complex tasks into subtasks
- `add_dependency(id="X", dependsOn="Y")` - Manage task dependencies
- `complexity_report()` - Generate complexity analysis

## Context Restart Instructions

**🚨 MANDATORY STARTUP SEQUENCE - NEVER SKIP:**

When context window requires restart:

1. **Read this framework document** for workflow guidelines
2. **MANDATORY**: Run complete quality validation sequence:
   ```bash
   hatch -e dev run pytest                    # Verify all tests pass
   hatch -e dev run ruff check --select=F,E9 # Verify zero critical violations
   hatch -e dev run pre-commit run --all-files # Verify all hooks pass
   git status                                 # Verify clean working tree
   ```
3. **Check TaskMaster status**: `mcp__taskmaster-ai__get_tasks()`
4. **Identify current focus**: `mcp__taskmaster-ai__next_task()`
5. **Review project health**: `mcp__taskmaster-ai__complexity_report()`
6. **Check git status**: `git log --oneline -5` and `git status`
7. **Verify CI status**: `gh pr checks` (if applicable)
8. **CONTAMINATION SCAN**: Verify no unrelated files in project structure
9. **Continue systematic development** following TaskMaster priorities

**⚠️ IF ANY STARTUP CHECK FAILS:**
- **STOP immediately** - do not proceed with development
- **Investigate root cause** thoroughly
- **Fix systematically** before resuming work
- **Document findings** for future prevention

## Framework Customization

### Project-Specific Adaptations

1. **Quality Commands**: Update quality check commands for your tech stack
2. **Task Complexity**: Adjust task breakdown complexity based on project size
3. **Branch Strategy**: Adapt branch naming to your team's conventions
4. **CI/CD Integration**: Configure TaskMaster updates to trigger on CI events

### Technology Stack Examples

**Python Projects**:
```bash
# Quality checks
hatch -e dev run pytest
hatch -e dev run ruff check --select=F,E9
hatch -e dev run mypy src/

# Dependencies
pip install taskmaster-ai  # If available as package
```

**Node.js Projects**:
```bash
# Quality checks
npm test
npm run lint
npm run type-check
npm run build

# Task management via MCP
# Use taskmaster-ai MCP server
```

**Go Projects**:
```bash
# Quality checks
go test ./...
go vet ./...
golangci-lint run
go build ./...
```

## Important Framework Principles

### 🚨 **FRAMEWORK FUNDAMENTALS**

- **TaskMaster-Driven**: All project tracking through TaskMaster AI, not manual files
- **Quality-First**: Never proceed without passing quality checks
- **Systematic Progress**: Follow task dependencies and priorities
- **Real-Time Updates**: Update TaskMaster status as work progresses
- **Documentation Through Tools**: Let TaskMaster generate reports instead of manual docs

### ⚠️ **CRITICAL SUCCESS FACTORS**

- **Use TaskMaster AI** instead of manual tracking documents
- **Maintain task dependency integrity** for systematic progress
- **Update task status immediately** after completion
- **Run quality checks before** marking tasks complete
- **Follow git workflow** with meaningful commit messages linked to tasks
- **Keep PR descriptions current** with TaskMaster progress updates

### 🛡️ **DISASTER PREVENTION PROTOCOLS**

**EARLY WARNING SYSTEMS:**
- **CI Failure**: Immediate investigation required - never ignore
- **Test Degradation**: Any reduction in test coverage triggers review
- **Lint Violations**: Address immediately before they multiply
- **Dependency Drift**: Monitor for unexpected package changes

**RECOVERY PROCEDURES:**
- **Project Corruption**: Stop immediately, identify source, clean systematically
- **CI Breakage**: Isolate changes, test locally, fix root cause
- **Quality Regression**: Rollback to last known good state if needed
- **Task Pile-up**: Re-prioritize with TaskMaster, break down complex tasks

**QUALITY ESCALATION MATRIX:**
1. **Green**: All checks pass → Proceed normally
2. **Yellow**: Non-critical warnings → Address within current task
3. **Red**: Critical failures → STOP, investigate, fix before proceeding
4. **Black**: Project corruption → Emergency cleanup protocol

**🎯 This framework transforms chaotic development into systematic, trackable, and high-quality project delivery using AI-assisted project management tools.**

## Complete Task Implementation Workflow

### 🔄 **PROVEN DEVELOPMENT WORKFLOW**
*Based on Environment Manager Detection and Integration Project (Tasks 1-10)*

This section documents the exact workflow used to successfully implement complex features with zero quality regressions. Follow this workflow for consistent, high-quality results.

#### **Phase 1: Task Status and Planning**

```bash
# 1. Check current project status
mcp__taskmaster-ai__get_tasks(projectRoot="/path/to/project", withSubtasks=true)

# 2. Get next prioritized task
mcp__taskmaster-ai__next_task(projectRoot="/path/to/project")

# 3. Mark task as in-progress
mcp__taskmaster-ai__set_task_status(id="X", status="in-progress", projectRoot="/path/to/project")

# 4. Update TodoWrite with current task
TodoWrite([{"content": "Implement Task X - [Description]", "status": "in_progress", "priority": "medium", "id": "task-x"}])
```

#### **Phase 2: Implementation Analysis**

```bash
# 5. Analyze existing codebase for patterns
Glob(pattern="**/*[relevant_pattern]*")  # Find related files
Grep(pattern="[relevant_concept]", include="*.py")  # Search for existing implementations

# 6. Read key files to understand architecture
Read(file_path="/path/to/key/file.py")  # Read implementation patterns
Read(file_path="/path/to/related/test.py")  # Read testing patterns

# 7. Use Task tool for complex searches
Task(description="Search for related patterns", prompt="Find all files related to [concept] and analyze implementation patterns")
```

#### **Phase 3: Core Implementation**

```bash
# 8. Write main implementation
Write(file_path="/path/to/new/module.py", content="[implementation]")

# 9. Write comprehensive tests
Write(file_path="/path/to/test_module.py", content="[test_implementation]")

# 10. Update module imports/exports
Edit(file_path="/path/to/__init__.py", old_string="[old_exports]", new_string="[new_exports]")
```

#### **Phase 4: Quality Validation Sequence**

**🚨 MANDATORY - RUN IN EXACT ORDER:**

```bash
# 11. Run tests with environment-specific command
pixi run -e dev pytest tests/path/to/new_tests.py -v

# 12. Run full test suite to ensure no regressions
pixi run -e dev pytest -x

# 13. Check critical lint violations
pixi run -e dev ruff check --select=F,E9

# 14. Run pre-commit hooks for full quality check
pixi run -e dev pre-commit run --all-files

# 15. Verify git status is clean
git status
```

#### **Phase 5: Task Completion and Git Workflow**

```bash
# 16. Mark task as complete only after quality validation
mcp__taskmaster-ai__set_task_status(id="X", status="done", projectRoot="/path/to/project")

# 17. Update TodoWrite
TodoWrite([{"content": "Implement Task X - [Description]", "status": "completed", "priority": "medium", "id": "task-x"}])

# 18. Stage only relevant files (avoid git add .)
git add src/module/new_file.py tests/test_new_file.py

# 19. Create commit with TaskMaster-linked message
git commit -m "$(cat <<'EOF'
feat: implement Task X - [Task Title]

- [Key implementation detail 1]
- [Key implementation detail 2]
- [Integration points or dependencies resolved]

✅ Quality: XXX tests passing, zero critical violations
✅ Tests: Complete test suite with [key test coverage]
📋 TaskMaster: Task X marked complete (Y/Z tasks done - N% progress)
🎯 Next: Task Y - [Next Task Description]

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# 20. Push to remote branch
git push origin [branch-name]
```

#### **Phase 6: PR Management and Documentation**

```bash
# 21. Check CI status
gh pr checks

# 22. Update PR description with current progress
gh pr edit [PR_NUMBER] --body "$(cat <<'EOF'
# [Project Title] - [Current Phase]

## Progress Summary
- **X/Y tasks completed** ✅
- **Current Phase:** [Phase description from TaskMaster]
- **Quality Status:** XXX tests passing, zero critical violations

## Recent Milestones (from TaskMaster)
- ✅ Task X: [Description] - [Key achievement]
- ✅ Task Y: [Description] - [Key achievement]

## Next Steps (from TaskMaster)
- [Next prioritized tasks from taskmaster-ai__next_task]

## Quality Verification
- All CI checks passing
- TaskMaster project health: [status]
EOF
)"
```

### **🔧 Common Implementation Patterns**

#### **Environment Manager Integration Pattern**
```python
# 1. Protocol-based design
from .protocol import EnvironmentManager

# 2. Factory pattern with detection
detector = EnvironmentManagerDetector(project_path=path)
manager = detector.get_active_manager()

# 3. Command wrapping
if manager:
    final_command = manager.build_command(base_command)
else:
    final_command = base_command  # Direct execution fallback
```

#### **Comprehensive Testing Pattern**
```python
# 1. Unit tests with mocks
@patch('module.subprocess.run')
def test_with_env_manager(self, mock_run, tmp_path):
    # Test implementation

# 2. Integration tests with real managers
def test_with_real_manager(self, tmp_path):
    # Create project files, test real behavior

# 3. Error handling tests
def test_timeout_handling(self):
    # Test all error conditions
```

#### **Quality Validation Commands by Project Type**

**Python Projects (Pixi/Poetry/Hatch):**
```bash
# Environment-aware testing
pixi run -e dev pytest
poetry run pytest
hatch run dev:pytest

# Environment-aware linting
pixi run -e dev ruff check --select=F,E9
poetry run ruff check --select=F,E9

# Pre-commit hooks
pixi run -e dev pre-commit run --all-files
```

### **🎯 Success Metrics**

**Quality Indicators:**
- ✅ All tests pass (typically 600+ tests)
- ✅ Zero critical lint violations (F,E9)
- ✅ All pre-commit hooks pass
- ✅ CI checks green
- ✅ TaskMaster status updated
- ✅ Clean git status

**Development Velocity:**
- **Task Implementation**: 20-30 minutes per moderate complexity task
- **Testing**: Comprehensive test suites with 15-25 tests per module
- **Quality Validation**: Full pipeline under 2 minutes
- **Integration**: Zero regressions across 600+ existing tests

**Project Health:**
- **Coverage**: Maintain or improve test coverage
- **Dependencies**: No unintended dependency changes
- **Architecture**: Consistent with existing patterns
- **Documentation**: Code self-documenting with clear interfaces

### **🛠️ Tool Usage Guidelines**

**Task Management:**
- **Primary**: TaskMaster AI for all project tracking
- **Secondary**: TodoRead/TodoWrite for session-level task tracking
- **Never**: Manual markdown task lists

**Code Search and Analysis:**
- **Large codebases**: Use Task tool for complex searches
- **Specific files**: Use Read tool directly
- **Pattern matching**: Use Glob and Grep in combination
- **Multiple rounds**: Use Task tool to avoid context bloat

**Implementation:**
- **New files**: Use Write tool
- **Existing files**: Use Edit or MultiEdit tools
- **Imports/exports**: Always update __init__.py files
- **Testing**: Write tests immediately after implementation

**Quality Validation:**
- **Always**: Use project-specific commands (pixi run, poetry run)
- **Never**: Use bare commands without environment context
- **Sequence**: Tests → Lint → Pre-commit → Git status
- **Failure**: Stop immediately, investigate, fix systematically

**Git Workflow:**
- **Staging**: Be selective, avoid `git add .`
- **Commits**: Use TaskMaster-linked commit messages
- **Pushing**: Always push after commit
- **PR Updates**: Update description, not comments

**🎯 This workflow has been proven to deliver high-quality features with zero regressions across complex software projects.**

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
# CI Verification Note
This minor addition verifies CI pipeline integration with development branch.
# CI Verification Note
This minor addition verifies CI pipeline integration with development branch.
