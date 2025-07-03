# Cherry-pick Commands for fix/server-failure Branch

## Critical Bug Fixes to Cherry-pick

Execute these commands in the fix-server-failure worktree:

```bash
# 1. Critical syntax error fix (MUST HAVE)
git cherry-pick c003ab9

# 2. Import proper git operations fix (MUST HAVE)
git cherry-pick 4797ff0

# 3. Clean up unused imports
git cherry-pick 375ec07

# 4. CI and test fixes (in order)
git cherry-pick fc22217  # fix: resolve CI test failure in environment loading test
git cherry-pick 33021cd  # fix: optimize CI pipeline for test timeout and performance
git cherry-pick d757cab  # fix: add CI resilience for GitHub Actions infrastructure issues
git cherry-pick b345bfe  # fix: exclude stress tests from CI to prevent timeouts

# 5. Additional fixes
git cherry-pick d496478  # fix: resolve remaining CI test failures and improve environment handling
git cherry-pick 89d9da4  # fix: resolve critical CI failures and import errors
```

## Optional: Pixi Migration (if needed for quick deployment)

If you want the pixi configuration for the fix branch:

```bash
# Pixi migration
git cherry-pick 2240cff  # feat: complete migration from uv to pixi package management
git cherry-pick 9564083  # feat: configure MCP server to run with pixi package management
```

## Recommended Order

1. First apply the critical fixes (syntax and imports)
2. Test that the server runs
3. Apply CI fixes
4. Optionally add pixi support

## Notes

- The syntax error fix (c003ab9) is absolutely critical - server won't run without it
- The import fix (4797ff0) is needed for proper git operations
- CI fixes improve stability but aren't critical for local development
- Pixi migration is useful but not required for the fix branch