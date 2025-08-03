#!/usr/bin/env python3
"""
GitHub Repository Settings Management Demo

This script demonstrates how to use the new GitHub repository settings management tools
in mcp-git to automate repository configuration.

Usage examples:
1. Set up a repository with organization-standard settings
2. Configure GitHub Actions for CI/CD workflows  
3. Apply branch protection rules
4. Enable security features

Note: Requires GITHUB_TOKEN environment variable to be set.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def demo_repository_settings():
    """Demonstrate repository settings configuration"""
    print("🏗️  Demo: Repository Settings Configuration")
    print("=" * 50)
    
    from mcp_server_git.core.handlers import CallToolHandler
    
    handler = CallToolHandler()
    
    # Example: Configure repository with standard settings
    print("\n📝 Setting up repository with organization standards...")
    result = await handler.call_tool("github_repo_settings", {
        "repo_owner": "example-org",
        "repo_name": "example-repo",
        "has_issues": True,
        "has_projects": True,
        "has_wiki": False,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": True,
        "delete_branch_on_merge": True,
        "allow_auto_merge": True,
        "squash_merge_commit_title": "PR_TITLE",
        "squash_merge_commit_message": "PR_BODY"
    })
    
    if result:
        print(f"Result: {result[0].text}")
    
    return True

async def demo_actions_configuration():
    """Demonstrate GitHub Actions configuration"""
    print("\n⚙️  Demo: GitHub Actions Configuration")
    print("=" * 50)
    
    from mcp_server_git.core.handlers import CallToolHandler
    
    handler = CallToolHandler()
    
    # Example: Configure Actions with organization-only permissions
    print("\n🔧 Configuring GitHub Actions for organization-only access...")
    result = await handler.call_tool("github_actions_settings", {
        "repo_owner": "example-org",
        "repo_name": "example-repo",
        "enabled": True,
        "allowed_actions": "selected",
        "github_owned_allowed": True,
        "verified_allowed": True,
        "patterns_allowed": ["example-org/*", "actions/*"]
    })
    
    if result:
        print(f"Result: {result[0].text}")
    
    # Example: Configure workflow permissions for PR approval
    print("\n🔐 Setting workflow permissions to allow PR approvals...")
    result = await handler.call_tool("github_workflow_permissions", {
        "repo_owner": "example-org", 
        "repo_name": "example-repo",
        "default_workflow_permissions": "write",
        "can_approve_pull_request_reviews": True
    })
    
    if result:
        print(f"Result: {result[0].text}")
    
    return True

async def demo_branch_protection():
    """Demonstrate branch protection configuration"""
    print("\n🛡️  Demo: Branch Protection Configuration")
    print("=" * 50)
    
    from mcp_server_git.core.handlers import CallToolHandler
    
    handler = CallToolHandler()
    
    # Example: Set up main branch protection
    print("\n🔒 Configuring branch protection for main branch...")
    result = await handler.call_tool("github_branch_protection", {
        "repo_owner": "example-org",
        "repo_name": "example-repo", 
        "branch": "main",
        "required_status_checks": {
            "strict": True,
            "contexts": ["ci/build", "ci/test", "ci/lint"]
        },
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False
        },
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_linear_history": True
    })
    
    if result:
        print(f"Result: {result[0].text}")
    
    return True

async def demo_security_settings():
    """Demonstrate security settings configuration"""
    print("\n🔐 Demo: Security Settings Configuration")
    print("=" * 50)
    
    from mcp_server_git.core.handlers import CallToolHandler
    
    handler = CallToolHandler()
    
    # Example: Enable security features
    print("\n🛡️ Enabling security features...")
    result = await handler.call_tool("github_security_settings", {
        "repo_owner": "example-org",
        "repo_name": "example-repo",
        "vulnerability_alerts": True,
        "automated_security_fixes": True,
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
            "dependency_graph": {"status": "enabled"}
        }
    })
    
    if result:
        print(f"Result: {result[0].text}")
    
    return True

async def demo_ci_framework_use_case():
    """Demonstrate the original ci-framework use case"""
    print("\n🚀 Demo: CI Framework Use Case")
    print("=" * 50)
    print("Automating repository setup for ci-framework cleanup workflow...")
    
    from mcp_server_git.core.handlers import CallToolHandler
    
    handler = CallToolHandler()
    
    repo_owner = "MementoRC"
    repo_name = "ci-framework"
    
    print(f"\n📋 Setting up {repo_owner}/{repo_name} for automated cleanup workflow...")
    
    # Step 1: Configure Actions to allow GitHub Actions to create PRs
    print("\n1️⃣ Enabling GitHub Actions with write permissions...")
    result = await handler.call_tool("github_workflow_permissions", {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "default_workflow_permissions": "write",
        "can_approve_pull_request_reviews": True
    })
    if result:
        print(f"   ✅ Workflow permissions: {result[0].text[:100]}...")
    
    # Step 2: Configure organization-only actions
    print("\n2️⃣ Restricting to organization-only actions...")
    result = await handler.call_tool("github_actions_settings", {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "enabled": True,
        "allowed_actions": "selected",
        "github_owned_allowed": True,
        "verified_allowed": True,
        "patterns_allowed": ["MementoRC/*"]
    })
    if result:
        print(f"   ✅ Actions settings: {result[0].text[:100]}...")
    
    # Step 3: Configure branch protection for development branch
    print("\n3️⃣ Setting up branch protection...")
    result = await handler.call_tool("github_branch_protection", {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "branch": "development",
        "required_status_checks": {
            "strict": True,
            "contexts": ["ci/cleanup-validation"]
        },
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True
        },
        "allow_force_pushes": False,
        "allow_deletions": False
    })
    if result:
        print(f"   ✅ Branch protection: {result[0].text[:100]}...")
    
    # Step 4: Enable security features for compliance
    print("\n4️⃣ Enabling security features...")
    result = await handler.call_tool("github_security_settings", {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "vulnerability_alerts": True,
        "automated_security_fixes": True
    })
    if result:
        print(f"   ✅ Security settings: {result[0].text[:100]}...")
    
    print("\n🎉 Repository configuration complete! The cleanup workflow can now:")
    print("   • Create and approve pull requests automatically")
    print("   • Use only organization-approved actions")
    print("   • Follow branch protection policies")
    print("   • Maintain security compliance")
    
    return True

async def main():
    """Run all demonstrations"""
    print("🌟 GitHub Repository Settings Management Demo")
    print("=" * 60)
    print("This demo shows how to use mcp-git's new GitHub repository")
    print("settings management capabilities to automate repository configuration.")
    print()
    
    # Check for GitHub token
    if not os.getenv("GITHUB_TOKEN"):
        print("⚠️  Note: GITHUB_TOKEN not set. Demos will show authentication errors,")
        print("   but demonstrate the tool call structure and parameters.")
        print()
    
    demos = [
        demo_repository_settings,
        demo_actions_configuration,
        demo_branch_protection,
        demo_security_settings,
        demo_ci_framework_use_case
    ]
    
    for demo in demos:
        try:
            await demo()
            print()
        except Exception as e:
            print(f"❌ Demo {demo.__name__} failed: {e}")
    
    print("📚 For more information, see:")
    print("   • GitHub REST API Documentation: https://docs.github.com/en/rest")
    print("   • mcp-git README: https://github.com/MementoRC/mcp-git/blob/main/README.md")
    print("   • Original issue: https://github.com/MementoRC/mcp-git/issues/41")

if __name__ == "__main__":
    asyncio.run(main())