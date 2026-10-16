"""Static MCP protocol constants and tool catalog advertised over HTTP."""

from typing import Any

PROTOCOL_VERSION = "2024-11-05"

TOOLS_LIST: list[dict[str, Any]] = [
    {
        "name": "discover_tools",
        "description": "Discover available Git, GitHub, and Azure DevOps tools. USE WHEN: finding tools by pattern",
        "inputSchema": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "default": ""}},
        },
    },
    {
        "name": "get_tool_spec",
        "description": "Get full specification for specific tool including schema and examples.",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
            "required": ["tool_name"],
        },
    },
    {
        "name": "execute_tool",
        "description": "Execute Git, GitHub, or Azure DevOps operation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "parameters": {"type": "object"},
            },
            "required": ["tool_name", "parameters"],
        },
    },
    {
        "name": "server_info",
        "description": "Returns server metadata, version, and support URLs. USE WHEN: identifying this server, finding where to file bugs or feature requests.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
