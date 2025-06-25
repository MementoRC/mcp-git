import logging
from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .notifications import CancelledNotification

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
