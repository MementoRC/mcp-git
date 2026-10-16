"""JSON-RPC 2.0 response builders for the MCP HTTP transport."""

from typing import Any

from fastapi.responses import JSONResponse


def rpc_result(req_id: Any, result: dict[str, Any]) -> JSONResponse:
    """Build a JSON-RPC success response."""
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


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
