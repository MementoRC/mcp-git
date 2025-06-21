"""Git security validation and enforcement"""

import logging
import os
import subprocess
from typing import Dict, List

import git

logger = logging.getLogger(__name__)


def validate_git_security_config(repo: git.Repo) -> Dict[str, any]:
    """Validate Git security configuration for the repository"""
    
    warnings = []
    recommendations = []
    
    try:
        # Check GPG signing configuration
        try:
            signing_key = repo.config_reader().get_value("user", "signingkey", fallback=None)
            gpg_sign = repo.config_reader().get_value("commit", "gpgsign", fallback="false")
            
            if not signing_key:
                warnings.append("No GPG signing key configured (user.signingkey)")
                recommendations.append("Set up GPG signing: git config user.signingkey <key-id>")
            
            if gpg_sign.lower() != "true":
                warnings.append("GPG signing not enabled by default (commit.gpgsign)")
                recommendations.append("Enable GPG signing: git config commit.gpgsign true")
        except Exception as e:
            warnings.append(f"Could not read GPG configuration: {e}")
        
        # Check user configuration
        try:
            user_name = repo.config_reader().get_value("user", "name", fallback=None)
            user_email = repo.config_reader().get_value("user", "email", fallback=None)
            
            if not user_name:
                warnings.append("No user name configured (user.name)")
                recommendations.append("Set user name: git config user.name 'Your Name'")
            
            if not user_email:
                warnings.append("No user email configured (user.email)")
                recommendations.append("Set user email: git config user.email 'your.email@example.com'")
        except Exception as e:
            warnings.append(f"Could not read user configuration: {e}")
        
        # Check if repository has commits
        try:
            latest_commit = repo.head.commit
            
            # Check if latest commit is signed
            try:
                verify_result = subprocess.run(
                    ["git", "log", "--show-signature", "-1", "--pretty=format:%G?"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True
                )
                
                if verify_result.returncode == 0:
                    signature_status = verify_result.stdout.strip()
                    if signature_status not in ["G", "U"]:  # G=good, U=good but untrusted
                        warnings.append("Latest commit is not properly signed")
                        recommendations.append("Ensure all commits are GPG signed")
                else:
                    warnings.append("Could not verify commit signatures")
            except Exception:
                warnings.append("Could not check commit signatures")
        except Exception:
            # No commits yet, this is fine
            pass
        
        # Determine overall status
        if not warnings:
            status = "secure"
        elif len(warnings) <= 2:
            status = "warning" 
        else:
            status = "insecure"
        
        return {
            "status": status,
            "warnings": warnings,
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "status": "error",
            "warnings": [f"Security validation failed: {e}"],
            "recommendations": ["Check repository access and git configuration"]
        }


def enforce_secure_git_config(repo: git.Repo, strict_mode: bool = True) -> str:
    """Enforce secure Git configuration (GPG signing, proper user config)"""
    
    try:
        config_writer = repo.config_writer()
        changes_made = []
        
        # Get current configuration
        try:
            user_name = repo.config_reader().get_value("user", "name", fallback=None)
            user_email = repo.config_reader().get_value("user", "email", fallback=None)
            signing_key = repo.config_reader().get_value("user", "signingkey", fallback=None)
            gpg_sign = repo.config_reader().get_value("commit", "gpgsign", fallback="false")
        except Exception as e:
            return f"❌ Could not read git configuration: {e}"
        
        # Enforce user configuration
        if not user_name:
            # Try to get from environment or system git config
            env_name = os.getenv("GIT_AUTHOR_NAME") or os.getenv("GIT_COMMITTER_NAME")
            if env_name:
                config_writer.set_value("user", "name", env_name)
                changes_made.append(f"Set user.name to '{env_name}' from environment")
            elif strict_mode:
                return "❌ No user name configured. Set GIT_AUTHOR_NAME env var or git config user.name"
        
        if not user_email:
            # Try to get from environment or system git config
            env_email = os.getenv("GIT_AUTHOR_EMAIL") or os.getenv("GIT_COMMITTER_EMAIL")
            if env_email:
                config_writer.set_value("user", "email", env_email)
                changes_made.append(f"Set user.email to '{env_email}' from environment")
            elif strict_mode:
                return "❌ No user email configured. Set GIT_AUTHOR_EMAIL env var or git config user.email"
        
        # Enforce GPG signing
        if gpg_sign.lower() != "true":
            config_writer.set_value("commit", "gpgsign", "true")
            changes_made.append("Enabled GPG signing for commits (commit.gpgsign=true)")
        
        # Detect and set GPG signing key
        if not signing_key:
            # Try environment variable first
            env_key = os.getenv("GPG_SIGNING_KEY")
            if env_key:
                config_writer.set_value("user", "signingkey", env_key)
                changes_made.append(f"Set GPG signing key to '{env_key}' from environment")
            else:
                # Try to auto-detect GPG keys
                try:
                    gpg_result = subprocess.run(
                        ["gpg", "--list-secret-keys", "--keyid-format", "LONG"],
                        capture_output=True,
                        text=True
                    )
                    
                    if gpg_result.returncode == 0 and "sec" in gpg_result.stdout:
                        # Extract first available key ID
                        lines = gpg_result.stdout.split('\n')
                        for line in lines:
                            if line.strip().startswith("sec"):
                                # Extract key ID from line like "sec   4096R/ABCD1234 2023-01-01"
                                parts = line.split()
                                if len(parts) >= 2 and "/" in parts[1]:
                                    key_id = parts[1].split("/")[1].split()[0]
                                    config_writer.set_value("user", "signingkey", key_id)
                                    changes_made.append(f"Auto-detected and set GPG signing key: {key_id}")
                                    break
                        else:
                            if strict_mode:
                                return "❌ No GPG keys found. Generate a GPG key or set GPG_SIGNING_KEY env var"
                    else:
                        if strict_mode:
                            return "❌ No GPG keys available. Install GPG and generate a key"
                except Exception as e:
                    if strict_mode:
                        return f"❌ Could not detect GPG keys: {e}. Set GPG_SIGNING_KEY env var"
        
        # Write configuration changes
        try:
            config_writer.write()
            config_writer.release()
        except Exception as e:
            return f"❌ Could not write git configuration: {e}"
        
        # Return success message
        if changes_made:
            result = "✅ Git security configuration enforced:\n"
            for change in changes_made:
                result += f"  • {change}\n"
            result += "🔒 Repository is now configured for secure commits"
            return result
        else:
            return "✅ Git security configuration already optimal"
            
    except Exception as e:
        return f"❌ Security enforcement failed: {e}"