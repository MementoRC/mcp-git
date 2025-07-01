# MCP Git Server Security Guide

## Overview

The MCP Git Server enforces strict security policies to prevent unverified commits and ensure all git operations are properly signed and authenticated.

## 🔒 Security Features

### Mandatory GPG Signing
- **ALL commits are GPG signed** - no exceptions
- Automatic GPG key detection and configuration
- Environment variable support for key specification
- Clear error messages for missing GPG setup

### Security Validation Tools
- `git_security_validate` - Check repository security configuration
- `git_security_enforce` - Automatically fix security issues

### MCP-Only Operations
- Prevents fallback to system git commands
- Type-safe git operations through MCP tools
- Structured error handling and validation

## 🚨 Critical Security Requirements

### GPG Configuration
The server requires GPG to be properly configured. It will:

1. **Auto-detect available GPG keys** from your system
2. **Use environment variables** if specified
3. **Configure git automatically** in strict mode
4. **Prevent unsigned commits** with clear error messages

### Required Environment Variables

```bash
# Optional: Specify GPG key (auto-detected if not set)
GPG_SIGNING_KEY=your_gpg_key_id

# Optional: Git user configuration (auto-configured if not set)
GIT_USER_NAME="Your Name"
GIT_USER_EMAIL="your.email@example.com"
```

## 🛠️ Setup Instructions

### 1. GPG Key Setup
```bash
# Generate a new GPG key (if needed)
gpg --full-generate-key

# List your GPG keys to get the key ID
gpg --list-secret-keys --keyid-format=LONG

# Example output:
# sec   rsa3072/C7927B4C27159961 2021-05-20 [SC]
#       07790D5A1947602D0BD20595C7927B4C27159961
# uid                 [ultimate] Your Name <your.email@example.com>

# Use the key ID: C7927B4C27159961
```

### 2. Environment Configuration
Create a `.env` file in your project or ClaudeCode workspace:

```bash
# .env file
GITHUB_TOKEN=your_github_token
GPG_SIGNING_KEY=C7927B4C27159961
GIT_USER_NAME="Your Name"
GIT_USER_EMAIL="your.email@example.com"
```

### 3. Automatic Configuration
The MCP Git Server will automatically:
- Enable GPG signing (`commit.gpgsign = true`)
- Set your GPG key (`user.signingkey = YOUR_KEY`)
- Configure user name and email if not set
- Validate configuration before each commit

## 🔧 Security Tools Usage

### Validate Security Configuration
```python
# Check current security configuration
git_security_validate(repo_path="/path/to/repo")
```

### Enforce Security Configuration
```python
# Automatically fix security issues
git_security_enforce(repo_path="/path/to/repo", strict_mode=True)
```

## ⚠️ Security Warnings

### Commit Failures
If commits fail due to security issues:

1. **Missing GPG key**: Set `GPG_SIGNING_KEY` or install GPG
2. **Invalid configuration**: Run `git_security_enforce` tool
3. **Wrong key configured**: Update `.env` file or git config

### Common Error Messages

#### "No GPG signing key configured"
```bash
# Solution 1: Set environment variable
export GPG_SIGNING_KEY=your_key_id

# Solution 2: Configure git locally
git config user.signingkey your_key_id
```

#### "GITHUB_TOKEN environment variable not set"
```bash
# Solution: Add to .env file
echo "GITHUB_TOKEN=your_token" >> .env
```

## 🚫 Prohibited Operations

### The following are NOT allowed:
- **Unsigned commits** - All commits must be GPG signed
- **System git fallback** - Must use MCP Git tools exclusively
- **Unverified identities** - User name/email must be configured
- **Insecure configurations** - Automatic security enforcement

## 🎯 Best Practices

### 1. Environment Setup
- Use `.env` files for sensitive configuration
- Keep GPG keys secure and backed up
- Use strong GPG key passphrases

### 2. Workflow Integration
- Let MCP Git Server handle security automatically
- Use security validation tools for diagnostics
- Monitor commit verification status on GitHub

### 3. Team Configuration
- Document GPG setup requirements for team
- Use consistent `.env.example` files
- Enforce security policies in CI/CD

## 🆘 Troubleshooting

### GPG Issues
```bash
# Check GPG installation
gpg --version

# List available keys
gpg --list-secret-keys

# Test GPG signing
echo "test" | gpg --clearsign
```

### Git Configuration Issues
```bash
# Check git configuration
git config --list | grep -E "(gpg|sign|user)"

# Reset security configuration
git config --unset commit.gpgsign
git config --unset user.signingkey
```

### MCP Server Issues
```bash
# Test MCP Git tools availability
# Use git_security_validate tool to check configuration
```

## 🔐 Security Benefits

### Prevents
- ✅ Unverified commits on GitHub
- ✅ Identity spoofing in git history
- ✅ Unauthorized code changes
- ✅ System git command fallbacks

### Ensures
- ✅ All commits are cryptographically signed
- ✅ Verified identity on GitHub
- ✅ Consistent security configuration
- ✅ Type-safe git operations

## 📞 Support

For security-related issues:
1. Use `git_security_validate` tool for diagnostics
2. Check environment variables and GPG setup
3. Verify GitHub token configuration
4. Review this security guide for troubleshooting steps
