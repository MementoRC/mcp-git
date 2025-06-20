from typing import Literal, Optional, Union

from pydantic import BaseModel


class CancelledParams(BaseModel):
    """Parameters for a cancelled notification."""

    requestId: Union[str, int]
    reason: Optional[str] = None


class CancelledNotification(BaseModel):
    """
    A notification indicating that a previously sent request has been cancelled.
    https://microsoft.github.io/language-server-protocol/specifications/mcp/0.2.0-pre.1/#cancelledNotification
    """

    jsonrpc: Literal["2.0"] = "2.0"
    method: Literal["notifications/cancelled"] = "notifications/cancelled"
    params: CancelledParams
