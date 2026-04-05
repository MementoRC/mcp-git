import sys

import click

__all__ = ["main"]


# Lazy imports to prevent GitPython cascade during test collection
def __getattr__(name):
    if name == "Session":
        from .session import Session

        return Session
    elif name == "SessionManager":
        from .session import SessionManager

        return SessionManager
    raise AttributeError(f"module {__name__} has no attribute {name}")


@click.command()
def main() -> None:
    """MCP Git Server - legacy stdio entry point (removed)."""
    print(
        "ERROR: mcp-server-git stdio entry point is no longer supported.\n"
        "Use 'mcp-git-http' for HTTP transport or 'mcp-git-lean' for lean stdio.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
