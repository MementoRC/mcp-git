# System Tests

End-to-end tests for full system functionality.

## Coverage Target: 80%+

System tests should cover:
- Complete user workflows
- MCP protocol compliance
- Server lifecycle management
- Error handling and recovery

## Structure

- `mcp_protocol/` - MCP protocol compliance tests
- `server_lifecycle/` - Server startup, shutdown, and lifecycle tests

## Guidelines

- Test complete workflows
- Use real MCP protocol messages
- May use external resources (test repositories)
- Longer execution time acceptable (< 10 seconds per test)
- Mark slow tests with `@pytest.mark.slow`