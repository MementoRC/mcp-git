import logging
import json
import sys


class SafeStreamHandler(logging.StreamHandler):
    """
    Stream handler that gracefully handles closed streams during shutdown.
    """
    
    def emit(self, record):
        try:
            super().emit(record)
        except (ValueError, OSError) as e:
            # Handle closed file errors during shutdown
            if "closed file" in str(e).lower() or "bad file descriptor" in str(e).lower():
                # Silently ignore - this is expected during shutdown
                pass
            else:
                # Re-raise other stream errors
                raise


class StructuredLogFormatter(logging.Formatter):
    """
    Formats log records as structured JSON with contextual fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add contextual fields if present
        for field in ("session_id", "request_id", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                log_record[field] = value
        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_record["exception"] = record.exc_text
        return json.dumps(log_record, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """
    Centralized logging configuration for MCP Git Server.
    Sets up root logger with structured JSON output and safe stream handling.
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    handler = SafeStreamHandler(sys.stderr)
    formatter = StructuredLogFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
    # Silence overly verbose loggers if needed
    logging.getLogger("asyncio").setLevel("WARNING")
    logging.getLogger("aiohttp").setLevel("WARNING")
    logging.getLogger("git").setLevel("WARNING")
    logging.getLogger("mcp").setLevel("WARNING")
