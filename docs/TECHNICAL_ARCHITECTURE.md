# MCP Server Protocol Compliance & Stability Documentation

## Architecture Overview

The MCP Git Server implements a layered architecture for handling MCP protocol messages:

1. **Message Validation Layer**: Validates incoming messages against Pydantic models
2. **Message Routing Layer**: Routes messages to appropriate handlers based on type
3. **Operation Execution Layer**: Executes Git operations based on messages
4. **Error Handling Layer**: Provides recovery mechanisms for errors
5. **Session Management Layer**: Maintains session state and health

### Architecture Diagram

```
MCP Client → Protocol Validation → Message Routing → Git Operations → Response
              ↓ (on error)           ↓ (on error)      ↓ (on error)
           Error Recovery ← Error Logging ← Session Management
```

## Protocol Compliance

### Notification Types

The server supports the following MCP notification types:

- `notifications/cancelled`: Cancellation of an operation
- `notifications/progress`: Progress updates for long-running operations
- `notifications/log`: Log messages from operations
- `notifications/status`: Status updates for operations

### Message Validation

All messages are validated using Pydantic models with the following features:

- Strict validation for required fields
- Optional fields with sensible defaults
- Flexible validation for unknown fields
- Graceful handling of validation errors

### Cancellation Handling

Cancellation notifications are handled as follows:

1. Validate the cancellation notification
2. Identify the operation being cancelled
3. Cancel any active tasks for the operation
4. Remove the operation from active operations list
5. Send acknowledgement to the client

## Error Handling

### Error Classification

Errors are classified into the following categories:

- **Critical**: Require session termination
- **High**: Operation must abort, but session can continue
- **Medium**: Operation might recover
- **Low**: Can safely ignore

### Recovery Strategies

The following recovery strategies are implemented:

- **Retry**: Automatically retry transient errors
- **Circuit Breaker**: Prevent cascading failures
- **Fallback**: Use default values when validation fails
- **Graceful Degradation**: Continue with reduced functionality

## Session Management

### Session Lifecycle

Sessions go through the following states:

1. **Initializing**: Session is being created
2. **Active**: Session is actively processing messages
3. **Paused**: Session is temporarily paused
4. **Error**: Session encountered an error
5. **Closing**: Session is being closed
6. **Closed**: Session is closed

### Heartbeat Mechanism

The heartbeat mechanism works as follows:

1. Server sends heartbeat requests at configurable intervals
2. Client responds with heartbeat responses
3. Server tracks missed heartbeats
4. After threshold of missed heartbeats, session is considered disconnected

## Performance Considerations

### Message Processing Optimization

- Validation caching for similar messages
- Optimized JSON parsing
- Asynchronous processing for long-running operations
- Memory usage optimization

### Benchmarks

The server meets the following performance targets:

- **Message Processing**: <100ms per message
- **Memory Usage**: <50MB base footprint
- **CPU Usage**: <5% during idle periods
- **Throughput**: >100 messages per second

## API Reference

### Server Configuration

```python
from mcp_server_git.server import MCPGitServer
from mcp_server_git.session import SessionManager, HeartbeatManager

# Basic server setup
server = MCPGitServer()
```

### Performance Optimization

```python
from mcp_server_git.optimizations import (
    enable_validation_cache,
    disable_validation_cache,
    clear_validation_cache,
    get_validation_cache_stats,
    PerformanceTimer
)

# Enable validation caching for better performance
enable_validation_cache()

# Use performance timer for benchmarking
with PerformanceTimer("operation_name"):
    # Your operation here
    pass

# Get cache statistics
stats = get_validation_cache_stats()
print(f"Cache hits: {stats['hits']}, misses: {stats['misses']}")
```

## Troubleshooting

### Common Errors

- **Validation Errors**: Check message format against MCP specification
- **Circuit Open**: Too many failures, wait for recovery timeout
- **Session Closed**: Session was closed due to inactivity or errors
- **Operation Cancelled**: Operation was cancelled by client

### Logging

Logs are structured in JSON format with the following fields:

- `timestamp`: ISO 8601 timestamp
- `level`: Log level (INFO, WARNING, ERROR, etc.)
- `message`: Log message
- `session_id`: Session identifier
- `request_id`: Request identifier
- `duration_ms`: Operation duration in milliseconds
- `exception`: Exception details if applicable

### Metrics

The following metrics are available:

- **Sessions**: Active, total created, errors
- **Messages**: Processed, errors, by type
- **Operations**: Active, completed, cancelled, failed
- **Performance**: Message processing time, average processing time

This documentation reflects the current stable implementation of the MCP Git Server's enhanced protocol compliance and stability features.
EOD < /dev/null
