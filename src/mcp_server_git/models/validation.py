import logging
from typing import Any, Dict, Type, TypeVar, Optional

from pydantic import BaseModel, ValidationError

from .notifications import CancelledNotification, parse_client_notification

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def validate_notification(data: Dict[str, Any], model: Type[T]) -> T:
    """
    Validates a dictionary against a Pydantic model.

    Args:
        data: The dictionary to validate.
        model: The Pydantic model class to validate against.

    Returns:
        An instance of the Pydantic model if validation is successful.

    Raises:
        ValueError: If validation fails.
    """
    try:
        return model.model_validate(data)
    except ValidationError as e:
        logger.error(f"Validation failed for model {model.__name__}: {e}")
        raise ValueError(f"Invalid notification format for {model.__name__}") from e


def validate_cancelled_notification(data: Dict[str, Any]) -> CancelledNotification:
    """
    Validates a dictionary to ensure it's a valid CancelledNotification.
    """
    return validate_notification(data, CancelledNotification)


class ValidationResult:
    """Container for validation results with error handling."""

    def __init__(
        self,
        model: Optional[BaseModel] = None,
        error: Optional[Exception] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        self.model = model
        self.error = error
        self.raw_data = raw_data or {}
        self.is_valid = model is not None and error is None

    @property
    def message_type(self) -> str:
        """Extract message type even if validation failed."""
        if self.model and hasattr(self.model, "method"):
            return self.model.method
        return self.raw_data.get("method", "unknown")


def safe_parse_notification(data: Dict[str, Any]) -> ValidationResult:
    """Parse a notification with fallback handling."""
    try:
        model = parse_client_notification(data)
        return ValidationResult(model=model, raw_data=data)
    except Exception as e:
        logger.error(f"Failed to parse notification: {e}")
        return ValidationResult(error=e, raw_data=data)


def handle_unknown_notification(data: Dict[str, Any]) -> ValidationResult:
    """Handle unknown notification types with graceful fallback."""
    method = data.get("method", "unknown")
    logger.warning(f"Received unknown notification type: {method}")

    # Try to create a minimal cancelled notification as fallback
    try:
        fallback_data = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {
                "requestId": data.get("params", {}).get("requestId", "unknown"),
                "reason": f"Unknown notification type: {method}",
            },
        }
        model = CancelledNotification.model_validate(fallback_data)
        logger.info(f"Created fallback cancelled notification for {method}")
        return ValidationResult(model=model, raw_data=data)
    except Exception as e:
        logger.error(f"Failed to create fallback notification: {e}")
        return ValidationResult(error=e, raw_data=data)
