# MCP Git Server API Reference

## Table of Contents

1. [Server Configuration](#server-configuration)
2. [Session Management](#session-management)
3. [Error Handling](#error-handling)
4. [Performance Optimization](#performance-optimization)
5. [Message Validation](#message-validation)
6. [Metrics and Monitoring](#metrics-and-monitoring)
7. [Circuit Breaker Pattern](#circuit-breaker-pattern)
8. [Heartbeat System](#heartbeat-system)

## Server Configuration

### MCPGitServer

The main server class for handling MCP protocol messages.

```python
from mcp_server_git.server import MCPGitServer

# Create server instance
server = MCPGitServer()

# Start the server
await server.start()

# Shutdown the server gracefully
await server.shutdown()
```

### Configuration Options

The server can be configured through environment variables or direct initialization:

```python
import os
from mcp_server_git.server import MCPGitServer
from mcp_server_git.session import SessionManager, HeartbeatManager

# Environment variables
os.environ['MCP_GIT_LOG_LEVEL'] = 'INFO'
os.environ['MCP_GIT_SESSION_TIMEOUT'] = '3600'  # 1 hour
os.environ['MCP_GIT_HEARTBEAT_INTERVAL'] = '30'  # 30 seconds

# Direct configuration
server = MCPGitServer()
```

## Session Management

### SessionManager

Manages client sessions and their lifecycle.

```python
from mcp_server_git.session import SessionManager, Session, SessionState

# Create session manager
session_manager = SessionManager()

# Create a new session
session = await session_manager.create_session()
print(f"Created session: {session.session_id}")

# Get session by ID
session = await session_manager.get_session(session_id)

# Update session activity
session.update_activity()
session.record_message()
session.record_error()

# Manage active operations
session.add_operation("operation_123")
session.remove_operation("operation_123")

# Check session status
print(f"Session active: {session.is_active}")
print(f"Idle time: {session.idle_time}s")
print(f"Duration: {session.session_duration}s")

# Close session
await session_manager.close_session(session_id)

# Cleanup idle sessions
closed_count = await session_manager.cleanup_idle_sessions(max_idle_time=3600)
```

### Session States

```python
from mcp_server_git.session import SessionState

# Available session states
SessionState.INITIALIZING  # Session is being created
SessionState.ACTIVE        # Session is actively processing messages
SessionState.PAUSED        # Session is temporarily paused
SessionState.ERROR         # Session encountered an error
SessionState.CLOSING       # Session is being closed
SessionState.CLOSED        # Session is closed
```

## Error Handling

### Error Classification

```python
from mcp_server_git.error_handling import ErrorSeverity, ErrorContext

# Error severity levels
ErrorSeverity.CRITICAL  # Session must terminate
ErrorSeverity.HIGH      # Operation must abort, session can continue
ErrorSeverity.MEDIUM    # Operation might recover
ErrorSeverity.LOW       # Can safely ignore

# Create error context
context = ErrorContext(
    error=exception,
    severity=ErrorSeverity.MEDIUM,
    operation="git_commit",
    session_id="session_123",
    recoverable=True,
    metadata={"commit_hash": "abc123"}
)

# Handle error
success = await handle_error(context)
```

### Recovery Decorators

```python
from mcp_server_git.error_handling import recoverable

# Automatic retry with backoff
@recoverable(max_retries=3, backoff_factor=1.0)
async def git_operation():
    # Operation that might fail
    return await perform_git_command()

# Usage
try:
    result = await git_operation()
except Exception as e:
    # All retries exhausted
    logger.error(f"Operation failed after retries: {e}")
```

## Performance Optimization

### Validation Caching

```python
from mcp_server_git.optimizations import (
    enable_validation_cache,
    disable_validation_cache,
    clear_validation_cache,
    get_validation_cache_stats
)

# Enable caching for better performance
enable_validation_cache()

# Check cache statistics
stats = get_validation_cache_stats()
print(f"Cache hits: {stats['hits']}")
print(f"Cache misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.2%}")

# Clear cache if needed
clear_validation_cache()

# Disable caching
disable_validation_cache()
```

### Performance Monitoring

```python
from mcp_server_git.optimizations import PerformanceTimer, CPUProfiler

# Time operations
with PerformanceTimer("git_commit") as timer:
    await perform_git_commit()
    print(f"Operation took: {timer.elapsed_ms}ms")

# CPU profiling
with CPUProfiler("validation_profile", enabled=True) as profiler:
    result = validate_large_message(data)
    profiler.save_stats("validation_profile.stats")
```

### Memory Monitoring

```python
from mcp_server_git.optimizations import MemoryMonitor

monitor = MemoryMonitor()

# Take memory snapshot
initial_memory = monitor.take_sample("start")

# Perform operations
await process_messages()

# Check memory usage
final_memory = monitor.take_sample("end")
growth = monitor.get_memory_growth()
slope = monitor.get_memory_slope()

print(f"Memory growth: {growth:.2f} MB")
print(f"Growth slope: {slope:.6f} MB/sample")
```

## Message Validation

### Validation Results

```python
from mcp_server_git.models.validation import validate_message, ValidationResult
from mcp_server_git.models.notifications import CancelledNotification

# Validate a message
data = {
    "type": "notifications/cancelled",
    "id": "msg_123",
    "request_id": "req_456",
    "reason": "User cancelled operation"
}

result = validate_message(data, CancelledNotification)

if result.is_valid:
    print(f"Message type: {result.message_type}")
    print(f"Model: {result.model}")
else:
    print(f"Validation error: {result.error}")
    print(f"Raw data: {result.raw_data}")
```

### Enhanced Validation

```python
from mcp_server_git.models.enhanced_validation import (
    enhanced_validate_message,
    get_validation_stats,
    reset_validation_stats
)

# Enhanced validation with fallback
result = enhanced_validate_message(data, strict_mode=False)

# Get validation statistics
stats = get_validation_stats()
print(f"Total validations: {stats['total']}")
print(f"Successful: {stats['successful']}")
print(f"Failed: {stats['failed']}")
print(f"Cache hits: {stats['cache_hits']}")

# Reset statistics
reset_validation_stats()
```

## Metrics and Monitoring

### Server Metrics

```python
from mcp_server_git.metrics import ServerMetrics

# Create metrics instance
metrics = ServerMetrics()

# Record metrics
metrics.record_message_processed("notifications/cancelled")
metrics.record_operation_started("git_commit")
metrics.record_operation_completed("git_commit", duration_ms=150)
metrics.record_error("validation_error", "Invalid message format")

# Get current metrics
current_metrics = metrics.get_current_metrics()
print(f"Active sessions: {current_metrics['sessions']['active']}")
print(f"Messages processed: {current_metrics['messages']['total']}")
print(f"Average response time: {current_metrics['performance']['avg_response_time_ms']}")

# Export metrics for monitoring
prometheus_metrics = metrics.export_prometheus()
```

### Performance Metrics

```python
# Track operation performance
with metrics.track_operation("git_push"):
    await perform_git_push()

# Record custom metrics
metrics.record_custom_metric("cache_size", 1024)
metrics.increment_counter("api_calls")
metrics.record_histogram("request_size_bytes", len(request_data))
```

## Circuit Breaker Pattern

### CircuitBreaker

```python
from mcp_server_git.error_handling import CircuitBreaker, CircuitState, with_circuit_breaker

# Create circuit breaker
circuit = CircuitBreaker(
    name="git_operations",
    failure_threshold=5,      # Trip after 5 failures
    recovery_timeout=30.0,    # Wait 30s before testing recovery
    half_open_max_calls=1     # Allow 1 test call in half-open state
)

# Use as decorator
@with_circuit_breaker(circuit)
async def git_operation():
    return await perform_git_command()

# Manual circuit management
if circuit.allow_request():
    try:
        result = await git_operation()
        circuit.record_success()
    except Exception as e:
        circuit.record_failure()
        raise
else:
    raise CircuitOpenError("Git operations circuit is open")

# Check circuit state
print(f"Circuit state: {circuit.state}")
print(f"Failure count: {circuit.failure_count}")

# Reset circuit manually
circuit.reset()
```

## Heartbeat System

### HeartbeatManager

```python
from mcp_server_git.session import HeartbeatManager

# Create heartbeat manager
heartbeat_manager = HeartbeatManager(
    session_manager=session_manager,
    heartbeat_interval=30.0,        # Send heartbeat every 30s
    missed_heartbeat_threshold=3    # Close session after 3 missed beats
)

# Start heartbeat monitoring
await heartbeat_manager.start()

# Record heartbeat from client
await heartbeat_manager.record_heartbeat(session_id)

# Stop heartbeat monitoring
await heartbeat_manager.stop()
```

### Heartbeat Messages

```python
# Client heartbeat message format
heartbeat_message = {
    "type": "heartbeat",
    "id": "heartbeat_123",
    "timestamp": "2024-01-01T12:00:00Z",
    "session_id": "session_456"
}

# Server heartbeat response
heartbeat_response = {
    "type": "heartbeat_ack",
    "id": "heartbeat_ack_123",
    "timestamp": "2024-01-01T12:00:01Z",
    "original_id": "heartbeat_123"
}
```

## Integration Examples

### Complete Server Setup

```python
import asyncio
from mcp_server_git.server import MCPGitServer
from mcp_server_git.session import SessionManager, HeartbeatManager
from mcp_server_git.optimizations import enable_validation_cache
from mcp_server_git.error_handling import CircuitBreaker

async def main():
    # Enable performance optimizations
    enable_validation_cache()
    
    # Create server
    server = MCPGitServer()
    
    # Setup session management
    session_manager = SessionManager()
    heartbeat_manager = HeartbeatManager(
        session_manager=session_manager,
        heartbeat_interval=30.0,
        missed_heartbeat_threshold=3
    )
    
    # Start components
    await server.start()
    await heartbeat_manager.start()
    
    try:
        # Server is now running and ready to handle clients
        print("MCP Git Server is running...")
        
        # Keep server running
        await asyncio.Event().wait()
        
    finally:
        # Graceful shutdown
        await heartbeat_manager.stop()
        await server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

### Custom Message Handler

```python
from mcp_server_git.server import MCPGitServer
from mcp_server_git.models.validation import validate_message

class CustomMCPServer(MCPGitServer):
    async def handle_custom_message(self, message, session):
        """Handle custom message type."""
        # Validate message
        result = validate_message(message, CustomMessageModel)
        
        if not result.is_valid:
            await self.send_error_response(
                session.session_id,
                f"Validation failed: {result.error}"
            )
            return
        
        # Process message
        try:
            response = await self.process_custom_operation(result.model)
            await self.send_response(session.session_id, response)
        except Exception as e:
            await self.handle_operation_error(e, session)
```

This API reference provides comprehensive documentation for all the major components and patterns implemented in the MCP Git Server's enhanced protocol compliance and stability system.