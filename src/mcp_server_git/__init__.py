import click
from pathlib import Path
import logging
import sys
import os
from datetime import datetime
from .server import main as serve


@click.command()
@click.option("--repository", "-r", type=Path, help="Git repository path")
@click.option("-v", "--verbose", count=True)
@click.option(
    "--enable-file-logging",
    is_flag=True,
    help="Enable logging to file in logs/ directory",
)
@click.option(
    "--test-mode",
    is_flag=True,
    help="Run in test mode for CI (stays alive without immediate stdio)",
)
def main(
    repository: Path | None, verbose: bool, enable_file_logging: bool, test_mode: bool
) -> None:
    """MCP Git Server - Git functionality for MCP"""
    import asyncio

    # Load .env file from repository if it exists
    if repository:
        from dotenv import load_dotenv

        env_file = repository / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logging.info(f"Loaded environment variables from {env_file}")

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    # Set up logging
    logger = logging.getLogger()
    logger.setLevel(logging_level)

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging_level)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File logging setup if enabled
    if enable_file_logging:
        # Create logs directory
        repo_path = repository if repository else Path.cwd()
        logs_dir = repo_path / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Generate session ID from current time or environment
        session_id = os.environ.get(
            "MCP_SESSION_ID", datetime.now().strftime("%Y%m%d_%H%M%S")
        )

        # Create file handler
        log_file = logs_dir / f"mcp_git_debug-{session_id}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always debug level for file
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Log the setup
        print(f"📝 Debug logging enabled: {log_file}", file=sys.stderr)
        logger.info(f"📝 File logging enabled: {log_file}")

    asyncio.run(serve(repository, test_mode=test_mode))


if __name__ == "__main__":
    main()
