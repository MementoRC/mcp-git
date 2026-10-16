"""JSON-RPC 2.0 response builders for the MCP HTTP transport."""

from typing import Any

from fastapi.responses import JSONResponse


def rpc_result(req_id: Any, result: dict[str, Any]) -> JSONResponse:
    """Build a JSON-RPC success response."""
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


def json_type_name(value: Any) -> str:
    """Return the JSON type name of a decoded value (null, string, number, ...)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def invalid_params(req_id: Any, what: str, value: Any) -> JSONResponse:
    """Build the -32602 response for a non-object ``params``/``arguments``."""
    return rpc_error(
        req_id,
        -32602,
        f"Invalid params: {what} must be an object, got {json_type_name(value)}",
    )


def rpc_error(
    req_id: Any,
    code: int,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    """Build a JSON-RPC error response (optionally with ``data`` and HTTP status)."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "id": req_id, "error": error},
    )
